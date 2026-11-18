"""Shared headless web search and SSRF-safe HTML text extractor.

Runs without any headless browser (Chromium/Playwright) for Raspberry Pi 5.
Optionally uses `ddgs` / `trafilatura` / `beautifulsoup4` when installed and
always works with standard-library HTML parsing + `requests`.
"""
from __future__ import annotations

from html.parser import HTMLParser
import ipaddress
import logging
import re
import socket
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, unquote, urlparse

logger = logging.getLogger("common.web_extractor")

_BLOCKED_HOST_SUFFIXES = (".local", ".internal", ".localhost", ".arpa")
_STRIP_SECTIONS = ("##  Gallery", "## Gallery", "##  Trivia", "## Trivia", "##  References", "## References")
_SKIP_TAGS = frozenset({"script", "style", "noscript", "svg", "nav", "footer", "aside", "header", "form"})
_BLOCK_TAGS = frozenset({"p", "div", "section", "article", "li", "tr", "blockquote", "pre", "br", "hr"})
_HEADING_TAGS = {"h1": "# ", "h2": "## ", "h3": "### ", "h4": "#### "}


def _is_public_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def validate_public_url(url: str, *, resolve_dns: bool = True) -> Tuple[bool, str]:
    """Validate URL scheme and guard against SSRF to local/private networks."""
    raw = str(url or "").strip()
    if not raw:
        return False, "URL is empty"
    parsed = urlparse(raw)
    if parsed.scheme.lower() not in {"http", "https"}:
        return False, f"Unsupported scheme '{parsed.scheme}'"
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return False, "Missing hostname"
    if host == "localhost" or any(host.endswith(suf) for suf in _BLOCKED_HOST_SUFFIXES):
        return False, f"Blocked private hostname '{host}'"
    try:
        ipaddress.ip_address(host)
        if not _is_public_ip(host):
            return False, f"Blocked non-public IP '{host}'"
        return True, ""
    except ValueError:
        pass
    if resolve_dns:
        try:
            infos = socket.getaddrinfo(host, parsed.port or 80, type=socket.SOCK_STREAM)
            ips = {info[4][0] for info in infos if info and info[4]}
            if not ips:
                return False, f"Could not resolve hostname '{host}'"
            for ip_addr in ips:
                if not _is_public_ip(ip_addr):
                    return False, f"Hostname '{host}' resolved to non-public IP '{ip_addr}'"
        except OSError as exc:
            return False, f"DNS lookup failed for '{host}': {exc}"
    return True, ""


class _ReadableHTMLParser(HTMLParser):
    """Lightweight stdlib HTML-to-Markdown text extractor."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._parts: List[str] = []
        self._in_title = False
        self.title = ""

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        t = tag.lower()
        if t in _SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth > 0:
            return
        if t == "title":
            self._in_title = True
        elif t in _HEADING_TAGS:
            self._parts.append(f"\n\n{_HEADING_TAGS[t]}")
        elif t == "li":
            self._parts.append("\n- ")
        elif t in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in _SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
            return
        if t == "title":
            self._in_title = False
        elif t in _HEADING_TAGS or t in {"p", "article", "section"}:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        if self._in_title and not self.title:
            self.title = " ".join(data.split()).strip()
        text = " ".join(data.split())
        if text:
            self._parts.append(f"{text} ")

    def get_text(self) -> str:
        joined = "".join(self._parts)
        joined = re.sub(r"[ \t]+\n", "\n", joined)
        joined = re.sub(r"\n{3,}", "\n\n", joined)
        return joined.strip()


def extract_html_title(html: str) -> str:
    """Extract and normalize a clean page title (stripping Portal Wiki suffix)."""
    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", str(html or ""))
    if not m:
        return ""
    import html as html_mod

    title = " ".join(html_mod.unescape(m.group(1)).split()).strip()
    for suffix in (" - Portal Wiki", " - Combine OverWiki", " - Wikipedia"):
        if title.endswith(suffix):
            title = title[: -len(suffix)].strip()
    return title


def trim_mediawiki_tail(markdown: str) -> str:
    """Trim noisy trailing sections such as Gallery/Trivia/References on Wiki pages."""
    text = str(markdown or "")
    match = re.search(r"(?im)^#{1,3}\s+(?:Gallery|Trivia|References)\b", text)
    if match and match.start() > 15:
        return text[: match.start()].strip()
    for marker in _STRIP_SECTIONS:
        idx = text.find(marker)
        if idx > 15:
            text = text[:idx]
    return text.strip()


def extract_readable_text(
    html: str,
    *,
    url: str = "",
    max_chars: int = 8000,
    strip_mediawiki_noise: bool = False,
) -> str:
    """Extract clean Markdown/plain text from raw HTML without browser dependencies."""
    raw = str(html or "")
    if not raw.strip():
        return ""

    target_html = raw
    if strip_mediawiki_noise:
        try:
            from bs4 import BeautifulSoup  # type: ignore

            soup = BeautifulSoup(raw, "html.parser")
            mw = soup.find("div", {"id": "mw-content-text"})
            if mw is not None:
                target_html = str(mw)
        except Exception:
            mw_idx = raw.find('id="mw-content-text"')
            if mw_idx >= 0:
                start = raw.rfind("<div", 0, mw_idx)
                end_footer = raw.find('<div class="printfooter"', mw_idx)
                if start >= 0:
                    target_html = raw[start:end_footer] if end_footer > start else raw[start:]

    extracted = ""
    try:
        import trafilatura  # type: ignore

        extracted = trafilatura.extract(
            target_html,
            url=url or None,
            output_format="markdown",
            include_links=False,
            favor_precision=True,
        ) or ""
    except Exception:
        extracted = ""

    if not extracted:
        try:
            from bs4 import BeautifulSoup  # type: ignore

            soup = BeautifulSoup(target_html, "html.parser")
            mw = soup.find("div", {"id": "mw-content-text"})
            if mw is not None:
                target_html = str(mw)
            else:
                for tag_name in ("main", "article"):
                    node = soup.find(tag_name)
                    if node is not None:
                        target_html = str(node)
                        break
        except Exception:
            pass
        parser = _ReadableHTMLParser()
        try:
            parser.feed(target_html)
            parser.close()
        except Exception:
            pass
        extracted = parser.get_text()

    if strip_mediawiki_noise and extracted:
        extracted = re.sub(r"(?im)^\s*Click to listen\s*$\n?", "", extracted)
        extracted = trim_mediawiki_tail(extracted)

    cleaned = re.sub(r"\n{3,}", "\n\n", extracted).strip()
    if max_chars > 0 and len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars].rstrip() + "..."
    return cleaned


def fetch_url_text(
    url: str,
    *,
    timeout_s: float = 8.0,
    max_chars: int = 6000,
    strip_mediawiki_noise: bool = False,
    resolve_dns: bool = True,
) -> Dict[str, Any]:
    """Fetch a public webpage over HTTP and return clean extracted text."""
    ok, err = validate_public_url(url, resolve_dns=resolve_dns)
    if not ok:
        return {"ok": False, "url": url, "error": err, "text": ""}

    try:
        import requests

        headers = {"User-Agent": "SentryBOT/5.0 (+headless-research; no-browser)"}
        resp = requests.get(url, headers=headers, timeout=float(timeout_s), allow_redirects=True)
        final_url = str(getattr(resp, "url", "") or url)
        ok_final, err_final = validate_public_url(final_url, resolve_dns=resolve_dns)
        if not ok_final:
            return {"ok": False, "url": final_url, "error": f"Redirect blocked: {err_final}", "text": ""}
        if resp.status_code != 200:
            return {"ok": False, "url": final_url, "error": f"HTTP {resp.status_code}", "text": ""}
        ctype = str(resp.headers.get("Content-Type", "text/html")).lower()
        body = resp.text[:250_000]
        title = ""
        if "text/plain" in ctype or "text/markdown" in ctype or url.lower().endswith((".txt", ".md")):
            text = body.strip()
            if max_chars > 0 and len(text) > max_chars:
                text = text[:max_chars].rstrip() + "..."
        else:
            title = extract_html_title(body)
            text = extract_readable_text(
                body,
                url=final_url,
                max_chars=max_chars,
                strip_mediawiki_noise=strip_mediawiki_noise,
            )
        return {"ok": bool(text), "url": final_url, "title": title, "text": text, "chars": len(text)}
    except Exception as exc:
        return {"ok": False, "url": url, "error": str(exc), "text": ""}


class _DDGResultHTMLParser(HTMLParser):
    """Minimal stdlib parser for DuckDuckGo HTML / Lite fallback search."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: List[Dict[str, str]] = []
        self._cur: Optional[Dict[str, str]] = None
        self._capture: str = ""
        self._buf: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        attr_map = dict(attrs)
        cls = str(attr_map.get("class") or "")
        if tag == "a" and ("result__a" in cls or "result-link" in cls):
            href = unquote(str(attr_map.get("href") or ""))
            if "uddg=" in href:
                qs = parse_qs(urlparse(href).query)
                href = qs.get("uddg", [href])[0]
            self._cur = {"title": "", "url": href, "snippet": ""}
            self._capture = "title"
            self._buf = []
        elif tag in {"a", "td", "div", "span"} and "result__snippet" in cls and self._cur is not None:
            self._capture = "snippet"
            self._buf = []

    def handle_endtag(self, tag: str) -> None:
        if not self._capture or self._cur is None:
            return
        text = " ".join("".join(self._buf).split()).strip()
        if self._capture == "title":
            self._cur["title"] = text
        elif self._capture == "snippet":
            self._cur["snippet"] = text
            if self._cur.get("title") or self._cur.get("url"):
                self.results.append(self._cur)
            self._cur = None
        self._capture = ""
        self._buf = []

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._buf.append(data)


def _search_ddgs_pkg(query: str, max_results: int) -> Optional[List[Dict[str, str]]]:
    try:
        from ddgs import DDGS  # type: ignore

        raw = list(DDGS().text(query, max_results=max_results) or [])
        return [
            {
                "title": str(r.get("title", "")).strip(),
                "url": str(r.get("href", "") or r.get("url", "")).strip(),
                "snippet": str(r.get("body", "") or r.get("snippet", "")).strip(),
            }
            for r in raw
            if isinstance(r, dict)
        ]
    except ImportError:
        return None
    except Exception as exc:
        logger.debug("ddgs search failed, trying HTTP fallback: %s", exc)
        return None


def _search_wikipedia_api(query: str, max_results: int, timeout_s: float) -> List[Dict[str, str]]:
    import requests

    for lang in ("tr", "en"):
        try:
            resp = requests.get(
                f"https://{lang}.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "list": "search",
                    "srsearch": query,
                    "srlimit": max_results,
                    "utf8": "1",
                    "format": "json",
                },
                headers={"User-Agent": "SentryBOT/5.0"},
                timeout=timeout_s,
            )
            if resp.status_code != 200:
                continue
            hits = ((resp.json() or {}).get("query") or {}).get("search") or []
            if not hits:
                continue
            out: List[Dict[str, str]] = []
            for h in hits[:max_results]:
                title = str(h.get("title", "")).strip()
                snippet = re.sub(r"<[^>]+>", " ", str(h.get("snippet", "")))
                snippet = " ".join(snippet.split())
                page_url = f"https://{lang}.wikipedia.org/wiki/{title.replace(' ', '_')}"
                out.append({"title": title, "url": page_url, "snippet": snippet})
            return out
        except Exception:
            continue
    return []


def search_web_headless(
    query: str,
    *,
    max_results: int = 5,
    timeout_s: float = 6.0,
) -> Dict[str, Any]:
    """Headless web search optimized for Raspberry Pi 5 (no Chromium/Playwright)."""
    q = str(query or "").strip()
    if not q:
        return {"ok": False, "error": "empty query", "results": []}
    limit = max(1, min(10, int(max_results)))

    pkg_hits = _search_ddgs_pkg(q, limit)
    if pkg_hits:
        return {"ok": True, "backend": "ddgs", "query": q, "results": pkg_hits[:limit]}

    import requests

    headers = {"User-Agent": "Mozilla/5.0 (compatible; SentryBOT/5.0)"}
    for endpoint in ("https://html.duckduckgo.com/html/", "https://lite.duckduckgo.com/lite/"):
        try:
            resp = requests.post(endpoint, data={"q": q}, headers=headers, timeout=float(timeout_s))
            if resp.status_code == 200 and resp.text:
                parser = _DDGResultHTMLParser()
                parser.feed(resp.text)
                parser.close()
                if parser.results:
                    return {
                        "ok": True,
                        "backend": "ddg_html",
                        "query": q,
                        "results": parser.results[:limit],
                    }
        except Exception as exc:
            logger.debug("DDG HTTP endpoint %s failed: %s", endpoint, exc)

    wiki_hits = _search_wikipedia_api(q, limit, float(timeout_s))
    if wiki_hits:
        return {"ok": True, "backend": "wikipedia_api", "query": q, "results": wiki_hits[:limit]}

    return {"ok": False, "backend": "none", "query": q, "results": [], "error": "No search backend returned results"}


__all__ = [
    "extract_readable_text",
    "fetch_url_text",
    "search_web_headless",
    "trim_mediawiki_tail",
    "validate_public_url",
]
