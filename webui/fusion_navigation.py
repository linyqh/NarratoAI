"""Pure navigation policy for the project-centered Fusion experience."""

PROJECT_LIBRARY_ROUTE = "project_library"
NEW_PROJECT_ROUTE = "new_fusion_project"
PROJECT_WORKSPACE_ROUTE = "fusion_project"
TASK_CENTER_ROUTE = "fusion_task_center"
LEGACY_MODES_ROUTE = "legacy_modes"

VALID_ROUTES = {
    PROJECT_LIBRARY_ROUTE,
    NEW_PROJECT_ROUTE,
    PROJECT_WORKSPACE_ROUTE,
    TASK_CENTER_ROUTE,
    LEGACY_MODES_ROUTE,
}


def selected_route(state) -> str:
    route = str(state.get("fusion_ui_route") or PROJECT_LIBRARY_ROUTE)
    return route if route in VALID_ROUTES else PROJECT_LIBRARY_ROUTE


def navigate(state, route: str, *, project_id: str = "") -> None:
    if route not in VALID_ROUTES:
        raise ValueError("unknown Fusion UI route")
    state["fusion_ui_route"] = route
    if project_id:
        state["fusion_project_id"] = project_id


def route_for_legacy_mode(mode: str, state) -> str:
    if str(mode) == "film_vision_fusion":
        state["fusion_ui_route"] = LEGACY_MODES_ROUTE
        state["fusion_traditional_fusion_mode"] = True
        return LEGACY_MODES_ROUTE
    state["fusion_ui_route"] = LEGACY_MODES_ROUTE
    return LEGACY_MODES_ROUTE


def enter_legacy_modes(state, *, fusion: bool = False) -> str:
    """Open an explicit traditional workflow without changing project state."""
    state["fusion_traditional_fusion_mode"] = bool(fusion)
    if fusion:
        state["video_clip_json_path"] = "film_vision_fusion"
    elif str(state.get("video_clip_json_path") or "") == "film_vision_fusion":
        state["video_clip_json_path"] = ""
    state["fusion_ui_route"] = LEGACY_MODES_ROUTE
    return LEGACY_MODES_ROUTE


def transfer_project_to_traditional(project: dict, state) -> str:
    """Copy a project's non-secret setup into one explicit legacy-session transfer."""
    settings = dict(project.get("project_settings") or {})
    sources = list(project.get("source_video_sequence") or [])
    state["fusion_traditional_transfer"] = {
        "project_name": str(project.get("name") or ""),
        "settings": {
            key: settings.get(key)
            for key in (
                "output_language", "commentary_style", "target_narration_length",
                "subtitle_policy", "original_sound_ratio", "background_music",
                "tts_engine", "voice_profile", "voice_parameters", "video_aspect",
                "output_format", "subtitle_enabled",
            )
            if key in settings
        },
        "source_paths": [str(source.get("path") or "") for source in sources if source.get("path")],
        "subtitle_paths": [str(source.get("subtitle_path") or "") for source in sources if source.get("subtitle_path")],
    }
    state["fusion_traditional_transfer_pending"] = True
    return enter_legacy_modes(state, fusion=True)


def traditional_session_to_project_draft(state) -> dict:
    """Expose the current traditional-session setup as an explicit project draft.

    This is intentionally a copy, not synchronization: credentials and provider
    endpoints stay in local configuration, while source references and creator
    choices can be adopted by a new durable project.
    """
    source_paths = state.get("video_origin_paths") or [state.get("video_origin_path")]
    subtitle_paths = state.get("subtitle_paths") or [state.get("subtitle_path")]
    return {
        "name": str(state.get("video_theme") or "从传统模式导入的项目"),
        "source_paths": [str(path) for path in source_paths if str(path or "").strip()],
        "subtitle_paths": [str(path) for path in subtitle_paths if str(path or "").strip()],
        "settings": {
            "tts_engine": state.get("tts_engine"),
            "voice_profile": state.get("voice_name"),
            "voice_parameters": {
                "rate": state.get("voice_rate"),
                "volume": state.get("voice_volume"),
                "pitch": state.get("voice_pitch"),
            },
        },
    }
