#!/usr/bin/env python3
"""
分数 → 全省位次 估算。

⚠️ MVP 版:目前没有真正的湖北一分一段表数据,使用粗略估算(基于 province_scores 表里的分数-位次锚点)。
后续应当接入官方一分一段表(湖北招办每年公布,可从 hbksw.cn 或 GitHub 现成数据集获取)。

用法:
  python3 score_to_rank.py --score 580 --type 物理类 --year 2024
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from lib import get_db


def estimate_rank(score: int, subject_type: str, year: int = 2024) -> dict:
    """
    用 province_scores 表里 (min_score, min_section) 锚点做线性插值。
    粗糙但 MVP 够用。
    """
    type_id = "2073" if subject_type == "物理类" else "2074"
    conn = get_db()

    rows = conn.execute(
        """
        SELECT CAST(min_score AS INTEGER) AS s, CAST(min_section AS INTEGER) AS r
        FROM province_scores
        WHERE type_id=? AND CAST(year AS INTEGER)=?
          AND min_score IS NOT NULL AND min_score != '' AND min_score != '-'
          AND min_section IS NOT NULL AND min_section != '' AND min_section != '-'
        """,
        (type_id, year),
    ).fetchall()
    if not rows:
        return {"error": f"暂无 {year} 年 {subject_type} 数据"}

    pairs = sorted({(r[0], r[1]) for r in rows if r[0] and r[1]})
    if not pairs:
        return {"error": "锚点数据为空"}

    if score >= pairs[-1][0]:
        return {
            "score": score,
            "estimated_rank": pairs[-1][1],
            "method": "high_score_capped",
            "anchor_low": pairs[-1],
            "anchor_high": pairs[-1],
            "note": f"分数 {score} 高于已知锚点最高分 {pairs[-1][0]},估计位次 ≤ {pairs[-1][1]}",
        }
    if score <= pairs[0][0]:
        return {
            "score": score,
            "estimated_rank": pairs[0][1],
            "method": "low_score_capped",
            "anchor_low": pairs[0],
            "anchor_high": pairs[0],
            "note": f"分数 {score} 低于已知锚点最低分 {pairs[0][0]},估计位次 ≥ {pairs[0][1]}",
        }

    # 线性插值
    lo, hi = pairs[0], pairs[-1]
    for i in range(len(pairs) - 1):
        if pairs[i][0] <= score <= pairs[i + 1][0]:
            lo, hi = pairs[i], pairs[i + 1]
            break
    if hi[0] == lo[0]:
        rank_est = (lo[1] + hi[1]) // 2
    else:
        ratio = (score - lo[0]) / (hi[0] - lo[0])
        # 分数高 → 位次小,所以反向
        rank_est = int(hi[1] - ratio * (hi[1] - lo[1]))

    return {
        "score": score,
        "subject_type": subject_type,
        "year": year,
        "estimated_rank": rank_est,
        "method": "linear_interpolation",
        "anchor_low": {"score": lo[0], "rank": lo[1]},
        "anchor_high": {"score": hi[0], "rank": hi[1]},
        "note": (
            "估算值,精度有限。后续接入官方一分一段表可大幅提升精度。"
        ),
    }


def main() -> int:
    p = argparse.ArgumentParser(description="分数 → 位次 估算(MVP 粗略版)")
    p.add_argument("--score", type=int, required=True)
    p.add_argument("--type", choices=["物理类", "历史类"], required=True)
    p.add_argument("--year", type=int, default=2024)
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    result = estimate_rank(args.score, args.type, args.year)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if "error" in result:
            print(f"ERROR: {result['error']}", file=sys.stderr)
            return 2
        print(
            f"分数 {result['score']} ({result['subject_type']}, {result['year']}) "
            f"→ 估算位次 ≈ {result['estimated_rank']}"
        )
        print(
            f"  锚点:[{result['anchor_low']}] ~ [{result['anchor_high']}]"
        )
        print(f"  {result['note']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
