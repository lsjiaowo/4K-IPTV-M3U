import os
import re
import time
import random
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
BASE_URL = "https://iptv.cqshushu.com/index.php"
GITHUB_COMMIT_PREFIX = "Auto update IPTV cqshushu"
EPG_URL = "http://epg.51zmt.top:8000/e.xml.gz"
TVG_LOGO_BASE_URL = "https://gcore.jsdelivr.net/gh/taksssss/tv/icon/"
README_FILE = "README_IPTV.md"
RAW_BASE_URL = "https://raw.githubusercontent.com/jia070310/4K-IPTV-M3U/main"
PROXY_PREFIX = "https://gh-proxy.org/"

PROVINCES = ["安徽", "四川", "浙江"]
# ============================================

def clear_output_files(txt_output_dir, m3u_output_dir):
    for out_dir, suffix in ((txt_output_dir, ".txt"), (m3u_output_dir, ".m3u")):
        if not os.path.exists(out_dir): continue
        for name in os.listdir(out_dir):
            if name.endswith(suffix):
                try: os.remove(os.path.join(out_dir, name))
                except OSError: pass

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
    # 使用 curl_cffi 完美伪装浏览器
    session = requests.Session(impersonate="chrome120")
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": "https://iptv.cqshushu.com/"
    })
    session.cookies.set("ad_ok", "1", domain="iptv.cqshushu.com", path="/")
    return session

def fetch_with_challenge_bypass(session, url):
    """ 智能过盾请求：自动处理 Cloudflare 和 自定义 JS 挑战 """
    for attempt in range(3):
        try:
            time.sleep(random.uniform(0.8, 1.5)) # 防封禁延迟
            resp = session.get(url, timeout=20)
            html = resp.text
            
            # 检测防爬拦截墙并提取跳转链接
            if "安全验证中" in html and "data-redirect" in html:
                m_redirect = re.search(r'data-redirect="([^"]+)"', html)
                if m_redirect:
                    redirect_uri = unescape(m_redirect.group(1))
                    if not redirect_uri.startswith("http"):
                        redirect_uri = f"https://iptv.cqshushu.com/{redirect_uri.lstrip('/')}"
                    print(f"[*] 🚨 触发验证墙，自动跳转 -> {redirect_uri}")
                    url = redirect_uri
                    continue
            return html
        except Exception as e:
            print(f"[-] 请求异常: {e}")
            return None
    return None

def extract_channels_from_html(html_text: str) -> list[str]:
    """ 强力正则提取器：通吃 HTML 表格、原生 M3U 文本、原生 TXT 文本 """
    lines = []
    
    # 1. 提取 HTML 表格数据
    for row_html in re.findall(r"<tr[^>]*>(.*?)</tr>", html_text, flags=re.IGNORECASE | re.DOTALL):
        tds = re.findall(r"<td[^>]*>(.*?)</td>", row_html, flags=re.IGNORECASE | re.DOTALL)
        if len(tds) >= 2:
            name = _strip_html(tds[0] if len(tds) == 2 else tds[1]).strip()
            play_url = _strip_html(tds[1] if len(tds) == 2 else tds[2]).strip()
            if re.search(r"^(https?|rtp|udp|igmp)://", play_url, flags=re.IGNORECASE):
                lines.append(f"{name},{play_url}")
                
    # 2. 提取原生 M3U 格式文本 (使用三引号防止单引号闭合错误)
    for m in re.finditer(r"""#EXTINF.*?,(.*?)\r?\n((?:https?|rtp|udp|igmp)://[^\s<>"']+)""", html_text, re.IGNORECASE):
        lines.append(f"{m.group(1).strip()},{m.group(2).strip()}")

    # 3. 提取原生 TXT 格式文本，限制匹配行首防止误伤JS
    for m in re.finditer(r"""^([^,<>\n]+),((?:https?|rtp|udp|igmp)://[^\s<>"']+)""", html_text, re.IGNORECASE | re.MULTILINE):
        name = m.group(1).strip()
        if "{" in name or "}" in name or "function" in name: continue
        lines.append(f"{name},{m.group(2).strip()}")
        
    return list(dict.fromkeys(lines))

def fetch_region_data(session, province, max_pages=30):
    print(f"[*] 正在模拟用户搜索，寻找 [{province}] 节点...")
    all_rows = []
    seen_tokens = set()

    for page_num in range(1, max_pages + 1):
        url = f"{BASE_URL}?q={quote(province)}"
        if page_num > 1: url += f"&page={page_num}"
        
        html = fetch_with_challenge_bypass(session, url)
        if not html: break
            
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, flags=re.S | re.I)
        added = 0
        
        for row in rows:
            if 'data-label="IP:"' not in row: continue
            
            # 正则完美匹配 gotoIP('token', 'type')
            m_goto = re.search(r"""gotoIP\(['"]([^'"]+)['"],\s*['"]([^'"]+)['"].*?>\s*([\d\.:]+)\s*<""", row, re.S)
            if not m_goto: continue
            
            p_token = m_goto.group(1)
            node_type = m_goto.group(2)
            ip_addr = m_goto.group(3).strip()
            
            if p_token in seen_tokens: continue
            seen_tokens.add(p_token)
            
            m_type = re.search(r'<td[^>]*类型:[^>]*>(.*?)</td>', row, re.S)
            m_update = re.search(r'<td[^>]*更新时间:[^>]*>(.*?)</td>', row, re.S)
            m_status = re.search(r'<span[^>]*status-badge[^>]*>(.*?)</span>', row, re.S)
            
            all_rows.append({
                "p_token": p_token,
                "host": ip_addr,
                "node_type": node_type,
                "type": _strip_html(m_type.group(1)) if m_type else province,
                "update_time": _strip_html(m_update.group(1)) if m_update else "",
                "status": _strip_html(m_status.group(1)) if m_status else "存活"
            })
            added += 1
            
        print(f"[*] [{province}] 第{page_num}页搜索完成，新增 {added} 个节点。")
        if added == 0: break

    print(f"[*] [{province}] 合计抓取到 {len(all_rows)} 个有效服务器。")
    return all_rows

def follow_links_to_channels(session, p_token, node_type):
    """
    终极提取法：沿着用户的点击逻辑一步步追踪，直到抓到直链
    第一层：详情页 -> 第二层：频道列表页 -> 第三层：M3U接口
    """
    # [第一层] 请求点击 IP 后的详情页
    detail_url = f"{BASE_URL}?p={p_token}&t={node_type}"
    html = fetch_with_challenge_bypass(session, detail_url)
    if not html: return []
    
    # 尝试在详情页直接解析（如有展示）
    channels = extract_channels_from_html(html)
    if channels: return channels
    
    # [寻找第二层入口] 查找“查看频道列表”按钮的链接
    list_url = None
    m_link = re.search(r'<a[^>]*href="([^"]+)"[^>]*>.*?查看频道列表.*?</a>', html, re.I | re.S)
    if m_link:
        list_url = m_link.group(1)
    else:
        # 暴力寻找页面里带有 channel 或 m3u 关键字的链接
        for link in re.findall(r'<a[^>]*href="([^"]+)"', html, re.I):
            if any(x in link.lower() for x in ['channel', 'list', 'm3u', 'txt']):
                list_url = link
                break
                
    if list_url:
        if not list_url.startswith("http"):
            if list_url.startswith("?"): list_url = f"{BASE_URL}{list_url}"
            else: list_url = f"https://iptv.cqshushu.com/{list_url.lstrip('/')}"
            
        print(f"    -> 深入列表页: {list_url}")
        list_html = fetch_with_challenge_bypass(session, list_url)
        if not list_html: return []
        
        # 尝试在列表页提取频道
        channels = extract_channels_from_html(list_html)
        if channels: return channels
        
        # [寻找第三层入口] 查找复制“M3U接口”的隐藏直链
        m_copy = re.search(r"""(https?://iptv\.cqshushu\.com/[^\s'"<]+\?(?:m3u|id|p|s)=?[^\s'"<]*)""", list_html)
        if m_copy:
            m3u_url = m_copy.group(1)
            print(f"    -> 提取到最终 M3U 接口: {m3u_url}")
            m3u_html = fetch_with_challenge_bypass(session, m3u_url)
            if m3u_html:
                return extract_channels_from_html(m3u_html)
                
    return []

def normalize_group_title(raw_type: str, province: str) -> str:
    text = (raw_type or "").strip()
    if not text: return province
    if "|" in text:
        right = text.split("|")[-1].strip()
        if right: return right
    for carrier in ("电信", "联通", "移动", "广电"):
        if carrier in text: return f"{province}{carrier}"
    return f"{province}组播"

def fetch_channel_lines_by_province(province: str, max_per_carrier: int = 5, max_pages: int = 10, max_age_hours: int = 72):
    session = get_session()
    rows = fetch_region_data(session, province, max_pages=max_pages)
    
    if not rows:
        return [], "list_empty", province
        
    now_dt = datetime.now()

    def _is_usable_status(status: str) -> bool:
        return ("新上线" in status) or ("存活" in status)

    selected_rows = []
    selected_tokens = set()
    
    # 三大运营商最优节点筛选
    for carrier in ("电信", "移动", "联通"):
        carrier_rows = [r for r in rows if carrier in r.get("type", "") and _is_usable_status(r.get("status", ""))]
        carrier_rows = sorted(carrier_rows, key=lambda x: _parse_site_datetime(x.get("update_time", "")).timestamp() if _parse_site_datetime(x.get("update_time", "")) else 0.0, reverse=True)
        
        for row in carrier_rows[:max_per_carrier]:
            if row["p_token"] not in selected_tokens:
                selected_rows.append(row)
                selected_tokens.add(row["p_token"])

    group_to_sources: dict[str, list[list[str]]] = {}
    success_count = 0
    
    for picked in selected_rows:
        group_title = normalize_group_title(picked.get("type", ""), province)
        token = picked.get("p_token", "")
        node_type = picked.get("node_type", "multicast")
        
        print(f"[*] 正在层层提取节点频道: {picked['host']} ({group_title})...")
        lines = follow_links_to_channels(session, token, node_type)
        
        if lines:
            group_to_sources.setdefault(group_title, []).append(lines)
            success_count += 1
            print(f"[+] 🎯 成功截获 {len(lines)} 条直播源直链！")
        else:
            print(f"[-] 节点 {picked['host']} 各级页面均未找到播放链接。")

    if not group_to_sources:
        return [], "channel_lines_empty", province
        
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
    ap.add_argument("--max-age-hours", type=int, default=168)
    ap.add_argument("--max-per-carrier", type=int, default=5)
    ap.add_argument("--max-pages", type=int, default=5) 
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
