#!/usr/bin/env python3
"""
import_score_dist.py — 一分一段表 CSV 标准化导入

用法:
    python3 pipeline/import_score_dist.py \
        --file /tmp/hubei_2025_wuli.csv \
        --prov hubei \
        --year 2025 \
        --type 物理类

输出: data/yifenduyiduan/{year}_{type}_{prov}.csv
列:   分数,本段人数,累计人数  (按分数降序)
"""

from __future__ import annotations

import argparse
import csv
import os
import shutil
import sys

# ---------------------------------------------------------------------------
# 列名归一化映射
# ---------------------------------------------------------------------------
SCORE_ALIASES = {"分数", "总分", "成绩", "score"}
COUNT_ALIASES  = {"本段人数", "人数", "count"}
CUMUL_ALIASES  = {"累计人数", "累积人数", "cumulative", "累计", "累积"}

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "yifenduyiduan")


def normalize_header(raw: str) -> str:
    return raw.strip().lstrip("﻿")  # strip BOM + whitespace


def detect_columns(header_row: list[str]) -> tuple[int, int, int | None]:
    """
    返回 (score_idx, count_idx, cumul_idx)
    cumul_idx 可能为 None（后续重新计算）
    """
    normalized = [normalize_header(h) for h in header_row]

    score_idx = cumul_idx = count_idx = None
    for i, h in enumerate(normalized):
        if h in SCORE_ALIASES:
            score_idx = i
        elif h in COUNT_ALIASES:
            count_idx = i
        elif h in CUMUL_ALIASES:
            cumul_idx = i

    if score_idx is None or count_idx is None:
        # 格式 B: 位次,分数,本段人数 — 位次在第一列，分数在第二列
        # 尝试按列序推断
        if len(normalized) >= 2:
            # 检查各列是否有 "位次" 关键字
            rank_idx = next(
                (i for i, h in enumerate(normalized) if "位次" in h or "rank" in h.lower()),
                None,
            )
            if rank_idx is not None:
                remaining = [i for i in range(len(normalized)) if i != rank_idx]
                if len(remaining) >= 2:
                    score_idx = remaining[0]
                    count_idx = remaining[1]
                    if len(remaining) >= 3:
                        cumul_idx = remaining[2]

    if score_idx is None or count_idx is None:
        raise ValueError(
            f"无法识别列名: {normalized}\n"
            "需要：分数列（分数/总分/成绩/score）和人数列（本段人数/人数/count）"
        )

    return score_idx, count_idx, cumul_idx


def parse_csv(filepath: str) -> list[tuple[int, int, int]]:
    """
    解析 CSV，返回 [(score, seg_count, cumul_count), ...]，按分数降序。
    """
    with open(filepath, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        rows = list(reader)

    if not rows:
        raise ValueError("CSV 文件为空")

    # 找表头行（跳过全为空或注释行）
    header_idx = None
    for i, row in enumerate(rows):
        stripped = [c.strip() for c in row if c.strip()]
        if stripped:
            header_idx = i
            break

    if header_idx is None:
        raise ValueError("未找到有效表头")

    header = rows[header_idx]
    score_idx, count_idx, cumul_idx = detect_columns(header)

    records: list[tuple[int, int]] = []
    for row in rows[header_idx + 1 :]:
        if not any(c.strip() for c in row):
            continue
        try:
            score = int(float(row[score_idx].strip()))
            seg   = int(float(row[count_idx].strip()))
        except (ValueError, IndexError):
            continue

        cumul_val: int | None = None
        if cumul_idx is not None and cumul_idx < len(row) and row[cumul_idx].strip():
            try:
                cumul_val = int(float(row[cumul_idx].strip()))
            except ValueError:
                pass

        records.append((score, seg, cumul_val))

    if not records:
        raise ValueError("CSV 中没有有效数据行")

    # 按分数降序排列
    records.sort(key=lambda x: x[0], reverse=True)

    # 重建 / 校验累计人数
    final: list[tuple[int, int, int]] = []
    running = 0
    for score, seg, cumul_hint in records:
        running += seg
        if cumul_hint is not None:
            # 如果原始数据有累计列，尊重它（首行）；
            # 后续行如有偏差超过 1 则 warn
            cumul = cumul_hint
        else:
            cumul = running
        final.append((score, seg, cumul))

    return final


def validate(records: list[tuple[int, int, int]]) -> list[str]:
    warnings: list[str] = []

    scores = [r[0] for r in records]
    if scores:
        if max(scores) > 750:
            warnings.append(f"分数最大值 {max(scores)} 超出合理范围(750)")
        if min(scores) < 150:
            warnings.append(f"分数最小值 {min(scores)} 低于合理范围(150)")

    if len(records) < 100:
        warnings.append(f"仅有 {len(records)} 行，可能数据不完整（建议 >100 行）")

    # 累计人数应单调递增（降序分数 → 累计递增）
    prev_cumul = 0
    non_mono = 0
    for score, seg, cumul in records:
        if cumul < prev_cumul:
            non_mono += 1
        prev_cumul = cumul
    if non_mono:
        warnings.append(f"累计人数存在 {non_mono} 处非单调递增")

    return warnings


def write_output(records: list[tuple[int, int, int]], outpath: str) -> None:
    os.makedirs(os.path.dirname(outpath), exist_ok=True)

    # 幂等：覆盖前备份
    if os.path.exists(outpath):
        bak = outpath + ".bak"
        shutil.copy2(outpath, bak)
        print(f"[备份] 已有文件备份到 {bak}")

    with open(outpath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["分数", "本段人数", "累计人数"])
        writer.writerows(records)

    print(f"[输出] {outpath}  ({len(records)} 行)")


def main() -> None:
    parser = argparse.ArgumentParser(description="一分一段表 CSV 标准化导入")
    parser.add_argument("--file",  required=True,  help="输入 CSV 文件路径")
    parser.add_argument("--prov",  required=True,  help="省份拼音 (如 hubei)")
    parser.add_argument("--year",  required=True,  help="年份 (如 2025)")
    parser.add_argument("--type",  required=True,  dest="exam_type", help="科类 (如 物理类 / 历史类)")
    args = parser.parse_args()

    if not os.path.isfile(args.file):
        print(f"[错误] 文件不存在: {args.file}", file=sys.stderr)
        sys.exit(1)

    print(f"[读取] {args.file}")
    try:
        records = parse_csv(args.file)
    except ValueError as e:
        print(f"[错误] {e}", file=sys.stderr)
        sys.exit(1)

    warnings = validate(records)
    for w in warnings:
        print(f"[警告] {w}")

    outname = f"{args.year}_{args.exam_type}_{args.prov}.csv"
    outpath = os.path.normpath(os.path.join(DATA_DIR, outname))
    write_output(records, outpath)

    print("[完成] 导入成功")


if __name__ == "__main__":
    main()
