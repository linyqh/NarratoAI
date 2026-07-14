"""Utilities for parsing structured JSON returned by language models."""

from __future__ import annotations

import json
import re
from typing import Any

from loguru import logger


def parse_and_fix_json(json_string: str) -> Any | None:
    """Parse JSON while repairing a small set of common model-output mistakes."""
    if not json_string or not json_string.strip():
        logger.error("JSON字符串为空")
        return None

    json_string = json_string.strip()

    try:
        return json.loads(json_string)
    except json.JSONDecodeError as exc:
        logger.warning(f"直接JSON解析失败: {exc}")

    try:
        return json.loads(json_string.replace("{{", "{").replace("}}", "}"))
    except json.JSONDecodeError:
        pass

    try:
        json_match = re.search(r"```json\s*(.*?)\s*```", json_string, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(1).strip())
    except json.JSONDecodeError:
        pass

    try:
        start_idx = json_string.find("{")
        end_idx = json_string.rfind("}")
        if start_idx != -1 and end_idx > start_idx:
            return json.loads(json_string[start_idx : end_idx + 1])
    except json.JSONDecodeError:
        pass

    try:
        fixed_json = json_string.replace("{{", "{").replace("}}", "}")
        start_idx = fixed_json.find("{")
        end_idx = fixed_json.rfind("}")
        if start_idx != -1 and end_idx > start_idx:
            fixed_json = fixed_json[start_idx : end_idx + 1]

        fixed_json = re.sub(r"#.*", "", fixed_json)
        fixed_json = re.sub(r"//.*", "", fixed_json)
        fixed_json = re.sub(r",\s*}", "}", fixed_json)
        fixed_json = re.sub(r",\s*]", "]", fixed_json)
        fixed_json = re.sub(r"'([^']*)':", r'"\1":', fixed_json)
        fixed_json = re.sub(
            r"([\{\[,]\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*:)",
            r'\1"\2"\3',
            fixed_json,
        )
        fixed_json = re.sub(r'""([^\"]*?)""', r'"\1"', fixed_json)
        return json.loads(fixed_json)
    except json.JSONDecodeError as exc:
        logger.debug(f"综合修复失败: {exc}")

    logger.error(f"所有JSON解析方法都失败，原始内容: {json_string[:200]}...")
    return None


def parse_script_payload(payload: Any) -> list[dict]:
    """Normalize a script payload into the list shape consumed by core services."""
    if isinstance(payload, list):
        return payload

    if isinstance(payload, str):
        parsed = parse_and_fix_json(payload)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict) and isinstance(parsed.get("items"), list):
            return parsed["items"]
        raise ValueError("Generated script JSON must be a list or contain an items list")

    raise ValueError("Generated script payload must be a list or JSON string")
