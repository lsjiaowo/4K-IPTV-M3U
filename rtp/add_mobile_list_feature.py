#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import shutil
from pathlib import Path


MOBILE_FUNCTION = r'''
def list_mobile_provinces(max_pages=30):
    """扫描中国大陆各省级地区，仅列出当前存在移动组播源的省份。"""
    print("\n" + "=" * 60)
    print(" 开始扫描全国移动组播源")
    print("=" * 60)

    excluded = {"台湾", "俄罗斯", "韩国"}
    provinces = [
        province
        for province in PROVINCE_CODES
        if province not in excluded
    ]

    results = []

    with requests.Session() as session:
        for index, province in enumerate(provinces):
            if index > 0:
                delay = random.uniform(
                    PROVINCE_SWITCH_DELAY_MIN_SEC,
                    PROVINCE_SWITCH_DELAY_MAX_SEC,
                )
                print(
                    f"\n[*] 切换到下一个省份前冷却 {delay:.1f} 秒，"
                    "降低省份列表接口触发429的概率。"
                )
                time.sleep(delay)

            print("\n" + "=" * 50)
            print(f" 正在检查：{province}移动")
            print("=" * 50)

            try:
                rows = fetch_region_rows_by_ajax(
                    province,
                    limit=20,
                    max_pages=max_pages,
                    session=session,
                )
            except Exception as exc:
                print(f"[-] [{province}] 扫描失败：{exc}")
                continue

            mobile_rows = [
                row
                for row in rows
                if "移动" in (row.get("type", "") or "")
            ]

            if mobile_rows:
                results.append((province, mobile_rows))
                print(
                    f"[+] [{province}移动] 找到 "
                    f"{len(mobile_rows)} 条服务器"
                )
            else:
                print(f"[-] [{province}移动] 未找到")

    print("\n" + "=" * 60)
    print(" 当前存在移动组播源的省份")
    print("=" * 60)

    if not results:
        print("未发现移动组播源。")
    else:
        total_servers = 0
        for province, rows in results:
            count = len(rows)
            total_servers += count
            print(f"{province}移动：{count} 条服务器")

        print("-" * 60)
        print(
            "省份列表："
            + ",".join(f"{province}移动" for province, _ in results)
        )
        print(f"共 {len(results)} 个省份存在移动源")
        print(f"移动服务器合计：{total_servers} 条")

    print("=" * 60)
    return results

'''


ARG_BLOCK = r'''    ap.add_argument(
        "--list-mobile-provinces",
        action="store_true",
        help="扫描中国大陆各省级地区，仅列出当前存在移动组播源的省份；不测速、不生成文件。",
    )
'''


MAIN_BLOCK = r'''    if args.list_mobile_provinces:
        list_mobile_provinces(max_pages=args.max_pages)
        return

'''


def patch_b_py(target: Path) -> None:
    if not target.exists():
        raise SystemExit(f"找不到文件：{target}")

    original = target.read_text(encoding="utf-8")
    text = original

    required_signatures = [
        "def fetch_region_rows_by_ajax(province, limit=20, max_pages=30, session=None):",
        "def source_status_rank(status: str) -> int:",
        "def parse_args():",
        'ap = argparse.ArgumentParser(description="按省份抓取频道并生成 txt/m3u。")',
        "def main():",
        "    args = parse_args()",
    ]
    missing = [item for item in required_signatures if item not in text]
    if missing:
        print("[-] 当前 b.py 结构与预期不一致，为避免破坏原逻辑，未修改。")
        for item in missing:
            print(f"    缺少：{item}")
        raise SystemExit(2)

    changed = False

    if "def list_mobile_provinces(" not in text:
        anchor = "def source_status_rank(status: str) -> int:"
        text = text.replace(anchor, MOBILE_FUNCTION + anchor, 1)
        changed = True
        print("[+] 已加入 list_mobile_provinces()。")
    else:
        print("[*] list_mobile_provinces() 已存在，跳过。")

    if '"--list-mobile-provinces"' not in text:
        anchor = '    ap = argparse.ArgumentParser(description="按省份抓取频道并生成 txt/m3u。")\n'
        if anchor not in text:
            raise SystemExit("[-] 找不到 argparse 插入位置，未覆盖原文件。")
        text = text.replace(anchor, anchor + ARG_BLOCK, 1)
        changed = True
        print("[+] 已加入 --list-mobile-provinces 参数。")
    else:
        print("[*] --list-mobile-provinces 已存在，跳过。")

    if "if args.list_mobile_provinces:" not in text:
        anchor = "def main():\n    args = parse_args()\n"
        if anchor not in text:
            raise SystemExit("[-] 找不到 main() 插入位置，未覆盖原文件。")
        text = text.replace(anchor, anchor + MAIN_BLOCK, 1)
        changed = True
        print("[+] 已加入 main() 扫描旁路。")
    else:
        print("[*] main() 扫描旁路已存在，跳过。")

    if not changed:
        print("[*] 无需修改，当前 b.py 已包含全部功能。")
        return

    try:
        compile(text, str(target), "exec")
    except SyntaxError as exc:
        print(f"[-] 修改后的代码语法检查失败：{exc}")
        print("[-] 原 b.py 未被覆盖。")
        raise SystemExit(3)

    backup = target.with_name(target.name + ".bak")
    shutil.copy2(target, backup)

    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(target)

    print("[+] 语法检查通过。")
    print(f"[+] 已修改：{target}")
    print(f"[+] 原文件备份：{backup}")
    print()
    print("现在可以运行：")
    print("    python rtp/b.py --list-mobile-provinces")
    print()
    print("原有运行方式无需修改；不传新参数时仍走原来的 main() 流程。")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="安全为当前 rtp/b.py 增加全国移动源扫描参数。"
    )
    parser.add_argument(
        "b_py",
        nargs="?",
        default="rtp/b.py",
        help="b.py 路径，默认 rtp/b.py",
    )
    args = parser.parse_args()
    patch_b_py(Path(args.b_py))


if __name__ == "__main__":
    main()
