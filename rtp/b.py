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
# 来源选择：remote_templates.txt 远程动态模板优先；失败后尝试本地 .m3u、.txt；仍无有效模板才锁定使用 cqshushu。
# 同一“省份+运营商”一次运行中来源锁定后不再混用。
# 模板只提供“频道名称 + 组播地址”；支持 rtp://、HTTP /rtp/ 和 udpxy 风格 HTTP /udp/。
# /udp/ 仅作为模板输入格式兼容，最终公网播放地址仍统一输出为 HTTP /rtp/。
# 最终 tvg-id/tvg-logo/group-title、EPG 和排序仍完全沿用本脚本现有输出逻辑。
CHANNEL_TEMPLATE_DIR = "channel_templates"
# 远程动态频道模板映射。每行格式：省份运营商=远程M3U/TXT地址；# 开头为注释。
# 远程模板优先于同名本地模板；下载/解析失败时自动回退本地模板，再无本地模板才使用 cqshushu。
REMOTE_TEMPLATE_CONFIG = os.path.join(CHANNEL_TEMPLATE_DIR, "remote_templates.txt")
_REMOTE_TEMPLATE_CONFIG_CACHE: dict[str, str] | None = None
_REMOTE_TEMPLATE_FETCH_CACHE: dict[str, tuple[list[tuple[str, str]], str | None]] = {}

# 一次脚本运行期间按“省份+运营商”锁定频道来源并复用测速频道模板。
# mode=template：测速和最终列表使用已锁定的远程/本地模板；cqshushu 仅用于解析候选真实 IP:PORT。
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

# “全部省份抓取”仅遍历中国大陆31个省级地区；台湾、俄罗斯、韩国不进入自动全国扫描。
ALL_MAINLAND_PROVINCES = [
    province for province in PROVINCE_CODES
    if province not in {"台湾", "俄罗斯", "韩国"}
]

# 全国抓取时的运营商优先省份。优先列表只改变执行顺序，不会重复抓取；
# 优先省份完成后继续处理其余全部大陆省份。
CARRIER_PRIORITY_PROVINCES = {
    "电信": ["四川", "浙江", "湖北", "安徽", "山西", "广东", "湖南", "河北", "陕西", "福建"],
    "联通": ["北京", "四川", "天津", "山东", "山西", "河北", "河南", "海南", "重庆", "黑龙江"],
    "移动": [],
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

    同时兼容 rtp://239.x.x.x:port、HTTP/HTTPS /rtp/ 与 /udp/ 模板地址；
    HTTP 主机既可是真实 IP:PORT，也可使用 {{your_udpxy_address}} 等占位符。
    /udp/ 只用于读取模板中的组播目标，最终输出仍统一生成 HTTP /rtp/ 地址；
    模板中的转发主机仅作为占位，最终会替换为当前候选的真实 endpoint。
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
            # 以 EXTINF 最后一个逗号后的显示名称为准；若没有
