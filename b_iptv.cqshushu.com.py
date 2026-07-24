import requests
import os
import re
import time
import subprocess
import argparse
import json
import base64
from datetime import datetime
from html import unescape
from urllib.parse import quote
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

# ================= 配置区域 =================
# 1. 更新为新的目标网站
MULTICAST_SOURCE_URL = "https://iptv.cqshushu.com"

# 2. GitHub 推送配置
GITHUB_COMMIT_PREFIX = "Auto update IPTV cqshushu"
# ============================================
EPG_URL = "http://epg.51zmt.top:8000/e.xml.gz"
TVG_LOGO_BASE_URL = "https://gcore.jsdelivr.net/gh/taksssss/tv/icon/"
# 独立 README 文件，防止冲突
README_FILE = "README_IPTV.md"
RAW_BASE_URL = "https://raw.githubusercontent.com/jia070310/4K-IPTV-M3U/main"
PROXY_PREFIX = "https://gh-proxy.org/"

# 你需要的省份列表
PROVINCES = ["安徽", "四川", "浙江"]

def get_root_domain(domain):
    if re.match(r'^\d+\.\d+\.\d+\.\d+$', domain): return domain
    parts = domain.split('.')
    if len(parts) >= 3:
        if parts[-2] in ['com', 'net', 'org', 'gov', 'edu', 'gx'] or len(parts[-2]) <= 2:
            return ".".join(parts[-3:])
        else: return ".".join(parts[-2:])
    return domain

def check_and_clear_existing(txt_file, m3u_file):
    if not os.path.exists(txt_file):
        return False
    print(f"[*] 不做测流，清空旧文件后重新导出...")
    for file in [txt_file, m3u_file]:
        with open(file, 'w', encoding='utf-8') as f: f.write("")
    return False

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
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None

def _encrypt_token(raw_token):
    key = b"cQshuShu88888888"
    cipher = AES.new(key, AES.MODE_ECB)
    encrypted = cipher.encrypt(pad(raw_token.encode("utf-8"), AES.block_size))
    return base64.b64encode(encrypted).decode("utf-8")

def _extract_ajax_config(html):
    m = re.search(r"var\s+multicastIptvAjax\s*=\s*(\{.*?\});", html, flags=re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except Exception:
        return None

def _extract_region_code_map(html):
    code_map = {}
    m = re.search(r'<select\s+name="region"[^>]*>(.*?)</select>', html, flags=re.IGNORECASE | re.DOTALL)
    if not m:
        return code_map
    options_html = m.group(1)
    for code, name in re.findall(r'<option\s+value="([^"]*)"\s*[^>]*>(.*?)</option>', options_html, flags=re.IGNORECASE | re.DOTALL):
        code = code.strip()
        if not code:
            continue
        code_map[_strip_html(name)] = code
    return code_map

def _parse_rows_from_html_fragment(fragment_html):
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", fragment_html, flags=re.IGNORECASE | re.DOTALL)
    result = []
    for row_html in rows:
        ip_match = re.search(
            r'<a[^>]*class="[^"]*ip-link[^"]*"[^>]*data-p="([^"]+)"[^>]*>\s*([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+:[0-9]+)\s*</a>',
            row_html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not ip_match:
            continue
        tds = re.findall(r"<td[^>]*>(.*?)</td>", row_html, flags=re.IGNORECASE | re.DOTALL)
        if len(tds) < 6:
            continue
        result.append({
            "p_token": ip_match.group(1).strip(),
            "host": ip_match.group(2).strip(),
            "type": _strip_html(tds[2]),
            "online_time": _strip_html(tds[3]),
            "update_time": _strip_html(tds[4]),
            "status": _strip_html(tds[5]),
        })
    return result

def fetch_region_rows_by_ajax(province, limit=20, max_pages=30):
    print(f"[*] 正在抓取组播源页面: {MULTICAST_SOURCE_URL}")
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    })
    try:
        home_resp = session.get(MULTICAST_SOURCE_URL, timeout=15)
        home_resp.raise_for_status()
    except Exception as e:
        print(f"[-] 访问组播源页面失败: {e}")
        return []

    home_html = home_resp.text
    ajax_cfg = _extract_ajax_config(home_html)
    code_map = _extract_region_code_map(home_html)
    region_code = code_map.get(province)
    if not ajax_cfg:
        print("[-] 页面中未找到 Ajax 配置。")
        return []
    if not region_code:
        print(f"[-] 页面中未找到省份 [{province}] 的 region code。")
        return []

    all_rows = []
    seen_tokens = set()
    empty_page_hits = 0

    for page_num in range(1, max_pages + 1):
        payload = {
            "action": "multicast_iptv_ajax",
            "action_type": "list",
            "page_num": page_num,
            "limit": limit,
            "region": region_code,
            "search": "",
            "nonce": ajax_cfg.get("nonce", ""),
            "token": _encrypt_token(ajax_cfg.get("token", "")),
        }
        try:
            resp = session.post(ajax_cfg.get("ajaxUrl", ""), data=payload, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"[-] Ajax 请求省份 [{province}] 第{page_num}页失败: {e}")
            break
        if not data.get("success"):
            break

        fragment = data.get("data", {}).get("html", "")
        rows = _parse_rows_from_html_fragment(fragment)
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

def parse_s_token(detail_html: str) -> str | None:
    m = re.search(r'data-s="([^"]+)"', detail_html, flags=re.IGNORECASE | re.DOTALL)
    if m:
        return m.group(1)
    m = re.search(r'href="[^"]*[?&]s=([^"&]+)', detail_html, flags=re.IGNORECASE | re.DOTALL)
    if m:
        return m.group(1)
    return None

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
        if not re.search(r"(https?://|rtp/|udp/|igmp/)", play_url, flags=re.IGNORECASE):
            continue
        lines.append(f"{name},{play_url}")
    return lines

def normalize_group_title(raw_type: str, province: str) -> str:
    text = (raw_type or "").strip()
    if not text:
        return province
    if "|" in text:
        right = text.split("|")[-1].strip()
        if right:
            return right
    carriers = ("电信", "联通", "移动", "广电")
    for carrier in carriers:
        if carrier in text:
            return f"{province}{carrier}"
    return province

def fetch_channel_lines_by_province(province: str, max_per_carrier: int = 10, max_pages: int = 30, max_age_hours: int = 72):
    rows = fetch_region_rows_by_ajax(province, limit=20, max_pages=max_pages)
    if not rows:
        return [], "list_empty", province

    now_dt = datetime.now()

    def _is_usable_status(status: str) -> bool:
        return ("新上线" in status) or ("存活" in status)

    def _is_recent_update(row: dict) -> bool:
        dt = _parse_site_datetime(row.get("update_time", "")) or _parse_site_datetime(row.get("online_time", ""))
        if not dt:
            return False
        age_hours = (now_dt - dt).total_seconds() / 3600
        return age_hours <= max_age_hours

    def _pick_many(rows_pool, carrier: str, limit: int):
        carrier_rows = [r for r in rows_pool if carrier in r.get("type", "") and _is_usable_status(r.get("status", "")) and _is_recent_update(r)]
        if not carrier_rows or limit <= 0: return []
        
        def _sort_key(row: dict):
            dt = _parse_site_datetime(row.get("update_time", "")) or _parse_site_datetime(row.get("online_time", ""))
            return (2 if "新上线" in row.get("status", "") else 1, dt.timestamp() if dt else 0.0)

        carrier_rows = sorted(carrier_rows, key=_sort_key, reverse=True)
        picked = []
        seen = set()
        for row in carrier_rows:
            token = row.get("p_token")
            if not token or token in seen: continue
            seen.add(token)
            picked.append(row)
            if len(picked) >= limit: break
        return picked

    selected_rows = []
    selected_tokens = set()
    for carrier in ("电信", "移动", "联通"):
        for row in _pick_many(rows, carrier, max_per_carrier):
            token = row.get("p_token")
            if token not in selected_tokens:
                selected_rows.append(row)
                selected_tokens.add(token)

    if not selected_rows:
        return [], "no_recent_new_or_alive", province

    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"})
    home_resp = session.get(MULTICAST_SOURCE_URL, timeout=15)
    ajax_cfg = _extract_ajax_config(home_resp.text)
    if not ajax_cfg: return [], "ajax_cfg_missing", province
    token_plain = ajax_cfg.get("token", "")

    group_to_sources: dict[str, list[list[str]]] = {}
    
    for picked in selected_rows:
        group_title = normalize_group_title(picked.get("type", ""), province)
        detail_payload = {
            "action": "multicast_iptv_ajax", "action_type": "detail", "p": picked.get("p_token", ""),
            "nonce": ajax_cfg.get("nonce", ""), "token": _encrypt_token(token_plain)
        }
        detail_resp = session.post(ajax_cfg.get("ajaxUrl", ""), data=detail_payload, timeout=15)
        detail_json = detail_resp.json()
        detail_html = detail_json.get("data", {}).get("html", "")
        if not detail_html: continue
        
        token_plain = detail_json.get("data", {}).get("new_token", token_plain)
        s_token = parse_s_token(detail_html)
        if not s_token: continue

        channels_payload = {
            "action": "multicast_iptv_ajax", "action_type": "channels", "s": s_token,
            "nonce": ajax_cfg.get("nonce", ""), "token": _encrypt_token(token_plain)
        }
        channels_resp = session.post(ajax_cfg.get("ajaxUrl", ""), data=channels_payload, timeout=15)
        channels_html = channels_resp.json().get("data", {}).get("html", "")
        if not channels_html: continue
        
        lines = parse_channel_lines(channels_html)
        if lines:
            group_to_sources.setdefault(group_title, []).append(list(dict.fromkeys(lines)))

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
    grouped_sources, status, _ = fetch_channel_lines_by_province(province, max_pages, max_per_carrier, max_age_hours)
    if not grouped_sources:
        print(f"[-] [{province}] 频道提取失败: {status}")
        return

    total_channels = exported_sources = 0
    for group_title, sources in grouped_sources.items():
        for idx, channel_lines in enumerate(sources):
            if not channel_lines: continue
            # 优化序号逻辑：永远自带数字后缀，例：四川电信1.m3u
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
    # 修改默认阈值为 72 小时，避免报 no_recent_new_or_alive 错误
    ap.add_argument("--max-age-hours", type=int, default=72)
    # 修改默认获取数量为 10
    ap.add_argument("--max-per-carrier", type=int, default=10)
    ap.add_argument("--max-pages", type=int, default=30)
    return ap.parse_args()

def main():
    args = parse_args()
    repo_root = os.path.dirname(os.path.abspath(__file__))
    
    # 启用隔离的输出目录，避免与老脚本冲突
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