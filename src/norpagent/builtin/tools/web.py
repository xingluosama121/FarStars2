# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Web retrieval tools: web_search / web_fetch / web_extract_links.

Migrated from the existing application's web_fetcher_native; features kept
consistent:
- SSRF protection: http/https only; internal / loopback / link-local addresses
  are rejected after DNS resolution;
- dual-engine graceful degradation: requests preferred (norpagent[web]), urllib
  standard library as fallback;
- text extraction: BeautifulSoup preferred, regex standard library as fallback.

All features work with zero third-party dependencies; installing norpagent[web]
gives better fetch and parse quality.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from html import unescape
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urljoin, urlparse

from norpagent.protocols.tool import Tool, ToolResult

# ── SSRF protection ────────────────────────────────────────

_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("240.0.0.0/4"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def is_private_url(url: str) -> Tuple[bool, str]:
    """Return (restricted or not, reason). Restricted = access forbidden."""
    try:
        parsed = urlparse(url)
    except Exception:
        return True, f"cannot parse URL: {url}"

    if parsed.scheme not in ("http", "https"):
        return True, f"unsupported protocol: {parsed.scheme} (http/https only)"

    hostname = parsed.hostname
    if not hostname:
        return True, "URL has no resolvable hostname"

    if hostname.lower() in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        return True, "access to localhost addresses is forbidden"

    try:
        infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        addr_str = infos[0][4][0] if infos else hostname
    except socket.gaierror:
        return True, f"cannot resolve hostname: {hostname}"
    except Exception as exc:  # noqa: BLE001
        return True, f"DNS resolution failed: {exc}"

    try:
        addr = ipaddress.ip_address(addr_str)
    except ValueError:
        return True, f"cannot parse as an IP address: {addr_str}"

    for net in _BLOCKED_NETWORKS:
        if addr in net:
            return True, f"security restriction: access to internal address {addr} is forbidden (part of {net})"
    return False, ""


# ── HTTP fetch (requests preferred, urllib fallback) ─────

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36"
)

_ACCEPT = (
    "text/html,application/xhtml+xml,"
    "application/xml;q=0.9,text/plain;q=0.8,*/*;q=0.5"
)

_MAX_RESPONSE_BYTES = 10 * 1024 * 1024

_TEXT_TYPES = (
    "text/", "application/json", "application/xml",
    "application/xhtml", "application/javascript",
)


def _requests_available() -> bool:
    try:
        import requests  # noqa: F401

        return True
    except ImportError:
        return False


def _bs4_available() -> bool:
    try:
        import bs4  # noqa: F401

        return True
    except ImportError:
        return False


def _fetch_url(url: str, timeout: int) -> Tuple[int, str, Optional[str]]:
    """Return (HTTP status code, response text, error). A non-None error means failure."""
    if _requests_available():
        return _fetch_with_requests(url, timeout)
    return _fetch_with_urllib(url, timeout)


def _check_content_type(content_type: str) -> Optional[str]:
    ctype = (content_type or "").lower()
    if ctype and not any(t in ctype for t in _TEXT_TYPES):
        return f"unsupported content type: {ctype}. Only text-like pages are supported."
    return None


def _fetch_with_requests(url: str, timeout: int) -> Tuple[int, str, Optional[str]]:
    import requests

    headers = {
        "User-Agent": _USER_AGENT,
        "Accept": _ACCEPT,
        "Accept-Language": "en-US,en;q=0.9,zh;q=0.8",
        "Accept-Encoding": "gzip, deflate",
    }
    try:
        resp = requests.get(
            url, headers=headers, timeout=timeout,
            allow_redirects=True, stream=True,
        )
        ctype_err = _check_content_type(resp.headers.get("Content-Type", ""))
        if ctype_err:
            resp.close()
            return resp.status_code, "", ctype_err

        chunks: List[bytes] = []
        total = 0
        for chunk in resp.iter_content(chunk_size=8192, decode_unicode=False):
            if chunk:
                total += len(chunk)
                if total > _MAX_RESPONSE_BYTES:
                    chunks.append(chunk[: _MAX_RESPONSE_BYTES - (total - len(chunk))])
                    break
                chunks.append(chunk)
        body = b"".join(chunks)
        resp.encoding = resp.apparent_encoding or "utf-8"
        try:
            text = body.decode(resp.encoding, errors="replace")
        except (LookupError, UnicodeDecodeError):
            text = body.decode("utf-8", errors="replace")
        return resp.status_code, text, None
    except requests.exceptions.Timeout:
        return 0, "", f"request timed out ({timeout}s). Increase timeout or retry later."
    except requests.exceptions.ConnectionError as exc:
        return 0, "", f"connection failed: {exc}"
    except requests.exceptions.TooManyRedirects:
        return 0, "", "too many redirects; request could not complete."
    except requests.exceptions.RequestException as exc:
        return 0, "", f"request failed: {exc}"
    except Exception as exc:  # noqa: BLE001
        return 0, "", f"unknown error: {exc}"


def _fetch_with_urllib(url: str, timeout: int) -> Tuple[int, str, Optional[str]]:
    import gzip
    from urllib.error import HTTPError, URLError
    from urllib.request import Request, urlopen

    headers = {
        "User-Agent": _USER_AGENT,
        "Accept": _ACCEPT,
        "Accept-Language": "en-US,en;q=0.9,zh;q=0.8",
        "Accept-Encoding": "gzip",
    }
    try:
        req = Request(url, headers=headers)
        resp = urlopen(req, timeout=timeout)
        status = getattr(resp, "status", 200)
        content_type = (resp.headers.get("Content-Type") or "").lower()
        ctype_err = _check_content_type(content_type)
        if ctype_err:
            return status, "", ctype_err

        data = resp.read(_MAX_RESPONSE_BYTES + 1)
        if len(data) > _MAX_RESPONSE_BYTES:
            data = data[:_MAX_RESPONSE_BYTES]
        if resp.headers.get("Content-Encoding", "").lower() == "gzip":
            try:
                data = gzip.decompress(data)
            except OSError:
                pass
        charset = "utf-8"
        if "charset=" in content_type:
            try:
                charset = content_type.split("charset=")[1].split(";")[0].strip()
            except IndexError:
                pass
        try:
            text = data.decode(charset, errors="replace")
        except LookupError:
            text = data.decode("utf-8", errors="replace")
        return status, text, None
    except HTTPError as exc:
        return exc.code, "", f"HTTP {exc.code}: {exc.reason}"
    except URLError as exc:
        return 0, "", f"connection failed: {exc.reason}"
    except socket.timeout:
        return 0, "", f"request timed out ({timeout}s). Increase timeout or retry later."
    except Exception as exc:  # noqa: BLE001
        return 0, "", f"unknown error: {exc}"


# ── HTML text extraction (bs4 preferred, regex fallback) ─

def _extract_text(html: str) -> str:
    if _bs4_available():
        return _extract_text_bs4(html)
    return _extract_text_regex(html)


def _extract_text_bs4(html: str) -> str:
    import bs4

    try:
        soup = bs4.BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg", "iframe", "head"]):
            tag.decompose()
        lines: List[str] = []
        for text in soup.stripped_strings:
            text = " ".join(text.split())
            if text and text not in lines:
                lines.append(text)
        return "\n".join(lines)
    except Exception:
        return _extract_text_regex(html)


def _extract_text_regex(html: str) -> str:
    body_match = re.search(r"<body[^>]*>(.*?)</body>", html, re.S | re.I)
    html = body_match.group(1) if body_match else html
    html = re.sub(r"<(script|style|noscript|svg|iframe)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    html = re.sub(r"</(p|div|h[1-6]|li|tr|section|article)>", "\n", html, flags=re.I)
    html = re.sub(r"<[^>]+>", " ", html)
    text = unescape(html)
    lines = [" ".join(ln.split()) for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


# ── link extraction ───────────────────────────────────────

def _extract_links(html: str, base_url: str) -> List[Tuple[str, str, bool]]:
    """Return [(absolute URL, text, same-domain or not)]."""
    if _bs4_available():
        return _extract_links_bs4(html, base_url)
    return _extract_links_regex(html, base_url)


def _extract_links_bs4(html: str, base_url: str) -> List[Tuple[str, str, bool]]:
    import bs4

    try:
        soup = bs4.BeautifulSoup(html, "html.parser")
        base_domain = urlparse(base_url).netloc.lower()
        result: List[Tuple[str, str, bool]] = []
        for a in soup.find_all("a", href=True):
            href = urljoin(base_url, a.get("href", ""))
            if not href.startswith(("http://", "https://")):
                continue
            text = " ".join(a.get_text(" ", strip=True).split())[:120]
            result.append((href, text, urlparse(href).netloc.lower() == base_domain))
        return result
    except Exception:
        return _extract_links_regex(html, base_url)


def _extract_links_regex(html: str, base_url: str) -> List[Tuple[str, str, bool]]:
    base_domain = urlparse(base_url).netloc.lower()
    result: List[Tuple[str, str, bool]] = []
    for m in re.finditer(r"<a\s+[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", html, re.S | re.I):
        href = urljoin(base_url, unescape(m.group(1)).strip())
        if not href.startswith(("http://", "https://")):
            continue
        text = " ".join(unescape(re.sub(r"<[^>]+>", " ", m.group(2))).split())[:120]
        result.append((href, text, urlparse(href).netloc.lower() == base_domain))
    return result


def _score_link_text(text: str) -> int:
    if not text:
        return 0
    score = min(len(text), 60)
    if re.search(r"[\u4e00-\u9fa5]", text):
        score += 10
    if re.search(r"[a-zA-Z]{2,}", text):
        score += 5
    return score


# ── tools ─────────────────────────────────────────────────

def _ensure_https(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        return "https://" + url
    return url


class WebFetchTool:
    name = "web_fetch"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": (
                    "Fetches the body text of a given URL (HTML tags/scripts/styles stripped automatically). "
                    "Built-in SSRF protection; only public http/https addresses allowed. "
                    "Returns truncated plain text, suitable for reading online docs, blogs, API responses, etc."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "The full URL to fetch"},
                        "max_chars": {"type": "integer", "description": "Max characters to return (default 8000, range 500-50000)"},
                        "timeout": {"type": "integer", "description": "Request timeout in seconds (default 15, range 5-60)"},
                    },
                    "required": ["url"],
                    "additionalProperties": False,
                },
            },
        }

    def run(self, args: Dict[str, Any], ctx: Any) -> ToolResult:
        url = _ensure_https(str(args.get("url") or "").strip())
        if not url or url == "https://":
            return ToolResult(output="Please provide a URL to fetch.", success=False, error="missing_url")
        max_chars = max(500, min(int(args.get("max_chars") or 8000), 50000))
        timeout = max(5, min(int(args.get("timeout") or 15), 60))

        blocked, reason = is_private_url(url)
        if blocked:
            return ToolResult(output=f"security restriction: {reason}", success=False, error=reason)

        status, html, error = _fetch_url(url, timeout)
        if error:
            if status > 0:
                return ToolResult(
                    output=f"HTTP {status}\nURL: {url}\nThe server returned an error status; no body content to extract.",
                    success=False,
                    error=f"HTTP {status}",
                )
            return ToolResult(output=f"fetch failed: {error}", success=False, error=error)

        if not html or not html.strip():
            return ToolResult(output=f"empty page content (HTTP {status}). URL: {url}", success=False, error="empty")

        text = _extract_text(html)
        if not text or not text.strip():
            return ToolResult(
                output=(
                    f"the page has no meaningful text content (HTTP {status}). "
                    f"It may be a pure JavaScript-rendered page or a blank page. URL: {url}"
                ),
                success=False,
                error="no_text",
            )

        original_len = len(text)
        if original_len > max_chars:
            text = text[:max_chars]
            last_period = max(text.rfind(". "),
                              text.rfind("\n"), text.rfind(" "))
            if last_period > max_chars * 0.7:
                text = text[: last_period + 1]

        engines = " + ".join(
            [("BeautifulSoup" if _bs4_available() else "regex (stdlib)"),
             ("requests" if _requests_available() else "urllib (stdlib)")]
        )
        lines = [
            "[web fetch result]",
            "",
            f"URL: {url}",
            f"status: HTTP {status}",
            f"original size: {original_len:,} chars",
            f"engines: {engines}",
        ]
        if original_len > max_chars:
            lines.append(f"truncated: showing first {len(text):,} chars")
        lines += ["", "-" * 60, "", text]
        return ToolResult(output="\n".join(lines))


class WebExtractLinksTool:
    name = "web_extract_links"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": (
                    "Extracts all hyperlinks from a given page, grouped into same-domain internal links / external links. "
                    "Useful for browsing an index page first, then deep-fetching interesting links."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "The page URL to extract links from"},
                        "same_domain_only": {"type": "boolean", "description": "Whether to return only same-domain links (default false)"},
                        "max_links": {"type": "integer", "description": "Max links to return (default 50, range 10-200)"},
                        "timeout": {"type": "integer", "description": "Request timeout in seconds (default 15, range 5-60)"},
                    },
                    "required": ["url"],
                    "additionalProperties": False,
                },
            },
        }

    def run(self, args: Dict[str, Any], ctx: Any) -> ToolResult:
        url = _ensure_https(str(args.get("url") or "").strip())
        if not url or url == "https://":
            return ToolResult(output="Please provide a URL to extract links from.", success=False, error="missing_url")
        same_domain_only = bool(args.get("same_domain_only", False))
        max_links = max(10, min(int(args.get("max_links") or 50), 200))
        timeout = max(5, min(int(args.get("timeout") or 15), 60))

        blocked, reason = is_private_url(url)
        if blocked:
            return ToolResult(output=f"security restriction: {reason}", success=False, error=reason)

        status, html, error = _fetch_url(url, timeout)
        if error:
            if status > 0:
                return ToolResult(output=f"HTTP {status}; cannot extract links.", success=False, error=f"HTTP {status}")
            return ToolResult(output=f"fetch failed: {error}", success=False, error=error)
        if not html or not html.strip():
            return ToolResult(output=f"empty page content (HTTP {status}); no links to extract.", success=False, error="empty")

        all_links = _extract_links(html, url)
        if not all_links:
            return ToolResult(
                output=(
                    f"[link extraction result]\n\nURL: {url}\nstatus: HTTP {status}\n"
                    f"links found: 0\n\nThe page has no extractable hyperlinks (it may be a pure JavaScript-rendered page)."
                )
            )

        internal = sorted(
            [l for l in all_links if l[2]], key=lambda x: _score_link_text(x[1]), reverse=True
        )
        external = sorted(
            [l for l in all_links if not l[2]], key=lambda x: _score_link_text(x[1]), reverse=True
        )
        if same_domain_only:
            internal = internal[:max_links]
            external = []
        elif len(internal) >= max_links:
            internal = internal[:max_links]
            external = []
        else:
            external = external[: max_links - len(internal)]

        base_domain = urlparse(url).netloc.lower()
        lines = [
            "[link extraction result]",
            "",
            f"source URL: {url}",
            f"domain: {base_domain}",
            f"HTTP: {status}",
            f"total raw links: {len(all_links)}",
        ]
        if same_domain_only:
            lines.append("filter: same-domain links only")
        lines.append(f"showing: {len(internal) + len(external)} (cap {max_links})")
        lines.append("")
        if internal:
            lines.append(f"## same-domain internal links ({len(internal)})")
            lines.append("")
            for i, (href, text, _) in enumerate(internal, 1):
                disp = text if len(text) <= 80 else text[:77] + "..."
                lines.append(f"  {i}. [{disp}]({href})")
        if external:
            lines.append("")
            lines.append(f"## external links ({len(external)})")
            lines.append("")
            for i, (href, text, _) in enumerate(external, 1):
                disp = text if len(text) <= 60 else text[:57] + "..."
                lines.append(f"  {i}. [{disp}]({href})")
        lines += ["", "-" * 60, "hint: call web_fetch on any of the URLs above to fetch that page's body text."]
        return ToolResult(output="\n".join(lines))


class WebSearchTool:
    name = "web_search"

    _ENDPOINT = "https://html.duckduckgo.com/html/"
    _FALLBACK = "https://lite.duckduckgo.com/lite/"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": (
                    "Searches the web for keywords and returns result titles, links and snippets (DuckDuckGo by default). "
                    "Suitable for looking up the latest material, API docs, error messages, etc."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search keywords or a question"},
                        "max_results": {"type": "integer", "description": "Max results to return (default 5, max 10)"},
                        "timeout": {"type": "integer", "description": "Request timeout in seconds (default 15, range 5-60)"},
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
            },
        }

    def run(self, args: Dict[str, Any], ctx: Any) -> ToolResult:
        query = str(args.get("query") or "").strip()
        if not query:
            return ToolResult(output="Please provide search keywords.", success=False, error="missing_query")
        max_results = max(1, min(int(args.get("max_results") or 5), 10))
        timeout = max(5, min(int(args.get("timeout") or 15), 60))

        blocked, reason = is_private_url(self._ENDPOINT)
        if blocked:
            return ToolResult(output=f"security restriction: {reason}", success=False, error=reason)

        results = self._search(self._ENDPOINT, query, timeout)
        if not results:
            results = self._search(self._FALLBACK, query, timeout)
        if not results:
            return ToolResult(
                output="search failed: no results returned. Retry later or try different keywords.",
                success=False,
                error="no_results",
            )

        lines = ["[search results]", "", f"keywords: {query}", f"results: {len(results)}", ""]
        for i, (title, href, snippet) in enumerate(results[:max_results], 1):
            lines.append(f"{i}. {title}")
            lines.append(f"   {href}")
            if snippet:
                lines.append(f"   {snippet}")
            lines.append("")
        return ToolResult(output="\n".join(lines).rstrip())

    def _search(self, endpoint: str, query: str, timeout: int) -> List[Tuple[str, str, str]]:
        """Fetch the search page and parse results."""
        try:
            if _requests_available():
                return self._search_requests(endpoint, query, timeout)
            return self._search_urllib(endpoint, query, timeout)
        except Exception:
            return []

    def _search_requests(self, endpoint: str, query: str, timeout: int) -> List[Tuple[str, str, str]]:
        import requests

        resp = requests.post(
            endpoint,
            data={"q": query},
            headers={"User-Agent": _USER_AGENT, "Accept-Language": "en-US,en;q=0.9,zh;q=0.8"},
            timeout=timeout,
            allow_redirects=True,
        )
        if resp.status_code != 200:
            return []
        return self._parse_results(resp.text)

    def _search_urllib(self, endpoint: str, query: str, timeout: int) -> List[Tuple[str, str, str]]:
        from urllib.parse import urlencode
        from urllib.request import Request, urlopen

        data = urlencode({"q": query}).encode("utf-8")
        req = Request(
            endpoint,
            data=data,
            headers={
                "User-Agent": _USER_AGENT,
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept-Language": "en-US,en;q=0.9,zh;q=0.8",
            },
        )
        resp = urlopen(req, timeout=timeout)
        body = resp.read(2 * 1024 * 1024)
        return self._parse_results(body.decode("utf-8", errors="replace"))

    def _parse_results(self, html: str) -> List[Tuple[str, str, str]]:
        results: List[Tuple[str, str, str]] = []
        for m in re.finditer(
            r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
            html, re.S | re.I,
        ):
            href = unescape(m.group(1)).strip()
            title = unescape(re.sub(r"<[^>]+>", "", m.group(2))).strip()
            href = _unwrap_ddg_redirect(href)
            if not href.startswith(("http://", "https://")):
                continue
            snippet = ""
            sm = re.search(
                r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
                html[m.end(): m.end() + 4000], re.S | re.I,
            )
            if sm:
                snippet = " ".join(unescape(re.sub(r"<[^>]+>", "", sm.group(1))).split())
            results.append((title or href, href, snippet[:300]))
        return results


def _unwrap_ddg_redirect(href: str) -> str:
    """DuckDuckGo result links are redirect URLs; unwrap the real target."""
    try:
        parsed = urlparse(href)
        if "duckduckgo.com" in (parsed.netloc or ""):
            qs = parse_qs(parsed.query)
            uddg = qs.get("uddg", [])
            if uddg and uddg[0].startswith(("http://", "https://")):
                return uddg[0]
    except Exception:
        pass
    return href
