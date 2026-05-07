#!/usr/bin/env python3
"""
分数 ↔ 位次 双向换算 (基于湖北招办官方一分一段表)。

数据源优先级:
1. data/yifenduyiduan/<year>_<物理类|历史类>.csv   ← 优先,精度 ±0
2. province_scores 表的 (min_score, min_section) 锚点 ← fallback,精度 ±500

用法:
  # score → rank
  python3 score_to_rank.py --score 580 --type 物理类 --year 2024
  python3 score_to_rank.py --score 580 --type 物理类 --year 2024 --json

  # rank → score (反向查询)
  python3 score_to_rank.py --rank 28232 --type 物理类 --year 2024

  # 不指定 year 默认用最新可用年份
  python3 score_to_rank.py --score 580 --type 物理类
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Optional

from lib import DATA_DIR, classify_score, get_db

YIFEN_DIR = DATA_DIR / "yifenduyiduan"


def _load_yifenduan(year: int, subject_type: str) -> Optional[list[tuple[int, int, int]]]:
    """加载某年某科类的一分一段表。返回 [(分数, 本段人数, 累计人数), ...] 按分数降序。

    返回 None 表示数据文件不存在(需 fallback)。
    """
    path = YIFEN_DIR / f"{year}_{subject_type}.csv"
    if not path.exists():
        return None
    rows = []
    with path.open() as f:
        reader = csv.DictReader(f)
        for r in reader:
            try:
                score = int(r["分数"])
                count = int(r["本段人数"])
                cum = int(r["累计人数"])
                rows.append((score, count, cum))
            except (ValueError, KeyError):
                continue
    rows.sort(key=lambda x: -x[0])  # 分数降序
    return rows


def _latest_yifenduan_year(subject_type: str) -> Optional[int]:
    """找该科类有数据的最新年份"""
    if not YIFEN_DIR.exists():
        return None
    years = []
    for p in YIFEN_DIR.glob(f"*_{subject_type}.csv"):
        try:
            year = int(p.stem.split("_")[0])
            years.append(year)
        except ValueError:
            continue
    return max(years) if years else None


def score_to_rank_official(score: int, subject_type: str, year: int) -> Optional[dict]:
    """官方一分一段表查询,精度 ±0"""
    table = _load_yifenduan(year, subject_type)
    if not table:
        return None
    # 精确匹配 / 找最近(若用户输入了表里没有的分数)
    for s, count, cum in table:
        if s == score:
            return {
                "score": score,
                "subject_type": subject_type,
                "year": year,
                "rank": cum,
                "count_at_score": count,
                "method": "official_yifenduyiduan",
                "precision": "±0",
                "note": f"该分数共 {count} 人,累计位次(=该分及以上人数){cum}",
            }
        if s < score:
            # 表里没有该分数(罕见,通常一分一段每分都有),取邻近上一档
            # 上一档分数 = 比 score 高 1 的那行
            return {
                "score": score,
                "subject_type": subject_type,
                "year": year,
                "rank": cum,  # 取下一个分数的累计 = 该分及以上的累计
                "count_at_score": 0,
                "method": "official_yifenduyiduan_interpolated",
                "precision": "±少量",
                "note": f"该分数在表里缺失,近似取下一档分数的位次",
            }
    # score 低于表里最小分
    last = table[-1]
    return {
        "score": score,
        "subject_type": subject_type,
        "year": year,
        "rank": last[2],
        "count_at_score": 0,
        "method": "official_yifenduyiduan_below_min",
        "precision": "下界估计",
        "note": f"分数低于表里最低 {last[0]} 分(累计 {last[2]} 名),实际位次 ≥ {last[2]}",
    }


def rank_to_score_official(rank: int, subject_type: str, year: int) -> Optional[dict]:
    """官方一分一段表反查:位次 → 分数。精度 ±0(取该位次落入的那一档分数)"""
    table = _load_yifenduan(year, subject_type)
    if not table:
        return None
    # 找第一个累计人数 >= rank 的分数
    # 即:该位次位于哪一分段
    for s, count, cum in table:
        if cum >= rank:
            return {
                "rank": rank,
                "subject_type": subject_type,
                "year": year,
                "score": s,
                "method": "official_yifenduyiduan",
                "precision": "±0",
                "note": f"位次 {rank} 落在分数段 {s} 分(该分累计 {cum} 名)",
            }
    # rank 大于表里最大累计(分数太低)
    last = table[-1]
    return {
        "rank": rank,
        "subject_type": subject_type,
        "year": year,
        "score": last[0],
        "method": "official_yifenduyiduan_below_min",
        "precision": "下界估计",
        "note": f"位次 {rank} 超出表覆盖({last[0]} 分累计 {last[2]} 名),实际分数 < {last[0]}",
    }


def score_to_rank_fallback(score: int, subject_type: str, year: int) -> dict:
    """Fallback:用 province_scores 表的 (min_score, min_section) 锚点做线性插值。
    精度 ±500 名,适用于一分一段表数据不存在的年份/科类。"""
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
        return {
            "score": score,
            "subject_type": subject_type,
            "year": year,
            "rank": None,
            "method": "fallback_no_data",
            "precision": "无法估算",
            "note": f"暂无 {year} 年 {subject_type} 数据",
        }

    pairs = sorted({(r[0], r[1]) for r in rows if r[0] and r[1]})
    if not pairs:
        return {
            "score": score,
            "rank": None,
            "method": "fallback_no_data",
            "precision": "无法估算",
            "note": "锚点数据为空",
        }

    if score >= pairs[-1][0]:
        return {
            "score": score,
            "subject_type": subject_type,
            "year": year,
            "rank": pairs[-1][1],
            "method": "fallback_high_capped",
            "precision": "上界估计",
            "note": f"分数高于已知锚点最高 {pairs[-1][0]} 分,位次 ≤ {pairs[-1][1]}",
        }
    if score <= pairs[0][0]:
        return {
            "score": score,
            "subject_type": subject_type,
            "year": year,
            "rank": pairs[0][1],
            "method": "fallback_low_capped",
            "precision": "下界估计",
            "note": f"分数低于已知锚点最低 {pairs[0][0]} 分,位次 ≥ {pairs[0][1]}",
        }

    lo, hi = pairs[0], pairs[-1]
    for i in range(len(pairs) - 1):
        if pairs[i][0] <= score <= pairs[i + 1][0]:
            lo, hi = pairs[i], pairs[i + 1]
            break
    if hi[0] == lo[0]:
        rank_est = (lo[1] + hi[1]) // 2
    else:
        ratio = (score - lo[0]) / (hi[0] - lo[0])
        rank_est = int(hi[1] - ratio * (hi[1] - lo[1]))

    return {
        "score": score,
        "subject_type": subject_type,
        "year": year,
        "rank": rank_est,
        "method": "fallback_linear_interpolation",
        "precision": "±500",
        "note": (
            f"基于 province_scores 锚点插值(精度有限,建议补一份 "
            f"data/yifenduyiduan/{year}_{subject_type}.csv 提升精度)"
        ),
    }


def estimate(
    score: Optional[int] = None,
    rank: Optional[int] = None,
    subject_type: str = "物理类",
    year: Optional[int] = None,
) -> dict:
    """统一入口:score / rank 二选一传入。"""
    if (score is None) == (rank is None):
        raise ValueError("必须 score 或 rank 二选一传入,不能同时传或都不传")

    # 默认用最新有数据的年份
    if year is None:
        year = _latest_yifenduan_year(subject_type) or 2024

    if score is not None:
        result = score_to_rank_official(score, subject_type, year)
        if result is None:
            result = score_to_rank_fallback(score, subject_type, year)
        # 附加批次分类(用于产品分流:本科 / 专科 / 复读)
        result["batch"] = classify_score(score, subject_type, year)
        return result
    else:  # rank
        result = rank_to_score_official(rank, subject_type, year)
        if result is None:
            return {
                "rank": rank,
                "subject_type": subject_type,
                "year": year,
                "score": None,
                "method": "fallback_no_data",
                "precision": "无法估算",
                "note": (
                    f"暂无 {year} 年 {subject_type} 一分一段表数据,"
                    f"反查 rank → score 需要官方表"
                ),
            }
        return result


def fmt_human(result: dict) -> str:
    out = []
    if result.get("score") and result.get("rank"):
        out.append(
            f"{result['score']} 分 ({result['subject_type']}, {result['year']}) "
            f"→ 位次 {result['rank']}"
        )
    elif result.get("rank") and result.get("score"):
        out.append(
            f"位次 {result['rank']} ({result['subject_type']}, {result['year']}) "
            f"→ 大致 {result['score']} 分"
        )
    out.append(f"  方法:{result['method']}({result.get('precision', '?')})")
    out.append(f"  说明:{result['note']}")
    batch = result.get("batch")
    if batch and batch.get("bracket") != "unknown":
        out.append(f"  批次:{batch['label']}")
        action_msg = {
            "main_skill": "→ 走主流程(本科填报 5 推荐 + 3 避坑)",
            "fork_repeat_or_vocational": "→ 触发分流:复读 vs 专科填报二选一",
            "suggest_repeat_or_alternative": "→ 建议复读 / 单招 / 自考(常规志愿不适用)",
        }.get(batch.get("action"), "")
        if action_msg:
            out.append(f"  分流:{action_msg}")
    return "\n".join(out)


def main() -> int:
    p = argparse.ArgumentParser(description="分数 ↔ 位次 双向换算(湖北一分一段表优先)")
    grp = p.add_mutually_exclusive_group(required=True)
    grp.add_argument("--score", type=int, help="高考分数 → 查位次")
    grp.add_argument("--rank", type=int, help="位次 → 查分数")
    p.add_argument("--type", choices=["物理类", "历史类"], required=True)
    p.add_argument(
        "--year",
        type=int,
        default=None,
        help="高考年份(默认用 yifenduyiduan/ 里最新数据的年份)",
    )
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    try:
        result = estimate(
            score=args.score, rank=args.rank, subject_type=args.type, year=args.year
        )
    except (FileNotFoundError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(fmt_human(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
