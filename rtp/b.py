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
import json
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
UPDATE_TIMES_FILE = ".github/iptv-update-times.json"
RAW_BASE_URL = "https://raw.githubusercontent.com/lsjiaowo/4K-IPTV-M3U/main"
PROXY_PREFIX = "https://gh-proxy.org/"

# 默认测速门槛；四川线路单独放宽。
DEFAULT_MIN_STREAM_SPEED_MB_S = 750.0 / 1024.0
PROVINCE_MIN_STREAM_SPEED_MB_S = {
    "四川": 100.0 / 1024.0,
}

# 中国省份全称及简称对照表，用于智能嗅探
# 未指定筛选参数时使用的兼容默认省份。
PROVINCES = ["浙江", "安徽", "福建", "湖南", "广东", "四川", "山西", "湖北"]
CARRIERS = ("电信", "联通", "移动")

# 每个运营商最多保留的完整可用播放列表数量。
TARGET_PLAYABLE_SOURCES_PER_CARRIER = 2


def resolve_min_stream_speed(province: str, cli_override: float | None = None) -> float:
    """返回当前省份测速门槛；显式命令行参数优先。"""
    if cli_override is not None:
        return cli_override
    return PROVINCE_MIN_STREAM_SPEED_MB_S.get(
        province, DEFAULT_MIN_STREAM_SPEED_MB_S
    )

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
    """检测历史文件但绝不预先清空；只有新列表成功生成后才覆盖对应文件。"""
    if os.path.exists(txt_file) or os.path.exists(m3u_file):
        print("[*] 检测到上一版列表；本次抓取成功后才覆盖对应文件，失败则原样保留。")
    return False



# 历史列表保护策略：不提供“运行前清空/删除旧源”的函数。
# 只有对应运营商本次成功生成新的有效列表后，才精确覆盖同名文件；
# 未抓到新源、请求/测速失败、未选择的运营商及未补足的源序号均保留上一版文件和原更新时间。

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


# 普通网络异常/非频道请求退避的基础时间。
REQUEST_DELAY_SEC = 0.8

# 频道列表：每次成功请求后随机等待 2～3 秒；IP详情页成功后不额外等待。
CHANNEL_DELAY_MIN_SEC = 2.0
CHANNEL_DELAY_MAX_SEC = 3.0

# 省份服务器列表第1～5页：每次成功请求后随机等待 5～10 秒。
REGION_LIST_DELAY_MIN_SEC = 5.0
REGION_LIST_DELAY_MAX_SEC = 10.0

# 省份服务器列表第1～5页：若请求发生连接/读取超时，随机冷却60～70秒后重试当前页。
REGION_LIST_TIMEOUT_COOLDOWN_MIN_SEC = 60.0
REGION_LIST_TIMEOUT_COOLDOWN_MAX_SEC = 70.0

# 省份服务器列表第1～5页：若触发 HTTP 429，优先遵守服务端 Retry-After；
# 若没有有效 Retry-After，则随机冷却60～70秒后重试当前页。
REGION_LIST_429_COOLDOWN_MIN_SEC = 60.0
REGION_LIST_429_COOLDOWN_MAX_SEC = 70.0

# 省份组播服务器列表固定只抓取前5页；每次成功请求后随机等待5～10秒。
# 第1～5页若发生连接/读取超时，仍按上面的60～70秒冷却策略重试当前页。
REGION_LIST_MAX_PAGES = 5

# 连续处理多个省份时，在进入下一个省份前随机冷却 10～15 秒。
PROVINCE_SWITCH_DELAY_MIN_SEC = 10.0
PROVINCE_SWITCH_DELAY_MAX_SEC = 15.0

REQUEST_MAX_RETRIES = 5

# 频道列表不设置专用“请求频繁”等待；仅保留普通网络异常重试。


def signed_get(
    path_query: str,
    session: requests.Session | None = None,
    request_kind: str = "default",
) -> dict:
    """带签名的 GET 请求，返回 JSON（含 html 字段）。

    request_kind:
      region  = 省份列表，成功后等待 5～10 秒
      detail  = IP详情，成功后不额外等待
      channel = 频道列表，每次成功请求后随机等待 2～3 秒；不设置专用限流长等待

    省份列表第1～5页若发生连接/读取超时：随机冷却60～70秒后重试同一页。
    省份列表第1～5页若触发 HTTP 429：优先遵守 Retry-After；否则随机冷却60～70秒后重试同一页。
    其他普通网络异常以及非省份列表的 HTTP 429/503 仍按 0.8 / 1.6 / 3.2 / 6.4 秒指数退避，最多5次请求。
    HTTP 请求自身 timeout 保持30秒。
    """
    url = IPTV_BASE_URL + path_query.lstrip("/")
    sess = session or requests.Session()
    last_error = None

    if request_kind == "default":
        if "province=" in path_query:
            request_kind = "region"
        elif re.search(r"(?:[?&])s=", path_query):
            request_kind = "channel"
        else:
            request_kind = "detail"

    is_region_list = request_kind == "region"

    for attempt in range(REQUEST_MAX_RETRIES):
        headers = {
            "User-Agent": USER_AGENT,
            "X-Requested-With": "XMLHttpRequest",
            "X-CSRF-TOKEN": generate_paer_token(),
        }
        try:
            resp = sess.get(url, headers=headers, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            # 频道接口若直接返回“请求频繁”，不做60～360秒专用等待，直接结束本次请求。
            if request_kind == "channel":
                message = str(data.get("message", "") or "")
                status = str(data.get("status", "") or "").lower()
                if status != "success" and ("频繁" in message or "too many" in message.lower()):
                    raise RuntimeError(f"频道列表请求频繁: {message or '请求频繁'}")

            if is_region_list:
                time.sleep(random.uniform(
                    REGION_LIST_DELAY_MIN_SEC,
                    REGION_LIST_DELAY_MAX_SEC,
                ))
            elif request_kind == "channel":
                time.sleep(random.uniform(
                    CHANNEL_DELAY_MIN_SEC,
                    CHANNEL_DELAY_MAX_SEC,
                ))
            return data

        except requests.HTTPError as e:
            last_error = e
            status_code = e.response.status_code if e.response is not None else None
            region_page_match = re.search(r"(?:[?&])page=(\d+)", path_query)
            region_page_num = int(region_page_match.group(1)) if region_page_match else 0

            # 省份服务器列表第1～5页若触发 HTTP 429，不再进行0.8/1.6/3.2/6.4秒短重试。
            # 优先遵守服务端 Retry-After；没有有效值时随机冷却60～70秒，然后重试当前页。
            if status_code == 429 and is_region_list and 1 <= region_page_num <= REGION_LIST_MAX_PAGES:
                if attempt + 1 >= REQUEST_MAX_RETRIES:
                    raise

                retry_after_raw = (e.response.headers.get("Retry-After", "") or "").strip()
                retry_after_seconds = None
                if retry_after_raw:
                    try:
                        retry_after_seconds = max(0.0, float(retry_after_raw))
                    except ValueError:
                        try:
                            from email.utils import parsedate_to_datetime
                            retry_dt = parsedate_to_datetime(retry_after_raw)
                            if retry_dt.tzinfo is None:
                                retry_dt = retry_dt.replace(tzinfo=timezone.utc)
                            retry_after_seconds = max(
                                0.0,
                                (retry_dt - datetime.now(timezone.utc)).total_seconds(),
                            )
                        except Exception:
                            retry_after_seconds = None

                if retry_after_seconds is not None:
                    wait = retry_after_seconds
                    wait_source = f"按服务器 Retry-After={retry_after_raw}"
                else:
                    wait = random.uniform(
                        REGION_LIST_429_COOLDOWN_MIN_SEC,
                        REGION_LIST_429_COOLDOWN_MAX_SEC,
                    )
                    wait_source = "未提供有效 Retry-After，随机长冷却"

                print(
                    f"[!] 省份服务器列表第{region_page_num}页触发 HTTP 429，"
                    f"{wait_source} {wait:.1f} 秒后重新抓取当前页 "
                    f"({attempt + 1}/{REQUEST_MAX_RETRIES})。"
                )
                time.sleep(wait)
                continue

            # 非省份列表的 HTTP 429/503 仍沿用普通短指数退避，避免改变频道/详情请求策略。
            if status_code in (429, 503):
                if attempt + 1 >= REQUEST_MAX_RETRIES:
                    raise
                wait = REQUEST_DELAY_SEC * (2 ** attempt)
                print(
                    f"[!] HTTP {status_code}，{wait:.1f}s 后重试 "
                    f"({attempt + 1}/{REQUEST_MAX_RETRIES})..."
                )
                time.sleep(wait)
                continue
            raise

        except requests.RequestException as e:
            last_error = e
            if attempt + 1 >= REQUEST_MAX_RETRIES:
                raise

            # 省份服务器列表第1～5页如果发生连接/读取超时，不使用0.8秒短退避；
            # 随机冷却60～70秒后重新请求当前页。页码从请求参数中识别。
            region_page_match = re.search(r"(?:[?&])page=(\d+)", path_query)
            region_page_num = int(region_page_match.group(1)) if region_page_match else 0
            if (
                is_region_list
                and 1 <= region_page_num <= 5
                and isinstance(e, requests.Timeout)
            ):
                wait = random.uniform(
                    REGION_LIST_TIMEOUT_COOLDOWN_MIN_SEC,
                    REGION_LIST_TIMEOUT_COOLDOWN_MAX_SEC,
                )
                print(
                    f"[!] 省份服务器列表第{region_page_num}页请求超时，"
                    f"随机冷却 {wait:.1f} 秒后重新抓取当前页 "
                    f"({attempt + 1}/{REQUEST_MAX_RETRIES}): {e}"
                )
                time.sleep(wait)
                continue

            wait = REQUEST_DELAY_SEC * (2 ** attempt)
            print(
                f"[!] 网络异常，{wait:.1f}s 后重试 "
                f"({attempt + 1}/{REQUEST_MAX_RETRIES}): {e}"
            )
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


def fetch_region_page_by_ajax(
    province: str,
    page_num: int,
    limit: int = 20,
    session: requests.Session | None = None,
) -> tuple[list[dict], bool]:
    """只抓取省份组播服务器列表的指定一页；返回(行列表, 请求是否成功)。"""
    region_code = PROVINCE_CODES.get(province)
    if not region_code:
        print(f"[-] 未找到省份 [{province}] 的 region code，跳过。")
        return [], False

    query = urlencode({
        "t": "multicast",
        "province": region_code,
        "limit": limit,
        "page": page_num,
    })
    path = f"{IPTV_INDEX}?{query}"

    # 省份服务器列表只允许请求第1～5页；正常成功间隔为5～10秒。
    # 连接/读取超时会随机冷却60～70秒后重试当前页；HTTP 429优先遵守
    # Retry-After，没有有效 Retry-After 时同样随机冷却60～70秒后重试当前页。
    try:
        data = signed_get(path, session=session, request_kind="region")
    except Exception as exc:
        print(f"[-] 请求省份 [{province}] 第{page_num}页失败: {exc}")
        return [], False

    if data.get("status") != "success":
        msg = data.get("message", "unknown error")
        print(f"[-] [{province}] 第{page_num}页返回失败: {msg}")
        return [], False

    rows = _parse_list_rows(data.get("html", ""))
    return rows, True


def fetch_region_rows_by_ajax(province, limit=20, max_pages=10, session=None):
    """兼容旧调用：按省份分页抓取服务器列表，最多抓到 max_pages 页。"""
    region_code = PROVINCE_CODES.get(province)
    if not region_code:
        print(f"[-] 未找到省份 [{province}] 的 region code，跳过。")
        return []

    print(f"[*] 正在抓取组播源: {IPTV_BASE_URL}{IPTV_INDEX}?t=multicast&province={region_code}")
    all_rows: list[dict] = []
    seen_tokens: set[str] = set()
    empty_page_hits = 0

    for page_num in range(1, max_pages + 1):
        rows, ok = fetch_region_page_by_ajax(
            province,
            page_num,
            limit=limit,
            session=session,
        )
        if not ok:
            break

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
    """按统一状态优先级提取服务器，最多返回前20条。"""
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
    )[:20]
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
    data = signed_get(path, session=session, request_kind="detail")
    return data.get("html", "") or ""


def extract_speed_test_candidates(channel_lines: list[str]) -> list[tuple[str, str]]:
    """提取CCTV1-CCTV15中不含标清/SD的HTTP测速频道，并按URL去重。"""
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
        if "标清" in channel_name or "SD" in channel_name.upper():
            continue
        if not play_url.lower().startswith(("http://", "https://")):
            continue
        if play_url in seen_urls:
            continue
        seen_urls.add(play_url)
        candidates.append((channel_name, play_url))
    return candidates


def fetch_channel_lines_by_s(
    s_token: str,
    session: requests.Session | None = None,
    max_pages: int = 20,
    stop_after_test_channels: int = 0,
    initial_lines: list[str] | None = None,
    start_page: int = 1,
    page_state: dict | None = None,
) -> list[str]:
    """分页抓取频道；支持从测速阶段的结果和下一页继续抓取。"""
    all_lines: list[str] = list(initial_lines or [])
    seen: set[str] = set(all_lines)
    empty_hits = 0
    for page_num in range(max(1, start_page), max_pages + 1):
        query = urlencode({"s": s_token, "t": "multicast", "page": page_num})
        path = f"{IPTV_INDEX}?{query}"
        try:
            data = signed_get(path, session=session, request_kind="channel")
        except Exception as e:
            print(f"[-] 频道列表第{page_num}页失败: {e}")
            break
        if data.get("status") != "success":
            msg = data.get("message", "unknown error")
            print(f"[-] 频道列表第{page_num}页返回失败: {msg}")
            break
        html = data.get("html", "")
        page_lines = parse_channel_lines(html)
        if page_state is not None:
            page_state["last_page"] = page_num
            page_state["has_next"] = "下一页" in html
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

        if stop_after_test_channels > 0:
            test_count = len(extract_speed_test_candidates(all_lines))
            if test_count >= stop_after_test_channels:
                print(
                    f"[*] 已找到 {test_count} 个 CCTV1-CCTV15 非标清测速频道，"
                    "暂停抓取完整列表并立即测速。"
                )
                break
        if "下一页" not in html:
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
    min_speed_mb_s: float = DEFAULT_MIN_STREAM_SPEED_MB_S,
    sample_seconds: float = 3.0,
    test_channels: int = 2,
) -> bool:
    """从 CCTV1 至 CCTV15 中排除标清/SD后随机抽测，任意一个通过即有效。"""
    candidates = extract_speed_test_candidates(channel_lines)
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
            print(
                f"[+] [{source_label}] 已有1个抽测频道通过，"
                "立即停止其余频道测速。"
            )
            return True
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
        r"运营商[\s\S]{0,120}?(" + re.escape(province) + r"(?:电信|联通|移动|广电))",
        detail_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if m:
        value = _strip_html(m.group(1))
        if value:
            return value
    # 次级匹配：不限定“运营商”字样，直接在详情中找“省份+运营商”
    m = re.search(
        r"(" + re.escape(province) + r"(?:电信|联通|移动|广电))",
        detail_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if m:
        value = _strip_html(m.group(1))
        if value:
            return value
    # 最后兜底：匹配任意运营商后缀
    for carrier in carriers:
        if carrier in detail_html:
            return f"{province}{carrier}"
    return province

def fetch_channel_lines_by_province(
    province: str,
    carriers: tuple[str, ...] = CARRIERS,
    max_per_carrier: int = 20,
    max_pages: int = 5,
    max_age_hours: int = 24,
    min_stream_speed_mb_s: float = DEFAULT_MIN_STREAM_SPEED_MB_S,
    stream_test_seconds: float = 3.0,
    test_channels_per_source: int = 2,
    previous_hosts_by_carrier: dict[str, set[str]] | None = None,
):
    """
    前5页扫描 + 提前测速：

    1. 省份组播服务器列表固定只抓取第1～5页。
    2. 前5页扫描完成后，优先测试新IP，直到达到2个可用源、候选池耗尽，
       或达到每运营商20台候选测试上限。
    3. 前5页的新IP仍不足目标时，直接使用这5页中的旧IP兜底；不再请求第6页及以后。
    4. 每个运营商找到 TARGET_PLAYABLE_SOURCES_PER_CARRIER 个可用播放列表后立即停止。
    """
    session = requests.Session()
    max_pages = min(max(1, int(max_pages)), REGION_LIST_MAX_PAGES)
    now_dt = datetime.now()

    region_code = PROVINCE_CODES.get(province)
    if not region_code:
        print(f"[-] 未找到省份 [{province}] 的 region code，跳过。")
        return [], "list_empty", province

    print(
        f"[*] [{province}] 省份服务器列表固定只扫描前{max_pages}页；"
        "扫描完成后优先测试新IP，不足目标时仅使用前5页旧IP兜底。"
    )

    all_rows: list[dict] = []
    seen_region_tokens: set[str] = set()
    empty_page_hits = 0

    group_to_sources: dict[str, list[list[str]]] = {}
    selected_ops: list[str] = []
    playable_counts = {carrier: 0 for carrier in carriers}
    tested_counts = {carrier: 0 for carrier in carriers}
    tested_tokens_by_carrier = {carrier: set() for carrier in carriers}

    def _is_usable_status(status: str) -> bool:
        return source_status_rank(status) > 0

    def _is_recent_update(row: dict) -> bool:
        dt = _parse_site_datetime(row.get("update_time", ""))
        if not dt:
            dt = _parse_site_datetime(row.get("online_time", ""))
        if not dt:
            return False
        age_hours = (now_dt - dt).total_seconds() / 3600
        return age_hours <= max_age_hours

    def _sort_key(row: dict):
        dt = (
            _parse_site_datetime(row.get("update_time", ""))
            or _parse_site_datetime(row.get("online_time", ""))
        )
        ts = dt.timestamp() if dt else 0.0
        return (source_status_rank(row.get("status", "")), ts)

    def _candidate_groups(carrier: str) -> tuple[list[dict], list[dict]]:
        """返回当前已扫描页面中的(新IP候选, 旧IP候选)，组内按状态和时间排序。"""
        carrier_rows = [
            row
            for row in all_rows
            if carrier in row.get("type", "")
            and _is_usable_status(row.get("status", ""))
            and _is_recent_update(row)
        ]
        carrier_rows.sort(key=_sort_key, reverse=True)

        previous_hosts = (previous_hosts_by_carrier or {}).get(carrier, set())
        new_rows = [
            row
            for row in carrier_rows
            if normalize_source_host(row.get("host", "")) not in previous_hosts
        ]
        old_rows = [
            row
            for row in carrier_rows
            if normalize_source_host(row.get("host", "")) in previous_hosts
        ]
        return new_rows, old_rows

    def _targets_complete() -> bool:
        return all(
            playable_counts.get(carrier, 0) >= TARGET_PLAYABLE_SOURCES_PER_CARRIER
            for carrier in carriers
        )

    def _test_one_candidate(carrier: str, picked: dict) -> bool:
        """测试一个候选；成功写入 group_to_sources。返回是否通过。"""
        token = picked.get("p_token")
        if not token:
            return False
        if token in tested_tokens_by_carrier[carrier]:
            return False
        if tested_counts.get(carrier, 0) >= max_per_carrier:
            return False
        if playable_counts.get(carrier, 0) >= TARGET_PLAYABLE_SOURCES_PER_CARRIER:
            return False

        tested_tokens_by_carrier[carrier].add(token)
        tested_counts[carrier] = tested_counts.get(carrier, 0) + 1

        candidate_started_at = datetime.now()
        candidate_started_clock = time.monotonic()
        candidate_host = picked.get("host", "")
        candidate_status = str(picked.get("status", "") or "").strip() or "状态未知"
        group_title = f"{province}{carrier}"

        print(
            f"[*] [{province}] 候选开始：{picked.get('type', '')} {candidate_host}；"
            f"时间={candidate_started_at.strftime('%Y-%m-%d %H:%M:%S')}；"
            f"测试序号={tested_counts[carrier]}/{max_per_carrier}"
        )

        try:
            print(f"[*] [{group_title} {candidate_host}] 开始获取IP详情页【{candidate_status}】。")
            try:
                detail_html = fetch_detail_html(token, session=session)
            except Exception as exc:
                print(f"[-] [{group_title} {candidate_host}] IP详情获取失败，未进入测速阶段: {exc}")
                return False

            if not detail_html:
                print(f"[-] [{group_title} {candidate_host}] IP详情为空，未进入测速阶段。")
                return False

            print(f"[+] [{group_title} {candidate_host}] IP详情页获取成功，HTML长度={len(detail_html)}。")
            s_token = parse_s_token(detail_html)
            if not s_token:
                print(
                    f"[-] [{group_title} {candidate_host}] IP详情页中未找到频道列表 s_token，"
                    "未进入测速阶段。"
                )
                return False

            token_preview = s_token if len(s_token) <= 16 else s_token[:8] + "..." + s_token[-4:]
            print(f"[+] [{group_title} {candidate_host}] s_token解析成功：{token_preview}")
            print(f"[*] [{group_title} {candidate_host}] 开始抓取测速频道。")

            # 第一阶段：只抓到足够测速的 CCTV 频道，立即测速。
            page_state: dict = {}
            test_lines = fetch_channel_lines_by_s(
                s_token,
                session=session,
                stop_after_test_channels=max(1, test_channels_per_source),
                page_state=page_state,
            )
            if not test_lines:
                print(
                    f"[-] [{group_title} {candidate_host}] 频道列表未解析到任何频道，"
                    "未进入测速阶段。"
                )
                return False

            speed_candidates = extract_speed_test_candidates(test_lines)
            if len(speed_candidates) < max(1, test_channels_per_source):
                print(
                    f"[-] [{group_title} {candidate_host}] 已解析 {len(test_lines)} 条频道，"
                    f"但仅找到 {len(speed_candidates)} 个 CCTV1-CCTV15 非标清HTTP测速频道，"
                    f"少于要求的 {max(1, test_channels_per_source)} 个，无法进入有效测速。"
                )

            source_label = f"{group_title} {candidate_host}".strip()
            if not is_source_playable(
                test_lines,
                source_label=source_label,
                min_speed_mb_s=min_stream_speed_mb_s,
                sample_seconds=stream_test_seconds,
                test_channels=test_channels_per_source,
            ):
                return False

            # 第二阶段：测速通过后才继续抓完整频道列表。
            last_page = int(page_state.get("last_page", 0))
            has_next = bool(page_state.get("has_next", False))
            print(
                f"[+] [{source_label}] 测速通过【{candidate_status}】，"
                f"复用前{last_page}页的 {len(test_lines)} 条频道，"
                f"从第{last_page + 1}页继续完整抓取。"
            )

            if has_next:
                lines = fetch_channel_lines_by_s(
                    s_token,
                    session=session,
                    initial_lines=test_lines,
                    start_page=last_page + 1,
                )
            else:
                lines = test_lines

            if not lines:
                print(f"[-] [{source_label}] 完整频道列表抓取失败，跳过该源。")
                return False

            selected_ops.append(group_title)
            group_to_sources.setdefault(group_title, []).append(lines)
            playable_counts[carrier] = playable_counts.get(carrier, 0) + 1

            print(
                f"[+] [{province}{carrier}] 可用源：{candidate_host}【{candidate_status}】；"
                f"已获得 {playable_counts[carrier]}/{TARGET_PLAYABLE_SOURCES_PER_CARRIER} "
                f"个可用播放列表（已测试 {tested_counts[carrier]}/{max_per_carrier} 台）。"
            )
            return True
        finally:
            candidate_finished_at = datetime.now()
            candidate_elapsed = time.monotonic() - candidate_started_clock
            print(
                f"[*] [{province}] 候选结束：{picked.get('type', '')} {candidate_host}；"
                f"时间={candidate_finished_at.strftime('%Y-%m-%d %H:%M:%S')}；"
                f"耗时={candidate_elapsed:.1f}秒"
            )

    def _test_available_candidates(allow_old: bool) -> None:
        """
        测试当前已扫描页面中的未测试候选。
        新IP永远排在旧IP之前；allow_old=False 时完全不碰旧IP。
        """
        for carrier in carriers:
            if playable_counts.get(carrier, 0) >= TARGET_PLAYABLE_SOURCES_PER_CARRIER:
                continue
            if tested_counts.get(carrier, 0) >= max_per_carrier:
                continue

            new_rows, old_rows = _candidate_groups(carrier)
            untested_new = [
                row for row in new_rows
                if row.get("p_token") not in tested_tokens_by_carrier[carrier]
            ]
            untested_old = [
                row for row in old_rows
                if row.get("p_token") not in tested_tokens_by_carrier[carrier]
            ]

            # 完整打印当前筛选后的候选池，便于Action日志直接核对新/旧IP。
            new_hosts = [row.get("host", "") for row in untested_new if row.get("host", "")]
            old_hosts = [row.get("host", "") for row in untested_old if row.get("host", "")]
            print(
                f"[*] [{province}{carrier}] 新IP候选：["
                + ", ".join(new_hosts)
                + "] / 旧IP候选：["
                + ", ".join(old_hosts)
                + "]"
            )

            print(
                f"[*] [{province}{carrier}] 当前候选："
                f"新IP未测试 {len(untested_new)} 条，"
                f"旧IP未测试 {len(untested_old)} 条；"
                f"{'允许旧IP兜底' if allow_old else '仅测试新IP'}。"
            )

            candidates = untested_new + (untested_old if allow_old else [])
            for picked in candidates:
                if playable_counts.get(carrier, 0) >= TARGET_PLAYABLE_SOURCES_PER_CARRIER:
                    break
                if tested_counts.get(carrier, 0) >= max_per_carrier:
                    break
                _test_one_candidate(carrier, picked)

    def _append_page_rows(page_num: int, page_rows: list[dict]) -> int:
        added = 0
        for row in page_rows:
            token = row.get("p_token")
            if not token or token in seen_region_tokens:
                continue
            seen_region_tokens.add(token)
            all_rows.append(row)
            added += 1
        print(
            f"[*] [{province}] 第{page_num}页 {len(page_rows)} 条，"
            f"新增 {added} 条；当前累计 {len(all_rows)} 条服务器。"
        )
        return added

    # ------------------------------------------------------------
    # 省份服务器列表固定只扫描第1～5页。
    # 扫描结束后先测试新IP；若仍不足目标，再仅使用这5页中的旧IP兜底。
    # 不请求第6页及以后。
    # ------------------------------------------------------------
    last_scanned_page = 0
    for page_num in range(1, max_pages + 1):
        page_rows, ok = fetch_region_page_by_ajax(
            province,
            page_num,
            limit=20,
            session=session,
        )
        if not ok:
            break

        last_scanned_page = page_num
        if not page_rows:
            empty_page_hits += 1
            if empty_page_hits >= 2:
                print(f"[*] [{province}] 连续2个空页，提前结束服务器列表扫描。")
                break
            continue

        empty_page_hits = 0
        _append_page_rows(page_num, page_rows)

    if not all_rows:
        return [], "list_empty", province

    print(
        f"[*] [{province}] 前{last_scanned_page}页扫描完成，"
        "立即筛选并测速新IP；省份服务器列表不再请求第6页及以后。"
    )
    _test_available_candidates(allow_old=False)

    if not _targets_complete():
        print(
            f"[*] [{province}] 已成功扫描的前{last_scanned_page}页中，新IP未满足目标，"
            f"现在仅使用这{last_scanned_page}页中的旧IP兜底；新IP仍保持最高优先级。"
        )
        _test_available_candidates(allow_old=True)
    else:
        print(
            f"[+] [{province}] 已成功扫描前{last_scanned_page}页并满足目标，"
            "省份服务器列表扫描结束。"
        )

    if not group_to_sources:
        return [], "no_playable_source", province

    for carrier in carriers:
        found = playable_counts.get(carrier, 0)
        tested = tested_counts.get(carrier, 0)
        if found >= TARGET_PLAYABLE_SOURCES_PER_CARRIER:
            print(
                f"[+] [{province}{carrier}] 已达到目标："
                f"{found}/{TARGET_PLAYABLE_SOURCES_PER_CARRIER} 个可用播放列表；"
                f"共测试 {tested}/{max_per_carrier} 台候选服务器。"
            )
        else:
            print(
                f"[!] [{province}{carrier}] 搜索结束："
                f"仅获得 {found}/{TARGET_PLAYABLE_SOURCES_PER_CARRIER} 个可用播放列表；"
                f"共测试 {tested}/{max_per_carrier} 台候选服务器。"
            )

    unique_ops = sorted(set(selected_ops))
    playable_source_count = sum(
        len(sources) for sources in group_to_sources.values()
    )
    print(
        f"[*] [{province}] 动态分页结束：实际扫描到第{last_scanned_page}页；"
        f"获得可用播放列表 {playable_source_count} 个；"
        f"状态=新上线/存活1至10天，更新时间<= {max_age_hours}小时；"
        f"来源: {', '.join(unique_ops)}"
    )
    return group_to_sources, "ok", province

def extract_test_targets(template_content, max_targets=5):
    """从模板中提取最多 N 个组播测试目标。"""
    matches = re.findall(
        r'(?:https?://[^/,]+/)?(udp|rtp|igmp)(?:/|://)(\d+\.\d+\.\d+\.\d+:\d+)',
        template_content,
        flags=re.IGNORECASE,
    )
    targets = []
    seen = set()
    for protocol, target in matches:
        protocol = protocol.lower()
        key = f"{protocol}://{target}"
        if key in seen:
            continue
        seen.add(key)
        targets.append((protocol, target))
        if len(targets) >= max_targets:
            break
    return targets


# 匹配越靠前的规则，导出时的排序优先级越高。
# 同一个元组中的关键词必须全部包含在频道名称中。
PRIORITY_CHANNEL_RULES = [
    ("凤凰", "中文"),
    ("凤凰", "资讯"),
    ("凤凰",),
    ("CCTV4K",),
    ("安徽经济",),
    ("安徽影视",),
    ("安徽公共",),
    ("安徽综艺",),
    ("安徽农业",),
    ("安徽国际",),
]


def sort_priority_channels(channel_lines: list[str]) -> list[str]:
    """将包含指定关键词的频道移到列表顶部。

    同一优先级内及未命中关键词的频道都保持原有相对顺序。
    """

    def priority_key(line: str) -> int:
        channel_name = line.split(",", 1)[0].strip().casefold()
        for index, required_keywords in enumerate(PRIORITY_CHANNEL_RULES):
            if all(
                keyword.casefold() in channel_name
                for keyword in required_keywords
            ):
                return index
        return len(PRIORITY_CHANNEL_RULES)

    return sorted(channel_lines, key=priority_key)

def build_tvg_logo_url(channel_name: str) -> str:
    safe_name = quote(channel_name.strip(), safe="")
    return f"{TVG_LOGO_BASE_URL}{safe_name}.png"

def txt_to_m3u_format(txt_content, group_title):
    """智能转换 M3U 分组格式"""
    m3u_lines = []
    for line in txt_content.splitlines():
        line = line.strip()
        if not line: continue
        if '#genre#' in line:
            continue
        elif ',' in line:
            name, url = [p.strip() for p in line.split(',', 1)]
            m3u_lines.append(
                f'#EXTINF:-1 tvg-id="{name}" tvg-logo="{build_tvg_logo_url(name)}" group-title="{group_title}",{name}\n{url}'
            )
    return "\n".join(m3u_lines)


def load_readme_update_times(repo_root: str) -> dict[str, str]:
    """读取当前 README 已显示的时间，用于首次启用独立时间记录时平滑迁移。"""
    readme_path = os.path.join(repo_root, README_FILE)
    try:
        with open(readme_path, "r", encoding="utf-8") as file:
            content = file.read()
    except OSError:
        return {}
    result = {}
    sections = (
        ("m3u", r"## M3U 文件列表([\s\S]*?)(?=\r?\n## TXT 文件列表)"),
        ("txt", r"## TXT 文件列表([\s\S]*?)(?=\r?\n---\r?\n\r?\n## 免责声明|\Z)"),
    )
    for subdir, pattern in sections:
        section_match = re.search(pattern, content)
        if not section_match:
            continue
        for row_html in re.findall(
            r"<tr[^>]*>([\s\S]*?)</tr>", section_match.group(1), flags=re.IGNORECASE
        ):
            cells = re.findall(
                r"<td[^>]*>([\s\S]*?)</td>", row_html, flags=re.IGNORECASE
            )
            if len(cells) < 3:
                continue
            name = _strip_html(cells[0])
            displayed_time = _strip_html(cells[2])
            if name and displayed_time:
                result[f"{subdir}/{name}"] = displayed_time
    return result


def load_file_update_times(repo_root: str) -> dict[str, str]:
    path = os.path.join(repo_root, UPDATE_TIMES_FILE)
    data = {}
    try:
        with open(path, "r", encoding="utf-8") as file:
            loaded = json.load(file)
        if isinstance(loaded, dict):
            data = loaded
    except (OSError, json.JSONDecodeError):
        pass
    # JSON 中缺失的旧文件继承 README 当前显示值，禁止重新计算并改乱时间。
    for key, value in load_readme_update_times(repo_root).items():
        data.setdefault(key, value)
    return data


def save_file_update_times(repo_root: str, update_times: dict[str, str]) -> None:
    path = os.path.join(repo_root, UPDATE_TIMES_FILE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # 自动移除已经不存在的列表记录。
    cleaned = {
        key: value
        for key, value in update_times.items()
        if os.path.exists(os.path.join(repo_root, *key.split("/")))
    }
    with open(path, "w", encoding="utf-8") as file:
        json.dump(cleaned, file, ensure_ascii=False, indent=2, sort_keys=True)
        file.write("\n")


def record_province_update_times(
    repo_root: str,
    province: str,
    generated_relative_paths: list[str],
) -> None:
    """仅更新本次实际覆盖写入的列表时间，未补足的旧源保持原时间。"""
    update_times = load_file_update_times(repo_root)
    updated_at = beijing_now().strftime("%Y-%m-%d %H:%M:%S")
    for relative_path in generated_relative_paths:
        update_times[relative_path.replace("\\", "/")] = updated_at
    save_file_update_times(repo_root, update_times)
    print(
        f"[+] [{province}] 已更新 {len(generated_relative_paths)} 个实际生成文件的时间："
        f"{updated_at}；未补足的旧源时间保持不变。"
    )


def get_git_file_update_time(repo_root: str, relative_path: str) -> str:
    """旧列表尚无时间记录时，使用该文件最后一次 Git 提交时间。"""
    try:
        result = subprocess.run(
            ["git", "-C", repo_root, "log", "-1", "--format=%cI", "--", relative_path],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
        value = result.stdout.strip()
        if result.returncode == 0 and value:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt.astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
    except (OSError, ValueError):
        pass
    return "历史时间未知"


def _build_readme_table_rows(
    repo_root: str,
    subdir: str,
    ext: str,
    update_times: dict[str, str],
) -> str:
    target_dir = os.path.join(repo_root, subdir)
    if not os.path.exists(target_dir):
        return '<tr><td colspan="4">暂无文件</td></tr>'
    names = sorted([n for n in os.listdir(target_dir) if n.endswith(ext)])
    if not names:
        return '<tr><td colspan="4">暂无文件</td></tr>'
    rows = []
    for name in names:
        relative_path = f"{subdir}/{name}"
        updated_at = update_times.get(relative_path) or get_git_file_update_time(
            repo_root, relative_path
        )
        # “加速链接”的 href 继续使用 gh-proxy + URL 编码后的文件名，保证浏览器兼容性；
        # “可复制直链”不经过 gh-proxy，并保留原始中文文件名，直接显示 raw.githubusercontent.com 直链。
        encoded_name = quote(name)
        raw_url = f"{RAW_BASE_URL}/{subdir}/{encoded_name}"
        proxy_url = f"{PROXY_PREFIX}{raw_url}"
        copy_raw_url = f"{RAW_BASE_URL}/{subdir}/{name}"
        rows.append(
            "<tr>"
            f'<td style="white-space:nowrap;">{name}</td>'
            f'<td style="white-space:nowrap;"><a href="{proxy_url}">下载链接</a></td>'
            f'<td style="white-space:nowrap;">{updated_at}</td>'
            f'<td><code>{copy_raw_url}</code></td>'
            "</tr>"
        )
    return "\n".join(rows)


def _build_readme_section_table(
    repo_root: str,
    subdir: str,
    ext: str,
    update_times: dict[str, str],
) -> str:
    rows = _build_readme_table_rows(repo_root, subdir, ext, update_times)
    return (
        '<table style="width:100%; table-layout:auto;">\n'
        "<colgroup>\n"
        '<col style="width: 220px;" />\n'
        '<col style="width: 120px;" />\n'
        '<col style="width: 170px;" />\n'
        "<col />\n"
        "</colgroup>\n"
        "<thead>\n"
        "<tr>\n"
        '<th style="white-space:nowrap;">文件名</th>\n'
        '<th style="white-space:nowrap;">加速链接</th>\n'
        '<th style="white-space:nowrap;">最近更新时间</th>\n'
        '<th style="white-space:nowrap;">可复制直链</th>\n'
        "</tr>\n"
        "</thead>\n"
        "<tbody>\n"
        f"{rows}\n"
        "</tbody>\n"
        "</table>"
    )


def beijing_now() -> datetime:
    """返回北京时间；Windows 无 tzdata 时回退到 UTC+8。"""
    if ZoneInfo is not None:
        try:
            return datetime.now(ZoneInfo("Asia/Shanghai"))
        except Exception:
            pass
    return datetime.now(timezone(timedelta(hours=8)))


def update_readme_file_list(repo_root: str) -> None:
    readme_path = os.path.join(repo_root, README_FILE)
    if not os.path.exists(readme_path):
        print("[-] README.md 不存在，跳过列表更新。")
        return
    with open(readme_path, "r", encoding="utf-8") as f:
        content = f.read()
    update_times = load_file_update_times(repo_root)
    m3u_table = _build_readme_section_table(repo_root, "m3u", ".m3u", update_times)
    txt_table = _build_readme_section_table(repo_root, "txt", ".txt", update_times)
    m3u_block = f"## M3U 文件列表\n\n{m3u_table}\n"
    txt_block = f"## TXT 文件列表\n\n{txt_table}\n"
    content, m3u_count = re.subn(
        r"## M3U 文件列表[\s\S]*?(?=\r?\n## TXT 文件列表)",
        m3u_block.rstrip(),
        content,
        count=1,
    )
    if "## 免责声明" in content:
        content, txt_count = re.subn(
            r"## TXT 文件列表[\s\S]*?(?=\r?\n---\r?\n\r?\n## 免责声明)",
            txt_block.rstrip(),
            content,
            count=1,
        )
    else:
        content, txt_count = re.subn(
            r"## TXT 文件列表[\s\S]*$",
            txt_block.rstrip(),
            content,
            count=1,
        )
    if m3u_count == 0 or txt_count == 0:
        print("[-] README 结构不匹配（未找到列表区块），跳过自动更新。")
        return

    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(content)
    print("[+] README.md 文件列表已自动更新。")


def process_province(
    province,
    txt_output_dir,
    m3u_output_dir,
    carriers=CARRIERS,
    max_pages=20,
    max_per_carrier=20,
    max_age_hours=72,
    min_stream_speed_mb_s=DEFAULT_MIN_STREAM_SPEED_MB_S,
    stream_test_seconds=3.0,
    test_channels_per_source=2,
):
    """单一省份核心流水线"""
    group_title = province
    out_txt = os.path.join(txt_output_dir, f"{group_title}.txt")
    out_m3u = os.path.join(m3u_output_dir, f"{group_title}.m3u")
    # 1. 检测历史文件。禁止在抓取前清空：本次失败时必须保留上一版列表及原更新时间。
    check_and_clear_existing(out_txt, out_m3u)
    # 2. 直接从频道列表提取 频道名+播放地址
    previous_hosts_by_carrier = load_previous_source_hosts(
        province, carriers, txt_output_dir
    )
    grouped_sources, status, _ = fetch_channel_lines_by_province(
        province,
        carriers=carriers,
        max_pages=max_pages,
        max_per_carrier=max_per_carrier,
        max_age_hours=max_age_hours,
        min_stream_speed_mb_s=min_stream_speed_mb_s,
        stream_test_seconds=stream_test_seconds,
        test_channels_per_source=test_channels_per_source,
        previous_hosts_by_carrier=previous_hosts_by_carrier,
    )
    if not grouped_sources:
        print(f"[-] [{province}] 频道提取失败: {status}")
        print(
            f"[*] [{province}] 本次未获取到新的可用直播源；"
            "保留上一版成功列表及其原更新时间，不删除、不覆盖。"
        )
        return []
    # 3. 按运营商和源序号逐个覆盖；本次未补足的序号保留上一版文件。
    #    例：山东电信.m3u、山东电信1.m3u、山东电信2.m3u ...
    total_channels = 0
    exported_sources = 0
    generated_relative_paths = []
    for group_title, sources in grouped_sources.items():
        for idx, channel_lines in enumerate(sources):
            if not channel_lines:
                continue

            channel_lines = sort_priority_channels(channel_lines)
            suffix = "" if idx == 0 else str(idx)
            file_stem = f"{group_title}{suffix}"
            out_txt = os.path.join(txt_output_dir, f"{file_stem}.txt")
            out_m3u = os.path.join(m3u_output_dir, f"{file_stem}.m3u")
            txt_content = "\n".join(channel_lines)
            with open(out_txt, 'w', encoding='utf-8') as f_txt, open(out_m3u, 'w', encoding='utf-8') as f_m3u:
                f_txt.write(txt_content + "\n")
                f_m3u.write(f'#EXTM3U x-tvg-url="{EPG_URL}"\n')
                f_m3u.write(txt_to_m3u_format(txt_content, group_title) + "\n")
            generated_relative_paths.extend([
                f"txt/{file_stem}.txt",
                f"m3u/{file_stem}.m3u",
            ])
            exported_sources += 1
            total_channels += len(channel_lines)
    if exported_sources == 0:
        print(f"[-] [{province}] 频道提取失败: channel_lines_empty")
        print(
            f"[*] [{province}] 本次没有生成新的有效列表；"
            "保留上一版成功列表及其原更新时间，不删除、不覆盖。"
        )
        return []
    print(
        f"[+] 完美！[{province}] 更新完成，导出 {total_channels} 条频道，"
        f"生成 {exported_sources} 条源文件（每运营商多条）。"
    )
    return generated_relative_paths

def push_to_github(files, province=""):
    """
    将本次生成文件提交并推送到当前 GitHub 仓库。
    依赖本机已配置好 git 远程与认证（SSH 或凭据管理器）。
    """
    print("\n[*] 正在同步到 GitHub 当前仓库...")
    try:
        # 使用 -A 同时提交新文件、修改和旧源文件删除。
        add_cmd = ["git", "add", "-A", "--"] + files
        add_run = subprocess.run(add_cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
        if add_run.returncode != 0:
            raise RuntimeError(f"git add 失败:\n{add_run.stderr.strip()}")

        check_run = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
        if check_run.returncode == 0:
            print("[*] 没有新增变更，无需提交。")
            return True

        target = f" {province}" if province else ""
        commit_msg = f"{GITHUB_COMMIT_PREFIX}{target} multicast files at {time.strftime('%Y-%m-%d %H:%M:%S')}"
        commit_run = subprocess.run(
            ["git", "commit", "-m", commit_msg],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
        if commit_run.returncode != 0:
            raise RuntimeError(f"git commit 失败:\n{commit_run.stderr.strip()}")
        print("[+] git commit 成功。")

        push_run = subprocess.run(
            ["git", "push"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
        if push_run.returncode != 0:
            raise RuntimeError(f"git push 失败:\n{push_run.stderr.strip()}")
        print("[+] 已成功推送到 GitHub。")
        return True
    except Exception as e:
        raise RuntimeError(f"GitHub 同步异常: {e}") from e

def split_selection(value: str) -> list[str]:
    """拆分英文/中文逗号或分号分隔的选择项，并保持原顺序去重。"""
    result = []
    for item in re.split(r"[,，;；]+", value or ""):
        item = item.strip()
        if item and item not in result:
            result.append(item)
    return result


def parse_province_selection(value: str) -> list[str]:
    items = split_selection(value)
    if not items:
        return list(PROVINCES)
    if "全部" in items:
        return list(PROVINCE_CODES)
    unknown = [item for item in items if item not in PROVINCE_CODES]
    if unknown:
        raise ValueError(f"未知省份：{', '.join(unknown)}")
    return items


def parse_carrier_selection(value: str) -> tuple[str, ...]:
    items = split_selection(value)
    if not items or "全部" in items:
        return CARRIERS
    unknown = [item for item in items if item not in CARRIERS]
    if unknown:
        raise ValueError(f"未知运营商：{', '.join(unknown)}")
    return tuple(items)


def parse_exact_targets(value: str) -> dict[str, tuple[str, ...]]:
    """解析“四川电信,浙江电信”或“四川:电信”格式的精确目标。"""
    plan: dict[str, list[str]] = {}
    for item in split_selection(value):
        compact = re.sub(r"\s+", "", item).replace("：", ":")
        matched = None
        for carrier in CARRIERS:
            if compact.endswith(carrier):
                province = compact[:-len(carrier)].rstrip(":")
                matched = (province, carrier)
                break
        if not matched or matched[0] not in PROVINCE_CODES:
            raise ValueError(f"无法识别目标：{item}")
        province, carrier = matched
        plan.setdefault(province, [])
        if carrier not in plan[province]:
            plan[province].append(carrier)
    return {province: tuple(carriers) for province, carriers in plan.items()}


def parse_args():
    ap = argparse.ArgumentParser(description="按省份抓取频道并生成 txt/m3u。")
    ap.add_argument(
        "--push",
        action="store_true",
        help="每个省份成功生成后立即更新 README 并执行 git add/commit/push（默认关闭）。",
    )
    ap.add_argument(
        "--test-region",
        default="",
        help="仅测试提取某地区全部服务器，不生成文件。例如：--test-region 湖北",
    )
    ap.add_argument(
        "--only-province",
        default="",
        help="仅处理指定省份。例如：--only-province 湖北",
    )
    ap.add_argument(
        "--provinces",
        default="",
        help="处理一个、多个或全部省份，例如：安徽,湖北 或 全部。",
    )
    ap.add_argument(
        "--carriers",
        default="全部",
        help="处理一个或多个运营商，例如：电信 或 电信,联通；默认全部。",
    )
    ap.add_argument(
        "--targets",
        default="",
        help="精确的省份运营商目标，例如：四川电信,浙江电信,河北电信。",
    )
    ap.add_argument(
        "--max-pages",
        type=int,
        default=20,
        help="每个省份组播服务器列表固定只抓取前5页；当前参数保留用于兼容工作流。",
    )
    ap.add_argument(
        "--max-per-carrier",
        type=int,
        default=20,
        help="每个运营商最多测试的候选服务器数量（默认20）；获得2个可用播放列表后提前停止。",
    )
    ap.add_argument(
        "--max-age-hours",
        type=int,
        default=72,
        help="仅提取最近更新 N 小时内的源（默认72，约3天）。",
    )
    ap.add_argument(
        "--min-stream-speed",
        type=float,
        default=None,
        help="显式覆盖所有省份的测速门槛，单位MB/s；不填写时四川100KB/s、其他省份750KB/s。",
    )
    ap.add_argument(
        "--stream-test-seconds",
        type=float,
        default=3.0,
        help="每个抽测频道的测速时长，单位秒（默认3）。",
    )
    ap.add_argument(
        "--test-channels-per-source",
        type=int,
        default=2,
        help="每条服务器最多抽测的频道数量（默认2）。",
    )
    return ap.parse_args()


def main():
    args = parse_args()

    # 省份组播服务器列表统一固定只抓取前5页。
    # 当前 GitHub Actions 仍可能传入其他 --max-pages 值；这里统一覆盖为5。
    if args.max_pages != REGION_LIST_MAX_PAGES:
        print(
            f"[*] 省份组播服务器列表分页上限固定为{REGION_LIST_MAX_PAGES}页 "
            f"（忽略 --max-pages {args.max_pages}）。"
        )
        args.max_pages = REGION_LIST_MAX_PAGES

    # “目标2个可用源”和“最多测试20台候选”是两个独立概念。
    # 工作流旧参数可能仍传入 --max-per-carrier 2；这里强制恢复为20，
    # 避免出现测试2台后即使只成功1台也无法继续测试第3台的逻辑错误。
    if args.max_per_carrier != 20:
        print(
            f"[*] 每运营商候选服务器测速上限固定为20台 "
            f"（忽略 --max-per-carrier {args.max_per_carrier}）；"
            f"目标仍为{TARGET_PLAYABLE_SOURCES_PER_CARRIER}个可用源。"
        )
        args.max_per_carrier = 20
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(script_dir)
    txt_output_dir = os.path.join(repo_root, "txt")
    m3u_output_dir = os.path.join(repo_root, "m3u")
    try:
        selected_carriers = parse_carrier_selection(args.carriers)
        if args.targets:
            execution_plan = parse_exact_targets(args.targets)
        elif args.only_province:
            provinces = parse_province_selection(args.only_province)
            if len(provinces) != 1:
                raise ValueError("--only-province 只能指定一个省份")
            execution_plan = {provinces[0]: selected_carriers}
        else:
            execution_plan = {
                province: selected_carriers
                for province in parse_province_selection(args.provinces)
            }
    except ValueError as exc:
        raise SystemExit(f"参数错误：{exc}") from exc

    if args.test_region:
        test_min_speed = resolve_min_stream_speed(
            args.test_region, args.min_stream_speed
        )
        print(
            f"[*] [{args.test_region}] 测速通过门槛："
            f"> {test_min_speed * 1024:.0f} KB/s"
        )
        grouped_sources, status, group_title = fetch_channel_lines_by_province(
            args.test_region,
            carriers=selected_carriers,
            max_pages=args.max_pages,
            max_per_carrier=args.max_per_carrier,
            max_age_hours=args.max_age_hours,
            min_stream_speed_mb_s=test_min_speed,
            stream_test_seconds=args.stream_test_seconds,
            test_channels_per_source=args.test_channels_per_source,
        )
        total = (
            sum(len(lines) for sources in grouped_sources.values() for lines in sources)
            if grouped_sources
            else 0
        )
        print(
            f"\n[*] 测试结果: 地区={args.test_region}，分组={group_title}，"
            f"状态={status}，频道数={total}"
        )
        for k, sources in grouped_sources.items():
            n_sources = len(sources)
            n_lines = sum(len(x) for x in sources)
            print(f"  - {k}: {n_sources} 条源，共 {n_lines} 条")
        return

    os.makedirs(txt_output_dir, exist_ok=True)
    os.makedirs(m3u_output_dir, exist_ok=True)

    # 历史成功列表采用增量保护策略：无论定时运行、手动运行还是全省份运行，
    # 都不在抓取前清空输出目录。只有对应运营商本次成功生成新列表后才覆盖对应文件；
    # 本次未抓到新源、请求失败、测速失败或未选择的运营商，均保留上一版文件及原更新时间。

    print(
        "[*] 本次执行计划："
        + "；".join(
            f"{province}({','.join(carriers)})"
            for province, carriers in execution_plan.items()
        )
    )

    for province_index, (province, carriers) in enumerate(execution_plan.items()):
        if province_index > 0:
            switch_delay = random.uniform(
                PROVINCE_SWITCH_DELAY_MIN_SEC,
                PROVINCE_SWITCH_DELAY_MAX_SEC,
            )
            print(
                f"\n[*] 切换到下一个省份前冷却 {switch_delay:.1f} 秒，"
                "降低省份列表接口触发429的概率。"
            )
            time.sleep(switch_delay)

        print(f"\n" + "=" * 50)
        print(f" 正在处理地区任务: {province}；运营商: {','.join(carriers)}")
        print("=" * 50)

        # 不再预先删除未选择运营商的历史文件。历史成功列表只有在对应运营商
        # 本次成功生成新列表时才会被精确覆盖，避免抓取失败导致旧源丢失。

        province_min_speed = resolve_min_stream_speed(
            province, args.min_stream_speed
        )
        print(
            f"[*] [{province}] 本次测速通过门槛："
            f"> {province_min_speed * 1024:.0f} KB/s"
        )

        generated_relative_paths = process_province(
            province,
            txt_output_dir,
            m3u_output_dir,
            carriers=carriers,
            max_pages=args.max_pages,
            max_per_carrier=args.max_per_carrier,
            max_age_hours=args.max_age_hours,
            min_stream_speed_mb_s=province_min_speed,
            stream_test_seconds=args.stream_test_seconds,
            test_channels_per_source=args.test_channels_per_source,
        )

        if generated_relative_paths:
            # 只记录本次实际成功覆盖的文件时间；未生成的新源继续保留旧文件和旧时间。
            record_province_update_times(
                repo_root, province, generated_relative_paths
            )
            update_readme_file_list(repo_root)
            if args.push:
                print(
                    f"\n[*] [{province}] 抓取完成，"
                    "立即更新 README 并推送到 GitHub..."
                )
                publish_paths = ["txt", "m3u", README_FILE]
                if os.path.exists(os.path.join(repo_root, UPDATE_TIMES_FILE)):
                    publish_paths.append(UPDATE_TIMES_FILE)
                push_to_github(publish_paths, province=province)
                print(f"[+] [{province}] 已发布，继续处理下一个省份。")
        else:
            print(
                f"[*] [{province}] 本次没有新的列表需要发布；"
                "GitHub 中上一版成功列表和对应更新时间保持不变。"
            )

    generated_files = []
    generated_files.extend(
        [
            os.path.join("txt", f)
            for f in os.listdir(txt_output_dir)
            if f.endswith(".txt")
        ]
    )
    generated_files.extend(
        [
            os.path.join("m3u", f)
            for f in os.listdir(m3u_output_dir)
            if f.endswith(".m3u")
        ]
    )

    if args.push:
        print("\n[] 全部省份处理完毕；每个成功省份均已即时发布。")
    else:
        update_readme_file_list(repo_root)
        generated_files.append(README_FILE)
        print("\n[] 流水线本地文件生成完毕（未启用 --push，跳过 git 推送）。")
        print(f"[] 本次生成文件数量: {len(generated_files)}")


if __name__ == "__main__":
    main()
