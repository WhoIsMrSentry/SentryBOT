"""Schema definitions for headless web search and page inspection tools."""
from __future__ import annotations

from typing import Any, Dict, List


def get_web_tool_definitions() -> List[Dict[str, Any]]:
    """Returns Pi-5-friendly headless web search & fetch tool schemas."""
    return [
        {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": (
                    "Search the internet headlessly (no browser) when you do not know a "
                    "factual or up-to-date answer. Returns titles, URLs, and short snippets."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query string.",
                        },
                        "max_results": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 10,
                            "default": 5,
                            "description": "Maximum number of results to return.",
                        },
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "fetch_webpage",
                "description": (
                    "Download a public webpage over HTTP (no browser) and extract its "
                    "clean readable text content to read details or sources."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "Public http/https URL to inspect.",
                        },
                        "max_chars": {
                            "type": "integer",
                            "minimum": 300,
                            "maximum": 12000,
                            "default": 4000,
                            "description": "Maximum extracted character budget.",
                        },
                    },
                    "required": ["url"],
                },
            },
        },
    ]
