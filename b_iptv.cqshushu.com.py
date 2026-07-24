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

# ================= 配置区域 =================
# 修复：只保留纯净的根域名地址，避免拼接出双问号
BASE_URL = "https://iptv.cqshushu.com/index.php"
GITHUB_COMMIT_PREFIX = "Auto update IPTV cqshushu"
EPG_URL = "http://epg.51zmt.top:8000/e.xml.gz"
TVG_LOGO_BASE_URL = "https://gcore.jsdelivr.net/gh/taksssss/tv/icon/"
README_FILE = "README_IPTV.md"
RAW_BASE_URL = "https://raw.githubusercontent.com/jia070310/4K-IPTV-M3U/main"
PROXY_PREFIX = "https://gh-proxy.org/"

# 你需要的省份列表
PROVINCES = ["安徽", "四川", "浙江"]
# ============================================

def clear_output_files(txt_output_dir, m3u_output_dir):
    for out_dir, suffix in ((txt_output_dir, ".txt"), (m3u_output_dir, ".m3u")):
        if not os.path.exists(out_dir):
            continue
        for name in os.listdir(out_dir):
            if name.endswith(suffix):
                try:
                    os.remove(os.path.join(out_dir, name))
                except OSError:
                    pass

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
    # 使用 curl_cffi 完美伪装浏览器，突破防火墙
    session = requests.Session(impersonate="chrome120")
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": "https://iptv.cqshushu.com/"
    })
    return session

def parse_channel_lines(html_text: str) -> list[str]:
    """ 从任意 HTML 中强力提取频道列表（兼容表格与纯文本） """
    lines = []
    
    # 方式 1：解析表格 (<td>频道名</td> <td>链接</td>)
    for row_html in re.findall(r"<tr[^>]*>(.*?)</tr>", html_text, flags=re.IGNORECASE | re.DOTALL):
        tds = re.findall(r"<td[^>]*>(.*?)</td>", row_html, flags=re.IGNORECASE | re.DOTALL)
        if len(tds) >= 2:
            name = _strip_html(tds[0] if len(tds) == 2 else tds[1])
            play_url = _strip_html(tds[1] if len(tds) == 2 else tds[2])
            if re.search(r"^(https?://|rtp/|udp/|igmp/)", play_url, flags=re.IGNORECASE):
                lines.append(f"{name},{play_url}")
                
    # 方式 2：解析纯文本的 "频道名,链接" 格式
    text_lines = html_text.split('\n')
    for line in text_lines:
        line = _strip_html(line).strip()
        if ',' in line:
            parts = line.split(',', 1)
            if re.search(r"^(https?://|rtp/|udp/|igmp/)", parts[1].strip(), flags=re.IGNORECASE):
                lines.append(f"{parts[0].strip()},{parts[1].strip()}")
                
    # 去重并返回
    return list(dict.fromkeys(lines))

def fetch_region_data(session, province, max_pages=30):
    print(f"[*] 正在模拟用户搜索，寻找 [{province}] ...")
    all_rows = []
    all_direct_channels = []
    seen_tokens = set()

    for page_num in range(1, max_pages + 1):
        # 🚨 核心修复：纯净 URL 拼接，避免出现双问号
        url = f"{BASE_URL}?q={quote(province)}&page={page_num}"
        
        try:
            resp = session.get(url, timeout=20)
            html = resp.text
        except Exception as e:
            print(f"[-] 获取省份 [{province}] 第{page_num}页失败: {e}")
            break
            
        # 探针 1：搜索页是否直接返回了播放链接？
        channels = parse_channel_lines(html)
        if channels:
            all_direct_channels.extend(channels)
            
        # 探针 2：解析 IP 节点表格
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, flags=re.S | re.I)
        added = 0
        
        for row in rows:
            if 'data-label="IP:"' not in row: continue
            
            # 提取 JS 函数中的 Token 和显示的 IP 地址
            m_ip = re.search(r"gotoIP\(['\"]([^'\"]+)['\"].*?>\s*([\d\.:]+)\s*<", row, re.S)
            if not m_ip: continue
            
            p_token = m_ip.group(1)
            if p_token in seen_tokens: continue
            
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
            
        print(f"[*] [{province}] 第{page_num}页搜索完成，新增 {added} 个节点，{len(channels)} 个直链。")
        
        # 翻页结束条件
        if added == 0 and len(channels) == 0: 
            break

    print(f"[*] [{province}] 合计抓取到 {len(all_rows)} 个有效服务器，{len(all_direct_channels)} 个直链。")
    return all_rows, list(dict.fromkeys(all_direct_channels))

def extract_channels_for_token(session, p_token):
    """ 黑盒探测：尝试枚举常见的详情页 API 和路由提取频道 """
    endpoints = [
        f"https://iptv.cqshushu.com/detail.php?id={p_token}",
        f"https://iptv.cqshushu.com/iptv_detail.php?p={p_token}",
        f"https://iptv.cqshushu.com/index.php?t=detail&p={p_token}",
        f"https://iptv.cqshushu.com/api.php?action=channels&p={p_token}"
    ]
    
    for url in endpoints:
        try:
            resp = session.get(url, timeout=10)
            lines = parse_channel_lines(resp.text)
            if lines:
                return lines
        except Exception:
            continue
            
    return []

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
    rows, direct_channels = fetch_region_data(session, province, max_pages=max_pages)
    
    group_to_sources: dict[str, list[list[str]]] = {}
    
    # 如果搜索结果直接就是频道列表（没有节点），直接打包返回
    if direct_channels:
        group_to_sources.setdefault(f"{province}直接提取", []).append(direct_channels)
        return group_to_sources, "ok", province

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
    
    # 按三大运营商分别筛选最优节点
    for carrier in ("电信", "移动", "联通"):
        carrier_rows = [r for r in rows if carrier in r.get("type", "") and _is_usable_status(r.get("status", "")) and _is_recent_update(r)]
        carrier_rows = sorted(carrier_rows, key=lambda x: _parse_site_datetime(x.get("update_time", "")).timestamp() if _parse_site_datetime(x.get("update_time", "")) else 0.0, reverse=True)
        
        for row in carrier_rows[:max_per_carrier]:
            if row["p_token"] not in selected_tokens:
                selected_rows.append(row)
                selected_tokens.add(row["p_token"])

    if not selected_rows: return [], "no_recent_new_or_alive", province

    success_count = 0
    for picked in selected_rows:
        group_title = normalize_group_title(picked.get("type", ""), province)
        token = picked.get("p_token", "")
        
        # 盲抓频道详情
        lines = extract_channels_for_token(session, token)
        
        if lines:
            group_to_sources.setdefault(group_title, []).append(lines)
            success_count += 1
        else:
            print(f"[-] 节点 {picked['host']} ({group_title}) 探针失效，未能提取到播放直链。")

    if not group_to_sources:
        return [], "channel_lines_empty_all_routes_failed", province
        
    return group_to_sources, "ok", province

def build_tvg_logo_url(channel_name: str) -> str:
    safe_name = quote(channel_name.strip(), safe="")
    return f"{TVG_LOGO_BASE_URL}{safe_name}.png"

def txt_to_m3u_format(txt_content, group_title):
    m3u_lines = []
    for line in txt_content.splitlines():
        line = line.strip()
        if not line or '#genre#' in line: continue
        if ',' in line:
            name, url = [p.strip() for p in line.split(',', 1)]
            m3u_lines.append(f'#EXTINF:-1 tvg-id="{name}" tvg-logo="{build_tvg_logo_url(name)}" group-title="{group_title}",{name}\n{url}')
    return "\n".join(m3u_lines)

def _build_readme_section_table(repo_root: str, subdir: str, ext: str, updated_at: str) -> str:
    target_dir = os.path.join(repo_root, subdir)
    if not os.path.exists(target_dir): return '暂无文件\n'
    names = sorted([n for n in os.listdir(target_dir) if n.endswith(ext)])
    if not names: return '暂无文件\n'

    rows = []
    for name in names:
        encoded_name = quote(name)
        proxy_url = f"{PROXY_PREFIX}{RAW_BASE_URL}/{subdir}/{encoded_name}"
        rows.append(f"| {name} | [下载链接]({proxy_url}) | {updated_at} | `{proxy_url}` |")
    
    header = "| 文件名 | 加速链接 | 最近更新时间 | 可复制直链 |\n| --- | --- | --- | --- |\n"
    return header + "\n".join(rows)

def update_readme_file_list(repo_root: str) -> None:
    readme_path = os.path.join(repo_root, README_FILE)
    updated_at = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S") if ZoneInfo else datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    m3u_table = _build_readme_section_table(repo_root, "m3u_iptv", ".m3u", updated_at)
    txt_table = _build_readme_section_table(repo_root, "txt_iptv", ".txt", updated_at)
    
    content = f"# 新源 IPTV 文件列表\n\n## M3U 文件列表\n\n{m3u_table}\n\n## TXT 文件列表\n\n{txt_table}\n"
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[+] {README_FILE} 文件列表已自动生成/更新。")

def process_province(province, txt_output_dir, m3u_output_dir, max_pages, max_per_carrier, max_age_hours):
    grouped_sources, status, _ = fetch_channel_lines_by_province(province, max_per_carrier, max_pages, max_age_hours)
    if not grouped_sources:
        print(f"[-] [{province}] 频道提取最终失败: {status}")
        return

    total_channels = exported_sources = 0
    for group_title, sources in grouped_sources.items():
        for idx, channel_lines in enumerate(sources):
            if not channel_lines: continue
            suffix = str(idx + 1)
            file_stem = f"{group_title}{suffix}"
            out_txt = os.path.join(txt_output_dir, f"{file_stem}.txt")
            out_m3u = os.path.join(m3u_output_dir, f"{file_stem}.m3u")
            txt_content = "\n".join(channel_lines)
            
            with open(out_txt, 'w', encoding='utf-8') as f_txt, open(out_m3u, 'w', encoding='utf-8') as f_m3u:
                f_txt.write(txt_content + "\n")
                f_m3u.write(f'#EXTM3U x-tvg-url="{EPG_URL}"\n')
                f_m3u.write(txt_to_m3u_format(txt_content, group_title) + "\n")
            exported_sources += 1
            total_channels += len(channel_lines)
    print(f"[+] 完美！[{province}] 更新完成，导出 {total_channels} 条频道，生成 {exported_sources} 条源文件。")

def push_to_github(files):
    existing_files = [f for f in files if os.path.exists(f)]
    if not existing_files: return
    try:
        subprocess.run(["git", "add", "--"] + existing_files, capture_output=True)
        check = subprocess.run(["git", "diff", "--cached", "--quiet"], capture_output=True)
        if check.returncode == 0: return
        subprocess.run(["git", "commit", "-m", f"{GITHUB_COMMIT_PREFIX} at {time.strftime('%Y-%m-%d %H:%M:%S')}"], capture_output=True)
        subprocess.run(["git", "push"], capture_output=True)
        print("[+] 已成功推送到 GitHub。")
    except Exception as e:
        print(f"[!] GitHub 同步异常: {e}")

def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--push", action="store_true")
    ap.add_argument("--max-age-hours", type=int, default=168) # 进一步放宽限制到一周内
    ap.add_argument("--max-per-carrier", type=int, default=10)
    ap.add_argument("--max-pages", type=int, default=30)
    return ap.parse_args()

def main():
    args = parse_args()
    repo_root = os.path.dirname(os.path.abspath(__file__))
    
    txt_output_dir = os.path.join(repo_root, "txt_iptv")
    m3u_output_dir = os.path.join(repo_root, "m3u_iptv")
    
    os.makedirs(txt_output_dir, exist_ok=True)
    os.makedirs(m3u_output_dir, exist_ok=True)
    clear_output_files(txt_output_dir, m3u_output_dir)

    for province in PROVINCES:
        print(f"\n{'='*50}\n 正在处理地区任务: {province}\n{'='*50}")
        process_province(province, txt_output_dir, m3u_output_dir, args.max_pages, args.max_per_carrier, args.max_age_hours)

    generated_files = [os.path.join("txt_iptv", f) for f in os.listdir(txt_output_dir) if f.endswith('.txt')] + \
                      [os.path.join("m3u_iptv", f) for f in os.listdir(m3u_output_dir) if f.endswith('.m3u')]
    
    update_readme_file_list(repo_root)
    generated_files.append(README_FILE)
    
    if args.push:
        push_to_github(generated_files)

if __name__ == '__main__':
    main()
