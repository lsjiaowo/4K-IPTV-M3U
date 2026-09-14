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
from pathlib import Path
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
# 成功抓取并通过测速后生成的 M3U 文件统一使用此 XMLTV EPG 节目单。
# 每个 M3U 仅在文件首行写入一次 x-tvg-url；TXT 文件不添加 EPG 头。
EPG_URL = "https://epg.catvod.com/epg.xml"
TVG_LOGO_BASE_URL = "https://gcore.jsdelivr.net/gh/taksssss/tv/icon/"
README_FILE = "README.md"
UPDATE_TIMES_FILE = ".github/iptv-update-times.json"
# README 中的 M3U 订阅地址使用 Secret Gist RAW；真实 Gist ID 只从 Actions Secret 注入，
# 不写死在源码中。TXT 文件保留在 Private 仓库，通过 GitHub 登录后的 blob 链接查看。
GITHUB_REPO_BLOB_BASE_URL = "https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main"
GIST_OWNER = "lsjiaowo"
IPTV_GIST_ID = os.environ.get("IPTV_GIST_ID", "").strip()

# 可选的本地频道模板目录。模板文件名使用“省份+运营商”，例如：
# channel_templates/天津联通.m3u 或 channel_templates/天津联通.txt
# 来源选择：优先 .m3u，其次 .txt；若均无有效模板，则锁定使用 cqshushu。
# 同一“省份+运营商”一次运行中来源锁定后不再混用。
# 模板只提供“频道名称 + RTP组播地址”；最终 tvg-id/tvg-logo/group-title、EPG 和排序
# 仍完全沿用本脚本现有输出逻辑。
CHANNEL_TEMPLATE_DIR = "channel_templates"

# 一次脚本运行期间按“省份+运营商”锁定频道来源并复用测速频道模板。
# mode=template：测速和最终列表都只使用 channel_templates；cqshushu 仅用于解析候选真实 IP:PORT。
# mode=cqshushu：测速和最终列表都使用 cqshushu；第一次抓到足够 CCTV 后缓存 RTP 测速模板，
#                 后续候选只替换真实 IP:PORT，不再重复抓取 CCTV 测速频道列表。
_CHANNEL_SOURCE_RUNTIME_CACHE: dict[str, dict] = {}

# 默认测速门槛；四川线路单独放宽。
DEFAULT_MIN_STREAM_SPEED_MB_S = 750.0 / 1024.0
PROVINCE_MIN_STREAM_SPEED_MB_S = {
    "四川": 400.0 / 1024.0,
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

# 省份服务器列表第1～10页：每次成功请求后统一随机等待 5～10 秒。
REGION_LIST_DELAY_MIN_SEC = 5.0
REGION_LIST_DELAY_MAX_SEC = 10.0

# 省份服务器列表第1～10页：只有出现连接/读取超时、接口提示请求频繁或 HTTP 429 时，
# 才额外随机冷却50～60秒后重试当前页。
REGION_LIST_ERROR_COOLDOWN_MIN_SEC = 50.0
REGION_LIST_ERROR_COOLDOWN_MAX_SEC = 60.0

# 省份组播服务器列表动态搜索最大10页。
# 第1～10页每次成功请求后都只随机等待5～10秒，不再对第6～10页设置固定深分页长等待。
# 前5页结束后立即筛选并测速新IP；若目标仍未满足，再继续第6～10页并逐页筛选/测速新增候选。
# 只有连接/读取超时、接口提示请求频繁或 HTTP 429 时，才额外随机冷却50～60秒后重试当前页。
REGION_LIST_MAX_PAGES = 10
REGION_LIST_DEEP_PAGE_START = 6

# 连续处理多个省份时，在进入下一个省份前随机冷却 5～10 秒。
PROVINCE_SWITCH_DELAY_MIN_SEC = 5.0
PROVINCE_SWITCH_DELAY_MAX_SEC = 10.0

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

    省份列表第1～10页每次成功请求后统一随机等待5～10秒。
    若发生连接/读取超时、接口提示请求频繁或 HTTP 429：额外随机冷却50～60秒后重试同一页。
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

            # 省份服务器列表接口若以JSON返回“请求频繁”，仅在此时触发50～60秒长冷却并重试当前页。
            if is_region_list:
                message = str(data.get("message", "") or "")
                status = str(data.get("status", "") or "").lower()
                if status != "success" and ("频繁" in message or "too many" in message.lower()):
                    if attempt + 1 >= REQUEST_MAX_RETRIES:
                        raise RuntimeError(f"省份服务器列表请求频繁: {message or '请求频繁'}")
                    wait = random.uniform(
                        REGION_LIST_ERROR_COOLDOWN_MIN_SEC,
                        REGION_LIST_ERROR_COOLDOWN_MAX_SEC,
                    )
                    print(
                        f"[!] 省份服务器列表接口提示请求频繁，"
                        f"额外额外随机冷却 {wait:.1f} 秒后重新抓取当前页 "
                        f"({attempt + 1}/{REQUEST_MAX_RETRIES})。"
                    )
                    time.sleep(wait)
                    continue

            # 频道接口若直接返回“请求频繁”，不做专用长等待，直接结束本次请求。
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

            # 省份服务器列表第1～10页若触发 HTTP 429，才启用50～60秒额外长冷却。
            if status_code == 429 and is_region_list and 1 <= region_page_num <= REGION_LIST_MAX_PAGES:
                if attempt + 1 >= REQUEST_MAX_RETRIES:
                    raise
                wait = random.uniform(
                    REGION_LIST_ERROR_COOLDOWN_MIN_SEC,
                    REGION_LIST_ERROR_COOLDOWN_MAX_SEC,
                )
                print(
                    f"[!] 省份服务器列表第{region_page_num}页触发 HTTP 429，"
                    f"额外额外随机冷却 {wait:.1f} 秒后重新抓取当前页 "
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

            # 省份服务器列表第1～10页如果发生连接/读取超时，不使用0.8秒短退避；
            # 仅在超时时额外随机冷却50～60秒后重新请求当前页。页码从请求参数中识别。
            region_page_match = re.search(r"(?:[?&])page=(\d+)", path_query)
            region_page_num = int(region_page_match.group(1)) if region_page_match else 0
            if (
                is_region_list
                and 1 <= region_page_num <= REGION_LIST_MAX_PAGES
                and isinstance(e, requests.Timeout)
            ):
                wait = random.uniform(
                    REGION_LIST_ERROR_COOLDOWN_MIN_SEC,
                    REGION_LIST_ERROR_COOLDOWN_MAX_SEC,
                )
                print(
                    f"[!] 省份服务器列表第{region_page_num}页请求超时，"
                    f"额外随机冷却 {wait:.1f} 秒后重新抓取当前页 "
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

    # 省份服务器列表最多请求第1～10页；所有成功请求后统一随机等待5～10秒。
    # 只有连接/读取超时、接口提示请求频繁或HTTP 429时，才额外随机冷却50～60秒后重试当前页。
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


def _parse_rtp_target(value: str) -> str | None:
    """从模板地址中提取 IPv4:port RTP 组播目标。"""
    text = (value or "").strip()
    match = re.fullmatch(
        r"(?i)rtp://(\d{1,3}(?:\.\d{1,3}){3}):(\d{1,5})/?",
        text,
    )
    if not match:
        return None
    ip_text, port_text = match.groups()
    octets = ip_text.split(".")
    if any(int(part) > 255 for part in octets):
        return None
    port = int(port_text)
    if not (1 <= port <= 65535):
        return None
    return f"{ip_text}:{port}"


def parse_channel_template_m3u(content: str) -> list[tuple[str, str]]:
    """解析 M3U 模板，仅保留“显示频道名 + RTP组播地址”。

    同时兼容 rtp://239.x.x.x:port 与
    http://任意IP:任意端口/rtp/239.x.x.x:port 两种模板地址；HTTP 地址中的
    公网/局域网转发 IP:PORT 仅作为占位，最终会替换为当前候选的真实 endpoint。
    模板中的 tvg-name/tvg-logo/group-title 等元数据不继承；最终 M3U 仍由
    txt_to_m3u_format() 按现有规则重新生成。
    """
    result: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    pending_name = ""

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.upper().startswith("#EXTINF"):
            # 以 EXTINF 最后一个逗号后的显示名称为准；若没有则尝试 tvg-name。
            pending_name = line.rsplit(",", 1)[-1].strip() if "," in line else ""
            if not pending_name:
                match = re.search(r'tvg-name\s*=\s*"([^"]+)"', line, flags=re.IGNORECASE)
                pending_name = match.group(1).strip() if match else ""
            continue
        if line.startswith("#"):
            continue

        rtp_target = _parse_rtp_target_from_play_url(line)
        if not rtp_target or not pending_name:
            pending_name = ""
            continue
        item = (pending_name, rtp_target)
        if item not in seen:
            seen.add(item)
            result.append(item)
        pending_name = ""
    return result


def parse_channel_template_txt(content: str) -> list[tuple[str, str]]:
    """解析 TXT 模板，仅保留“频道名 + RTP组播地址”，忽略 #genre# 分类行。"""
    result: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "#genre#" in line.lower() or "," not in line:
            continue
        name, play_url = [part.strip() for part in line.split(",", 1)]
        if not name:
            continue
        rtp_target = _parse_rtp_target_from_play_url(play_url)
        if not rtp_target:
            continue
        item = (name, rtp_target)
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def load_local_channel_template(
    group_title: str,
    template_dir: str = CHANNEL_TEMPLATE_DIR,
) -> tuple[list[tuple[str, str]], str | None]:
    """读取“省份+运营商”本地模板；优先 M3U，其次 TXT。

    某个文件存在但无有效 RTP 频道时继续尝试下一种格式；两种都不可用时返回空。
    调用方会在“省份+运营商”层级锁定为 cqshushu 模式，本轮后续不再切换来源。
    """
    for extension, parser in ((".m3u", parse_channel_template_m3u), (".txt", parse_channel_template_txt)):
        path = os.path.join(template_dir, f"{group_title}{extension}")
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8-sig") as file:
                content = file.read()
        except OSError as exc:
            print(f"[!] [{group_title}] 本地频道模板读取失败：{path}；{exc}")
            continue

        channels = parser(content)
        if channels:
            print(f"[+] [{group_title}] 找到本地频道模板：{path}；有效RTP频道={len(channels)}条。")
            return channels, path
        print(f"[!] [{group_title}] 本地频道模板存在但未解析到有效RTP频道：{path}")

    return [], None


def resolve_relay_host_with_port(
    candidate_host: str,
    p_token: str,
    session: requests.Session | None = None,
) -> str:
    """解析候选公网转发服务器的完整 host:port。

    省份服务器列表中的 host 字段有时只有 IPv4，不包含实际 HTTP 转发端口。
    若候选本身已有端口则直接使用；否则只借助 cqshushu 的详情页和频道列表
    获取一条完整 HTTP 播放地址，从其 netloc 提取真正的 IP:PORT。
    本地模板仍然负责频道名称和 RTP 组播地址，不使用 cqshushu 的频道内容输出。
    """
    normalized = normalize_source_host(candidate_host)
    if not normalized:
        return ""

    parsed_candidate = urlparse(
        candidate_host if "://" in candidate_host else f"http://{candidate_host}"
    )
    if parsed_candidate.port is not None:
        return normalized

    try:
        detail_html = fetch_detail_html(p_token, session=session)
    except Exception as exc:
        print(
            f"[-] [{candidate_host}] 为本地模板解析公网转发端口时，"
            f"IP详情页获取失败：{exc}"
        )
        return ""

    if not detail_html:
        print(f"[-] [{candidate_host}] IP详情页为空，无法解析公网转发端口。")
        return ""

    s_token = parse_s_token(detail_html)
    if not s_token:
        print(f"[-] [{candidate_host}] IP详情页未找到 s_token，无法解析公网转发端口。")
        return ""

    # 这里只需拿到一页中的一条完整 HTTP 播放地址来确定公网端口。
    # 不使用 cqshushu 的频道名称/组播地址生成最终列表。
    probe_lines = fetch_channel_lines_by_s(
        s_token,
        session=session,
        max_pages=1,
    )
    candidate_ip = parsed_candidate.hostname or normalized.split(":", 1)[0]
    fallback_netloc = ""

    for line in probe_lines:
        if "," not in line:
            continue
        play_url = line.split(",", 1)[1].strip()
        parsed_url = urlparse(play_url)
        if parsed_url.scheme.lower() not in ("http", "https") or not parsed_url.netloc:
            continue
        if parsed_url.port is None:
            continue
        netloc = parsed_url.netloc.lower().strip()
        if parsed_url.hostname == candidate_ip:
            print(f"[+] [{candidate_host}] 已解析公网转发地址：{netloc}")
            return netloc
        if not fallback_netloc:
            fallback_netloc = netloc

    if fallback_netloc:
        print(
            f"[!] [{candidate_host}] 频道页中的公网IP与列表IP不完全一致；"
            f"采用频道播放地址中的转发地址：{fallback_netloc}"
        )
        return fallback_netloc

    print(f"[-] [{candidate_host}] 未能从频道页解析出带端口的 HTTP 转发地址。")
    return ""


def build_template_channel_lines(
    template_channels: list[tuple[str, str]],
    relay_host: str,
) -> list[str]:
    """把模板 RTP 地址转换为带真实公网端口的 HTTP /rtp/ 地址。"""
    host = normalize_source_host(relay_host)
    if not host:
        return []
    return [
        f"{name},http://{host}/rtp/{rtp_target}"
        for name, rtp_target in template_channels
    ]


def _parse_rtp_target_from_play_url(value: str) -> str | None:
    """从 cqshushu 的 HTTP /rtp/ 播放地址或标准 rtp:// 地址提取 IPv4:port。"""
    direct = _parse_rtp_target(value)
    if direct:
        return direct

    text = (value or "").strip()
    parsed = urlparse(text)
    match = re.search(
        r"(?i)(?:^|/)rtp/(\d{1,3}(?:\.\d{1,3}){3}):(\d{1,5})(?:/|$)",
        parsed.path or "",
    )
    if not match:
        return None
    ip_text, port_text = match.groups()
    octets = ip_text.split(".")
    if any(int(part) > 255 for part in octets):
        return None
    port = int(port_text)
    if not (1 <= port <= 65535):
        return None
    return f"{ip_text}:{port}"


def build_cctv_speed_template(channel_lines: list[str]) -> list[tuple[str, str]]:
    """从已抓频道中提取可复用的 CCTV 测速模板，仅保留“频道名 + RTP组播地址”。

    公网 IP:PORT 不进入缓存；后续候选只需解析自己的真实 endpoint，
    再用 build_template_channel_lines() 重新拼成 HTTP /rtp/ 测速地址。
    """
    result: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for name, play_url in extract_speed_test_candidates(channel_lines):
        rtp_target = _parse_rtp_target_from_play_url(play_url)
        if not rtp_target:
            continue
        item = (name, rtp_target)
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def extract_general_speed_test_candidates(channel_lines: list[str]) -> list[tuple[str, str]]:
    """模板缺少足够 CCTV 时的兜底测速候选：普通 HTTP 频道，排除标清/SD/4K。"""
    candidates: list[tuple[str, str]] = []
    seen_urls: set[str] = set()
    for line in channel_lines:
        if "," not in line:
            continue
        channel_name, play_url = [part.strip() for part in line.split(",", 1)]
        upper_name = channel_name.upper()
        if not channel_name or "标清" in channel_name or "SD" in upper_name or "4K" in upper_name:
            continue
        if not play_url.lower().startswith(("http://", "https://")) or play_url in seen_urls:
            continue
        seen_urls.add(play_url)
        candidates.append((channel_name, play_url))
    return candidates


def extract_speed_test_candidates(channel_lines: list[str]) -> list[tuple[str, str]]:
    """提取CCTV1-CCTV17中不含标清/SD/4K字样的HTTP测速频道，并按URL去重。"""
    candidates: list[tuple[str, str]] = []
    seen_urls: set[str] = set()
    cctv_pattern = re.compile(
        r"(?i)(?<![A-Z0-9])CCTV\s*[-_ ]?\s*(5\+|1[0-7]|[1-9])(?!\d)"
    )
    for line in channel_lines:
        if "," not in line:
            continue
        channel_name, play_url = line.split(",", 1)
        channel_name = channel_name.strip()
        play_url = play_url.strip()
        if not cctv_pattern.search(channel_name):
            continue
        # 测速使用 CCTV1-CCTV17，并额外允许 CCTV5+；剔除标清/SD以及频道名中包含4K字样的频道。
        channel_name_upper = channel_name.upper()
        if "标清" in channel_name or "SD" in channel_name_upper or "4K" in channel_name_upper:
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
                    f"[*] 已找到 {test_count} 个 CCTV1-CCTV17 非标清/非4K测速频道，"
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
    """从CCTV1至CCTV17中排除标清/SD/4K字样频道后随机抽测，任意一个通过即有效。"""
    candidates = extract_speed_test_candidates(channel_lines)
    required_count = max(1, test_channels)
    if len(candidates) < required_count:
        print(
            f"[-] [{source_label}] CCTV1-CCTV17 非标清/非4K可测试频道不足："
            f"{len(candidates)}/{required_count}，判定无效。"
        )
        return False

    sampled_channels = random.sample(candidates, required_count)
    passed_count = 0
    print(
        f"[*] [{source_label}] 从 {len(candidates)} 个 CCTV1-CCTV17 非标清/非4K频道中"
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

def is_template_source_playable(
    channel_lines: list[str],
    source_label: str,
    min_speed_mb_s: float = DEFAULT_MIN_STREAM_SPEED_MB_S,
    sample_seconds: float = 3.0,
    test_channels: int = 2,
) -> bool:
    """本地模板测速：严格只使用 CCTV1-CCTV17 非标清/非4K测速频道，不切换其它来源。"""
    required_count = max(1, test_channels)
    candidates = extract_speed_test_candidates(channel_lines)

    if len(candidates) < required_count:
        print(
            f"[-] [{source_label}] channel_templates 中可测试的 "
            f"CCTV1-CCTV17 非标清/非4K频道不足：{len(candidates)}/{required_count}；"
            "频道来源已锁定为本地模板，本轮不切换到 cqshushu 或普通频道测速。"
        )
        return False

    sampled_channels = random.sample(candidates, required_count)
    print(
        f"[*] [{source_label}] 从 channel_templates 的 {len(candidates)} 个 "
        f"CCTV1-CCTV17 非标清/非4K频道中随机抽测 {required_count} 个。"
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
            print(f"[+] [{source_label}] {channel_name} 测速通过。")
            print(f"[+] [{source_label}] 已有1个抽测频道通过，立即停止其余频道测速。")
            return True
        print(f"[-] [{source_label}] {channel_name} 速度不足。")

    print(f"[-] [{source_label}] 0/{required_count} 个抽测频道通过，丢弃该服务器。")
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
    target_playable_sources: int = TARGET_PLAYABLE_SOURCES_PER_CARRIER,
    excluded_endpoints_by_carrier: dict[str, set[str]] | None = None,
    deprioritized_ips_by_carrier: dict[str, set[str]] | None = None,
):
    """
    最大10页动态扫描 + 提前测速：

    1. 先扫描省份组播服务器列表第1～5页，每页成功后随机等待5～10秒。
    2. 前5页扫描完成后立即优先测试新IP；达到2个可用源则立即结束，不请求第6～10页。
    3. 若仍不足目标，则继续第6～10页；第6～10页成功请求后同样只随机等待5～10秒，
       每抓取一页就立即筛选并测试新增的新IP，达到目标后立即停止后续分页。
    4. 搜索到第10页仍不足目标时，才允许已扫描页面中的旧IP兜底；新IP始终最高优先级。
    5. 每个运营商最多测试 max_per_carrier 台候选，找到 target_playable_sources 个可用源后停止。
    6. 每个“省份+运营商”在本次脚本运行中锁定唯一频道来源：
       - 有 channel_templates：测速与最终列表都使用模板；cqshushu 仅辅助解析真实 IP:PORT。
       - 无 channel_templates：全程使用 cqshushu；第一次找到足够 CCTV 后缓存 RTP 测速模板，
         后续候选只替换真实 IP:PORT，不再重复获取 CCTV 测速频道列表。
    """
    session = requests.Session()
    target_playable_sources = max(1, int(target_playable_sources))
    max_pages = min(max(1, int(max_pages)), REGION_LIST_MAX_PAGES)
    now_dt = datetime.now()

    region_code = PROVINCE_CODES.get(province)
    if not region_code:
        print(f"[-] 未找到省份 [{province}] 的 region code，跳过。")
        return [], "list_empty", province

    print(
        f"[*] [{province}] 启用动态分页：前5页正常扫描；"
        f"新IP搜索深度={max_pages}页；最大搜索={REGION_LIST_MAX_PAGES}页。"
    )
    multicast_source_url = (
        f"https://iptv.cqshushu.com/index.php?t=multicast&province={region_code}"
    )
    print(f"[*] 正在抓取组播源: {multicast_source_url}")

    all_rows: list[dict] = []
    seen_region_tokens: set[str] = set()
    empty_page_hits = 0

    group_to_sources: dict[str, list[list[str]]] = {}
    selected_ops: list[str] = []
    playable_counts = {carrier: 0 for carrier in carriers}
    tested_counts = {carrier: 0 for carrier in carriers}
    tested_tokens_by_carrier = {carrier: set() for carrier in carriers}

    def _get_channel_source_context(group_title: str) -> dict:
        """按“省份+运营商”在本次脚本运行期间锁定唯一频道来源。"""
        context = _CHANNEL_SOURCE_RUNTIME_CACHE.get(group_title)
        if context is not None:
            return context

        template_channels, template_path = load_local_channel_template(group_title)
        if template_channels:
            context = {
                "mode": "template",
                "template_channels": template_channels,
                "template_path": template_path,
                "speed_template": [],
                "candidate_meta": {},
            }
            print(
                f"[*] [{group_title}] 频道来源锁定：channel_templates；"
                "本轮测速与最终完整频道列表均使用本地模板，绝不切换到 cqshushu 频道内容。"
            )
        else:
            context = {
                "mode": "cqshushu",
                "template_channels": [],
                "template_path": None,
                "speed_template": [],
                "candidate_meta": {},
            }
            print(
                f"[*] [{group_title}] 频道来源锁定：cqshushu；"
                "本轮测速与最终完整频道列表均使用 cqshushu，绝不切换到 channel_templates。"
            )
        _CHANNEL_SOURCE_RUNTIME_CACHE[group_title] = context
        return context

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
        deprioritized_ips = (deprioritized_ips_by_carrier or {}).get(carrier, set())

        def _row_ip(row: dict) -> str:
            host = normalize_source_host(row.get("host", ""))
            parsed = urlparse("//" + host)
            return parsed.hostname or host.split(":", 1)[0]

        # 正常完整抓取保持原有“新 endpoint 优先、旧 endpoint 最后兜底”。
        # 健康修复时 additionally 将“与失效/占用 endpoint 同公网IP但不同端口”的候选降为第二优先级，
        # 但绝不拉黑整个公网IP：例如 222.2.2.2:8188 失效后，222.2.2.2:4022 仍可测速采用。
        preferred_new_rows = []
        same_ip_rows = []
        old_rows = []
        for row in carrier_rows:
            host = normalize_source_host(row.get("host", ""))
            if host in previous_hosts:
                old_rows.append(row)
            elif _row_ip(row) in deprioritized_ips:
                same_ip_rows.append(row)
            else:
                preferred_new_rows.append(row)
        return preferred_new_rows + same_ip_rows, old_rows

    def _targets_complete() -> bool:
        return all(
            playable_counts.get(carrier, 0) >= target_playable_sources
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
        if playable_counts.get(carrier, 0) >= target_playable_sources:
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
            source_context = _get_channel_source_context(group_title)
            source_mode = source_context.get("mode", "cqshushu")

            # ------------------------------------------------------------
            # 模式 A：channel_templates
            # - 从一开始就只使用本地模板中的频道名/RTP组播地址。
            # - cqshushu 仅允许用于解析候选真实公网 IP:PORT，不采用其频道内容。
            # - 测速通过后的最终完整列表仍直接套用同一份本地模板。
            # ------------------------------------------------------------
            if source_mode == "template":
                template_channels = source_context.get("template_channels", [])
                template_path = source_context.get("template_path")
                candidate_meta = source_context.setdefault("candidate_meta", {})
                cached_meta = candidate_meta.get(token, {})
                relay_host = cached_meta.get("relay_host", "")
                if relay_host:
                    print(
                        f"[*] [{group_title} {candidate_host}] 复用本轮已解析 endpoint：{relay_host}；"
                        "无需再次请求频道页解析端口。"
                    )
                else:
                    relay_host = resolve_relay_host_with_port(
                        candidate_host,
                        token,
                        session=session,
                    )
                    if relay_host:
                        candidate_meta[token] = {"relay_host": normalize_source_host(relay_host)}
                source_label = f"{group_title} {relay_host or candidate_host}".strip()
                if not relay_host:
                    print(
                        f"[-] [{group_title} {candidate_host}] 无法解析候选服务器的公网转发 IP:PORT，"
                        "跳过该源，避免错误地按80端口测速。"
                    )
                    return False
                relay_host = normalize_source_host(relay_host)
                excluded_endpoints = (excluded_endpoints_by_carrier or {}).get(carrier, set())
                if relay_host in excluded_endpoints:
                    print(
                        f"[*] [{source_label}] endpoint {relay_host} "
                        "本轮已失效或已被同组槽位占用，跳过。"
                    )
                    return False

                lines = build_template_channel_lines(template_channels, relay_host)
                if not lines:
                    print(f"[-] [{source_label}] 无法使用 channel_templates 构造播放地址，跳过该源。")
                    return False

                print(
                    f"[*] [{source_label}] 频道来源=channel_templates：{template_path}；"
                    f"已按当前 endpoint {relay_host} 构造 {len(lines)} 条 HTTP /rtp/ 播放地址。"
                )
                if not is_template_source_playable(
                    lines,
                    source_label=source_label,
                    min_speed_mb_s=min_stream_speed_mb_s,
                    sample_seconds=stream_test_seconds,
                    test_channels=test_channels_per_source,
                ):
                    return False

                selected_ops.append(group_title)
                group_to_sources.setdefault(group_title, []).append(lines)
                playable_counts[carrier] = playable_counts.get(carrier, 0) + 1
                print(
                    f"[+] [{province}{carrier}] 可用源：{candidate_host}【{candidate_status}】；"
                    f"频道来源=channel_templates；已获得 "
                    f"{playable_counts[carrier]}/{target_playable_sources} "
                    f"个可用播放列表（已测试 {tested_counts[carrier]}/{max_per_carrier} 台）。"
                )
                return True

            # ------------------------------------------------------------
            # 模式 B：cqshushu
            # - 第一个能抓到足够 CCTV 的候选建立“频道名 + RTP组播地址”测速模板。
            # - 后续候选复用该 CCTV 模板，只替换各自真实 IP:PORT，不再重复抓测速频道列表。
            # - 最终完整列表仍只从 cqshushu 获取，绝不切换到 channel_templates。
            # ------------------------------------------------------------
            print(f"[*] [{group_title} {candidate_host}] 频道来源=cqshushu（本轮已锁定）。")
            candidate_meta = source_context.setdefault("candidate_meta", {})
            cached_meta = candidate_meta.get(token, {})
            s_token = cached_meta.get("s_token", "")
            relay_host = cached_meta.get("relay_host", "")

            if s_token:
                token_preview = s_token if len(s_token) <= 16 else s_token[:8] + "..." + s_token[-4:]
                print(
                    f"[*] [{group_title} {candidate_host}] 复用本轮候选解析缓存："
                    f"s_token={token_preview}，endpoint={relay_host or '待解析'}。"
                )
            else:
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
                cached_meta = dict(cached_meta)
                cached_meta["s_token"] = s_token
                candidate_meta[token] = cached_meta

            cached_speed_template = source_context.get("speed_template", [])
            page_state: dict = {}
            cq_lines_for_current: list[str] = []

            if not cached_speed_template:
                print(
                    f"[*] [{group_title} {candidate_host}] 本轮尚无 cqshushu CCTV 测速模板；"
                    "开始抓取频道，首次找到足够 CCTV 后立即缓存并供后续候选复用。"
                )
                cq_lines_for_current = fetch_channel_lines_by_s(
                    s_token,
                    session=session,
                    stop_after_test_channels=max(1, test_channels_per_source),
                    page_state=page_state,
                )
                if not cq_lines_for_current:
                    print(
                        f"[-] [{group_title} {candidate_host}] 频道列表未解析到任何频道，"
                        "未进入测速阶段。"
                    )
                    return False

                speed_template = build_cctv_speed_template(cq_lines_for_current)
                if len(speed_template) < max(1, test_channels_per_source):
                    print(
                        f"[-] [{group_title} {candidate_host}] 已解析 {len(cq_lines_for_current)} 条频道，"
                        f"但仅找到 {len(speed_template)} 个可复用的 CCTV1-CCTV17 非标清/非4K测速频道，"
                        f"少于要求的 {max(1, test_channels_per_source)} 个，无法建立测速模板。"
                    )
                    return False

                source_context["speed_template"] = speed_template
                cached_speed_template = speed_template
                print(
                    f"[+] [{group_title}] 已建立 cqshushu CCTV 测速缓存："
                    f"{len(cached_speed_template)} 个频道；后续候选不再重复抓取 CCTV 测速频道列表。"
                )
                relay_host = _source_host_from_lines(cq_lines_for_current) or relay_host or normalize_source_host(candidate_host)
                cached_meta = dict(candidate_meta.get(token, {}))
                cached_meta.update({"s_token": s_token, "relay_host": normalize_source_host(relay_host)})
                candidate_meta[token] = cached_meta
            else:
                print(
                    f"[*] [{group_title} {candidate_host}] 复用本轮 cqshushu CCTV 测速缓存："
                    f"{len(cached_speed_template)} 个频道；仅解析当前候选真实 IP:PORT。"
                )
                if relay_host:
                    print(
                        f"[*] [{group_title} {candidate_host}] 已有本轮 endpoint 缓存：{relay_host}；"
                        "直接套用 CCTV 测速模板。"
                    )
                else:
                    normalized_candidate = normalize_source_host(candidate_host)
                    parsed_candidate = urlparse(
                        candidate_host if "://" in candidate_host else f"http://{candidate_host}"
                    )
                    if parsed_candidate.port is not None:
                        relay_host = normalized_candidate
                        print(f"[+] [{group_title} {candidate_host}] 候选已包含端口：{relay_host}")
                    else:
                        # 这里只请求当前候选 cqshushu 的第1页来提取真实公网 IP:PORT。
                        # 页面中的频道内容不参与本轮测速模板选择；测速仍严格复用第一次缓存的 CCTV RTP。
                        cq_lines_for_current = fetch_channel_lines_by_s(
                            s_token,
                            session=session,
                            max_pages=1,
                            page_state=page_state,
                        )
                        relay_host = _source_host_from_lines(cq_lines_for_current) if cq_lines_for_current else ""
                        if relay_host:
                            print(
                                f"[+] [{group_title} {candidate_host}] 已解析当前真实公网转发地址："
                                f"{relay_host}；第1页仅用于 endpoint 解析，不重新建立测速频道模板。"
                            )
                    if relay_host:
                        cached_meta = dict(candidate_meta.get(token, {}))
                        cached_meta.update({"s_token": s_token, "relay_host": normalize_source_host(relay_host)})
                        candidate_meta[token] = cached_meta

                if not relay_host:
                    print(
                        f"[-] [{group_title} {candidate_host}] 无法解析当前候选真实公网 IP:PORT，"
                        "跳过该源。"
                    )
                    return False

            relay_host = normalize_source_host(relay_host)
            excluded_endpoints = (excluded_endpoints_by_carrier or {}).get(carrier, set())
            if relay_host and relay_host in excluded_endpoints:
                print(
                    f"[*] [{group_title} {candidate_host}] endpoint {relay_host} "
                    "本轮已失效或已被同组槽位占用，跳过。"
                )
                return False

            test_lines = build_template_channel_lines(cached_speed_template, relay_host)
            if not test_lines:
                print(f"[-] [{group_title} {candidate_host}] 无法使用缓存 CCTV 模板构造测速地址。")
                return False

            source_label = f"{group_title} {relay_host}".strip()
            print(
                f"[*] [{source_label}] 测速频道来源=cqshushu首次缓存；"
                f"当前仅替换 endpoint={relay_host}，可测速CCTV={len(test_lines)}。"
            )
            if not is_source_playable(
                test_lines,
                source_label=source_label,
                min_speed_mb_s=min_stream_speed_mb_s,
                sample_seconds=stream_test_seconds,
                test_channels=test_channels_per_source,
            ):
                return False

            # 测速通过后，最终完整频道列表仍严格使用当前候选自己的 cqshushu s_token。
            # 若为了首次测速或 endpoint 解析已经抓过当前候选前几页，则直接复用并从下一页继续。
            if cq_lines_for_current:
                last_page = int(page_state.get("last_page", 0))
                has_next = bool(page_state.get("has_next", False))
                print(
                    f"[+] [{source_label}] 测速通过【{candidate_status}】；最终列表来源仍为 cqshushu。"
                    f"复用当前候选已抓前{last_page}页的 {len(cq_lines_for_current)} 条频道，"
                    f"从第{last_page + 1}页继续完整抓取。"
                )
                if has_next:
                    lines = fetch_channel_lines_by_s(
                        s_token,
                        session=session,
                        initial_lines=cq_lines_for_current,
                        start_page=last_page + 1,
                    )
                else:
                    lines = cq_lines_for_current
            else:
                print(
                    f"[+] [{source_label}] 测速通过【{candidate_status}】；"
                    "最终列表来源仍为 cqshushu，现在从第1页开始抓取完整频道列表。"
                )
                lines = fetch_channel_lines_by_s(
                    s_token,
                    session=session,
                )

            if not lines:
                print(f"[-] [{source_label}] cqshushu 完整频道列表抓取失败，跳过该源。")
                return False

            selected_ops.append(group_title)
            group_to_sources.setdefault(group_title, []).append(lines)
            playable_counts[carrier] = playable_counts.get(carrier, 0) + 1

            print(
                f"[+] [{province}{carrier}] 可用源：{candidate_host}【{candidate_status}】；"
                f"频道来源=cqshushu；已获得 {playable_counts[carrier]}/{target_playable_sources} "
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
            if playable_counts.get(carrier, 0) >= target_playable_sources:
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
                if playable_counts.get(carrier, 0) >= target_playable_sources:
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
    # 第一阶段：扫描第1～5页。前5页完成后立即测试新IP。
    # 第二阶段：若目标未满足，再逐页扫描第6～10页；成功请求后同样随机等待5～10秒，
    #           每抓取一页就立即测试新出现且尚未测试的新IP。
    # 第三阶段：到第10页仍未满足目标时，才允许旧IP兜底。
    # ------------------------------------------------------------
    last_scanned_page = 0
    initial_end = min(5, max_pages)

    for page_num in range(1, initial_end + 1):
        page_rows, ok = fetch_region_page_by_ajax(
            province, page_num, limit=20, session=session,
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
        f"[*] [{province}] 前{last_scanned_page}页扫描完成，不等待第6页，立即筛选并测速新IP。"
    )
    _test_available_candidates(allow_old=False)

    if _targets_complete():
        print(
            f"[+] [{province}] 前{last_scanned_page}页已满足目标，"
            "后续第6～10页不再请求。"
        )
    else:
        # 只有前5页完整扫描到位后才进入6～10页；若前5页因请求失败提前中断，
        # 不跳过失败页继续向后请求，避免在源站异常/限流时继续增加请求压力。
        if last_scanned_page >= initial_end and max_pages > initial_end:
            for page_num in range(initial_end + 1, max_pages + 1):
                if _targets_complete():
                    break
                page_rows, ok = fetch_region_page_by_ajax(
                    province, page_num, limit=20, session=session,
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
                _test_available_candidates(allow_old=False)

                if _targets_complete():
                    print(
                        f"[+] [{province}] 扫描到第{page_num}页后已满足目标，"
                        "停止后续省份服务器列表请求。"
                    )
                    break

        if not _targets_complete():
            print(
                f"[*] [{province}] 已搜索到第{last_scanned_page}页仍未满足目标，"
                "现在开启旧IP兜底；新IP仍保持最高优先级。"
            )
            _test_available_candidates(allow_old=True)

    if not group_to_sources:
        return [], "no_playable_source", province

    for carrier in carriers:
        found = playable_counts.get(carrier, 0)
        tested = tested_counts.get(carrier, 0)
        if found >= target_playable_sources:
            print(
                f"[+] [{province}{carrier}] 已达到目标："
                f"{found}/{target_playable_sources} 个可用播放列表；"
                f"共测试 {tested}/{max_per_carrier} 台候选服务器。"
            )
        else:
            print(
                f"[!] [{province}{carrier}] 搜索结束："
                f"仅获得 {found}/{target_playable_sources} 个可用播放列表；"
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
    ("CCTV16", "4K"),
    ("安徽经济",),
    ("安徽影视",),
    ("安徽公共",),
    ("安徽综艺",),
    ("安徽农业",),
    ("安徽国际",),
    ("CHC影迷电影",),
    ("CHC高清电影",),
    ("CHC动作电影",),
    ("CHC家庭影院",),
    ("北京卫视4K",),
    ("纪实科教4K",),
    ("广东卫视4K",),
    ("深圳卫视4K",),
    ("南国都市4K",),
    ("东方卫视4K",),
    ("欢笑剧场4K",),
    ("江苏卫视4K",),
    ("浙江卫视4K",),
    ("山东卫视4K",),
    ("湖南卫视4K",),
    ("四川卫视4K",),
]


def _is_excluded_4k_channel(channel_name: str) -> bool:
    """含4K但同时标记为SD/标清的频道，不参与任何4K优先排序。"""
    normalized = channel_name.casefold()
    return "4k" in normalized and ("sd" in normalized or "标清" in normalized)


def sort_priority_channels(channel_lines: list[str]) -> list[str]:
    """按指定优先级提升频道，其余频道保持原始相对顺序。

    排序规则：
    1. 先按 PRIORITY_CHANNEL_RULES 的固定顺序提升指定频道；
    2. 未命中固定规则、但名称含4K的频道统一归入“其他4K”；
    3. CCTV4KSD、CCTV4K SD、CCTV4K标清等含SD/标清的4K名称，
       既不进入CCTV4K，也不进入“其他4K”，保持在普通频道中的原始相对位置；
    4. 同一优先级内及所有普通频道均依赖Python稳定排序保持原始顺序。
    """

    other_4k_priority = len(PRIORITY_CHANNEL_RULES)
    normal_priority = other_4k_priority + 1

    def priority_key(line: str) -> int:
        channel_name = line.split(",", 1)[0].strip()
        normalized_name = channel_name.casefold()

        # 这是所有4K优先规则的统一排除条件。
        # 例如 CCTV4KSD / CCTV4K SD / CCTV4K标清：
        # 不进入 CCTV4K，也不进入最后的“其他4K”。
        excluded_4k = _is_excluded_4k_channel(channel_name)

        for index, required_keywords in enumerate(PRIORITY_CHANNEL_RULES):
            rule_is_4k = any("4k" in keyword.casefold() for keyword in required_keywords)
            if excluded_4k and rule_is_4k:
                continue
            if all(
                keyword.casefold() in normalized_name
                for keyword in required_keywords
            ):
                return index

        # 所有明确列出的4K频道之后，再统一提升其他名称的合格4K频道。
        if "4k" in normalized_name and not excluded_4k:
            return other_4k_priority

        return normal_priority

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


def _readme_carrier_group(name: str) -> str:
    """按文件名中的运营商将 README 列表分为电信、联通、移动；无法识别的文件放到“其他”。"""
    stem = os.path.splitext(name)[0]
    for carrier in ("电信", "联通", "移动"):
        if carrier in stem:
            return carrier
    return "其他"


def _build_readme_table_rows(
    repo_root: str,
    subdir: str,
    ext: str,
    update_times: dict[str, str],
    names: list[str] | None = None,
) -> str:
    target_dir = os.path.join(repo_root, subdir)
    if not os.path.exists(target_dir):
        return '<tr><td colspan="4">暂无文件</td></tr>'
    if names is None:
        names = sorted([n for n in os.listdir(target_dir) if n.endswith(ext)])
    else:
        names = sorted(names)
    if not names:
        return '<tr><td colspan="4">暂无文件</td></tr>'

    rows = []
    for name in names:
        relative_path = f"{subdir}/{name}"
        updated_at = update_times.get(relative_path) or get_git_file_update_time(
            repo_root, relative_path
        )
        encoded_name = quote(name)

        if subdir == "m3u":
            # M3U 对外订阅统一走 Secret Gist RAW。Gist ID 只来自环境变量 IPTV_GIST_ID，
            # 由 GitHub Actions 的 secrets.IPTV_GIST_ID 注入，不在仓库源码中保存真实 ID。
            if IPTV_GIST_ID:
                gist_raw_base = f"https://gist.githubusercontent.com/{GIST_OWNER}/{IPTV_GIST_ID}/raw"
                href_url = f"{gist_raw_base}/{encoded_name}"
                copy_url = f"{gist_raw_base}/{name}"
                action_text = "播放链接"
            else:
                # 本地运行或 Secret 未注入时不回退到公开 raw.githubusercontent.com，
                # 避免 Private 架构下误生成失效/不符合预期的公开仓库地址。
                href_url = ""
                copy_url = "未配置 IPTV_GIST_ID"
                action_text = "未配置"
        else:
            # TXT 不发布到 Gist，继续保存在 Private 仓库中；README 本身仅仓库成员可见，
            # 登录 GitHub 后可通过 blob 链接直接查看文件内容。
            href_url = f"{GITHUB_REPO_BLOB_BASE_URL}/{subdir}/{encoded_name}"
            copy_url = f"{GITHUB_REPO_BLOB_BASE_URL}/{subdir}/{name}"
            action_text = "查看文件"

        action_html = (
            f'<a href="{href_url}">{action_text}</a>'
            if href_url else action_text
        )
        rows.append(
            "<tr>"
            f'<td style="white-space:nowrap;">{name}</td>'
            f'<td style="white-space:nowrap;">{action_html}</td>'
            f'<td style="white-space:nowrap;">{updated_at}</td>'
            f'<td><code>{copy_url}</code></td>'
            "</tr>"
        )
    return "\n".join(rows)


def _build_readme_html_table(
    repo_root: str,
    subdir: str,
    ext: str,
    update_times: dict[str, str],
    names: list[str],
) -> str:
    rows = _build_readme_table_rows(repo_root, subdir, ext, update_times, names)
    link_header = "播放链接" if subdir == "m3u" else "仓库链接"
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
        f'<th style="white-space:nowrap;">{link_header}</th>\n'
        '<th style="white-space:nowrap;">最近更新时间</th>\n'
        '<th style="white-space:nowrap;">可复制直链</th>\n'
        "</tr>\n"
        "</thead>\n"
        "<tbody>\n"
        f"{rows}\n"
        "</tbody>\n"
        "</table>"
    )

def _build_readme_section_table(
    repo_root: str,
    subdir: str,
    ext: str,
    update_times: dict[str, str],
) -> str:
    """README 文件列表按运营商分组：电信 → 联通 → 移动 → 其他；组内按文件名排序。"""
    target_dir = os.path.join(repo_root, subdir)
    if not os.path.exists(target_dir):
        return '<table><tbody><tr><td>暂无文件</td></tr></tbody></table>'

    names = [n for n in os.listdir(target_dir) if n.endswith(ext)]
    if not names:
        return '<table><tbody><tr><td>暂无文件</td></tr></tbody></table>'

    groups = {carrier: [] for carrier in ("电信", "联通", "移动", "其他")}
    for name in names:
        groups[_readme_carrier_group(name)].append(name)

    blocks = []
    for carrier in ("电信", "联通", "移动", "其他"):
        carrier_names = groups[carrier]
        if not carrier_names:
            continue
        blocks.append(f"### {carrier}\n\n" + _build_readme_html_table(
            repo_root, subdir, ext, update_times, carrier_names
        ))
    return "\n\n".join(blocks)


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



# ===== 已有播放列表健康检查 / 单槽位修复 =====
HEALTH_CHECK_RETRY_DELAY_MIN_SEC = 5.0
HEALTH_CHECK_RETRY_DELAY_MAX_SEC = 10.0

def parse_existing_m3u_channel_lines(path: str) -> list[str]:
    """读取已生成 M3U，转换成“频道名,播放地址”，供健康检查复用现有测速规则。"""
    try:
        content = Path(path).read_text(encoding="utf-8-sig", errors="ignore")
    except OSError as exc:
        print(f"[-] 无法读取已有播放列表 {path}: {exc}")
        return []
    lines: list[str] = []
    pending_name = ""
    for raw in content.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#EXTINF"):
            pending_name = line.rsplit(",", 1)[-1].strip() if "," in line else ""
            continue
        if line.startswith("#"):
            continue
        if pending_name and line.lower().startswith(("http://", "https://")):
            lines.append(f"{pending_name},{line}")
        pending_name = ""
    return lines

def _health_test_once(
    path: str,
    label: str,
    min_speed_mb_s: float,
    sample_seconds: float = 3.0,
    test_channels: int = 2,
    exclude_urls: set[str] | None = None,
) -> tuple[str, set[str]]:
    """单轮健康检查。返回 (healthy/failed/untestable, 本轮抽测URL集合)。"""
    lines = parse_existing_m3u_channel_lines(path)
    candidates = extract_speed_test_candidates(lines)
    required_count = max(1, test_channels)
    if len(candidates) < required_count:
        print(
            f"[!] [{label}] 可用于健康检查的 CCTV1-CCTV17 非标清/非4K频道不足："
            f"{len(candidates)}/{required_count}；不判定网络失效，也不触发重抓。"
        )
        return "untestable", set()

    excluded = exclude_urls or set()
    fresh = [item for item in candidates if item[1] not in excluded]
    pool = fresh if len(fresh) >= required_count else candidates
    sampled = random.sample(pool, required_count)
    sampled_urls = {url for _, url in sampled}
    if exclude_urls and pool is fresh:
        print(f"[*] [{label}] 复检优先改抽与首轮不同的 {required_count} 个 CCTV 频道。")
    else:
        print(f"[*] [{label}] 从 {len(candidates)} 个候选中随机抽测 {required_count} 个 CCTV 频道。")

    for channel_name, play_url in sampled:
        print(f"[*] [{label}] 健康测速：{channel_name} {play_url}")
        try:
            speed_mb_s, total_bytes = measure_stream_speed(play_url, sample_seconds=sample_seconds)
        except requests.RequestException as exc:
            print(f"[-] [{label}] 健康测速失败：{exc}")
            continue
        print(
            f"[*] [{label}] 下载 {total_bytes / (1024 * 1024):.2f} MB，"
            f"平均速度 {speed_mb_s * 1024:.0f} KB/s，要求 > {min_speed_mb_s * 1024:.0f} KB/s"
        )
        if speed_mb_s > min_speed_mb_s:
            print(f"[+] [{label}] {channel_name} >{min_speed_mb_s * 1024:.0f} KB/s，当前播放列表健康。")
            return "healthy", sampled_urls
        print(f"[-] [{label}] {channel_name} 未达到健康门槛。")
    return "failed", sampled_urls


def existing_playlist_health_check(
    path: str,
    label: str,
    min_speed_mb_s: float = DEFAULT_MIN_STREAM_SPEED_MB_S,
    sample_seconds: float = 3.0,
    test_channels: int = 2,
) -> bool:
    """兼容入口：单轮健康检查；测速门槛与正式抓取保持一致。"""
    status, _ = _health_test_once(
        path, label, min_speed_mb_s, sample_seconds, test_channels
    )
    return status == "healthy"


def _playlist_identity(filename: str):
    """山西联通1.m3u -> (山西, 联通, 山西联通, 1)。"""
    stem = Path(filename).stem
    m = re.match(r"^(.+?)(电信|联通|移动|广电)(\d*)$", stem)
    if not m:
        return None
    province, carrier, suffix = m.group(1), m.group(2), m.group(3)
    if province not in PROVINCE_CODES:
        return None
    return province, carrier, f"{province}{carrier}", suffix


def _source_host_from_lines(lines: list[str]) -> str:
    for line in lines:
        if "," not in line:
            continue
        url = line.split(",", 1)[1].strip()
        parsed = urlparse(url)
        if parsed.hostname:
            return normalize_source_host(parsed.netloc)
    return ""


def _endpoint_ip(endpoint: str) -> str:
    endpoint = normalize_source_host(endpoint)
    if not endpoint:
        return ""
    parsed = urlparse("//" + endpoint)
    return parsed.hostname or endpoint.split(":", 1)[0]


def _source_host_from_m3u(path: str) -> str:
    return _source_host_from_lines(parse_existing_m3u_channel_lines(path))


def _write_single_playlist_slot(repo_root: str, group_title: str, suffix: str, channel_lines: list[str]) -> list[str]:
    """只覆盖一个失效槽位，并同步覆盖同名 TXT；其它健康槽位绝不改动。"""
    file_stem = f"{group_title}{suffix}"
    channel_lines = sort_priority_channels(channel_lines)
    txt_path = os.path.join(repo_root, "txt", f"{file_stem}.txt")
    m3u_path = os.path.join(repo_root, "m3u", f"{file_stem}.m3u")
    txt_content = "\n".join(channel_lines)
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(txt_content + "\n")
    with open(m3u_path, "w", encoding="utf-8") as f:
        f.write(f'#EXTM3U x-tvg-url="{EPG_URL}"\n')
        f.write(txt_to_m3u_format(txt_content, group_title) + "\n")
    return [f"txt/{file_stem}.txt", f"m3u/{file_stem}.m3u"]


def repair_failed_playlist_slot(
    repo_root: str,
    province: str,
    carrier: str,
    group_title: str,
    suffix: str,
    failed_endpoint: str,
    occupied_endpoints: set[str],
    args,
) -> tuple[list[str], str]:
    """
    只为一个失效槽位寻找1个替代源。
    精确 endpoint(IP:port) 才禁止复用；同公网IP的其它端口允许测速采用。
    候选优先级仍优先真正的新公网IP，其次同IP不同端口。
    """
    excluded_endpoints = {normalize_source_host(x) for x in occupied_endpoints if x}
    if failed_endpoint:
        excluded_endpoints.add(normalize_source_host(failed_endpoint))
    deprioritized_ips = {_endpoint_ip(x) for x in excluded_endpoints if _endpoint_ip(x)}

    formal_speed = resolve_min_stream_speed(province, args.min_stream_speed)
    print(
        f"[*] [{group_title}{suffix}.m3u] 启动单槽位修复；正式新源门槛 > {formal_speed * 1024:.0f} KB/s；"
        f"只寻找1个替代源。"
    )
    print(
        f"[*] [{group_title}{suffix}.m3u] 本轮禁止重复 endpoint："
        f"{sorted(excluded_endpoints) or ['无']}；同公网IP不同端口仍允许采用。"
    )

    grouped, status, _ = fetch_channel_lines_by_province(
        province,
        carriers=(carrier,),
        max_pages=args.max_pages,
        max_per_carrier=args.max_per_carrier,
        max_age_hours=args.max_age_hours,
        min_stream_speed_mb_s=formal_speed,
        stream_test_seconds=args.stream_test_seconds,
        test_channels_per_source=args.test_channels_per_source,
        previous_hosts_by_carrier={carrier: set()},
        target_playable_sources=1,
        excluded_endpoints_by_carrier={carrier: excluded_endpoints},
        deprioritized_ips_by_carrier={carrier: deprioritized_ips},
    )
    sources = grouped.get(group_title, []) if grouped else []
    for lines in sources:
        endpoint = _source_host_from_lines(lines)
        if not endpoint:
            continue
        endpoint = normalize_source_host(endpoint)
        if endpoint in excluded_endpoints:
            print(f"[*] [{group_title}{suffix}.m3u] 候选 endpoint {endpoint} 已被占用/失效，跳过。")
            continue
        paths = _write_single_playlist_slot(repo_root, group_title, suffix, lines)
        print(
            f"[+] [{group_title}{suffix}.m3u] 单槽位修复成功："
            f"{failed_endpoint or '未知旧地址'} -> {endpoint}"
        )
        return paths, endpoint

    print(
        f"[!] [{group_title}{suffix}.m3u] 本轮未找到合格且 endpoint 不重复的替代服务器；"
        f"保留原 M3U/TXT，等待下一轮。状态={status}"
    )
    return [], ""


def _normalize_health_file_name(value: str) -> str:
    """规范化指定健康检查/重抓文件名：允许“北京联通1”或“北京联通1.m3u”。"""
    name = (value or "").strip()
    if not name:
        return ""
    # 只接受文件名，禁止借参数越出 m3u 目录。
    name = os.path.basename(name.replace("\\", "/"))
    if not name.lower().endswith(".m3u"):
        name += ".m3u"
    return name


def _selected_health_files(args) -> list[str]:
    """返回最多3个去重后的指定播放列表；全部留空表示沿用原来的全量健康检查模式。"""
    values = [
        getattr(args, "health_file_1", ""),
        getattr(args, "health_file_2", ""),
        getattr(args, "health_file_3", ""),
    ]
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        name = _normalize_health_file_name(value)
        if not name or name in seen:
            continue
        seen.add(name)
        result.append(name)
    return result


def run_health_check_and_repair(repo_root: str, args) -> list[str]:
    """
    健康检查/定向重抓入口。

    未指定 --health-file-1/2/3：保持原行为，按 --health-carriers 检查全部现有 M3U，
    两轮失败后只修复失效槽位。

    指定1～3个播放列表时：只处理指定槽位，未指定文件不测速、不重抓、不改内容/时间。
      - --health-file-mode check：先检查指定旧列表；两轮失败才重抓。
      - --health-file-mode refresh：跳过指定旧列表测速，直接为这些槽位寻找并测速新候选。
    无论哪种指定模式，同组其它槽位只读取现有 endpoint 用于去重，绝不主动测速或更新。
    """
    selected_names = _selected_health_files(args)
    targeted_mode = bool(selected_names)
    file_mode = getattr(args, "health_file_mode", "check")
    if file_mode not in {"check", "refresh"}:
        raise ValueError(f"不支持的 --health-file-mode：{file_mode}")

    m3u_dir = os.path.join(repo_root, "m3u")
    if not os.path.isdir(m3u_dir):
        print("[*] 未发现 m3u 目录，没有可处理的播放列表。")
        return []

    all_files: list[tuple[str, tuple]] = []
    for name in sorted(os.listdir(m3u_dir)):
        ident = _playlist_identity(name)
        if name.endswith(".m3u") and ident:
            all_files.append((name, ident))

    if targeted_mode:
        all_by_name = {name: ident for name, ident in all_files}
        missing = [name for name in selected_names if name not in all_by_name]
        if missing:
            print(
                "[-] 指定的播放列表不存在或文件名无法识别："
                + ", ".join(f"m3u/{name}" for name in missing)
            )
            print("[-] 为避免误处理其它列表，本轮指定列表模式已终止；不会自动扩大到整组或全部文件。")
            return []
        files = [(name, all_by_name[name]) for name in selected_names]
        mode_text = "先测速，失败才重新抓取" if file_mode == "check" else "跳过旧源测速，直接重新抓取"
        print(
            f"[*] 指定播放列表模式：共 {len(files)} 个槽位；处理方式={mode_text}；"
            "未指定播放列表不测速、不重抓、不修改。"
        )
        print(f"[*] 本轮指定列表：{', '.join(name for name, _ in files)}")
    else:
        selected_health_carriers = set(parse_carrier_selection(args.health_carriers))
        files = [
            (name, ident) for name, ident in all_files
            if ident[1] in selected_health_carriers
        ]
        if not files:
            print(f"[*] 未发现可健康检查的 M3U 文件；运营商={','.join(selected_health_carriers)}。")
            return []
        print(
            f"[*] 健康检查模式：运营商={','.join(selected_health_carriers)}；共 {len(files)} 个现有 M3U；"
            "按省份逐组处理；每个随机抽2个CCTV；测速门槛与正式抓取完全一致。"
        )

    # 只把“本轮需要处理”的槽位按省份+运营商分组。
    grouped_files: dict[str, list[tuple[str, tuple]]] = {}
    group_order: list[str] = []
    for name, ident in files:
        group_title = ident[2]
        if group_title not in grouped_files:
            grouped_files[group_title] = []
            group_order.append(group_title)
        grouped_files[group_title].append((name, ident))

    # 建立全部现有槽位索引。指定模式下，这些未指定同组文件只用于读取 endpoint 去重。
    all_group_files: dict[str, list[tuple[str, tuple]]] = {}
    for name, ident in all_files:
        all_group_files.setdefault(ident[2], []).append((name, ident))

    changed: list[str] = []

    for group_title in group_order:
        group_files = grouped_files[group_title]
        province = group_files[0][1][0]
        carrier = group_files[0][1][1]
        if targeted_mode:
            print(
                f"\n[*] ===== 开始处理 {group_title}：本轮指定 {len(group_files)} 个槽位；"
                f"同组其它槽位仅用于 endpoint 去重 ====="
            )
        else:
            print(f"\n[*] ===== 开始处理 {group_title}：现有 {len(group_files)} 个播放列表槽位 =====")

        health_status: dict[str, str] = {}
        hosts: dict[str, str] = {}

        # 先读取同组所有现有 endpoint。读取不产生网络请求，只用于避免新抓取结果与现有槽位重复。
        sibling_files = all_group_files.get(group_title, group_files)
        for sibling_name, _ in sibling_files:
            sibling_path = os.path.join(m3u_dir, sibling_name)
            hosts[sibling_name] = _source_host_from_m3u(sibling_path)

        if targeted_mode and file_mode == "refresh":
            # 强制重抓：不测试旧源，但新候选仍必须经过正式测速门槛。
            for name, _ in group_files:
                health_status[name] = "refresh"
                print(
                    f"[*] [{name}] 指定为直接重新抓取：跳过旧列表健康测速；"
                    "旧文件暂时保留，只有找到测速合格的新 endpoint 后才覆盖。"
                )
        else:
            # 普通模式，或指定模式 check：只检测本轮 group_files。
            for name, ident in group_files:
                path = os.path.join(m3u_dir, name)
                health_min_speed = resolve_min_stream_speed(province, args.min_stream_speed)
                print(
                    f"[*] [{name}] 健康检查测速门槛与正式抓取一致："
                    f"> {health_min_speed * 1024:.0f} KB/s。"
                )
                status, first_urls = _health_test_once(
                    path, name, health_min_speed, args.health_stream_test_seconds, 2
                )
                if status == "failed":
                    delay = random.uniform(HEALTH_CHECK_RETRY_DELAY_MIN_SEC, HEALTH_CHECK_RETRY_DELAY_MAX_SEC)
                    print(f"[!] [{name}] 首轮健康检查失败；{delay:.1f}秒后重新抽2个CCTV复检。")
                    time.sleep(delay)
                    status, _ = _health_test_once(
                        path,
                        name,
                        health_min_speed,
                        args.health_stream_test_seconds,
                        2,
                        exclude_urls=first_urls,
                    )
                health_status[name] = status
                result_text = {
                    "healthy": "HEALTHY，保持现状",
                    "failed": "FAILED，需要单槽位修复",
                    "untestable": "UNTESTABLE，可测试CCTV不足，本轮保持现状",
                }[status]
                print(
                    f"[{'+' if status == 'healthy' else '!' if status == 'untestable' else '-'}] "
                    f"[{name}] 健康检查最终结果：{result_text}。"
                )

        repair_files = [
            (name, ident) for name, ident in group_files
            if health_status.get(name) in {"failed", "refresh"}
        ]

        if not repair_files:
            if targeted_mode:
                print(
                    f"[+] [{group_title}] 本轮指定槽位均无需重抓；"
                    "指定文件及同组其它文件、更新时间全部保持不变。"
                )
            else:
                print(
                    f"[+] [{group_title}] 本组健康检查完成：没有失效槽位；"
                    "现有 M3U/TXT 及上一次更新时间全部保持不变。"
                )
            continue

        if targeted_mode and file_mode == "refresh":
            print(
                f"[*] [{group_title}] 将直接重抓 {len(repair_files)} 个指定槽位；"
                "旧源不参与健康判定，新候选仍必须通过正式测速。"
            )
        else:
            print(
                f"[!] [{group_title}] 检测到 {len(repair_files)} 个失效槽位；"
                "现在立即完成本省份定向修复，修复结束后才进入下一个省份。"
            )

        # 占用池规则：
        # - 普通全量健康检查：沿用原逻辑，只占用健康/不可测槽位和本轮刚修复的新 endpoint。
        # - 指定列表模式：同组所有现有槽位 endpoint 都先占用（包含被指定重抓槽位的旧 endpoint），
        #   这样既不会撞到未指定列表，也不会把另一个指定槽位的旧 endpoint 当作“新源”互换回来。
        occupied_endpoints: set[str] = set()
        if targeted_mode:
            for sibling_name, _ in sibling_files:
                endpoint = hosts.get(sibling_name, "")
                if endpoint:
                    occupied_endpoints.add(endpoint)
            print(
                f"[*] [{group_title}] 已读取同组 {len(sibling_files)} 个现有槽位用于 endpoint 去重；"
                f"占用 endpoint={len(occupied_endpoints)} 个。未指定槽位不会测速或更新。"
            )
        else:
            for name, _ in group_files:
                if health_status.get(name) in {"healthy", "untestable"} and hosts.get(name):
                    occupied_endpoints.add(hosts[name])

        group_changed: list[str] = []
        repaired_slots = 0
        unrepaired_slots = 0

        # 当前仍采用“每个槽位独立找到1个替代源”的稳定逻辑。
        for name, (slot_province, slot_carrier, slot_group_title, suffix) in repair_files:
            action_label = "强制重抓" if health_status.get(name) == "refresh" else "失效修复"
            print(f"[*] [{name}] 开始{action_label}。")
            paths, new_endpoint = repair_failed_playlist_slot(
                repo_root,
                slot_province,
                slot_carrier,
                slot_group_title,
                suffix,
                hosts.get(name, ""),
                occupied_endpoints,
                args,
            )
            if paths:
                changed.extend(paths)
                group_changed.extend(paths)
                repaired_slots += 1
                if new_endpoint:
                    occupied_endpoints.add(new_endpoint)
                    hosts[name] = new_endpoint
                    health_status[name] = "healthy"
            else:
                unrepaired_slots += 1

        if group_changed:
            # 只有真正抓到新 endpoint 并覆盖文件时才更新时间。
            record_province_update_times(repo_root, province, group_changed)
            if targeted_mode:
                print(
                    f"[+] [{group_title}] 指定槽位处理完成：成功更新 {repaired_slots} 个"
                    + (f"；{unrepaired_slots} 个未找到合格替代源，旧文件保持不变。" if unrepaired_slots else "。")
                )
                print("[*] 未指定播放列表没有测速、没有重抓、没有修改更新时间。")
            else:
                print(
                    f"[+] [{group_title}] 本组定向修复完成：成功更新 {repaired_slots} 个失效槽位"
                    + (f"；仍有 {unrepaired_slots} 个槽位未找到合格替代源，旧文件保持不变。" if unrepaired_slots else "。")
                )
                print(
                    f"[*] [{group_title}] 上方记录的更新时间仅对应本轮实际抓取到新 IP/播放列表并生成的文件；"
                    "原本测速有效的文件继续保持上一次记录。"
                )
        else:
            print(
                f"[!] [{group_title}] 本轮需要重抓的槽位均未找到合格替代源；"
                "保留原 M3U/TXT 和原更新时间，不写入新的完成时间。"
            )

    if changed:
        update_readme_file_list(repo_root)
    return changed

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
    将本次生成文件提交并安全推送到当前 GitHub 仓库。

    若远程 main 在本次抓取期间被其他 Action 或人工提交更新，普通 git push
    可能出现 non-fast-forward。此处不使用 force push，而是在推送前先 fetch +
    rebase origin/main；若推送竞态仍导致 non-fast-forward，则最多自动重试3次。
    """
    print("\n[*] 正在同步到 GitHub 当前仓库...")

    def run_git(args):
        return subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )

    try:
        # 只暂存本次明确需要发布的文件；历史成功列表不会因本次失败被删除。
        add_run = run_git(["add", "-A", "--"] + files)
        if add_run.returncode != 0:
            raise RuntimeError(f"git add 失败:\n{add_run.stderr.strip()}")

        check_run = run_git(["diff", "--cached", "--quiet"])
        if check_run.returncode == 0:
            print("[*] 没有新增变更，无需提交。")
            return True

        target = f" {province}" if province else ""
        commit_msg = f"{GITHUB_COMMIT_PREFIX}{target} multicast files at {time.strftime('%Y-%m-%d %H:%M:%S')}"
        commit_run = run_git(["commit", "-m", commit_msg])
        if commit_run.returncode != 0:
            raise RuntimeError(f"git commit 失败:\n{commit_run.stderr.strip()}")
        print("[+] git commit 成功。")

        max_push_attempts = 3
        for attempt in range(1, max_push_attempts + 1):
            # 每次 push 前同步远程，避免覆盖其他 Action/人工提交。
            fetch_run = run_git(["fetch", "origin", "main"])
            if fetch_run.returncode != 0:
                raise RuntimeError(f"git fetch origin main 失败:\n{fetch_run.stderr.strip()}")

            rebase_run = run_git(["rebase", "origin/main"])
            if rebase_run.returncode != 0:
                # 冲突时立即终止 rebase，保持仓库处于可诊断状态；绝不 force push。
                run_git(["rebase", "--abort"])
                raise RuntimeError(
                    "git rebase origin/main 失败，可能存在远程并发修改冲突：\n"
                    f"{rebase_run.stderr.strip()}"
                )

            push_run = run_git(["push", "origin", "HEAD:main"])
            if push_run.returncode == 0:
                print(f"[+] 已成功推送到 GitHub（第 {attempt}/{max_push_attempts} 次尝试）。")
                return True

            push_error = (push_run.stderr or "").strip()
            is_non_fast_forward = (
                "non-fast-forward" in push_error.lower()
                or "fetch first" in push_error.lower()
                or "rejected" in push_error.lower()
            )
            if is_non_fast_forward and attempt < max_push_attempts:
                print(
                    f"[!] git push 第 {attempt}/{max_push_attempts} 次遇到远程并发更新，"
                    "重新 fetch + rebase 后再推送。"
                )
                time.sleep(random.uniform(2.0, 5.0))
                continue

            raise RuntimeError(f"git push 失败:\n{push_error}")

        raise RuntimeError("git push 重试次数已耗尽。")
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
    ap = argparse.ArgumentParser(description="IPTV 双模式：按省份完整抓取，或检查现有M3U并对失效槽位定向修复。")
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
        help="每个省份组播服务器列表动态搜索最大10页；前5页后先测速，不足目标再进入第6～10页。",
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
        help="显式覆盖所有省份的测速门槛，单位MB/s；不填写时四川400KB/s、其他省份750KB/s。",
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
    ap.add_argument(
        "--health-check", action="store_true",
        help="健康检查/定向重抓模式：未指定文件时按 --health-carriers 检查全部M3U；也可用 --health-file-1/2/3 精确指定最多3个槽位。",
    )
    ap.add_argument(
        "--health-carriers", default="全部",
        help="健康检查仅处理指定运营商，例如：电信 或 联通；默认全部。",
    )
    ap.add_argument(
        "--health-file-1", default="",
        help="可选：只处理指定播放列表槽位1，例如 北京联通1.m3u；也可省略 .m3u。",
    )
    ap.add_argument(
        "--health-file-2", default="",
        help="可选：只处理指定播放列表槽位2；留空忽略。",
    )
    ap.add_argument(
        "--health-file-3", default="",
        help="可选：只处理指定播放列表槽位3；留空忽略。最多指定3个且自动去重。",
    )
    ap.add_argument(
        "--health-file-mode", choices=("check", "refresh"), default="check",
        help=(
            "指定 --health-file-1/2/3 时的处理方式："
            "check=先测速旧列表，两轮失败才重抓；"
            "refresh=不测试旧列表，直接寻找并测速新候选。默认check。"
        ),
    )
    ap.add_argument(
        "--health-stream-test-seconds", type=float, default=3.0,
        help="已有播放列表健康检查单频道测速时长，单位秒（默认3）。",
    )
    return ap.parse_args()


def main():
    args = parse_args()

    # 省份组播服务器列表统一采用最大10页动态搜索。
    # 当前 GitHub Actions 仍可能传入旧的 --max-pages 值；这里统一覆盖为10。
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

    if args.health_check:
        os.makedirs(txt_output_dir, exist_ok=True)
        os.makedirs(m3u_output_dir, exist_ok=True)
        changed = run_health_check_and_repair(repo_root, args)
        if changed:
            if args.push:
                publish_paths = sorted(set(changed + [README_FILE]))
                if os.path.exists(os.path.join(repo_root, UPDATE_TIMES_FILE)):
                    publish_paths.append(UPDATE_TIMES_FILE)
                push_to_github(publish_paths, province="健康检查修复")
            else:
                print(f"[+] 健康检查完成：成功修复 {len(changed)//2} 个失效播放列表；未启用 --push。")
        else:
            print("[*] 健康检查完成：没有需要发布的新文件（全部健康，或失效槽位暂未找到合格替代源）。")
        return
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
