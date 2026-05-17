#!/usr/bin/env python3
"""
import_batch_lines.py — 批次线手动录入工具

用法（直接参数模式）:
    python3 pipeline/import_batch_lines.py \
        --prov hubei --year 2026 \
        --lines "本科批:437:物理类,专科批:200:物理类"

用法（交互模式）:
    python3 pipeline/import_batch_lines.py --prov hubei --year 2026

输出: data/batch_lines/{prov}.csv
格式: 年份,科类,批次,控制线分数,对应位次,数据来源
      （位次列先留空，由 score_to_rank.py 反查后补全）
"""

import argparse
import csv
import os
import sys
from datetime import date

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "batch_lines")
HEADER = ["年份", "科类", "批次", "控制线分数", "对应位次", "数据来源"]


# ---------------------------------------------------------------------------
# 解析 --lines 参数
# ---------------------------------------------------------------------------
def parse_lines_arg(lines_str: str, year: str) -> list[dict]:
    """
    解析格式: "批次:分数:科类,批次:分数:科类,..."
    例: "本科批:437:物理类,专科批:200:物理类"
    """
    entries = []
    for part in lines_str.split(","):
        part = part.strip()
        if not part:
            continue
        pieces = [p.strip() for p in part.split(":")]
        if len(pieces) < 3:
            print(f"[警告] 跳过格式不正确的项: {part!r}  (期望 批次:分数:科类)")
            continue
        batch, score_str, exam_type = pieces[0], pieces[1], pieces[2]
        try:
            score = int(score_str)
        except ValueError:
            print(f"[警告] 跳过分数非整数的项: {part!r}")
            continue
        entries.append(
            {
                "年份": year,
                "科类": exam_type,
                "批次": batch,
                "控制线分数": score,
                "对应位次": "",
                "数据来源": f"手动录入 {date.today()}",
            }
        )
    return entries


# ---------------------------------------------------------------------------
# 交互模式
# ---------------------------------------------------------------------------
def interactive_input(year: str) -> list[dict]:
    entries = []
    print(f"交互录入 {year} 批次线（空行结束）")
    print("每条格式:  批次:分数:科类  例: 本科批:437:物理类")
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            break
        parsed = parse_lines_arg(line, year)
        if parsed:
            entries.extend(parsed)
            print(f"  ✓ 已录入: {parsed[0]['批次']} {parsed[0]['科类']} {parsed[0]['控制线分数']} 分")
    return entries


# ---------------------------------------------------------------------------
# CSV 读写（追加/更新）
# ---------------------------------------------------------------------------
def load_existing(filepath: str) -> list[dict]:
    if not os.path.isfile(filepath):
        return []
    with open(filepath, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return list(reader)


def merge_entries(existing: list[dict], new_entries: list[dict]) -> list[dict]:
    """
    以 (年份, 科类, 批次) 为 key 做 upsert。
    """
    index: dict[tuple, int] = {}
    merged = list(existing)
    for i, row in enumerate(merged):
        key = (str(row.get("年份", "")), str(row.get("科类", "")), str(row.get("批次", "")))
        index[key] = i

    updated = 0
    added = 0
    for entry in new_entries:
        key = (str(entry["年份"]), str(entry["科类"]), str(entry["批次"]))
        if key in index:
            merged[index[key]] = entry
            updated += 1
        else:
            index[key] = len(merged)
            merged.append(entry)
            added += 1

    print(f"[合并] 更新 {updated} 条，新增 {added} 条")
    return merged


def write_csv(filepath: str, rows: list[dict]) -> None:
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    # 按年份升序、科类、批次排序
    rows_sorted = sorted(
        rows,
        key=lambda r: (str(r.get("年份", "")), str(r.get("科类", "")), str(r.get("批次", ""))),
    )
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=HEADER, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows_sorted)
    print(f"[输出] {filepath}  ({len(rows_sorted)} 行)")


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="批次线手动录入工具")
    parser.add_argument("--prov",  required=True, help="省份拼音 (如 hubei)")
    parser.add_argument("--year",  required=True, help="年份 (如 2026)")
    parser.add_argument(
        "--lines",
        default=None,
        help='批次线数据，格式: "批次:分数:科类,..."  例: "本科批:437:物理类,专科批:200:物理类"',
    )
    args = parser.parse_args()

    if args.lines:
        new_entries = parse_lines_arg(args.lines, args.year)
    else:
        new_entries = interactive_input(args.year)

    if not new_entries:
        print("[提示] 没有录入任何数据，退出")
        sys.exit(0)

    filepath = os.path.normpath(os.path.join(DATA_DIR, f"{args.prov}.csv"))
    existing = load_existing(filepath)
    if not existing:
        print(f"[新建] {filepath}")
    merged = merge_entries(existing, new_entries)
    write_csv(filepath, merged)
    print("[完成] 批次线录入成功")


if __name__ == "__main__":
    main()
