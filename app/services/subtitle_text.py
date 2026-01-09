#!/usr/bin/env python
# -*- coding: UTF-8 -*-

"""
Subtitle text utilities.

This module provides a shared, cross-platform way to read and normalize subtitle
content. Both Short Drama Editing (混剪) and Short Drama Narration (解说) should
consume subtitle content through this module to avoid platform-specific parsing
issues (e.g. Windows UTF-16 SRT, timestamp separators, etc.).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Iterable, Optional


_SRT_TIME_RE = re.compile(
    r"\b\d{2}:\d{2}:\d{2}(?:[,.]\d{3})?\s*-->\s*\d{2}:\d{2}:\d{2}(?:[,.]\d{3})?\b"
)
_SRT_MS_DOT_RE = re.compile(r"(\b\d{2}:\d{2}:\d{2})\.(\d{3}\b)")


@dataclass(frozen=True)
class DecodedSubtitle:
    text: str
    encoding: str


def has_timecodes(text: str) -> bool:
    """Return True if the subtitle text contains at least one SRT timecode."""
    if not text:
        return False
    return _SRT_TIME_RE.search(text) is not None


def normalize_subtitle_text(text: str) -> str:
    """
    Normalize subtitle text to improve cross-platform reliability.

    - Unifies line endings to LF
    - Removes BOM and NUL bytes
    - Normalizes millisecond separators from '.' to ',' in timecodes
    """
    if text is None:
        return ""

    normalized = str(text)

    # Strip BOM.
    if normalized.startswith("\ufeff"):
        normalized = normalized.lstrip("\ufeff")

    # Remove NUL bytes (common when UTF-16 is mis-decoded elsewhere).
    normalized = normalized.replace("\x00", "")

    # Normalize newlines.
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")

    # Normalize timestamp millisecond separator: 00:00:01.000 -> 00:00:01,000
    normalized = _SRT_MS_DOT_RE.sub(r"\1,\2", normalized)

    return normalized.strip()


def decode_subtitle_bytes(
    data: bytes,
    *,
    encodings: Optional[Iterable[str]] = None,
) -> DecodedSubtitle:
    """
    Decode subtitle bytes using a small set of common encodings.

    Preference is given to decodings that yield detectable SRT timecodes.
    """
    if data is None:
        return DecodedSubtitle(text="", encoding="utf-8")

    candidates = list(encodings) if encodings else [
        "utf-8",
        "utf-8-sig",
        "utf-16",
        "utf-16-le",
        "utf-16-be",
        "gbk",
        "gb2312",
    ]

    decoded_results: list[DecodedSubtitle] = []
    for encoding in candidates:
        try:
            decoded_text = data.decode(encoding)
        except UnicodeDecodeError:
            continue
        decoded_results.append(
            DecodedSubtitle(text=normalize_subtitle_text(decoded_text), encoding=encoding)
        )

        # Fast path: if we already see timecodes, keep the first such decode.
        if has_timecodes(decoded_results[-1].text):
            return decoded_results[-1]

    if decoded_results:
        # Fall back to the first successful decoding.
        return decoded_results[0]

    # Last resort: replace undecodable bytes.
    return DecodedSubtitle(text=normalize_subtitle_text(data.decode("utf-8", errors="replace")), encoding="utf-8")


def read_subtitle_text(file_path: str) -> DecodedSubtitle:
    """Read subtitle file from disk, decode and normalize its text."""
    if not file_path or not str(file_path).strip():
        return DecodedSubtitle(text="", encoding="utf-8")

    normalized_path = os.path.abspath(str(file_path))
    with open(normalized_path, "rb") as f:
        data = f.read()

    return decode_subtitle_bytes(data)

