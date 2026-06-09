"""Tavily-powered web search helpers for plot analysis."""

from __future__ import annotations

import os
from typing import Any

import requests
from loguru import logger


TAVILY_API_BASE_URL = "https://api.tavily.com"
DEFAULT_SEARCH_DEPTH = "basic"
DEFAULT_MAX_RESULTS = 5
DEFAULT_TIMEOUT = 20


class TavilySearchError(RuntimeError):
    """Raised when Tavily search cannot be completed."""


def _trim_text(value: Any, max_chars: int) -> str:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars].rstrip()}..."


def search_short_drama(
    short_name: str,
    api_key: str | None = None,
    *,
    search_depth: str = DEFAULT_SEARCH_DEPTH,
    max_results: int = DEFAULT_MAX_RESULTS,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Search web context for a short drama name with Tavily."""
    return search_story_context(
        short_name,
        api_key,
        search_keywords="短剧 剧情 介绍 人物 结局",
        empty_name_message="短剧名称不能为空",
        search_depth=search_depth,
        max_results=max_results,
        timeout=timeout,
    )


def search_story_context(
    title: str,
    api_key: str | None = None,
    *,
    search_keywords: str = "剧情 介绍 人物 结局",
    empty_name_message: str = "作品名称不能为空",
    search_depth: str = DEFAULT_SEARCH_DEPTH,
    max_results: int = DEFAULT_MAX_RESULTS,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Search web context for a story title with Tavily."""
    title = str(title or "").strip()
    if not title:
        raise TavilySearchError(empty_name_message)

    api_key = (api_key or os.getenv("TAVILY_API_KEY") or "").strip()
    if not api_key:
        raise TavilySearchError("Tavily API Key 未配置")

    query = f"{title} {search_keywords}".strip()
    payload = {
        "query": query,
        "search_depth": search_depth or DEFAULT_SEARCH_DEPTH,
        "topic": "general",
        "max_results": max(1, min(int(max_results or DEFAULT_MAX_RESULTS), 10)),
        "include_answer": True,
        "include_raw_content": False,
        "include_images": False,
    }

    try:
        response = requests.post(
            f"{TAVILY_API_BASE_URL}/search",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise TavilySearchError(f"Tavily 请求失败: {exc}") from exc

    if response.status_code >= 400:
        message = _trim_text(response.text, 500)
        raise TavilySearchError(f"Tavily 请求失败: HTTP {response.status_code} {message}")

    try:
        data = response.json()
    except ValueError as exc:
        raise TavilySearchError("Tavily 返回内容不是有效 JSON") from exc

    logger.info(
        "Tavily 剧情检索完成: query={}, results={}",
        query,
        len(data.get("results") or []),
    )
    return data

def format_search_context(search_data: dict[str, Any], *, max_chars: int = 6000) -> str:
    """Format Tavily response into compact LLM context."""
    if not search_data:
        return ""

    lines = [
        "# Tavily 联网检索结果",
        f"检索 query: {search_data.get('query', '')}",
    ]

    answer = _trim_text(search_data.get("answer"), 1200)
    if answer:
        lines.extend(["", "## 综合回答", answer])

    results = search_data.get("results") or []
    if results:
        lines.extend(["", "## 搜索来源"])
    for index, result in enumerate(results, start=1):
        title = _trim_text(result.get("title"), 120)
        url = _trim_text(result.get("url"), 240)
        content = _trim_text(result.get("content") or result.get("raw_content"), 700)
        lines.extend(
            [
                f"{index}. 标题: {title}",
                f"   来源: {url}",
                f"   摘要: {content}",
            ]
        )

    return _trim_text("\n".join(lines).strip(), max_chars)
