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
import json
import os
import re
import socket
import threading
import time
from html import unescape
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, quote, urljoin, urlparse

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

# ── search engine health cache (2026-09-12): on networks that block
#    DuckDuckGo, every single search burned one full connection timeout per
#    endpoint (up to ~16 s) before falling back to Bing. Recently failed
#    engines are now remembered and skipped for a short cooldown window, so
#    repeated searches stay responsive instead of re-probing a dead engine.
_ENGINE_COOLDOWN: Dict[str, float] = {}
_ENGINE_COOLDOWN_SECONDS = 180.0

# ── 引擎节流 + 反爬识别（2026-09-19）─────────────────────────
# 实测（2026-09-19）：连续快速请求会被引擎判定为爬虫。
#   百度最明显——一轮并发查询之后，同一 IP 在数分钟内所有查询都只返回
#   安全验证页（HTTP 200、无结果块），且不会自行恢复。
# 因此：① 对同一引擎的相邻请求强制最小间隔；② 把"安全验证页"识别为
#   引擎不可用并进冷却，而不是当成"这次没搜到"——后者会让每一次搜索
#   都重新去撞同一堵墙。
_ENGINE_LAST_CALL: Dict[str, float] = {}
_ENGINE_MIN_INTERVAL = 1.2      # 同一引擎相邻请求的最小间隔（秒）

# 命中任一特征即视为被反爬拦截。
_BLOCK_MARKERS = (
    # 百度
    "百度安全验证", "wappass.baidu.com", "verify.baidu.com", "security-verify",
    # Bing
    "unusual traffic", "captcha", "verify you are human", "are you a robot",
    # DuckDuckGo
    "unfortunately, bots use duckduckgo too",
    # 通用
    "enable javascript and cookies to continue",
)

# ── 可选搜索引擎 + 翻页上限（2026-09-14）─────────────────────
# 内置引擎：auto（默认回退链 Bing → Baidu → DuckDuckGo）/ duckduckgo /
# bing / baidu / custom（自定义端点）。默认引擎可被环境变量
# NORPAGENT_WEB_SEARCH_ENGINE 覆盖。
# 2026-09-19：回退链顺序改为 Bing 优先，不再按查询语言分流。
_BUILTIN_ENGINES = ("auto", "duckduckgo", "bing", "baidu", "custom")
_ENGINE_LABELS = {"duckduckgo": "DuckDuckGo", "bing": "Bing", "baidu": "Baidu"}
_MAX_RESULTS_CAP = 50      # max_results 上限
_PAGE_TARGET = 10          # 单页目标条数（各引擎每页实际 10~30 条）
_MAX_PAGES = 8             # 翻页上限（防止无限抓取）


def _engine_on_cooldown(name: str) -> bool:
    ts = _ENGINE_COOLDOWN.get(name)
    return bool(ts) and (time.time() - ts) < _ENGINE_COOLDOWN_SECONDS


def _mark_engine_down(name: str) -> None:
    _ENGINE_COOLDOWN[name] = time.time()


def _reset_engine_cooldown() -> None:
    """Clear the engine health cache (tests / manual reset)."""
    _ENGINE_COOLDOWN.clear()
    _ENGINE_LAST_CALL.clear()


def _throttle(engine_key: str) -> None:
    """同一引擎相邻请求之间的最小间隔（防反爬）。"""
    now = time.time()
    last = _ENGINE_LAST_CALL.get(engine_key)
    if last is not None:
        wait = _ENGINE_MIN_INTERVAL - (now - last)
        if wait > 0:
            time.sleep(wait)
    _ENGINE_LAST_CALL[engine_key] = time.time()


def _looks_blocked(body: str) -> bool:
    """响应体是否像反爬 / 安全验证页。"""
    if not body:
        return False
    head = body[:20000].lower()
    return any(marker.lower() in head for marker in _BLOCK_MARKERS)


def _query_tokens(query: str) -> List[str]:
    """查询词切分：ASCII 词（>=2 字符）+ 中文双字组（单字中文自成一组）。"""
    tokens: List[str] = []
    for word in re.findall(r"[A-Za-z0-9_]{2,}", query or ""):
        tokens.append(word.lower())
    for run in re.findall(r"[\u4e00-\u9fff]+", query or ""):
        if len(run) == 1:
            tokens.append(run)
        else:
            tokens.extend(run[i:i + 2] for i in range(len(run) - 1))
    return tokens


def _results_relevant(results: List[Tuple[str, str, str]], query: str) -> bool:
    """结果与查询词是否存在任何字面重叠。

    用于识别"引擎返回了一个与查询无关的通用页"（实测遇到过：查询
    'Chalkbeat Khanmigo' 返回加拿大本地的披萨店聚合页）。只在**完全无
    重叠**时判为无关，以免误杀。
    注意这是粗筛：它抓不住"只匹配了查询里第一个词"这种部分退化，那种
    情况需要更重的语义判断，本函数不做承诺。
    """
    tokens = _query_tokens(query)
    if not tokens or not results:
        return True
    haystack = " ".join(
        ((title or "") + " " + (snippet or "")) for title, _href, snippet in results
    ).lower()
    return any(token in haystack for token in tokens)


# ── 工具层并行（2026-09-19）──────────────────────────────────
# 并发全部落在**工具内部**，不改内核调度：内核的 tool_calls 循环仍是串行
# 的（kernel/agent.py），避免把并发语义污染进内核。这里直接复用库自研的
# nasyncio 事件循环设施（norpagent.loops.nasyncio.NasyncioLoopRuntime，
# 零 asyncio 依赖），而不是另起 stdlib 线程池。
#
# 并发维度是**关键词 / URL**，不是引擎：一次调用里的多个关键词各自独立跑
# 完自己的引擎回退链，彼此并发。
#
# 两档限流：
#   - _MAX_LANES：整体并发上限（关键词 / URL 级），默认 64；
#   - _DOMAIN_LIMIT：同一 DNS 归属（域名相同，或解析到同一 IP）上限
#     5 路/次，防止对同一目标站短时猛打被封。
_MAX_LANES = 64
_DOMAIN_LIMIT = 5
_PARALLEL_FALLBACK = 8      # 自研循环不可用时的降级并发度
_COLLECT_TIMEOUT = 60.0     # 整批收集的总预算（秒）

_RUNTIME_LOCK = threading.Lock()
_RUNTIME: Any = None


def _get_runtime():
    """惰性启动自研 nasyncio 运行时（进程内单例，64 worker）。

    复用库自身的异步设施而非另造线程池；启动失败返回 None，调用方降级为
    受控的小并发。
    """
    global _RUNTIME
    if _RUNTIME is not None:
        return _RUNTIME
    with _RUNTIME_LOCK:
        if _RUNTIME is not None:
            return _RUNTIME
        try:
            from norpagent.loops.nasyncio import NasyncioLoopRuntime
        except Exception:
            _RUNTIME = False
            return None
        try:
            rt = NasyncioLoopRuntime(config={"max_workers": _MAX_LANES})
            rt.start()
        except Exception:
            _RUNTIME = False
            return None
        _RUNTIME = rt
        return rt


def _host_group(url: str) -> str:
    """同一 DNS 归属分组键：优先用解析后的 IP，取不到则退回主机名。

    同组内最多 _DOMAIN_LIMIT 路并发。用 IP 而非域名作键，是为了让"不同
    域名指向同一台机器"也能被同一档限流覆盖。
    """
    try:
        host = urlparse(url).hostname or ""
    except Exception:
        return ""
    if not host:
        return ""
    try:
        infos = socket.getaddrinfo(host, None)
        if infos:
            return infos[0][4][0]
    except Exception:
        pass
    return host


def _parallel_map(jobs, timeout: float = _COLLECT_TIMEOUT):
    """并发跑完 jobs 里的每一项，**等全部结束**再返回（不做提前中止）。

    Args:
        jobs: [(key, group, fn), ...]；key 用于回传顺序，group 是限流分组键。

    Returns:
        {key: (ok, value_or_exception)} —— 与 jobs 一一对应；超时未完成的
        项标记为 (False, TimeoutError)。
    """
    n = len(jobs)
    if n == 0:
        return {}
    if n == 1:
        key, _grp, fn = jobs[0]
        try:
            return {key: (True, fn())}
        except Exception as exc:  # noqa: BLE001
            return {key: (False, exc)}

    runtime = _get_runtime()
    out: Dict[Any, Tuple[bool, Any]] = {}
    deadline = time.monotonic() + timeout

    if runtime is None:
        # 降级：受控的小并发，保证工具仍可用。
        from concurrent.futures import ThreadPoolExecutor
        lanes = max(1, min(_PARALLEL_FALLBACK, n))
        with ThreadPoolExecutor(max_workers=lanes) as pool:
            fut = {key: pool.submit(fn) for key, _grp, fn in jobs}
            for key, f in fut.items():
                try:
                    out[key] = (True, f.result(timeout=max(1.0, deadline - time.monotonic())))
                except Exception as exc:  # noqa: BLE001
                    out[key] = (False, exc)
        return out

    handles: Dict[Any, Any] = {}
    groups: Dict[Any, str] = {}
    inflight: Dict[Any, str] = {}
    group_count: Dict[str, int] = {}
    waiting = [key for key, _grp, _fn in jobs]
    fn_of = {key: fn for key, _grp, fn in jobs}
    grp_of = {key: (grp or "") for key, grp, _fn in jobs}

    def _fill():
        rest = []
        for key in waiting:
            group = grp_of[key]
            if len(inflight) >= _MAX_LANES or group_count.get(group, 0) >= _DOMAIN_LIMIT:
                rest.append(key)
                continue
            handles[key] = runtime.submit_async(fn_of[key])
            inflight[key] = group
            groups[key] = group
            group_count[group] = group_count.get(group, 0) + 1
        waiting[:] = rest

    _fill()
    while inflight:
        for key in list(inflight):
            handle = handles[key]
            try:
                finished = handle.done()
            except Exception:  # noqa: BLE001
                finished = True
            if not finished:
                continue
            group = inflight.pop(key)
            group_count[group] = max(0, group_count.get(group, 0) - 1)
            try:
                out[key] = (True, handle.result(timeout=0))
            except Exception as exc:  # noqa: BLE001
                out[key] = (False, exc)
        _fill()
        if time.monotonic() > deadline:
            break
        if inflight:
            time.sleep(0.005)

    # 超时仍未完成的：主动取消并标记
    for key in list(inflight):
        try:
            handles[key].cancel()
        except Exception:  # noqa: BLE001
            pass
    for key, _grp, _fn in jobs:
        if key not in out:
            out[key] = (False, TimeoutError("parallel task not finished within the budget"))
    return out


def _host_of_result(href: str) -> str:
    """搜索结果按目标域名分组（不做 DNS，避免翻页时为每条结果额外解析）。"""
    try:
        return (urlparse(href).hostname or "").lower()
    except Exception:
        return ""


def _dedupe_by_url(items):
    """按 URL 去重，保留首次出现顺序。"""
    seen = set()
    out = []
    for item in items:
        href = item[1] if len(item) > 1 else ""
        key = (href or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


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


def _charset_from_content_type(content_type: str) -> str:
    """Extract a charset from a Content-Type header value ("" when absent)."""
    match = re.search(r"charset\s*=\s*[\"']?([\w.-]+)", content_type or "", re.I)
    return (match.group(1) or "").strip().lower() if match else ""


def _detect_charset_bytes(body: bytes) -> str:
    """Best-effort charset detection over already-read bytes ("" when unknown).

    Detection always runs on the bytes in hand; it never re-reads the HTTP
    stream. The previous implementation touched ``resp.apparent_encoding``
    after ``stream=True`` + ``iter_content`` had consumed the body, which made
    requests raise ``RuntimeError("The content for this response was already
    consumed")`` on every fetch (2026-09-12 fix).
    """
    if not body:
        return ""
    sample = body[: 512 * 1024]  # detection is reliable on the head of the body
    try:
        import charset_normalizer  # ships with requests >= 2.26

        best = charset_normalizer.from_bytes(sample).best()
        if best is not None and getattr(best, "encoding", None):
            return str(best.encoding).strip().lower()
    except Exception:  # noqa: BLE001 — fall through to chardet / utf-8
        pass
    try:
        import chardet  # optional fallback

        guess = chardet.detect(sample) or {}
        enc = str(guess.get("encoding") or "").strip().lower()
        if enc:
            return enc
    except Exception:  # noqa: BLE001
        pass
    return ""


def _decode_body(body: bytes, content_type: str = "") -> str:
    """Decode a fully-read response body: header charset > sniffed charset > utf-8 > gbk.

    An explicitly declared header charset wins: charset sniffers are unreliable on
    short/ambiguous samples (a GBK page can be mis-detected as Big5 etc.).
    """
    candidates: List[str] = []
    header_charset = _charset_from_content_type(content_type)
    if header_charset:
        candidates.append(header_charset)
    sniffed = _detect_charset_bytes(body)
    if sniffed:
        candidates.append(sniffed)
    candidates += ["utf-8", "gbk"]
    seen: set = set()
    for enc in candidates:
        if not enc or enc in seen:
            continue
        seen.add(enc)
        try:
            return body.decode(enc, errors="strict")
        except (LookupError, UnicodeDecodeError):
            continue
    return body.decode("utf-8", errors="replace")


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
        resp.close()
        # decode from the bytes already read — never touch resp.content /
        # resp.apparent_encoding again: with stream=True the body stream is
        # consumed and requests raises RuntimeError("The content for this
        # response was already consumed") (2026-09-12 fix).
        text = _decode_body(body, resp.headers.get("Content-Type", ""))
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
                    "Fetches the body text of one or more URLs (HTML tags/scripts/styles stripped "
                    "automatically). Pass several URLs in \"urls\" and they are fetched "
                    "concurrently; every URL is collected before returning. "
                    "Built-in SSRF protection; only public http/https addresses allowed. "
                    "Overall concurrency is capped at 64, and at most 5 lanes per target domain "
                    "or resolved IP. Returns truncated plain text, suitable for reading online "
                    "docs, blogs, API responses, etc."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "The full URL to fetch. For several independent URLs prefer \"urls\" instead of calling the tool repeatedly."},
                        "urls": {"type": "array", "items": {"type": "string"}, "description": "Optional. Several URLs fetched CONCURRENTLY; all of them are collected before returning. Overall concurrency is capped at 64, and at most 5 lanes per target domain / resolved IP."},
                        "max_chars": {"type": "integer", "description": "Max characters to return (default 8000, range 500-50000)"},
                        "timeout": {"type": "integer", "description": "Request timeout in seconds (default 15, range 5-60)"},
                    },
                    "additionalProperties": False,
                },
            },
        }

    def run(self, args: Dict[str, Any], ctx: Any) -> ToolResult:
        raw = args.get("urls")
        targets: List[str] = []
        if isinstance(raw, (list, tuple)):
            for item in raw:
                candidate = _ensure_https(str(item or "").strip())
                if candidate and candidate != "https://" and candidate not in targets:
                    targets.append(candidate)
        single = _ensure_https(str(args.get("url") or "").strip())
        if single and single != "https://" and single not in targets:
            targets.insert(0, single)
        if not targets:
            return ToolResult(output="Please provide a URL to fetch.", success=False, error="missing_url")
        max_chars = max(500, min(int(args.get("max_chars") or 8000), 50000))
        timeout = max(5, min(int(args.get("timeout") or 15), 60))

        # 单个 URL：直接返回原有的单页版式（不引入并发与分组开销）。
        if len(targets) == 1:
            return self._fetch_one(targets[0], max_chars, timeout)

        # 多个 URL：自研 nasyncio 运行时并发抓取，整批全部收集完再返回。
        # 限流分组键按"解析后的 IP（取不到则退回主机名）"计算，使指向同一
        # 台机器的不同域名共享 5 路上限。
        jobs = []
        for idx, target in enumerate(targets):
            jobs.append((idx, _host_group(target),
                         (lambda u: (lambda: self._fetch_one(u, max_chars, timeout)))(target)))
        outcomes = _parallel_map(jobs, timeout=min(_COLLECT_TIMEOUT, max(timeout, 10) * 2))

        lines = ["[web fetch results]", "",
                 "URLs: %d (concurrent, all collected)" % len(targets), ""]
        ok_count = 0
        for idx, target in enumerate(targets):
            ok, value = outcomes.get(idx, (False, RuntimeError("missing outcome")))
            lines.append("=" * 60)
            if not ok:
                lines.append("URL: %s" % target)
                lines.append("failed: %s" % value)
                lines.append("")
                continue
            result = value
            if result.success:
                ok_count += 1
                lines.append(result.output)
            else:
                lines.append("URL: %s" % target)
                lines.append("failed: %s" % (result.error or "unknown"))
            lines.append("")
        lines.append("-" * 60)
        lines.append("summary: %d/%d fetched" % (ok_count, len(targets)))
        if ok_count == 0:
            return ToolResult(output="\n".join(lines).rstrip(), success=False,
                              error="all_failed")
        return ToolResult(output="\n".join(lines).rstrip())

    def _fetch_one(self, url: str, max_chars: int, timeout: int) -> ToolResult:
        """抓取并抽取单个 URL 的正文（单 URL 与多 URL 共用）。"""
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
    # 2026-09-12 round 9: DDG is the primary engine (free / no key), but it is
    # unreachable on some networks; Bing is used as an automatic fallback so the
    # web-search switch actually works wherever the user runs the agent.
    _BING_ENDPOINTS = ("https://cn.bing.com/search", "https://www.bing.com/search")

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": (
                    "Searches the web and returns result titles, links and snippets. "
                    "Pass several independent keyword sets in \"queries\" and they run "
                    "concurrently (the whole batch is collected before returning). "
                    "Engine is selectable: auto (default; Bing, then Baidu, then DuckDuckGo), "
                    "bing, baidu, duckduckgo, or custom (your own search endpoint, JSON API or "
                    "HTML page). Up to 50 results per keyword (automatic pagination). "
                    "Suitable for looking up the latest material, API docs, error messages, etc."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search keywords or a question. Two unrelated terms joined together often return an irrelevant generic page; short focused keywords work better, and 2-4 word queries are the sweet spot. For several independent topics prefer \"queries\" instead of joining them into one string."},
                        "queries": {"type": "array", "items": {"type": "string"}, "description": "Optional. Several independent keyword sets searched CONCURRENTLY; all of them are collected before returning. Overall concurrency is capped at 64, and at most 5 lanes per target domain / resolved IP. Use this instead of calling the tool repeatedly when you already have a list of topics to look up."},
                        "max_results": {"type": "integer", "description": "Max results to return (default 5, range 1-50; paginated automatically)"},
                        "timeout": {"type": "integer", "description": "Request timeout in seconds (default 15, range 5-60)"},
                        "engine": {
                            "type": "string",
                            "enum": list(_BUILTIN_ENGINES),
                            "description": "Search engine: auto (default) / duckduckgo / bing / baidu / custom",
                        },
                        "engine_url": {"type": "string", "description": "custom only: URL template, e.g. https://api.example.com/search?q={query}&offset={offset} (placeholders: {query} URL-encoded, {offset}, {page}, {count})"},
                        "engine_name": {"type": "string", "description": "custom only: display name for the engine"},
                        "engine_type": {"type": "string", "enum": ["json", "html"], "description": "custom only: response kind (default json)"},
                        "engine_results_path": {"type": "string", "description": "custom+json: dot path to the results array, e.g. web.results or data.items"},
                        "engine_title_field": {"type": "string", "description": "custom+json: field name/path for the title (default title)"},
                        "engine_url_field": {"type": "string", "description": "custom+json: field name/path for the link (default url)"},
                        "engine_snippet_field": {"type": "string", "description": "custom+json: field name/path for the snippet (default snippet)"},
                        "engine_headers": {"type": "object", "description": "custom only: extra HTTP headers (e.g. API key)"},
                        "engine_result_selector": {"type": "string", "description": "custom+html: CSS selector for each result block"},
                        "engine_title_selector": {"type": "string", "description": "custom+html: CSS selector for the title (inside a result block)"},
                        "engine_link_selector": {"type": "string", "description": "custom+html: CSS selector for the link"},
                        "engine_snippet_selector": {"type": "string", "description": "custom+html: CSS selector for the snippet"},
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
            },
        }

    def run(self, args: Dict[str, Any], ctx: Any) -> ToolResult:
        raw = args.get("queries")
        keywords: List[str] = []
        if isinstance(raw, (list, tuple)):
            for item in raw:
                text = str(item or "").strip()
                if text and text not in keywords:
                    keywords.append(text)
        single = str(args.get("query") or "").strip()
        if single and single not in keywords:
            keywords.insert(0, single)
        if not keywords:
            return ToolResult(output="Please provide search keywords.",
                              success=False, error="missing_query")

        engine = str(args.get("engine")
                     or os.environ.get("NORPAGENT_WEB_SEARCH_ENGINE")
                     or "auto").strip().lower()
        if engine not in _BUILTIN_ENGINES:
            return ToolResult(
                output=("unknown engine: %r; choose one of %s"
                        % (engine, ", ".join(_BUILTIN_ENGINES))),
                success=False, error="bad_engine")
        max_results = max(1, min(int(args.get("max_results") or 5), _MAX_RESULTS_CAP))
        timeout = max(5, min(int(args.get("timeout") or 15), 60))

        # 多个关键词 -> 自研 nasyncio 运行时并发；每个关键词各自跑完整条
        # 引擎回退链。整批**全部收集完**再返回。
        def _one(keyword: str) -> Tuple[List[Tuple[str, str, str]], str]:
            if engine == "custom":
                cfg = self._custom_config(args)
                if not cfg["url"]:
                    return [], "custom (no engine_url)"
                found = self._collect_pages(
                    lambda off, t: self._custom_page(cfg, keyword, off, t),
                    max_results, timeout)
                return found, "custom (%s)" % cfg["name"]
            if engine == "auto":
                found, label = self._search_chain(keyword, timeout)
                if found and len(found) < max_results:
                    found, label = self._paginate_auto(
                        keyword, found, label, max_results, timeout)
                return found, label
            found = self._collect_pages(
                lambda off, t: self._builtin_page(engine, keyword, off, t),
                max_results, timeout)
            return found, _ENGINE_LABELS.get(engine, engine)

        if engine == "custom" and not self._custom_config(args)["url"]:
            return ToolResult(
                output=("custom engine requires 'engine_url' (a URL template containing "
                        "{query}); see the tool schema for optional JSON/HTML mapping."),
                success=False, error="missing_engine_url")

        jobs = []
        for idx, keyword in enumerate(keywords):
            group = ("direct:" + keyword) if engine == "custom" else ""
            jobs.append((idx, group, (lambda kw: (lambda: _one(kw)))(keyword)))
        outcomes = _parallel_map(jobs, timeout=min(_COLLECT_TIMEOUT, max(timeout, 10) * 2))

        per_keyword: List[Tuple[str, List[Tuple[str, str, str]], str]] = []
        for idx, keyword in enumerate(keywords):
            ok, value = outcomes.get(idx, (False, RuntimeError("missing outcome")))
            if ok and value:
                found, label = value
                per_keyword.append((keyword, found or [], label))
            elif ok:
                per_keyword.append((keyword, [], ""))
            else:
                per_keyword.append((keyword, [], "error: %s" % type(value).__name__))

        if len(per_keyword) == 1:
            keyword, found, label = per_keyword[0]
            if not found:
                return ToolResult(
                    output=("search failed: no results returned (%s). "
                            "Retry later, pick another engine, or try different keywords."
                            % label),
                    success=False,
                    error="no_results",
                )
            lines = ["[search results]", "", f"keywords: {keyword}",
                     f"engine: {label}", f"results: {len(found)}", ""]
            for i, (title, href, snippet) in enumerate(found[:max_results], 1):
                lines.append(f"{i}. {title}")
                lines.append(f"   {href}")
                if snippet:
                    lines.append(f"   {snippet}")
                lines.append("")
            return ToolResult(output="\n".join(lines).rstrip())

        merged: List[Tuple[str, str, str]] = []
        for _keyword, found, _label in per_keyword:
            merged.extend(found)
        merged = _dedupe_by_url(merged)

        lines = ["[search results]",
                 "",
                 "keywords: %d (%s)" % (len(per_keyword),
                                        "concurrent, all collected"),
                 "engine: %s" % ("auto" if len({l for _k, _f, l in per_keyword}) > 1
                                 else (per_keyword[0][2] or "n/a")),
                 "results: %d after de-duplication" % len(merged),
                 ""]
        lines.append("per keyword:")
        for keyword, found, label in per_keyword:
            lines.append("  - %s -> %s (%d)" % (keyword, label or "no results", len(found)))
        lines.append("")
        lines.append("merged results:")
        lines.append("")
        for i, (title, href, snippet) in enumerate(merged[:max_results * len(per_keyword)], 1):
            lines.append(f"{i}. {title}")
            lines.append(f"   {href}")
            if snippet:
                lines.append(f"   {snippet}")
            lines.append("")
        return ToolResult(output="\n".join(lines).rstrip())

    def _search_chain(self, query: str,
                      timeout: int) -> Tuple[List[Tuple[str, str, str]], str]:
        """Single-query engine fallback chain. Returns (results, engine-label).

        顺序固定为 **Bing → Baidu → DuckDuckGo**（2026-09-19 起不再按查询
        语言分流）。处于冷却期的引擎直接跳过：否则被墙的网络会在每次搜索
        都白白烧掉一个完整的连接超时。

        结果与查询词完全无重叠时判为该引擎返回了无关页，继续尝试下一个。
        相关性判定只决定优先级、不构成否决：若所有引擎都只给出无字面重叠
        的结果，宁可返回其中第一份，也好过返回空。

        注意这里处理的是**一个**关键词的引擎回退；多个关键词之间的并发在
        run() 里由自研 nasyncio 运行时调度。
        """
        ddg_timeout = max(5, min(timeout, 6))

        def _try_bing():
            if _engine_on_cooldown("Bing"):
                return None
            attempted_b = False
            for endpoint in self._BING_ENDPOINTS:
                blocked, _reason = is_private_url(endpoint)
                if blocked:
                    continue
                attempted_b = True
                results = self._search_bing(endpoint, query, timeout)
                if results:
                    return results, "Bing"
            if attempted_b:
                _mark_engine_down("Bing")
            return None

        def _try_baidu():
            if _engine_on_cooldown("Baidu"):
                return None
            results = self._baidu_page(query, 0, timeout)
            if results:
                return results, "Baidu"
            return None

        def _try_duckduckgo():
            # Probe attempts are capped so a blocked network cannot stall the
            # chain; failures enter the cooldown cache.
            if _engine_on_cooldown("DuckDuckGo"):
                return None
            attempted = False
            for endpoint in (self._ENDPOINT, self._FALLBACK):
                blocked, _reason = is_private_url(endpoint)
                if blocked:
                    continue
                attempted = True
                results = self._search(endpoint, query, ddg_timeout)
                if results:
                    return results, "DuckDuckGo"
            if attempted:
                _mark_engine_down("DuckDuckGo")
            return None

        probes = (("Bing", _try_bing),
                  ("Baidu", _try_baidu),
                  ("DuckDuckGo", _try_duckduckgo))
        fallback: Optional[Tuple[List[Tuple[str, str, str]], str]] = None
        for name, probe in probes:
            got = probe()
            if not got:
                continue
            results, label = got
            if _results_relevant(results, query):
                return results, label
            if fallback is None:
                fallback = (results, label)
            # 不调用 _mark_engine_down：引擎确实应答了，只是结果不理想；
            # 冷却只留给"被封 / 连不上"这类真正的不可用。
        if fallback is not None:
            return fallback
        return [], ""

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
        if _looks_blocked(resp.text):
            _mark_engine_down("DuckDuckGo")
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
        body = resp.read(2 * 1024 * 1024).decode("utf-8", errors="replace")
        if _looks_blocked(body):
            _mark_engine_down("DuckDuckGo")
            return []
        return self._parse_results(body)

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


    # ── Bing fallback (2026-09-12 round 9) ─────────────────────

    def _search_bing(self, endpoint: str, query: str,
                     timeout: int) -> List[Tuple[str, str, str]]:
        """Fetch a Bing result page and parse it (fallback engine)."""
        try:
            if _requests_available():
                return self._search_bing_requests(endpoint, query, timeout)
            return self._search_bing_urllib(endpoint, query, timeout)
        except Exception:
            return []

    def _search_bing_requests(self, endpoint: str, query: str,
                              timeout: int) -> List[Tuple[str, str, str]]:
        import requests

        resp = requests.get(
            endpoint,
            params={"q": query},
            headers={"User-Agent": _USER_AGENT,
                     "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8"},
            timeout=timeout,
            allow_redirects=True,
        )
        if resp.status_code != 200:
            return []
        if _looks_blocked(resp.text):
            _mark_engine_down("Bing")
            return []
        return self._parse_bing(resp.text)

    def _search_bing_urllib(self, endpoint: str, query: str,
                            timeout: int) -> List[Tuple[str, str, str]]:
        from urllib.parse import urlencode
        from urllib.request import Request, urlopen

        req = Request(
            endpoint + "?" + urlencode({"q": query}),
            headers={"User-Agent": _USER_AGENT,
                     "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8"},
        )
        resp = urlopen(req, timeout=timeout)
        body = resp.read(3 * 1024 * 1024).decode("utf-8", errors="replace")
        if _looks_blocked(body):
            _mark_engine_down("Bing")
            return []
        return self._parse_bing(body)

    def _parse_bing(self, html: str) -> List[Tuple[str, str, str]]:
        results: List[Tuple[str, str, str]] = []
        for block in re.findall(r'<li class="b_algo".*?</li>', html, re.S | re.I):
            m = re.search(
                r'<h2[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                block, re.S | re.I,
            )
            if not m:
                continue
            href = unescape(m.group(1)).strip()
            title = " ".join(unescape(re.sub(r"<[^>]+>", " ", m.group(2))).split())
            if not href.startswith(("http://", "https://")):
                continue
            snippet = ""
            sm = re.search(r'<p[^>]*>(.*?)</p>', block, re.S | re.I)
            if sm:
                snippet = " ".join(unescape(re.sub(r"<[^>]+>", " ", sm.group(1))).split())
            results.append((title or href, href, snippet[:300]))
        return results

    # ── 引擎选择 / 翻页 / 自定义引擎（2026-09-14）──────────────

    @staticmethod
    def _norm_url(url: str) -> str:
        """去重键：忽略 scheme / www / 末尾斜杠 / fragment。"""
        try:
            p = urlparse(str(url))
            host = (p.netloc or "").lower()
            if host.startswith("www."):
                host = host[4:]
            path = (p.path or "").rstrip("/")
            return (host + path + "?" + p.query) if p.query else (host + path)
        except Exception:  # noqa: BLE001
            return str(url)

    def _collect_pages(self, fetch_page, target: int, timeout: int,
                       max_pages: int = _MAX_PAGES) -> List[Tuple[str, str, str]]:
        """按页抓取并按 URL 去重，直到凑够 target 条或该引擎不再有新结果。"""
        out: List[Tuple[str, str, str]] = []
        seen = set()
        offset = 0
        for _ in range(max(1, int(max_pages))):
            if len(out) >= target:
                break
            try:
                page = fetch_page(offset, timeout)
            except Exception:  # noqa: BLE001 — 单页失败不放弃整体
                break
            if not page:
                break
            fresh = 0
            for title, href, snippet in page:
                key = self._norm_url(href)
                if not key or key in seen:
                    continue
                seen.add(key)
                out.append((title, href, snippet))
                fresh += 1
            if fresh == 0:
                break
            offset += len(page)
        return out

    def _paginate_auto(self, query: str,
                       first: List[Tuple[str, str, str]], label: str,
                       target: int, timeout: int) -> Tuple[List[Tuple[str, str, str]], str]:
        """auto 模式翻页：沿用首个成功引擎继续取后续页。"""
        if "DuckDuckGo" in label:
            fetch_page = self._ddg_page
        elif "Bing" in label:
            fetch_page = self._bing_page
        else:
            return first, label
        out = list(first)
        seen = {self._norm_url(u) for _, u, _ in out}
        offset = len(out)
        for _ in range(_MAX_PAGES):
            if len(out) >= target:
                break
            try:
                page = fetch_page(query, offset, timeout)
            except Exception:  # noqa: BLE001
                break
            if not page:
                break
            fresh = 0
            for title, href, snippet in page:
                key = self._norm_url(href)
                if not key or key in seen:
                    continue
                seen.add(key)
                out.append((title, href, snippet))
                fresh += 1
            if fresh == 0:
                break
            offset += len(page)
        return out, label

    def _builtin_page(self, engine: str, query: str, offset: int,
                      timeout: int) -> List[Tuple[str, str, str]]:
        """内置引擎的分页取数（offset 为已取条数）。"""
        if engine == "duckduckgo":
            return self._ddg_page(query, offset, timeout)
        if engine == "bing":
            return self._bing_page(query, offset, timeout)
        if engine == "baidu":
            return self._baidu_page(query, offset, timeout)
        return []

    # -- DuckDuckGo（分页：表单参数 s / dc）--

    def _ddg_page(self, query: str, offset: int,
                  timeout: int) -> List[Tuple[str, str, str]]:
        endpoint = self._ENDPOINT
        blocked, _ = is_private_url(endpoint)
        if blocked:
            return []
        _throttle("DuckDuckGo")
        form = {"q": query, "s": str(offset), "dc": str(offset + 1)}
        try:
            if _requests_available():
                import requests
                resp = requests.post(
                    endpoint, data=form,
                    headers={"User-Agent": _USER_AGENT,
                             "Accept-Language": "en-US,en;q=0.9,zh;q=0.8"},
                    timeout=timeout, allow_redirects=True)
                if resp.status_code != 200:
                    return []
                return self._parse_results(resp.text)
            from urllib.parse import urlencode
            from urllib.request import Request, urlopen
            req = Request(endpoint, data=urlencode(form).encode("utf-8"),
                          headers={"User-Agent": _USER_AGENT,
                                   "Content-Type": "application/x-www-form-urlencoded",
                                   "Accept-Language": "en-US,en;q=0.9,zh;q=0.8"})
            resp = urlopen(req, timeout=timeout)
            return self._parse_results(
                resp.read(2 * 1024 * 1024).decode("utf-8", errors="replace"))
        except Exception:  # noqa: BLE001
            return []

    # -- Bing（分页：first=offset+1）--

    def _bing_page(self, query: str, offset: int,
                   timeout: int) -> List[Tuple[str, str, str]]:
        endpoints = self._BING_ENDPOINTS
        last: List[Tuple[str, str, str]] = []
        for endpoint in endpoints:
            blocked, _ = is_private_url(endpoint)
            if blocked:
                continue
            _throttle("Bing")
            params = {"q": query, "first": str(offset + 1)}
            try:
                if _requests_available():
                    import requests
                    resp = requests.get(
                        endpoint, params=params,
                        headers={"User-Agent": _USER_AGENT,
                                 "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8"},
                        timeout=timeout, allow_redirects=True)
                    if resp.status_code == 200:
                        last = self._parse_bing(resp.text)
                else:
                    from urllib.parse import urlencode
                    from urllib.request import Request, urlopen
                    req = Request(endpoint + "?" + urlencode(params),
                                  headers={"User-Agent": _USER_AGENT,
                                           "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8"})
                    resp = urlopen(req, timeout=timeout)
                    last = self._parse_bing(
                        resp.read(3 * 1024 * 1024).decode("utf-8", errors="replace"))
            except Exception:  # noqa: BLE001
                last = []
            if last:
                return last
        return last

    # -- Baidu（分页：pn=offset）--

    def _baidu_page(self, query: str, offset: int,
                    timeout: int) -> List[Tuple[str, str, str]]:
        endpoint = "https://www.baidu.com/s"
        blocked, _ = is_private_url(endpoint)
        if blocked:
            return []
        _throttle("Baidu")
        params = {"wd": query, "pn": str(offset)}
        try:
            if _requests_available():
                import requests
                resp = requests.get(
                    endpoint, params=params,
                    headers={"User-Agent": _USER_AGENT,
                             "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"},
                    timeout=timeout, allow_redirects=True)
                if resp.status_code != 200:
                    return []
                if _looks_blocked(resp.text):
                    _mark_engine_down("Baidu")
                    return []
                return self._parse_baidu(resp.text)
            from urllib.parse import urlencode
            from urllib.request import Request, urlopen
            req = Request(endpoint + "?" + urlencode(params),
                          headers={"User-Agent": _USER_AGENT,
                                   "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"})
            resp = urlopen(req, timeout=timeout)
            body = resp.read(3 * 1024 * 1024).decode("utf-8", errors="replace")
            if _looks_blocked(body):
                _mark_engine_down("Baidu")
                return []
            return self._parse_baidu(body)
        except Exception:  # noqa: BLE001
            return []

    def _parse_baidu(self, html: str) -> List[Tuple[str, str, str]]:
        results: List[Tuple[str, str, str]] = []
        for block in re.findall(r'<div[^>]+class="result[^"]*".*?(?=<div[^>]+class="result|<div id="page)',
                                html, re.S | re.I):
            m = re.search(r'<h3[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                          block, re.S | re.I)
            if not m:
                continue
            href = unescape(m.group(1)).strip()
            title = " ".join(unescape(re.sub(r"<[^>]+>", " ", m.group(2))).split())
            if not href.startswith(("http://", "https://")):
                continue
            snippet = ""
            sm = re.search(r'class="content-right[^"]*"[^>]*>(.*?)</span>', block, re.S | re.I)
            if sm:
                snippet = " ".join(unescape(re.sub(r"<[^>]+>", " ", sm.group(1))).split())
            results.append((title or href, href, snippet[:300]))
        return results

    # -- 自定义引擎 --

    def _custom_config(self, args: Dict[str, Any]) -> Dict[str, Any]:
        headers = args.get("engine_headers")
        return {
            "name": str(args.get("engine_name") or "custom"),
            "url": str(args.get("engine_url") or "").strip(),
            "type": str(args.get("engine_type") or "json").strip().lower(),
            "results_path": str(args.get("engine_results_path") or "").strip(),
            "title_field": str(args.get("engine_title_field") or "title").strip(),
            "url_field": str(args.get("engine_url_field") or "url").strip(),
            "snippet_field": str(args.get("engine_snippet_field") or "snippet").strip(),
            "headers": headers if isinstance(headers, dict) else {},
            "result_selector": str(args.get("engine_result_selector") or "").strip(),
            "title_selector": str(args.get("engine_title_selector") or "").strip(),
            "link_selector": str(args.get("engine_link_selector") or "").strip(),
            "snippet_selector": str(args.get("engine_snippet_selector") or "").strip(),
        }

    @staticmethod
    def _dig(obj: Any, path: str) -> Any:
        """按点路径取值（支持 a.b.0.c 与列表下标）。"""
        if not path:
            return obj
        cur = obj
        for part in str(path).split("."):
            if part == "":
                continue
            if isinstance(cur, dict):
                cur = cur.get(part)
            elif isinstance(cur, list):
                try:
                    cur = cur[int(part)]
                except Exception:  # noqa: BLE001
                    return None
            else:
                return None
            if cur is None:
                return None
        return cur

    def _render_url(self, template: str, query: str, offset: int) -> str:
        page = (offset // max(1, _PAGE_TARGET)) + 1
        try:
            return template.format(query=quote(query), offset=offset,
                                   page=page, count=_PAGE_TARGET)
        except Exception:  # noqa: BLE001 — 模板里出现未知占位符时退化为直接拼接
            sep = "&" if "?" in template else "?"
            return template + sep + "q=" + quote(query)

    def _custom_page(self, cfg: Dict[str, Any], query: str, offset: int,
                     timeout: int) -> List[Tuple[str, str, str]]:
        url = self._render_url(cfg["url"], query, offset)
        for key, value in list(cfg["headers"].items()):
            if isinstance(value, str) and "{query}" in value:
                cfg["headers"][key] = value.replace("{query}", quote(query))
        blocked, _reason = is_private_url(url)
        if blocked:
            return []
        headers = {"User-Agent": _USER_AGENT,
                   "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8"}
        headers.update({str(k): str(v) for k, v in cfg["headers"].items()})
        try:
            if _requests_available():
                import requests
                resp = requests.get(url, headers=headers, timeout=timeout,
                                    allow_redirects=True)
                if resp.status_code != 200:
                    return []
                body = resp.text
            else:
                from urllib.request import Request, urlopen
                resp = urlopen(Request(url, headers=headers), timeout=timeout)
                body = resp.read(4 * 1024 * 1024).decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            return []
        if cfg["type"] == "html":
            return self._parse_custom_html(cfg, body)
        return self._parse_custom_json(cfg, body)

    def _parse_custom_json(self, cfg: Dict[str, Any], body: str) -> List[Tuple[str, str, str]]:
        try:
            data = json.loads(body)
        except Exception:  # noqa: BLE001
            return []
        items = self._dig(data, cfg["results_path"])
        if items is None and isinstance(data, list):
            items = data
        if not isinstance(items, list):
            return []
        out: List[Tuple[str, str, str]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            href = str(self._dig(item, cfg["url_field"]) or "").strip()
            title = str(self._dig(item, cfg["title_field"]) or "").strip()
            snippet = str(self._dig(item, cfg["snippet_field"]) or "").strip()
            if not href.startswith(("http://", "https://")):
                continue
            out.append((title or href, href, " ".join(snippet.split())[:300]))
        return out

    def _parse_custom_html(self, cfg: Dict[str, Any], body: str) -> List[Tuple[str, str, str]]:
        if not cfg["result_selector"]:
            return []
        try:
            from bs4 import BeautifulSoup
        except Exception:  # noqa: BLE001 — 没装 bs4 时无法按选择器解析
            return []
        soup = BeautifulSoup(body, "html.parser")
        out: List[Tuple[str, str, str]] = []
        for block in soup.select(cfg["result_selector"]):
            link_el = block.select_one(cfg["link_selector"]) if cfg["link_selector"] else None
            if link_el is None:
                link_el = block.find("a")
            href = str((link_el.get("href") if link_el else "") or "").strip()
            if href and not href.startswith(("http://", "https://")):
                href = urljoin(cfg["url"], href)
            if not href.startswith(("http://", "https://")):
                continue
            title_el = block.select_one(cfg["title_selector"]) if cfg["title_selector"] else link_el
            title = " ".join((title_el.get_text(" ", strip=True) if title_el else "").split())
            snippet = ""
            if cfg["snippet_selector"]:
                sn_el = block.select_one(cfg["snippet_selector"])
                snippet = " ".join((sn_el.get_text(" ", strip=True) if sn_el else "").split())
            out.append((title or href, href, snippet[:300]))
        return out


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
