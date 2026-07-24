#!/usr/bin/env python3
"""Fetch public M3U playlists exposed by iptv.cqshushu.com.

This program intentionally has no dependency on rtp/b.py.  It writes only to
``cqshushu_txt`` and ``cqshushu_m3u`` at the repository root, so the two
updaters can be scheduled and run independently.

The website currently presents a JavaScript browser verification page to
non-browser clients.  This script does not bypass that control.  When it is
enabled, obtain a valid first-party session cookie in your browser and supply
it with CQS_COOKIE (recommended as a GitHub Actions secret).  The program
detects the verification page and exits with an actionable error instead of
silently producing empty playlists.
"""

from __future__ import annotations

import argparse
import html
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

import requests


SITE_URL = "https://iptv.cqshushu.com/index.php"
DEFAULT_PROVINCE = "sc"
DEFAULT_LIMIT = 10
REQUEST_TIMEOUT = 25
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
IP_RE = re.compile(r"(?<![\d.])(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}(?![\d.])")
M3U_URL_RE = re.compile(
    r"https?://[^\s'\"<>\\]+?(?:\.m3u8?(?:\?[^\s'\"<>\\]*)?|[?&][^\s'\"<>\\]*(?:m3u|playlist)[^\s'\"<>\\]*)",
    re.IGNORECASE,
)


class CqshushuError(RuntimeError):
    pass


@dataclass(frozen=True)
class Server:
    host: str
    detail_url: str


def text_only(fragment: str) -> str:
    return html.unescape(re.sub(r"<[^>]*>", "", fragment)).replace("\xa0", " ").strip()


def unique(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def is_challenge_page(page: str) -> bool:
    lower = page.lower()
    return "\u5b89\u5168\u9a8c\u8bc1" in page or "paer.js" in lower or "_js_challenge" in lower


def make_session(cookie: str) -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "zh-CN,zh;q=0.9"})
    if cookie:
        # Accept a full Cookie header so it can be copied verbatim to a secret.
        session.headers["Cookie"] = cookie.strip()
    return session


def get(session: requests.Session, url: str) -> requests.Response:
    response = session.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
    response.raise_for_status()
    if is_challenge_page(response.text):
        raise CqshushuError(
            "目标站点返回了 JavaScript 安全验证页。请在正常浏览器完成验证后，将该站点"
            "的 Cookie 整串保存为 CQS_COOKIE（GitHub Actions 请配置为 secret），再运行。"
        )
    return response


def list_url(province: str, limit: int) -> str:
    return f"{SITE_URL}?{urlencode({'t': 'all', 'province': province, 'limit': limit})}"


def extract_server_links(page: str, page_url: str) -> list[Server]:
    """Return only anchors whose visible text or URL contains an IPv4 address."""
    found: list[Server] = []
    for match in re.finditer(r"<a\b([^>]*)>(.*?)</a>", page, re.I | re.S):
        attrs, body = match.groups()
        href_match = re.search(r"\bhref\s*=\s*(['\"])(.*?)\1", attrs, re.I | re.S)
        if not href_match:
            continue
        href = html.unescape(href_match.group(2)).strip()
        visible = text_only(body)
        host_match = IP_RE.search(visible) or IP_RE.search(href)
        if not host_match:
            continue
        absolute = urljoin(page_url, href)
        if urlparse(absolute).netloc != urlparse(SITE_URL).netloc:
            continue
        found.append(Server(host_match.group(0), absolute))

    # Some releases use an onclick URL instead of an href.  Preserve this
    # fallback, but do not invent an endpoint: it only accepts same-site URLs.
    if not found:
        for url in re.findall(r"(?:location(?:\.href)?|window\.open)\s*\(\s*['\"]([^'\"]+)", page, re.I):
            absolute = urljoin(page_url, html.unescape(url))
            host_match = IP_RE.search(absolute)
            if host_match and urlparse(absolute).netloc == urlparse(SITE_URL).netloc:
                found.append(Server(host_match.group(0), absolute))

    result: list[Server] = []
    seen: set[str] = set()
    for item in found:
        if item.detail_url not in seen:
            seen.add(item.detail_url)
            result.append(item)
    return result


def extract_channel_page(page: str, page_url: str) -> str | None:
    for match in re.finditer(r"<a\b([^>]*)>(.*?)</a>", page, re.I | re.S):
        attrs, body = match.groups()
        if "\u67e5\u770b\u9891\u9053\u5217\u8868" not in text_only(body):
            continue
        href = re.search(r"\bhref\s*=\s*(['\"])(.*?)\1", attrs, re.I | re.S)
        if href:
            return urljoin(page_url, html.unescape(href.group(2)))
    # Be tolerant of a minor wording change, while preferring a link that
    # looks like a channel route.
    for href, body in re.findall(r"<a\b[^>]*href\s*=\s*['\"]([^'\"]+)['\"][^>]*>(.*?)</a>", page, re.I | re.S):
        if "\u9891\u9053" in text_only(body):
            return urljoin(page_url, html.unescape(href))
    return None


def extract_m3u_url(page: str, page_url: str) -> str | None:
    """Find the M3U interface in attributes, inline scripts, or copy buttons."""
    candidates: list[str] = []
    for match in re.finditer(r"<[^>]+>(.*?)</(?:a|button|span)>", page, re.I | re.S):
        if "m3u\u63a5\u53e3" not in text_only(match.group(1)).lower():
            continue
        tag_start = page.rfind("<", 0, match.start())
        tag = page[tag_start: page.find(">", tag_start) + 1]
        candidates.extend(re.findall(r"(?:href|data-(?:url|copy|m3u))\s*=\s*['\"]([^'\"]+)", tag, re.I))
    candidates.extend(M3U_URL_RE.findall(html.unescape(page)))
    for candidate in unique(html.unescape(x).replace("\\/", "/") for x in candidates):
        absolute = urljoin(page_url, candidate)
        if absolute.lower().startswith(("http://", "https://")):
            return absolute
    return None


def m3u_to_txt(content: str) -> list[str]:
    lines = [line.strip() for line in content.replace("\r", "").split("\n")]
    output: list[str] = []
    pending_name = ""
    for line in lines:
        if line.startswith("#EXTINF"):
            pending_name = line.rsplit(",", 1)[-1].strip() if "," in line else "频道"
        elif line and not line.startswith("#") and pending_name:
            output.append(f"{pending_name},{line}")
            pending_name = ""
    return unique(output)


def safe_stem(host: str, index: int) -> str:
    return f"{index:03d}_{host.replace(':', '_')}"


def write_playlist(m3u_dir: Path, txt_dir: Path, server: Server, index: int, m3u_url: str, content: str) -> int:
    stem = safe_stem(server.host, index)
    m3u_path = m3u_dir / f"{stem}.m3u"
    txt_path = txt_dir / f"{stem}.txt"
    m3u_path.write_text(content if content.endswith("\n") else content + "\n", encoding="utf-8")
    channel_lines = m3u_to_txt(content)
    if channel_lines:
        txt_path.write_text("\n".join(channel_lines) + "\n", encoding="utf-8")
    else:
        # Keep the interface URL visible if the provider temporarily returns a
        # non-standard playlist format; this is more useful than empty output.
        txt_path.write_text(f"M3U接口,{m3u_url}\n", encoding="utf-8")
    return len(channel_lines)


def clear_old_outputs(*directories: Path) -> None:
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
        for file in directory.glob("*"):
            if file.is_file() and file.suffix.lower() in {".m3u", ".m3u8", ".txt"}:
                file.unlink()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="抓取 iptv.cqshushu.com 的公开 M3U 接口。")
    parser.add_argument("--province", default=DEFAULT_PROVINCE, help="省份代码，四川为 sc（默认）。")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="列表页显示数量（默认 10）。")
    parser.add_argument("--max-servers", type=int, default=0, help="最多处理的 IP 数，0 表示全部。")
    parser.add_argument("--cookie", default=os.getenv("CQS_COOKIE", ""), help="站点 Cookie；也可设置 CQS_COOKIE。")
    parser.add_argument("--dry-run", action="store_true", help="只列出 IP 详情页，不下载 M3U。")
    parser.add_argument("--keep-old", action="store_true", help="不清空本脚本以往的独立输出目录。")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.limit < 1 or args.max_servers < 0:
        raise SystemExit("--limit 必须大于 0，--max-servers 不可为负数。")
    repo_root = Path(__file__).resolve().parent.parent
    m3u_dir, txt_dir = repo_root / "cqshushu_m3u", repo_root / "cqshushu_txt"
    if not args.keep_old and not args.dry_run:
        clear_old_outputs(m3u_dir, txt_dir)
    else:
        m3u_dir.mkdir(parents=True, exist_ok=True)
        txt_dir.mkdir(parents=True, exist_ok=True)

    session = make_session(args.cookie)
    source_url = list_url(args.province, args.limit)
    print(f"[*] 列表页：{source_url}")
    servers = extract_server_links(get(session, source_url).text, source_url)
    if args.max_servers:
        servers = servers[:args.max_servers]
    if not servers:
        raise CqshushuError("列表页未找到 IP 详情链接：页面结构可能已变更，或 Cookie 已失效。")
    print(f"[*] 找到 {len(servers)} 个 IP 详情页。")
    if args.dry_run:
        for item in servers:
            print(f"  {item.host}\t{item.detail_url}")
        return 0

    exported = channels = failures = 0
    for index, server in enumerate(servers, 1):
        try:
            detail = get(session, server.detail_url)
            channel_url = extract_channel_page(detail.text, detail.url)
            if not channel_url:
                raise CqshushuError("详情页没有“查看频道列表”链接")
            channel = get(session, channel_url)
            m3u_url = extract_m3u_url(channel.text, channel.url)
            if not m3u_url:
                raise CqshushuError("频道页没有找到 M3U 接口 URL")
            playlist = get(session, m3u_url)
            count = write_playlist(m3u_dir, txt_dir, server, index, m3u_url, playlist.text)
            exported += 1
            channels += count
            print(f"[+] {server.host}: {count} 个频道 -> {m3u_url}")
        except (requests.RequestException, CqshushuError) as exc:
            failures += 1
            print(f"[-] {server.host}: {exc}", file=sys.stderr)
        time.sleep(0.4)
    print(f"[*] 完成：成功 {exported} 个源，{channels} 个频道，失败 {failures} 个。")
    return 0 if exported else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CqshushuError as exc:
        print(f"[-] {exc}", file=sys.stderr)
        raise SystemExit(2)
