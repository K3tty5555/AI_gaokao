#!/usr/bin/env python3
"""
百分点位拟合法 — 基于多次模考分预测高考位次。

设计原则(PM 自创):
1. **加权 = 最新年优先**:用最新可用年的一分一段表作基准,不做多年拟合
2. **多次模考 median + mean**:中位数主预测,均值作波动检测
3. **基准用最新可用年**:简单不冒险
4. **不猜难度**:假设模考难度 = 高考难度,让用户给真实位次最准
5. **误差用人话**:不量化精度,讲"大概在 X 档"
6. **同年内不换算**:用最新年的一分一段 + 同年录取数据 → 自洽,不需百分位中转

用法:
  python3 predict.py --scores 545 552 548 --type 物理类
  python3 predict.py --scores 580 --type 物理类                   # 单次模考
  python3 predict.py --scores 540 545 550 --type 物理类 --json
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import List, Optional

from lib import DATA_DIR, classify_score


def _median(lst: List[float]) -> float:
    s = sorted(lst)
    n = len(s)
    if n == 0:
        return 0
    if n % 2 == 1:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2


def _mean(lst: List[float]) -> float:
    return sum(lst) / len(lst) if lst else 0


def _find_latest_year(subject_type: str) -> Optional[int]:
    """找一分一段表里最新可用年份"""
    yifen_dir = DATA_DIR / "yifenduyiduan"
    years = []
    for p in yifen_dir.glob(f"*_{subject_type}.csv"):
        try:
            year = int(p.stem.split("_")[0])
            years.append(year)
        except ValueError:
            continue
    return max(years) if years else None


def _score_to_rank(score: int, subject_type: str, year: int):
    """简单查一分一段表(预测专用,不走 score_to_rank.py 完整流程)"""
    path = DATA_DIR / "yifenduyiduan" / f"{year}_{subject_type}.csv"
    if not path.exists():
        return None, None
    rows = []
    with path.open() as f:
        for r in csv.DictReader(f):
            try:
                rows.append((int(r['分数']), int(r['累计人数'])))
            except (ValueError, KeyError):
                continue
    if not rows:
        return None, None
    total = rows[-1][1]  # 末行累计 ≈ 总考生
    rows.sort(key=lambda x: -x[0])  # 分数降序
    # 精确匹配
    for s, cum in rows:
        if s == int(score):
            return cum, total
        if s < int(score):
            return cum, total  # 取下一个分数累计(代表"该分及以上"的位次)
    # 分数低于表里最低分
    return rows[-1][1], total


def predict(scores: List[float], subject_type: str, target_year: Optional[int] = None):
    if not scores:
        raise ValueError("至少需要 1 次模考分数")
    if not all(0 <= s <= 750 for s in scores):
        raise ValueError("模考分数必须在 0-750 之间")

    # 1. 选基准年(最新可用)
    base_year = target_year or _find_latest_year(subject_type)
    if not base_year:
        raise ValueError(f"未找到 {subject_type} 一分一段表数据")

    # 2. 计算 median + mean
    med = round(_median(scores))
    avg = round(_mean(scores), 1)

    # 3. 波动检测(两条判据,任一触发即"波动大")
    #    a. mean vs median 差 > 10:被异常值拉偏(发挥过好/过差的单次)
    #    b. max - min 跨度 > 30:整体起伏大
    n = len(scores)
    if n == 1:
        volatility = "未知(单次模考)"
        warn = "单次模考精度低,建议用近 3 次模考分平均判断"
    elif n == 2:
        volatility = "信号弱(仅 2 次)"
        warn = "建议用 3 次或以上模考分,提高判断稳定性"
    else:
        score_range = max(scores) - min(scores)
        avg_med_diff = abs(avg - med)
        reasons = []
        if avg_med_diff > 10:
            reasons.append(f"均值 {avg} vs 中位 {med} 差 {avg_med_diff:.1f} 分")
        if score_range > 30:
            reasons.append(f"最高最低差 {score_range:.0f} 分")
        if reasons:
            volatility = "波动大"
            warn = (
                f"{n} 次模考发挥不稳定({'; '.join(reasons)}),"
                "预测以中位数为主 + 带保守 buffer"
            )
        else:
            volatility = "稳定"
            warn = None

    # 4. median → rank (主预测)
    rank_median, total = _score_to_rank(med, subject_type, base_year)
    rank_mean, _ = _score_to_rank(round(avg), subject_type, base_year)

    # 5. 百分位(辅助展示)
    pct_median = round(rank_median / total * 100, 2) if (rank_median and total) else None
    pct_mean = round(rank_mean / total * 100, 2) if (rank_mean and total) else None

    # 6. 批次档位
    batch = classify_score(med, subject_type, base_year) if med else None

    return {
        "input_scores": scores,
        "subject_type": subject_type,
        "base_year": base_year,
        "median_score": med,
        "mean_score": avg,
        "volatility": volatility,
        "warning": warn,
        "predicted_rank_median": rank_median,
        "predicted_rank_mean": rank_mean,
        "predicted_percentile_median": pct_median,
        "predicted_percentile_mean": pct_mean,
        "total_candidates_base_year": total,
        "batch": batch,
    }


def fmt_human(r: dict) -> str:
    out = []
    out.append(f"# 百分点位拟合法 - 模考分预测")
    out.append("")
    out.append(f"输入:{r['input_scores']} 共 {len(r['input_scores'])} 次模考")
    out.append(f"  中位数:{r['median_score']} 分(主预测)")
    out.append(f"  均值  :{r['mean_score']} 分(波动参考)")
    out.append(f"  波动  :{r['volatility']}")
    if r['warning']:
        out.append(f"  注意  :{r['warning']}")
    out.append("")
    out.append(f"基准年:{r['base_year']} 年湖北 {r['subject_type']} 一分一段表")
    if r['predicted_rank_median']:
        out.append(
            f"  → 中位分 {r['median_score']} 对应位次:{r['predicted_rank_median']:,}"
        )
        if r['predicted_percentile_median']:
            out.append(
                f"     百分位:{r['subject_type']}前 {r['predicted_percentile_median']}%"
            )
    if r['predicted_rank_mean'] and r['predicted_rank_mean'] != r['predicted_rank_median']:
        out.append(
            f"  → 均值分 {r['mean_score']} 对应位次:{r['predicted_rank_mean']:,} "
            f"(前 {r['predicted_percentile_mean']}%)"
        )
    if r['total_candidates_base_year']:
        out.append(
            f"  (该年 {r['subject_type']} 总考生 {r['total_candidates_base_year']:,} 名)"
        )

    batch = r.get("batch") or {}
    if batch.get("label"):
        out.append("")
        out.append(f"批次定位:{batch['label']}")
        action = batch.get("action")
        if action == "main_skill":
            out.append("  → 走主流程(本科填报 5 推荐 + 3 避坑)")
        elif action == "fork_repeat_or_vocational":
            out.append("  → 触发分流:复读 vs 专科填报二选一")
        elif action == "suggest_repeat_or_alternative":
            out.append("  → 建议复读 / 单招 / 自考")

    out.append("")
    out.append("说明:")
    out.append("  本预测假设今年高考分布 ≈ 最新年(基准年)分布,不预测大小年。")
    out.append("  实际高考可能波动 ±5%,出分后请重新走 L1-B 流程拿具体志愿表。")
    return "\n".join(out)


def main() -> int:
    p = argparse.ArgumentParser(
        description="百分点位拟合法 — 多次模考分预测今年高考位次"
    )
    p.add_argument("--scores", type=float, nargs="+", required=True, help="模考分数(可多个)")
    p.add_argument("--type", choices=["物理类", "历史类"], required=True)
    p.add_argument("--year", type=int, default=None, help="基准年(默认最新)")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    try:
        result = predict(args.scores, args.type, args.year)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(fmt_human(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
