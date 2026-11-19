"""Headless Pi-5-friendly web research tools for ToolRegistry."""
from __future__ import annotations

import logging
from typing import List

logger = logging.getLogger("agent.tools.web")


class WebToolsMixin:
    """Provides browser-free web search and page text inspection tools."""

    def web_search(self, query: str, max_results: int = 5) -> str:
        from modules.common.web_extractor import search_web_headless

        q = str(query or "").strip()
        if not q:
            return "Error: empty search query."
        limit = max(1, min(10, int(max_results or 5)))
        res = search_web_headless(q, max_results=limit, timeout_s=6.0)
        if not res.get("ok"):
            return f"Web search failed ({res.get('error', 'unavailable')})."
        items = res.get("results") or []
        if not items:
            return "No web search results found."
        lines: List[str] = [f"Search backend: {res.get('backend', 'http')}"]
        for idx, item in enumerate(items[:limit], start=1):
            title = str(item.get("title", "")).strip()
            url = str(item.get("url", "")).strip()
            snippet = str(item.get("snippet", "")).strip()
            lines.append(f"{idx}. {title}\n   URL: {url}\n   {snippet}")
        return "\n".join(lines)

    def fetch_webpage(self, url: str, max_chars: int = 4000) -> str:
        from modules.common.web_extractor import fetch_url_text

        target = str(url or "").strip()
        if not target:
            return "Error: empty URL."
        budget = max(300, min(12000, int(max_chars or 4000)))
        res = fetch_url_text(target, timeout_s=8.0, max_chars=budget)
        if not res.get("ok"):
            return f"Failed to fetch webpage: {res.get('error', 'unknown error')}"
        return f"URL: {res.get('url', target)}\n\n{res.get('text', '')}"
