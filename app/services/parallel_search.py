"""Anonymous Parallel Unified MCP search using the existing requests dependency."""

from __future__ import annotations

import json
from typing import Any

import requests
from loguru import logger

from app.services.tavily_search import TavilySearchError

MCP_URL = "https://mcp.parallel.ai/mcp"
USER_AGENT = "NarratoAI/0.8.7 (Parallel plot-context search)"
PROTOCOL_VERSION = "2025-03-26"


def _rpc_result(response: requests.Response, request_id: int) -> dict[str, Any]:
    """Read JSON or the matching JSON-RPC response from a finite SSE stream."""
    response.encoding = "utf-8"
    try:
        if "text/event-stream" in response.headers.get("Content-Type", ""):
            messages = []
            # An SSE event may contain several data lines and unrelated notifications.
            # Only CR/LF delimit SSE lines; Unicode separators belong to JSON strings.
            for event in response.text.replace("\r\n", "\n").replace("\r", "\n").split("\n\n"):
                data = "\n".join(line[5:].lstrip() for line in event.split("\n") if line.startswith("data:"))
                if data:
                    messages.append(json.loads(data))
        else:
            messages = [response.json()]
        for message in messages:
            if not isinstance(message, dict) or message.get("id") != request_id:
                continue
            if message.get("error"):
                raise TavilySearchError("Parallel MCP 返回错误")
            if not isinstance(message.get("result"), dict):
                break
            return message["result"]
    except (ValueError, TypeError) as exc:
        raise TavilySearchError("Parallel MCP 返回内容不是有效 JSON-RPC") from exc
    raise TavilySearchError("Parallel MCP 缺少匹配的响应")


def _search_results(result: dict[str, Any], query: str, max_results: int) -> dict[str, Any]:
    if result.get("isError"):
        raise TavilySearchError("Parallel 搜索工具返回错误")
    data = result.get("structuredContent")
    if data is None:
        if not isinstance(result.get("content"), list):
            raise TavilySearchError("Parallel 搜索结果格式无效")
        try:
            data = json.loads("\n".join(
                part["text"] for part in result.get("content", [])
                if isinstance(part, dict) and part.get("type") == "text"
            ))
        except (ValueError, TypeError, KeyError) as exc:
            raise TavilySearchError("Parallel 搜索结果格式无效") from exc
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        raise TavilySearchError("Parallel 搜索结果格式无效")
    results = []
    for item in data["results"]:
        if (not isinstance(item, dict) or not isinstance(item.get("url"), str)
                or not item["url"].startswith(("https://", "http://"))
                or not isinstance(item.get("excerpts"), list)
                or not all(isinstance(part, str) for part in item["excerpts"])):
            raise TavilySearchError("Parallel 搜索来源格式无效")
        results.append({
            "title": item.get("title") or "",
            "url": item["url"],
            "content": "\n\n".join(item["excerpts"]),
        })
    return {"provider": "parallel", "query": query, "answer": "", "results": results[:max_results]}


def search_parallel_context(query: str, *, max_results: int = 5, timeout: int = 20) -> dict[str, Any]:
    """Use only web_search. No source fetches, background GET stream or retries."""
    max_results = max(1, min(int(max_results or 5), 10))
    with requests.Session() as session:
        session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json, text/event-stream"})

        def request(method: str, payload=None):
            response = session.request(method, MCP_URL, json=payload, timeout=timeout, allow_redirects=False)
            # Do not follow redirects to another transport or origin.
            if not 200 <= response.status_code < 300:
                response.close()
                raise TavilySearchError(f"Parallel 请求失败: HTTP {response.status_code}")
            return response

        def rpc(request_id: int, method: str, params: dict):
            with request("POST", {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}) as response:
                if method == "initialize":
                    session_id = response.headers.get("Mcp-Session-Id")
                    if session_id:
                        session.headers["Mcp-Session-Id"] = session_id
                return _rpc_result(response, request_id)

        try:
            initialized = rpc(1, "initialize", {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "NarratoAI", "version": "0.8.7"},
            })
            if initialized.get("protocolVersion") != PROTOCOL_VERSION:
                raise TavilySearchError("Parallel MCP 协议版本不兼容")
            session.headers["MCP-Protocol-Version"] = PROTOCOL_VERSION
            with request("POST", {"jsonrpc": "2.0", "method": "notifications/initialized"}):
                pass
            tools = rpc(2, "tools/list", {})
            listed_tools = tools.get("tools")
            if not isinstance(listed_tools, list) or not any(
                isinstance(tool, dict) and tool.get("name") == "web_search" for tool in listed_tools
            ):
                raise TavilySearchError("Parallel MCP 未提供 web_search")
            result = rpc(3, "tools/call", {
                "name": "web_search",
                "arguments": {"objective": f"Find plot, characters and story background for: {query}", "search_queries": [query]},
            })
            return _search_results(result, query, max_results)
        except requests.RequestException as exc:
            raise TavilySearchError("Parallel 网络请求失败") from exc
        finally:
            if session.headers.get("Mcp-Session-Id"):
                try:
                    # Some servers do not support client termination. It must not mask search errors.
                    with session.delete(MCP_URL, timeout=timeout, allow_redirects=False):
                        pass
                except requests.RequestException:
                    logger.debug("Parallel MCP session cleanup failed")
