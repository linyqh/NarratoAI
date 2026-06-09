"""FFmpeg engine discovery and capability diagnostics."""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from loguru import logger


_FFMPEG_EXE = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
_FFPROBE_EXE = "ffprobe.exe" if os.name == "nt" else "ffprobe"
_SOURCE_PRIORITY = {
    "Configured": 0,
    "NarratoAI packaged runtime": 1,
    "Integrated runtime": 2,
    "System PATH": 3,
    "Homebrew": 4,
    "Python environment": 5,
    "Python executable folder": 6,
    "IMAGEIO_FFMPEG_EXE": 7,
    "imageio-ffmpeg": 8,
    "System": 9,
}


@dataclass(frozen=True)
class FFmpegEngine:
    """A discovered FFmpeg executable."""

    path: str
    source: str
    ffprobe_path: str
    available: bool
    version_line: str

    @property
    def label(self) -> str:
        status = "OK" if self.available else "Unavailable"
        version = self.version_line.replace("ffmpeg version", "").strip() or "unknown version"
        return f"{self.source} - {version} - {self.path} ({status})"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["label"] = self.label
        return payload


def _run_command(args: list[str], timeout: int = 10) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=timeout,
    )


def _first_line(text: str) -> str:
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def _is_executable(path: str) -> bool:
    if not path:
        return False
    if os.name == "nt":
        return os.path.isfile(path)
    return os.path.isfile(path) and os.access(path, os.X_OK)


def _normalize_path(path: str) -> str:
    return str(Path(path).expanduser().resolve())


def _ffmpeg_version_line(ffmpeg_path: str) -> tuple[bool, str]:
    if not _is_executable(ffmpeg_path):
        return False, ""
    try:
        result = _run_command([ffmpeg_path, "-version"], timeout=8)
    except Exception as exc:
        logger.debug(f"FFmpeg version check failed for {ffmpeg_path}: {exc}")
        return False, ""

    output = result.stdout or result.stderr
    return result.returncode == 0, _first_line(output)


def _paired_ffprobe_path(ffmpeg_path: str) -> str:
    ffmpeg = Path(ffmpeg_path)
    sibling = ffmpeg.with_name(_FFPROBE_EXE)
    if _is_executable(str(sibling)):
        return _normalize_path(str(sibling))

    scoped_path = os.pathsep.join([str(ffmpeg.parent), os.environ.get("PATH", "")])
    discovered = shutil.which(_FFPROBE_EXE, path=scoped_path)
    return _normalize_path(discovered) if discovered else ""


def _candidate_paths(root_dir: str = "", include_system: bool = True) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    root = Path(root_dir).expanduser().resolve() if root_dir else Path.cwd().resolve()
    project_parent = root.parent

    candidates.extend(
        [
            ("Integrated runtime", str(root / "runtime" / "python" / "bin" / _FFMPEG_EXE)),
            ("Integrated runtime", str(root.parent / "runtime" / "python" / "bin" / _FFMPEG_EXE)),
            (
                "NarratoAI packaged runtime",
                str(
                    project_parent
                    / "NarratoAI-Pack"
                    / "dist"
                    / "NarratoAI-macos-arm64"
                    / "runtime"
                    / "python"
                    / "bin"
                    / _FFMPEG_EXE
                ),
            ),
            ("Python environment", str(Path(sys.prefix) / "bin" / _FFMPEG_EXE)),
            ("Python executable folder", str(Path(sys.executable).with_name(_FFMPEG_EXE))),
        ]
    )

    env_ffmpeg = os.environ.get("IMAGEIO_FFMPEG_EXE", "")
    if env_ffmpeg:
        candidates.append(("IMAGEIO_FFMPEG_EXE", env_ffmpeg))

    if include_system:
        path_ffmpeg = shutil.which(_FFMPEG_EXE)
        if path_ffmpeg:
            candidates.append(("System PATH", path_ffmpeg))

        for source, path in (
            ("Homebrew", f"/opt/homebrew/bin/{_FFMPEG_EXE}"),
            ("Homebrew", f"/usr/local/bin/{_FFMPEG_EXE}"),
            ("System", f"/usr/bin/{_FFMPEG_EXE}"),
        ):
            candidates.append((source, path))

    try:
        import imageio_ffmpeg

        candidates.append(("imageio-ffmpeg", imageio_ffmpeg.get_ffmpeg_exe()))
    except Exception as exc:
        logger.debug(f"imageio-ffmpeg discovery skipped: {exc}")

    return candidates


def discover_ffmpeg_engines(
    configured_path: str = "",
    root_dir: str = "",
    include_system: bool = True,
) -> list[dict[str, Any]]:
    """Discover available FFmpeg engines from config, packaged runtime and PATH."""

    candidates: list[tuple[str, str]] = []
    if configured_path:
        candidates.append(("Configured", configured_path))
    candidates.extend(_candidate_paths(root_dir=root_dir, include_system=include_system))

    engines: list[FFmpegEngine] = []
    seen: set[str] = set()
    for source, raw_path in candidates:
        if not raw_path:
            continue
        try:
            path = _normalize_path(raw_path)
        except Exception:
            path = str(Path(raw_path).expanduser())
        key = os.path.normcase(path)
        if key in seen:
            continue
        seen.add(key)

        available, version_line = _ffmpeg_version_line(path)
        if not available and source not in {"Configured", "IMAGEIO_FFMPEG_EXE"}:
            continue
        engines.append(
            FFmpegEngine(
                path=path,
                source=source,
                ffprobe_path=_paired_ffprobe_path(path),
                available=available,
                version_line=version_line,
            )
        )

    engines.sort(
        key=lambda engine: (
            not engine.available,
            _SOURCE_PRIORITY.get(engine.source, 99),
            engine.path,
        )
    )
    return [engine.to_dict() for engine in engines]


def _parse_hwaccels(output: str) -> list[str]:
    values: list[str] = []
    for line in output.splitlines():
        item = line.strip().lower()
        if not item or item.startswith("hardware acceleration"):
            continue
        if re.fullmatch(r"[a-z0-9_]+", item):
            values.append(item)
    return sorted(set(values))


def _parse_ffmpeg_table_names(output: str) -> set[str]:
    names: set[str] = set()
    for line in output.splitlines():
        match = re.match(r"\s*[A-Z.]{2,}\s+([A-Za-z0-9_]+)\b", line)
        if match:
            names.add(match.group(1).lower())
    return names


def _run_optional(args: list[str], timeout: int = 15, max_output_chars: int = 1200) -> tuple[bool, str]:
    try:
        result = _run_command(args, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, "Command timed out"
    except Exception as exc:
        return False, str(exc)

    output = "\n".join(part for part in (result.stderr, result.stdout) if part)
    if max_output_chars > 0:
        output = output[-max_output_chars:]
    return result.returncode == 0, output


def _hardware_candidates() -> list[tuple[str, str, list[str]]]:
    system = platform.system().lower()
    if system == "darwin":
        return [
            ("videotoolbox", "h264_videotoolbox", ["-c:v", "h264_videotoolbox", "-q:v", "65"]),
        ]
    if system == "windows":
        return [
            ("nvenc", "h264_nvenc", ["-c:v", "h264_nvenc", "-preset", "fast"]),
            ("qsv", "h264_qsv", ["-c:v", "h264_qsv", "-preset", "fast"]),
            ("amf", "h264_amf", ["-c:v", "h264_amf"]),
        ]
    return [
        ("nvenc", "h264_nvenc", ["-c:v", "h264_nvenc", "-preset", "fast"]),
        ("qsv", "h264_qsv", ["-vf", "format=nv12", "-c:v", "h264_qsv"]),
        ("vaapi", "h264_vaapi", ["-vf", "format=nv12,hwupload", "-c:v", "h264_vaapi"]),
    ]


def _detect_hardware_encoding(ffmpeg_path: str, encoders: set[str]) -> dict[str, Any]:
    tested: list[dict[str, Any]] = []
    for accel_type, encoder, encoder_args in _hardware_candidates():
        if encoder.lower() not in encoders:
            tested.append(
                {
                    "type": accel_type,
                    "encoder": encoder,
                    "available": False,
                    "message": "Encoder not listed by this FFmpeg build",
                }
            )
            continue

        cmd = [
            ffmpeg_path,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=0.5:size=128x72:rate=15",
            "-frames:v",
            "5",
            *encoder_args,
            "-pix_fmt",
            "yuv420p",
            "-f",
            "null",
            "-",
        ]
        ok, message = _run_optional(cmd, timeout=18)
        tested.append(
            {
                "type": accel_type,
                "encoder": encoder,
                "available": ok,
                "message": "Hardware encode test passed" if ok else message,
            }
        )
        if ok:
            return {
                "available": True,
                "type": accel_type,
                "encoder": encoder,
                "message": "Hardware encode test passed",
                "tested": tested,
            }

    return {
        "available": False,
        "type": None,
        "encoder": None,
        "message": "No hardware encoder passed the runtime test",
        "tested": tested,
    }


def _escape_filter_path(path: str) -> str:
    return path.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def _test_subtitle_burn(ffmpeg_path: str, filters: set[str]) -> dict[str, Any]:
    filter_status = {
        "subtitles": "subtitles" in filters,
        "ass": "ass" in filters,
        "drawtext": "drawtext" in filters,
        "overlay": "overlay" in filters,
    }

    if filter_status["subtitles"]:
        with tempfile.TemporaryDirectory() as tmp_dir:
            srt_path = Path(tmp_dir) / "subtitle_test.srt"
            srt_path.write_text(
                "1\n00:00:00,000 --> 00:00:00,800\nNarratoAI FFmpeg subtitle test\n",
                encoding="utf-8",
            )
            ok, message = _run_optional(
                [
                    ffmpeg_path,
                    "-y",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=black:size=320x180:duration=1",
                    "-vf",
                    f"subtitles={_escape_filter_path(str(srt_path))}",
                    "-frames:v",
                    "1",
                    "-f",
                    "null",
                    "-",
                ],
                timeout=18,
            )
            if ok:
                return {
                    "available": True,
                    "method": "subtitles",
                    "message": "SRT subtitle burn-in test passed",
                    "filters": filter_status,
                }
            subtitles_error = message
    else:
        subtitles_error = "subtitles filter is not listed by this FFmpeg build"

    if filter_status["drawtext"]:
        ok, message = _run_optional(
            [
                ffmpeg_path,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=black:size=320x180:duration=1",
                "-vf",
                "drawtext=text=NarratoAI:x=10:y=10:fontsize=18:fontcolor=white",
                "-frames:v",
                "1",
                "-f",
                "null",
                "-",
            ],
            timeout=18,
        )
        if ok:
            return {
                "available": True,
                "method": "drawtext",
                "message": "drawtext burn-in fallback test passed",
                "filters": filter_status,
            }
        drawtext_error = message
    else:
        drawtext_error = "drawtext filter is not listed by this FFmpeg build"

    return {
        "available": False,
        "method": None,
        "message": f"{subtitles_error}\n{drawtext_error}".strip(),
        "filters": filter_status,
    }


def validate_ffmpeg_engine(ffmpeg_path: str) -> dict[str, Any]:
    """Run runtime checks for a selected FFmpeg engine."""

    path = _normalize_path(ffmpeg_path)
    report: dict[str, Any] = {
        "path": path,
        "ffmpeg_available": False,
        "version_line": "",
        "ffprobe_path": "",
        "ffprobe_available": False,
        "ffprobe_version_line": "",
        "hwaccels": [],
        "hardware_acceleration": {
            "available": False,
            "type": None,
            "encoder": None,
            "message": "",
            "tested": [],
        },
        "subtitle_burn": {
            "available": False,
            "method": None,
            "message": "",
            "filters": {},
        },
        "software_encoder_available": False,
        "errors": [],
    }

    available, version_line = _ffmpeg_version_line(path)
    report["ffmpeg_available"] = available
    report["version_line"] = version_line
    if not available:
        report["errors"].append("FFmpeg is not executable or failed to run -version")
        return report

    ffprobe_path = _paired_ffprobe_path(path)
    report["ffprobe_path"] = ffprobe_path
    if ffprobe_path:
        probe_available, probe_version = _ffmpeg_version_line(ffprobe_path)
        report["ffprobe_available"] = probe_available
        report["ffprobe_version_line"] = probe_version

    ok, hwaccel_output = _run_optional(
        [path, "-hide_banner", "-hwaccels"],
        timeout=10,
        max_output_chars=0,
    )
    if ok:
        report["hwaccels"] = _parse_hwaccels(hwaccel_output)
    else:
        report["errors"].append(f"Failed to list hardware acceleration methods: {hwaccel_output}")

    ok, encoders_output = _run_optional(
        [path, "-hide_banner", "-encoders"],
        timeout=10,
        max_output_chars=0,
    )
    encoders = _parse_ffmpeg_table_names(encoders_output) if ok else set()
    report["software_encoder_available"] = "libx264" in encoders or "libopenh264" in encoders
    if not ok:
        report["errors"].append(f"Failed to list encoders: {encoders_output}")

    ok, filters_output = _run_optional(
        [path, "-hide_banner", "-filters"],
        timeout=10,
        max_output_chars=0,
    )
    filters = _parse_ffmpeg_table_names(filters_output) if ok else set()
    if not ok:
        report["errors"].append(f"Failed to list filters: {filters_output}")

    report["hardware_acceleration"] = _detect_hardware_encoding(path, encoders)
    report["subtitle_burn"] = _test_subtitle_burn(path, filters)
    return report
