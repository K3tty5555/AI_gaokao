#!/usr/bin/env python3
"""
按位次 + 选科组合,从湖北 2024 录取数据召回院校专业组,分"冲/稳/保"三档。

用法:
  python3 query_school.py --rank 6000 --type 物理类 --combo 物化生
  python3 query_school.py --rank 6000 --type 物理类 --combo 物化生 --top 5
  python3 query_school.py --rank 6000 --type 物理类 --combo 物化生 --json
  python3 query_school.py --rank 6000 --type 物理类 --combo 物化生 --only-985
  python3 query_school.py --rank 6000 --type 物理类 --combo 物化生 --zslx 普通类

输出(默认人类可读):
  ## 冲(N=10)
  - 北京大学 (05) | 普通类 | 2024 录取位次 1234, 分 691, 选科:首选物理，再选化学
  - ...
  ## 稳(N=20)
  ...
  ## 保(N=15)
  ...

JSON 输出供 agent 调用使用。
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from lib import (
    compute_admission_probability,
    compute_risk,
    get_db,
    get_history_ranks,
    matches_sg_info,
    parse_combo,
    school_attrs,
)

# 三档窗口 — 位次模式(位次差,可调)
CHONG_BACK = 3000   # 冲:院校位次 ∈ [N-3000, N-500]
CHONG_FRONT = 500
WEN_BACK = 500      # 稳:院校位次 ∈ [N-500, N+1000]
WEN_FRONT = 1000
BAO_BACK = 1000     # 保:院校位次 ∈ [N+1000, N+5000]
BAO_FRONT = 5000

# 三档窗口 — 分数模式(分差,适用于无位次数据的省份如西藏)
# 高分=好，窗口方向与位次相反
CHONG_SCORE_UP = 40    # 冲:院校 min_score ∈ (user+5, user+40]
CHONG_SCORE_DOWN = 5
WEN_SCORE_UP = 5       # 稳:院校 min_score ∈ [user-10, user+5]
WEN_SCORE_DOWN = 10
BAO_SCORE_UP = 10      # 保:院校 min_score ∈ [user-50, user-10)
BAO_SCORE_DOWN = 50


def _has_position_data(conn, type_ids: list, min_year: int, year_target: Optional[int]) -> bool:
    """检查当前省份 DB 是否有有效的 min_section 位次数据。"""
    placeholders = ", ".join("?" * len(type_ids))
    yr_sql = "AND CAST(year AS INTEGER) = ?" if year_target else "AND CAST(year AS INTEGER) >= ?"
    yr_param = year_target if year_target else min_year
    row = conn.execute(
        f"""SELECT COUNT(*) FROM province_scores
            WHERE type_id IN ({placeholders}) {yr_sql}
              AND min_section IS NOT NULL AND min_section != ''
              AND min_section != '-' AND CAST(min_section AS INTEGER) > 0""",
        [*type_ids, yr_param],
    ).fetchone()
    return row[0] >= 3


def query(
    rank: Optional[int] = None,
    score: Optional[int] = None,
    subject_type: str = "物理类",
    combo: str = "",
    top_per_tier: int = 10,
    only_985: bool = False,
    only_211: bool = False,
    zslx_filter: Optional[str] = None,
    year_target: Optional[int] = None,
    min_year: int = 2021,
):
    # type_id 映射：覆盖三种体系
    #   3+1+2: 物理类=2073(+理科=1回退), 历史类=2074(+文科=2回退)
    #   3+3:   综合=3（无回退，直接用 3）
    #   老高考: 理科=1 / 文科=2
    LEGACY_MAP = {
        "物理类": ("2073", "1"),
        "历史类": ("2074", "2"),
        "综合":   ("3",),
        "理科":   ("1",),
        "文科":   ("2",),
    }
    type_ids = LEGACY_MAP.get(subject_type, (subject_type,))
    type_id = type_ids[0]
    extra_type_id = type_ids[1] if len(type_ids) > 1 else None
    placeholders = ", ".join("?" * len(type_ids))

    if rank is None and score is None:
        raise ValueError("rank 或 score 二选一必须提供")

    # 综合/理科/文科 无选科组合约束；3+1+2 物理类/历史类才解析
    if subject_type in ("综合", "理科", "文科"):
        user_subjects: set = set()
    else:
        user_subjects = parse_combo(combo)

    conn = get_db()

    # 自动检测：有 rank 但省份无有效位次数据时，降级为分数模式
    use_score_mode = rank is None
    if not use_score_mode and score is not None:
        use_score_mode = not _has_position_data(conn, list(type_ids), min_year, year_target)

    SELECT_COLS = """
        SELECT
            ps.school_id,
            ps.year,
            ps.type_id,
            ps.special_group,
            ps.sg_name,
            ps.sg_info,
            ps.zslx_name,
            ps.local_batch_name,
            ps.min_score,
            CAST(ps.min_section AS INTEGER) AS section_int,
            ps.filing,
            ps.proscore,
            ps.diff,
            s.name AS school_name,
            s.province_name,
            s.city_name,
            s.f985,
            s.f211,
            s.dual_class_name
        FROM province_scores ps
        JOIN schools s ON s.school_id = ps.school_id
        WHERE ps.type_id IN ({placeholders})
    """.format(placeholders=placeholders)

    if use_score_mode:
        # ── 分数模式（无位次数据省份，如西藏）────────────────────────────────
        user_score = score  # type: ignore[assignment]
        sc_hi = user_score + CHONG_SCORE_UP    # 全窗口上界
        sc_lo = user_score - BAO_SCORE_DOWN    # 全窗口下界
        sql = SELECT_COLS + """
          AND ps.min_score IS NOT NULL AND ps.min_score != ''
          AND ps.min_score != '-'
          AND CAST(ps.min_score AS INTEGER) BETWEEN ? AND ?
        """
        params: list = [*type_ids, sc_lo, sc_hi]
        if year_target:
            sql += " AND CAST(ps.year AS INTEGER) = ?"
            params.append(year_target)
        else:
            sql += " AND CAST(ps.year AS INTEGER) >= ?"
            params.append(min_year)
            sql += """
              AND CAST(ps.year AS INTEGER) = (
                  SELECT MAX(CAST(year AS INTEGER))
                  FROM province_scores
                  WHERE school_id = ps.school_id
                    AND type_id = ps.type_id
                    AND special_group = ps.special_group
                    AND CAST(year AS INTEGER) >= ?
                    AND min_score IS NOT NULL AND min_score != ''
                    AND min_score != '-' AND CAST(min_score AS INTEGER) > 0
              )
            """
            params.append(min_year)
        if only_985:
            sql += " AND s.f985 = 1"
        if only_211:
            sql += " AND s.f211 = 1"
        if zslx_filter:
            sql += " AND ps.zslx_name = ?"
            params.append(zslx_filter)
        sql += " ORDER BY CAST(ps.min_score AS INTEGER) DESC"
        rows = conn.execute(sql, params).fetchall()

        chong, wen, bao = [], [], []
        for r in rows:
            if not matches_sg_info(r["sg_info"], user_subjects):
                continue
            try:
                ms = int(r["min_score"])
            except (TypeError, ValueError):
                continue
            item = {
                "school_id": r["school_id"],
                "school_name": r["school_name"],
                "province": r["province_name"],
                "city": r["city_name"],
                "f985": r["f985"] == 1,
                "f211": r["f211"] == 1,
                "dual_class": r["dual_class_name"],
                "year": int(r["year"]),
                "sg_code": r["special_group"],
                "sg_name": r["sg_name"],
                "sg_info": r["sg_info"],
                "zslx": r["zslx_name"],
                "batch": r["local_batch_name"],
                "min_score": r["min_score"],
                "min_section": r["section_int"],
                "filing": r["filing"],
                "proscore": r["proscore"],
                "diff": r["diff"],
                "history_ranks": [],
                "risk": {"level": "unknown", "note": "分数模式，无历史位次"},
                "admission_prob": {"display": "-", "label": "分数模式"},
            }
            delta = ms - user_score  # 正=学校更难，负=学校更易
            if CHONG_SCORE_DOWN < delta <= CHONG_SCORE_UP:
                chong.append(item)
            elif -WEN_SCORE_DOWN <= delta <= WEN_SCORE_UP:
                wen.append(item)
            elif -BAO_SCORE_DOWN <= delta < -BAO_SCORE_UP:
                bao.append(item)

        chong = sorted(chong, key=lambda x: int(x["min_score"] or 0), reverse=True)[:top_per_tier]
        wen   = sorted(wen,   key=lambda x: int(x["min_score"] or 0), reverse=True)[:top_per_tier]
        bao   = sorted(bao,   key=lambda x: int(x["min_score"] or 0))[:top_per_tier]

        return {
            "input": {
                "rank": rank,
                "score": score,
                "mode": "score_fallback",
                "subject_type": subject_type,
                "combo": combo,
                "user_subjects": sorted(user_subjects),
                "filters": {"only_985": only_985, "only_211": only_211,
                            "zslx": zslx_filter, "year_target": year_target},
            },
            "windows": {
                "冲": [user_score + CHONG_SCORE_DOWN, user_score + CHONG_SCORE_UP],
                "稳": [user_score - WEN_SCORE_DOWN, user_score + WEN_SCORE_UP],
                "保": [user_score - BAO_SCORE_DOWN, user_score - BAO_SCORE_UP],
            },
            "chong": chong, "wen": wen, "bao": bao,
        }

    # ── 位次模式（标准路径）────────────────────────────────────────────────────
    chong_min = max(1, rank - CHONG_BACK)
    chong_max = max(1, rank - CHONG_FRONT)
    wen_min = max(1, rank - WEN_BACK)
    wen_max = rank + WEN_FRONT
    bao_min = rank + BAO_BACK
    bao_max = rank + BAO_FRONT

    sql = SELECT_COLS + """
          AND ps.min_section IS NOT NULL
          AND ps.min_section != ''
          AND ps.min_section != '-'
          AND CAST(ps.min_section AS INTEGER) BETWEEN ? AND ?
    """
    params = [*type_ids, chong_min, bao_max]

    if year_target:
        sql += " AND CAST(ps.year AS INTEGER) = ?"
        params.append(year_target)
    else:
        sql += " AND CAST(ps.year AS INTEGER) >= ?"
        params.append(min_year)
        sql += """
          AND CAST(ps.year AS INTEGER) = (
              SELECT MAX(CAST(year AS INTEGER))
              FROM province_scores
              WHERE school_id = ps.school_id
                AND type_id = ps.type_id
                AND special_group = ps.special_group
                AND CAST(year AS INTEGER) >= ?
                AND min_section IS NOT NULL
                AND min_section != ''
                AND min_section != '-'
                AND CAST(min_section AS INTEGER) > 0
          )
        """
        params.append(min_year)

    if only_985:
        sql += " AND s.f985 = 1"
    if only_211:
        sql += " AND s.f211 = 1"
    if zslx_filter:
        sql += " AND ps.zslx_name = ?"
        params.append(zslx_filter)

    sql += " ORDER BY section_int"
    rows = conn.execute(sql, params).fetchall()

    # 去重：同一 school_id 可能因 type_id 扩展出现两条（新格式+旧格式）
    if extra_type_id:
        school_max_year: dict[int, int] = {}
        for r in rows:
            sid = r["school_id"]
            yr = int(r["year"])
            if sid not in school_max_year or yr > school_max_year[sid]:
                school_max_year[sid] = yr
        rows = [r for r in rows if int(r["year"]) == school_max_year[r["school_id"]]]

    chong, wen, bao = [], [], []
    for r in rows:
        if not matches_sg_info(r["sg_info"], user_subjects):
            continue
        s = r["section_int"]
        history = get_history_ranks(conn, r["school_id"], str(r["type_id"]),
                                    extra_type_id=extra_type_id)
        risk = compute_risk(history)
        admission = compute_admission_probability(rank, history)
        item = {
            "school_id": r["school_id"],
            "school_name": r["school_name"],
            "province": r["province_name"],
            "city": r["city_name"],
            "f985": r["f985"] == 1,
            "f211": r["f211"] == 1,
            "dual_class": r["dual_class_name"],
            "year": int(r["year"]),
            "sg_code": r["special_group"],
            "sg_name": r["sg_name"],
            "sg_info": r["sg_info"],
            "zslx": r["zslx_name"],
            "batch": r["local_batch_name"],
            "min_score": r["min_score"],
            "min_section": s,
            "filing": r["filing"],
            "proscore": r["proscore"],
            "diff": r["diff"],
            "history_ranks": [{"year": y, "rank": rk} for y, rk in history],
            "risk": risk,
            "admission_prob": admission,
        }
        # 归档基准：优先用历史均值位次，避免大小年年份被错误归档
        # （如某校今年突然大年，实际位次远高于历史均值，若用实际值会被降档）
        ref_rank = risk.get("mean") or s
        if chong_min <= ref_rank < chong_max:
            chong.append(item)
        elif wen_min <= ref_rank <= wen_max:
            wen.append(item)
        elif bao_min < ref_rank <= bao_max:
            bao.append(item)

    chong = sorted(chong, key=lambda x: x["min_section"])[:top_per_tier]
    wen   = sorted(wen,   key=lambda x: x["min_section"])[:top_per_tier]
    bao   = sorted(bao,   key=lambda x: x["min_section"], reverse=True)[:top_per_tier]

    return {
        "input": {
            "rank": rank,
            "score": score,
            "mode": "rank",
            "subject_type": subject_type,
            "combo": combo,
            "user_subjects": sorted(user_subjects),
            "filters": {"only_985": only_985, "only_211": only_211,
                        "zslx": zslx_filter, "year_target": year_target},
        },
        "windows": {
            "冲": [chong_min, chong_max],
            "稳": [wen_min, wen_max],
            "保": [bao_min, bao_max],
        },
        "chong": chong, "wen": wen, "bao": bao,
    }


def fmt_human(result: dict) -> str:
    out = []
    inp = result["input"]
    out.append(
        f"# 召回结果(湖北 {inp['subject_type']},位次 {inp['rank']},选科 {inp['combo']})"
    )
    win = result["windows"]
    out.append(
        f"档位窗口:冲 {win['冲'][0]}-{win['冲'][1]} / "
        f"稳 {win['稳'][0]}-{win['稳'][1]} / 保 {win['保'][0]}-{win['保'][1]}"
    )
    out.append("")

    for tier_name, key in [("冲", "chong"), ("稳", "wen"), ("保", "bao")]:
        items = result[key]
        out.append(f"## {tier_name}(N={len(items)})")
        if not items:
            out.append("  (无)")
            out.append("")
            continue
        for it in items:
            tags = []
            if it["f985"]:
                tags.append("985")
            elif it["f211"]:
                tags.append("211")
            if it["dual_class"] and "双一流" in it["dual_class"]:
                tags.append("双一流")
            tag_str = "[" + "/".join(tags) + "]" if tags else ""
            out.append(
                f"  - {it['school_name']} {it['sg_name']} {tag_str}"
                f" | {it['zslx']} | {it['province']}{it['city'] or ''}"
            )
            out.append(
                f"    {it['year']} 录取 位次 {it['min_section']} 分 {it['min_score']}"
                f"  | {it['sg_info']}"
            )
            risk = it.get("risk") or {}
            risk_label = {
                "stable": "[稳]",
                "low_risk": "[稳]",
                "moderate": "[中风险]",
                "high_risk": "[高风险]",
                "unknown": "[未知]",
            }.get(risk.get("level", "unknown"), "[未知]")
            out.append(f"    {risk_label} 大小年:{risk.get('note', '-')}")
            adm = it.get("admission_prob") or {}
            adm_display = adm.get("display", "-")
            adm_label = adm.get("label", "-")
            adm_mean = adm.get("mean_rank")
            adm_std = adm.get("std_rank")
            if adm_mean is not None and adm_std is not None:
                out.append(f"  录取概率: {adm_display} ({adm_label}) | 均值位次 {adm_mean} ± {adm_std}")
            else:
                out.append(f"  录取概率: {adm_display} ({adm_label})")
        out.append("")
    return "\n".join(out)


def main() -> int:
    p = argparse.ArgumentParser(description="志愿候选院校召回(跨省通用)")
    grp = p.add_mutually_exclusive_group(required=True)
    grp.add_argument("--rank", type=int, help="考生全省位次")
    grp.add_argument("--score", type=int, help="高考分数(无位次数据省份自动降级为分数模式)")
    p.add_argument("--score-also", type=int, default=None,
                   help="与 --rank 同时传入分数，供无位次数据时自动降级")
    p.add_argument(
        "--type",
        choices=["物理类", "历史类", "综合", "理科", "文科"],
        required=True,
        help="科类：3+1+2 用 物理类/历史类；3+3 用 综合；老高考 用 理科/文科",
    )
    p.add_argument(
        "--combo",
        type=str,
        default=None,
        help="选科组合(物化生/物化政/…)；综合/文科/理科 科类可省略",
    )
    p.add_argument("--top", type=int, default=10, help="每档最多展示数(默认 10)")
    p.add_argument("--only-985", action="store_true")
    p.add_argument("--only-211", action="store_true")
    p.add_argument("--zslx", type=str, default=None,
                   help="招生类型过滤(普通类/国家专项计划/地方专项计划/民族班等)")
    p.add_argument("--year", type=int, default=None, help="只看指定年份(覆盖 --min-year)")
    p.add_argument("--min-year", type=int, default=2023,
                   help="最早可用年份(默认 2023)")
    p.add_argument("--json", action="store_true", help="JSON 输出(给 agent 调用)")

    args = p.parse_args()

    no_combo_types = {"综合", "理科", "文科"}
    if args.type not in no_combo_types and not args.combo:
        p.error(f"--type {args.type} 需要提供 --combo")
    combo = args.combo or ""

    # 解析 rank / score
    rank = args.rank
    score = args.score if args.score is not None else args.score_also

    try:
        result = query(
            rank=rank,
            score=score,
            subject_type=args.type,
            combo=combo,
            top_per_tier=args.top,
            only_985=args.only_985,
            only_211=args.only_211,
            zslx_filter=args.zslx,
            year_target=args.year,
            min_year=args.min_year,
        )
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
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
