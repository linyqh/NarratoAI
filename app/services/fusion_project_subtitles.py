"""Source-bound subtitle commands for Fusion Projects."""

from __future__ import annotations

from app.config import config
from app.services.fusion_projects import FusionProjectStore


class FusionProjectSubtitleWorkflow:
    """Keep ASR and subtitle derivatives behind one project-command interface."""

    def __init__(self, store: FusionProjectStore) -> None:
        self._store = store

    def transcribe(self, project_id: str, source_id: str, backend: str) -> dict:
        from app.services import fun_asr_subtitle

        project, source = self._source(project_id, source_id)
        output = self._store.source_subtitle_output_path(project_id, source_id=source_id, label=f"asr-{backend}")
        if backend == "local":
            result = fun_asr_subtitle.create_with_local_fun_asr(
                source["path"], output, api_url=config.fun_asr.get("api_url", ""),
                hotword=config.fun_asr.get("hotword", ""), enable_spk=bool(config.fun_asr.get("enable_spk", False)),
            )
        elif backend == "firered":
            result = fun_asr_subtitle.create_with_local_firered_asr(
                source["path"], output, api_url=config.fun_asr.get("firered_api_url", ""),
            )
        elif backend == "bailian":
            result = fun_asr_subtitle.create_with_fun_asr(source["path"], output, api_key=config.fun_asr.get("api_key", ""))
        else:
            raise ValueError("unsupported Fusion ASR backend")
        return self._store.set_source_subtitle(project_id, source_id=source_id, subtitle_path=str(result or output), origin=f"asr:{backend}")

    def translate(self, project_id: str, source_id: str) -> dict:
        from app.services import subtitle_translator

        project, source = self._source(project_id, source_id, require_subtitle=True)
        provider = config.app.get("text_llm_provider", "openai").lower()
        output = self._store.source_subtitle_output_path(project_id, source_id=source_id, label="translated")
        result = subtitle_translator.translate_subtitle_file(
            source["subtitle_path"], output_file=output,
            target_language=str((project.get("project_settings") or {}).get("output_language") or "中文"),
            provider=provider, api_key=config.app.get(f"text_{provider}_api_key", ""),
            base_url=config.app.get(f"text_{provider}_base_url", ""),
        )
        return self._store.set_source_subtitle(project_id, source_id=source_id, subtitle_path=result, origin="translated")

    def calibrate(self, project_id: str, source_id: str) -> dict:
        from app.services import subtitle_corrector

        _, source = self._source(project_id, source_id, require_subtitle=True)
        provider = config.app.get("text_llm_provider", "openai").lower()
        output = self._store.source_subtitle_output_path(project_id, source_id=source_id, label="corrected")
        result = subtitle_corrector.correct_subtitle_file(
            source["subtitle_path"], output_file=output,
            provider=provider, api_key=config.app.get(f"text_{provider}_api_key", ""),
            base_url=config.app.get(f"text_{provider}_base_url", ""),
        )
        return self._store.set_source_subtitle(project_id, source_id=source_id, subtitle_path=result, origin="corrected")

    def _source(self, project_id: str, source_id: str, *, require_subtitle: bool = False) -> tuple[dict, dict]:
        project = self._store.read(project_id)
        source = next((item for item in project.get("source_video_sequence") or [] if item.get("source_id") == source_id), None)
        if source is None:
            raise ValueError("Fusion source video not found")
        if not source.get("available"):
            raise ValueError("Fusion source video is offline")
        if require_subtitle and not source.get("subtitle_path"):
            raise ValueError("Fusion source subtitle is missing")
        return project, source
