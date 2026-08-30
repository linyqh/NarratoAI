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
        state["fusion_ui_route"] = PROJECT_LIBRARY_ROUTE
        state["fusion_legacy_redirect_notice"] = True
        return PROJECT_LIBRARY_ROUTE
    state["fusion_ui_route"] = LEGACY_MODES_ROUTE
    return LEGACY_MODES_ROUTE


def enter_legacy_modes(state) -> str:
    """Open traditional modes without allowing stale Fusion controls to render."""
    if str(state.get("video_clip_json_path") or "") == "film_vision_fusion":
        state["video_clip_json_path"] = ""
    state["fusion_ui_route"] = LEGACY_MODES_ROUTE
    return LEGACY_MODES_ROUTE
