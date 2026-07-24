import os
import re
import time
import subprocess
import argparse
from datetime import datetime
from html import unescape
from urllib.parse import quote
from curl_cffi import requests

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

MULTICAST_SOURCE_URL = "https://iptv.cqshushu.com/index.php?t=multicast"
GITHUB_COMMIT_PREFIX = "Auto update IPTV cqshushu"
EPG_URL = "http://epg.51zmt.top:8000/e.xml.gz"
TVG_LOGO_BASE_URL = "https://gcore.jsdelivr.net/gh/taksssss/tv/icon/"
README_FILE = "README_IPTV.md"
RAW_BASE_URL = "https://raw.githubusercontent.com/jia070310/4K-IPTV-M3U/main"
PROXY_PREFIX = "https://gh-proxy.org/"

PROVINCES = ["安徽", "四川", "浙江"]

def _strip_html(raw):
    no_tags = re.sub(r"<[^>]+>", "", raw)
    return unescape(no_tags).replace("\xa0", " ").strip()

def _parse_site_datetime(value: str) -> datetime | None:
    s = (value or "").strip()
    if not s: return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try: return datetime.strptime(s, fmt)
        except ValueError: continue
    return None

def get_session():
    session = requests.Session(impersonate="chrome120")
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": "https://iptv.cqshushu.com/"
    })
    return session

def fetch_region_rows_from_html(session, province, max_pages=30):
    print(f"[*] 正在抓取组播源页面，寻找 {province} 节点...")
    try:
        home_resp = session.get(MULTICAST_SOURCE_URL, timeout=20)
    except Exception as e:
        print(f"[-] 访问主页失败: {e}")
        return []

    # 动态获取省份的代码映射 (如 ah, sc, zj)
    code_map = {}
    m_select = re.search(r'<select name="province"[^>]*>(.*?)</select>', home_resp.text, flags=re.S | re.I)
    if m_select:
        for match in re.finditer(r'<option value="([^"]+)"[^>]*>(.*?)</option>', m_select.group(1)):
            code_map[_strip_html(match.group(2))] = match.group(1).strip()
            
    region_code = code_map.get(province)
    if not region_code:
        print(f"[-] 页面中未找到省份 [{province}] 的 region code。")
        return []

    all_rows = []
    seen_tokens = set()

    for page_num in range(1, max_pages + 1):
        url = f"{MULTICAST_SOURCE_URL}&province={region_code}&limit=6&page={page_num}"
        try:
            resp = session.get(url, timeout=20)
            html = resp.text
        except Exception as e:
            print(f"[-] 获取省份 [{province}] 第{page_num}页失败: {e}")
            break
            
        # 解析表格中的行
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, flags=re.S | re.I)
        added = 0
        for row in rows:
            if 'data-label="IP:"' not in row: continue
            
            # 提取 Token 和 IP
            m_ip = re.search(r"gotoIP\('([^']+)',\s*'[^']+'\).*?>\s*([\d\.:]+)\s*<", row, re.S)
            if not m_ip: continue
            
            p_token = m_ip.group(1)
            if p_token in seen_tokens: continue
            
            # 提取信息
            m_type = re.search(r'<td data-label="类型:">(.*?)</td>', row, re.S)
            m_update = re.search(r'<td data-label="更新时间:">(.*?)</td>', row, re.S)
            m_status = re.search(r'<span class="status-badge[^>]*>(.*?)</span>', row, re.S)
            
            all_rows.append({
                "p_token": p_token,
                "host": m_ip.group(2).strip(),
                "type": _strip_html(m_type.group(1)) if m_type else "",
                "update_time": _strip_html(m_update.group(1)) if m_update else "",
                "status": _strip_html(m_status.group(1)) if m_status else ""
            })
            seen_tokens.add(p_token)
            added += 1
            
        print(f"[*] [{province}] 第{page_num}页抓取完成，新增 {added} 条。")
        # 如果当前页没有新增数据，说明已经到底了，退出翻页
        if added == 0: break

    print(f"[*] [{province}] 全分页合计抓取到 {len(all_rows)} 条服务器。")
    return all_rows

def normalize_group_title(raw_type: str, province: str) -> str:
    text = (raw_type or "").strip()
    if not text: return province
    if "|" in text:
        right = text.split("|")[-1].strip()
        if right: return right
    for carrier in ("电信", "联通", "移动", "广电"):
        if carrier in text: return f"{province}{carrier}"
    return province

def fetch_channel_lines_by_province(province: str, max_per_carrier: int = 10, max_pages: int = 30, max_age_hours: int = 72):
    session = get_session()
    rows = fetch_region_rows_from_html(session, province, max_pages=max_pages)
    if not rows: return [], "list_empty", province

    now_dt = datetime.now()

    def _is_usable_status(status: str) -> bool:
        return ("新上线" in status) or ("存活" in status)

    def _is_recent_update(row: dict) -> bool:
        dt = _parse_site_datetime(row.get("update_time", "")) or _parse_site_datetime(row.get("online_time", ""))
        if not dt: return False
        age_hours = (now_dt - dt).total_seconds() / 3600
        return age_hours <= max_age_hours

    selected_rows = []
    selected_tokens = set()
    for carrier in ("电信", "移动", "联通"):
        carrier_rows = [r for r in rows if carrier in r.get("type", "") and _is_usable_status(r.get("status", "")) and _is_recent_update(r)]
        carrier_rows = sorted(carrier_rows, key=lambda x: _parse_site_datetime(x.get("update_time", "")).timestamp() if _parse_site_datetime(x.get("update_time", "")) else 0.0, reverse=True)
        
        for row in carrier_rows[:max_per_carrier]:
            if row["p_token"] not in selected_tokens:
                selected_rows.append(row)
                selected_tokens.add(row["p_token"])

    if not selected_rows: return [], "no_recent_new_or_alive", province

    group_to_sources: dict[str, list[list[str]]] = {}
    
    # 🚨 这里是最后的断点 🚨
    for picked in selected_rows:
        group_title = normalize_group_title(picked.get("type", ""), province)
        print(f"[-] 找到优质节点: {picked['host']} ({group_title})，但缺少获取详情页的 API 接口数据！")
        # 由于我们不知道 gotoIP() 函数向后端发送了什么请求，代码在这里必须中断。

    if not group_to_sources: return [], "channel_lines_empty", province
    return group_to_sources, "ok", province

# ... (后续生成 README 和 git push 的代码保持不变，为节省篇幅略过) ...

def main():
    repo_root = os.path.dirname(os.path.abspath(__file__))
    for province in PROVINCES:
        print(f"\n{'='*50}\n 正在处理地区任务: {province}\n{'='*50}")
        fetch_channel_lines_by_province(province)

if __name__ == '__main__':
    main()
