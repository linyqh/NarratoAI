"""Regression coverage for Streamlit widget state initialization."""

import ast
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).parents[1]


def _attribute_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _attribute_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


def _session_state_key(target: ast.expr) -> str | None:
    if not isinstance(target, ast.Subscript):
        return None
    if _attribute_name(target.value) != "st.session_state":
        return None
    if isinstance(target.slice, ast.Constant) and isinstance(target.slice.value, str):
        return target.slice.value
    return None


@pytest.mark.parametrize(
    ("source_path", "function_name", "widget_key"),
    [
        (
            "webui/components/audio_settings.py",
            "render_bgm_settings",
            "bgm_source_selection",
        ),
        (
            "webui/components/subtitle_settings.py",
            "_render_subtitle_preview_image",
            "subtitle_preview_orientation",
        ),
    ],
)
def test_state_initialized_widgets_do_not_also_declare_defaults(
    source_path: str,
    function_name: str,
    widget_key: str,
):
    """Streamlit warns when a keyed widget has both a default and state value."""
    module = ast.parse((PROJECT_ROOT / source_path).read_text(encoding="utf-8"))
    function = next(
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == function_name
    )

    assigned_keys = {
        key
        for node in ast.walk(function)
        if isinstance(node, ast.Assign)
        for target in node.targets
        if (key := _session_state_key(target)) is not None
    }
    assert widget_key in assigned_keys

    widget_calls = []
    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue
        widget_name = _attribute_name(node.func)
        keywords = {keyword.arg: keyword.value for keyword in node.keywords}
        key_node = keywords.get("key")
        if (
            widget_name is not None
            and widget_name.startswith("st.")
            and isinstance(key_node, ast.Constant)
            and key_node.value == widget_key
        ):
            widget_calls.append(keywords)

    assert widget_calls
    assert all("default" not in keywords for keywords in widget_calls)
