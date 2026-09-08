import requests
import os
import re
import time
import subprocess
import argparse
import hmac
import hashlib
import random
import string
from datetime import datetime, timedelta, timezone
from html import unescape
from urllib.parse import quote, urlencode, urlparse
try:
    from zoneinfo import ZoneInfo  # py3.9+
except Exception:  # pragma: no cover
    ZoneInfo = None

# ================= 配置区域 =================
# 1. 组播源网站配置（IPTV神器Pro）
IPTV_BASE_URL = "https://iptv.cqshushu.com/"
IPTV_INDEX = "index.php"
PAER_HMAC_KEY = "tdSQ4QZEaQPPff7e4wMReKjhnwXecJUxJTdAVDGIql9xR3fIAf"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# 2. GitHub 推送配置
# 提交说明前缀；为空时使用默认文案
GITHUB_COMMIT_PREFIX = "Auto update"
# ============================================
EPG_URL = "http://epg.51zmt.top:8000/e.xml.gz"
TVG_LOGO_BASE_URL = "https://gcore.jsdelivr.net/gh/taksssss/tv/icon/"
README_FILE = "README.md"
RAW_BASE_URL = "https://raw.githubusercontent.com/lsjiaowo/4K-IPTV-M3U/main"
PROXY_PREFIX = "https://gh-proxy.org/"

# 中国省份全称及简称对照表，用于智能嗅探
# 未指定筛选参数时使用的兼容默认省份。
PROVINCES = ["浙江", "安徽", "福建", "湖南", "广东", "四川", "山西", "湖北"]
CARRIERS = ("电信", "联通", "移动")

# 新站点省份筛选 code（与 iptv.cqshushu.com 下拉框一致）
PROVINCE_CODES = {
    "北京": "bj", "天津": "tj", "河北": "he", "山西": "sx", "内蒙古": "nm",
    "辽宁": "ln", "吉林": "jl", "黑龙江": "hl", "上海": "sh",
    "江苏": "js", "浙江": "zj", "安徽": "ah", "福建": "fj", "江西": "jx",
    "山东": "sd", "河南": "ha", "湖北": "hb", "湖南": "hn", "广东": "gd",
    "广西": "gx", "海南": "hi", "重庆": "cq", "四川": "sc", "贵州": "gz",
    "云南": "yn", "陕西": "sn", "甘肃": "gs", "青海": "qh", "宁夏": "nx",
    "新疆": "xj", "台湾": "tw", "俄罗斯": "ru", "韩国": "kr",
}


def get_root_domain(domain):
    """提取根域名，防 DDNS 假去重"""
    if re.match(r'^\d+\.\d+\.\d+\.\d+$', domain): return domain
    parts = domain.split('.')
    if len(parts) >= 3:
        if parts[-2] in ['com', 'net', 'org', 'gov', 'edu', 'gx'] or len(parts[-2]) <= 2:
            return ".".join(parts[-3:])
        else: return ".".join(parts[-2:])
    return domain

def check_and_clear_existing(txt_file, m3u_file):
    """不做测流，直接清空旧文件并重新导出。"""
    if not os.path.exists(txt_file):
        return False
    print(f"[*] 不做测流，清空旧文件后重新导出...")
    for file in [txt_file, m3u_file]:
        with open(file, 'w', encoding='utf-8') as f: f.write("")
    return False


def clear_output_files(txt_output_dir, m3u_output_dir):
    """运行前清理历史产物，避免旧命名文件残留。"""
    for out_dir, suffix in ((txt_output_dir, ".txt"), (m3u_output_dir, ".m3u")):
        if not os.path.exists(out_dir):
            continue
        for name in os.listdir(out_dir):
            if name.endswith(suffix):
                try:
                    os.remove(os.path.join(out_dir, name))
                except OSError:
                    pass


def clear_province_output_files(province, txt_output_dir, m3u_output_dir):
    """成功取得新结果后，清理该省全部旧源文件，避免遗留未选择的运营商。"""
    carrier_pattern = "|".join(re.escape(carrier) for carrier in ("电信", "联通", "移动", "广电"))
    stem_pattern = re.compile(
        rf"^{re.escape(province)}(?:(?:{carrier_pattern})\d*)?$"
    )
    removed = []
    for out_dir, suffix in ((txt_output_dir, ".txt"), (m3u_output_dir, ".m3u")):
        if not os.path.exists(out_dir):
            continue
        for name in os.listdir(out_dir):
            stem, ext = os.path.splitext(name)
            if ext.lower() != suffix or not stem_pattern.fullmatch(stem):
                continue
            os.remove(os.path.join(out_dir, name))
            removed.append(name)
    if removed:
        print(f"[*] [{province}] 已清理 {len(removed)} 个旧源文件（包括未选择运营商的遗留文件）。")
    return removed


def clear_unselected_carrier_files(province, carriers, txt_output_dir, m3u_output_dir):
    """清除本省未选择运营商的历史文件，保留所选运营商的上一版结果。"""
    allowed = set(carriers)
    carrier_pattern = "|".join(re.escape(carrier) for carrier in ("电信", "联通", "移动", "广电"))
    stem_pattern = re.compile(
        rf"^{re.escape(province)}(?P<carrier>{carrier_pattern})\d*$"
    )
    removed = []
    for out_dir, suffix in ((txt_output_dir, ".txt"), (m3u_output_dir, ".m3u")):
        if not os.path.exists(out_dir):
            continue
        for name in os.listdir(out_dir):
            stem, ext = os.path.splitext(name)
            match = stem_pattern.fullmatch(stem)
            if ext.lower() != suffix or not match or match.group("carrier") in allowed:
                continue
            os.remove(os.path.join(out_dir, name))
            removed.append(name)
    if removed:
        print(
            f"[*] [{province}] 已删除 {len(removed)} 个未选择运营商的历史文件；"
            f"本次仅允许：{','.join(carriers)}。"
        )
    return removed


def normalize_source_host(value: str) -> str:
    """统一服务器地址为小写的 host:port，便于识别新旧源。"""
    text = (value or "").strip()
    if not text:
        return ""
    parsed = urlparse(text if "://" in text else f"http://{text}")
    return parsed.netloc.lower().strip()


def load_previous_source_hosts(province, carriers, txt_output_dir):
    """从该省所选运营商的现有 TXT 列表中读取上一版服务器地址。"""
    result = {carrier: set() for carrier in carriers}
    if not os.path.exists(txt_output_dir):
        return result

    for carrier in carriers:
        stem_pattern = re.compile(
            rf"^{re.escape(province + carrier)}\d*\.txt$",
            flags=re.IGNORECASE,
        )
        for name in os.listdir(txt_output_dir):
            if not stem_pattern.fullmatch(name):
                continue
            path = os.path.join(txt_output_dir, name)
            try:
                with open(path, "r", encoding="utf-8") as file:
                    for line in file:
                        if "," not in line:
                            continue
                        play_url = line.split(",", 1)[1].strip()
                        host = normalize_source_host(play_url)
                        if host:
                            result[carrier].add(host)
            except OSError as exc:
                print(f"[!] [{province}{carrier}] 读取旧列表失败，跳过新旧比较: {exc}")

        if result[carrier]:
            print(
                f"[*] [{province}{carrier}] 从上一版列表识别到 "
                f"{len(result[carrier])} 个旧服务器地址，新候选将优先测速。"
            )
    return result

def _strip_html(raw):
    no_tags = re.sub(r"<[^>]+>", "", raw)
    return unescape(no_tags).replace("\xa0", " ").strip()


def _parse_site_datetime(value: str) -> datetime | None:
    s = (value or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def generate_paer_token() -> str:
    """生成 iptv.cqshushu.com 请求签名（X-CSRF-TOKEN）。"""
    ts = str(int(time.time()))
    rand = "".join(random.choices(string.ascii_lowercase + string.digits, k=20))
    msg = f"{ts}|{rand}"
    sig = hmac.new(PAER_HMAC_KEY.encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{ts}|{rand}|{sig}"


# 仅用于 429/503 等重试退避的基础时间。
REQUEST_DELAY_SEC = 0.8

# 每次成功请求后的随机间隔，避免短时间内请求过于密集。
REQUEST_DELAY_MIN_SEC = 2.0
REQUEST_DELAY_MAX_SEC = 4.0
REQUEST_MAX_RETRIES = 5


def signed_get(path_query: str, session: requests.Session | None = None) -> dict:
    """带签名的 GET 请求，返回 JSON（含 html 字段）。"""
    url = IPTV_BASE_URL + path_query.lstrip("/")
    sess = session or requests.Session()
    last_error = None

    for attempt in range(REQUEST_MAX_RETRIES):
        headers = {
            "User-Agent": USER_AGENT,
            "X-Requested-With": "XMLHttpRequest",
            "X-CSRF-TOKEN": generate_paer_token(),
        }
        try:
            resp = sess.get(url, headers=headers, timeout=30)
            if resp.status_code == 429:
                wait = min(30, REQUEST_DELAY_SEC * (2 ** attempt) * 3)
                print(f"[!] 请求过于频繁，{wait:.1f}s 后重试 ({attempt + 1}/{REQUEST_MAX_RETRIES})...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            time.sleep(
                random.uniform(
                    REQUEST_DELAY_MIN_SEC,
                    REQUEST_DELAY_MAX_SEC,
                )
            )
            return resp.json()
        except requests.HTTPError as e:
            last_error = e
            if e.response is not None and e.response.status_code in (429, 503):
                wait = min(30, REQUEST_DELAY_SEC * (2 ** attempt) * 3)
                print(f"[!] HTTP {e.response.status_code}，{wait:.1f}s 后重试 ({attempt + 1}/{REQUEST_MAX_RETRIES})...")
                time.sleep(wait)
                continue
            raise
        except requests.RequestException as e:
            last_error = e
            if attempt + 1 >= REQUEST_MAX_RETRIES:
                raise
            wait = REQUEST_DELAY_SEC * (2 ** attempt)
            print(f"[!] 网络异常，{wait:.1f}s 后重试 ({attempt + 1}/{REQUEST_MAX_RETRIES}): {e}")
            time.sleep(wait)

    if last_error:
        raise last_error
    raise RuntimeError(f"请求失败: {url}")


def _parse_list_rows(html: str) -> list[dict]:
    """从 IP 列表页 HTML 解析组播行。"""
    rows = []
    for row_html in re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.IGNORECASE | re.DOTALL):
        ip_match = re.search(
            r"gotoIP\('([^']+)',\s*'multicast'\)",
            row_html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not ip_match:
            continue
        tds = re.findall(r"<td[^>]*>(.*?)</td>", row_html, flags=re.IGNORECASE | re.DOTALL)
        if len(tds) < 6:
            continue
        rows.append({
            "p_token": ip_match.group(1).strip(),
            "host": _strip_html(tds[0]),
            "type": _strip_html(tds[2]),
            "online_time": _strip_html(tds[3]),
            "update_time": _strip_html(tds[4]),
            "status": _strip_html(tds[5]),
        })
    return rows


def fetch_region_rows_by_ajax(province, limit=20, max_pages=30, session=None):
    """按省份+组播类型分页抓取 IP 列表。"""
    region_code = PROVINCE_CODES.get(province)
    if not region_code:
        print(f"[-] 未找到省份 [{province}] 的 region code，跳过。")
        return []

    print(f"[*] 正在抓取组播源: {IPTV_BASE_URL}{IPTV_INDEX}?t=multicast&province={region_code}")
    all_rows = []
    seen_tokens = set()
    empty_page_hits = 0

    for page_num in range(1, max_pages + 1):
        query = urlencode({
            "t": "multicast",
            "province": region_code,
            "limit": limit,
            "page": page_num,
        })
        path = f"{IPTV_INDEX}?{query}"
        try:
            data = signed_get(path, session=session)
        except Exception as e:
            print(f"[-] 请求省份 [{province}] 第{page_num}页失败: {e}")
            break
        if data.get("status") != "success":
            msg = data.get("message", "unknown error")
            print(f"[-] 第{page_num}页返回失败: {msg}")
            break

        rows = _parse_list_rows(data.get("html", ""))
        if not rows:
            empty_page_hits += 1
            if empty_page_hits >= 2:
                break
            continue

        empty_page_hits = 0
        added = 0
        for row in rows:
            token = row.get("p_token")
            if not token or token in seen_tokens:
                continue
            seen_tokens.add(token)
            all_rows.append(row)
            added += 1
        print(f"[*] [{province}] 第{page_num}页 {len(rows)} 条，新增 {added} 条。")

    print(f"[*] [{province}] 全分页合计 {len(all_rows)} 条服务器。")
    return all_rows


def source_status_rank(status: str) -> int:
    """返回状态优先级：新上线 > 存活1天 > ... > 存活10天。"""
    normalized = re.sub(r"\s+", "", status or "")
    if "新上线" in normalized:
        return 11
    # 先匹配10，再匹配1至9，并使用完整匹配排除“存活11天”等状态。
    match = re.fullmatch(r"存活(10|[1-9])天", normalized)
    if not match:
        return 0
    return 11 - int(match.group(1))


def get_region_assets(province, rows=None):
    """按统一状态优先级提取服务器，最多返回前5条。"""
    rows = rows if rows is not None else fetch_region_rows_by_ajax(province)
    region_all = [r for r in rows if province in r.get("type", "")]
    if not region_all:
        print(f"[-] 未找到 [{province}] 地区服务器。")
        return [], []

    preferred = sorted(
        [
            r
            for r in region_all
            if source_status_rank(r.get("status", "")) > 0
        ],
        key=lambda r: source_status_rank(r.get("status", "")),
        reverse=True,
    )[:5]
    if not preferred:
        print(f"[-] [{province}] 当前没有新上线或存活1至10天的服务器，本次不提取。")
        return region_all, []
    return region_all, preferred

def parse_s_token(detail_html: str) -> str | None:
    """从 IP 详情页提取频道列表 s token。"""
    m = re.search(
        r"href=['\"]\?s=([^&'\"]+)&t=multicast['\"]",
        detail_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if m:
        return m.group(1)
    m = re.search(r'data-s="([^"]+)"', detail_html, flags=re.IGNORECASE | re.DOTALL)
    if m:
        return m.group(1)
    m = re.search(r'href="[^"]*[?&]s=([^"&]+)', detail_html, flags=re.IGNORECASE | re.DOTALL)
    if m:
        return m.group(1)
    return None


def fetch_detail_html(p_token: str, session: requests.Session | None = None) -> str:
    query = urlencode({"p": p_token, "t": "multicast"})
    path = f"{IPTV_INDEX}?{query}"
    data = signed_get(path, session=session)
    return data.get("html", "") or ""


def fetch_channel_lines_by_s(s_token: str, session: requests.Session | None = None, max_pages: int = 50) -> list[str]:
    """分页抓取完整频道列表。"""
    all_lines: list[str] = []
    seen: set[str] = set()
    empty_hits = 0

    for page_num in range(1, max_pages + 1):
        query = urlencode({"s": s_token, "t": "multicast", "page": page_num})
        path = f"{IPTV_INDEX}?{query}"
        try:
            data = signed_get(path, session=session)
        except Exception as e:
            print(f"[-] 频道列表第{page_num}页失败: {e}")
            break
        if data.get("status") != "success":
            break
        html = data.get("html", "")
        page_lines = parse_channel_lines(html)
        if not page_lines:
            empty_hits += 1
            if empty_hits >= 2:
                break
            continue
        empty_hits = 0
        for line in page_lines:
            if line in seen:
                continue
            seen.add(line)
            all_lines.append(line)

        print(
            f"[*] 正在抓取频道列表：第{page_num}页，"
            f"本页{len(page_lines)}条，累计{len(all_lines)}条"
        )

        if "下一页" not in html and page_num > 1:
            break
    return all_lines


def measure_stream_speed(
    play_url: str,
    sample_seconds: float = 3.0,
    connect_timeout: float = 5.0,
    read_timeout: float = 5.0,
) -> tuple[float, int]:
    """流式读取直播地址，返回平均下载速度（MB/s）和读取字节数。"""
    headers = {
        "User-Agent": "Mozilla/5.0 IPTV-Stream-Validator/1.0",
        "Accept": "*/*",
        "Connection": "close",
    }
    total_bytes = 0
    first_byte_at = None

    with requests.get(
        play_url,
        headers=headers,
        stream=True,
        allow_redirects=True,
        timeout=(connect_timeout, read_timeout),
    ) as response:
        response.raise_for_status()
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            now = time.monotonic()
            if first_byte_at is None:
                first_byte_at = now
            total_bytes += len(chunk)
            if now - first_byte_at >= sample_seconds:
                break

    if first_byte_at is None or total_bytes == 0:
        return 0.0, 0

    elapsed = max(time.monotonic() - first_byte_at, 0.001)
    # 返回很快结束的小型错误页不能算直播流；至少持续读取1秒。
    if elapsed < min(max(sample_seconds, 0.1), 1.0):
        return 0.0, total_bytes
    speed_mb_s = total_bytes / elapsed / (1024 * 1024)
    return speed_mb_s, total_bytes


def is_source_playable(
    channel_lines: list[str],
    source_label: str,
    min_speed_mb_s: float = 750.0 / 1024.0,
    sample_seconds: float = 3.0,
    test_channels: int = 2,
) -> bool:
    """从 CCTV1 至 CCTV15 中排除标清/SD后随机抽测，任意一个通过即有效。"""
    candidates: list[tuple[str, str]] = []
    seen_urls: set[str] = set()
    cctv_pattern = re.compile(
        r"(?i)(?<![A-Z0-9])CCTV\s*[-_ ]?\s*(1[0-5]|[1-9])(?!\d|\+)"
    )

    for line in channel_lines:
        if "," not in line:
            continue
        channel_name, play_url = line.split(",", 1)
        channel_name = channel_name.strip()
        play_url = play_url.strip()
        if not cctv_pattern.search(channel_name):
            continue
        # 只排除明确标记为“标清”或“SD”的频道；普通、高清、HD名称均可抽测。
        if "标清" in channel_name or "SD" in channel_name.upper():
            continue
        if not play_url.lower().startswith(("http://", "https://")):
            continue
        if play_url in seen_urls:
            continue
        seen_urls.add(play_url)
        candidates.append((channel_name, play_url))

    required_count = max(1, test_channels)
    if len(candidates) < required_count:
        print(
            f"[-] [{source_label}] CCTV1-CCTV15 非标清可测试频道不足："
            f"{len(candidates)}/{required_count}，判定无效。"
        )
        return False

    sampled_channels = random.sample(candidates, required_count)
    passed_count = 0
    print(
        f"[*] [{source_label}] 从 {len(candidates)} 个 CCTV1-CCTV15 非标清频道中"
        f"随机抽测 {required_count} 个。"
    )

    for channel_name, play_url in sampled_channels:
        print(f"[*] [{source_label}] 测速频道：{channel_name} {play_url}")
        try:
            speed_mb_s, total_bytes = measure_stream_speed(
                play_url,
                sample_seconds=sample_seconds,
            )
        except requests.RequestException as exc:
            print(f"[-] [{source_label}] 测速失败：{exc}")
            continue

        print(
            f"[*] [{source_label}] 下载 {total_bytes / (1024 * 1024):.2f} MB，"
            f"平均速度 {speed_mb_s * 1024:.0f} KB/s，"
            f"要求 > {min_speed_mb_s * 1024:.0f} KB/s"
        )
        if speed_mb_s > min_speed_mb_s:
            passed_count += 1
            print(f"[+] [{source_label}] {channel_name} 测速通过。")
        else:
            print(f"[-] [{source_label}] {channel_name} 速度不足。")

    if passed_count >= 1:
        print(
            f"[+] [{source_label}] {passed_count}/{required_count} 个抽测频道通过，"
            "服务器判定有效。"
        )
        return True

    print(
        f"[-] [{source_label}] {passed_count}/{required_count} 个抽测频道通过，"
        "丢弃该服务器。"
    )
    return False


def parse_channel_lines(channels_html: str) -> list[str]:
    lines = []
    for row_html in re.findall(r"<tr[^>]*>(.*?)</tr>", channels_html, flags=re.IGNORECASE | re.DOTALL):
        tds = re.findall(r"<td[^>]*>(.*?)</td>", row_html, flags=re.IGNORECASE | re.DOTALL)
        if len(tds) < 3:
            continue
        name = _strip_html(tds[1])
        play_url = _strip_html(tds[2])
        if not name or not play_url:
            continue
        # 保留站点返回的完整播放地址（含服务器 IP:PORT），避免只剩组播段地址
        if not re.search(r"(https?://|rtp/|udp/|igmp/)", play_url, flags=re.IGNORECASE):
            continue
        lines.append(f"{name},{play_url}")
    return lines


def normalize_group_title(raw_type: str, province: str) -> str:
    """将站点 type 字段规范化为“省份+运营商”格式（如：江西电信）。"""
    text = (raw_type or "").strip()
    if not text:
        return province
    # 常见格式：江西上饶组播|江西电信，优先使用“|”后半段
    if "|" in text:
        right = text.split("|")[-1].strip()
        if right:
            return right
    # 兜底：统一裁剪为“省份+运营商”，去掉城市等中间信息
    carriers = ("电信", "联通", "移动", "广电")
    for carrier in carriers:
        if carrier in text:
            return f"{province}{carrier}"
    return province


def parse_operator_name(detail_html: str, province: str) -> str:
    """优先从详情页“运营商”字段提取文件名，如：湖北电信。"""
    carriers = ("电信", "联通", "移动", "广电")
    # 先在“运营商”附近做精确提取（兼容 th/td 或 div 结构）
    m = re.search(
        r"运营商[\s\S]{0,120}?(" + re.escape(provinc
