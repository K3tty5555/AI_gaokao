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
    get_db,
    matches_sg_info,
    parse_combo,
    school_attrs,
)

# 三档窗口(位次差,可调)
CHONG_BACK = 3000   # 冲:院校位次 ∈ [N-3000, N-500]
CHONG_FRONT = 500
WEN_BACK = 500      # 稳:院校位次 ∈ [N-500, N+1000]
WEN_FRONT = 1000
BAO_BACK = 1000     # 保:院校位次 ∈ [N+1000, N+5000]
BAO_FRONT = 5000


def query(
    rank: int,
    subject_type: str,
    combo: str,
    top_per_tier: int = 10,
    only_985: bool = False,
    only_211: bool = False,
    zslx_filter: Optional[str] = None,
    year_target: Optional[int] = None,
    min_year: int = 2023,
):
    type_id = "2073" if subject_type == "物理类" else "2074"
    user_subjects = parse_combo(combo)

    # 三档位次区间
    chong_min = max(1, rank - CHONG_BACK)
    chong_max = max(1, rank - CHONG_FRONT)
    wen_min = max(1, rank - WEN_BACK)
    wen_max = rank + WEN_FRONT
    bao_min = rank + BAO_BACK
    bao_max = rank + BAO_FRONT

    conn = get_db()

    # 默认拉最新一年的数据(每个学校独立取自己最新)
    sql = """
        SELECT
            ps.school_id,
            ps.year,
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
        WHERE ps.type_id = ?
          AND ps.min_section IS NOT NULL
          AND ps.min_section != ''
          AND ps.min_section != '-'
          AND CAST(ps.min_section AS INTEGER) BETWEEN ? AND ?
    """
    params: list = [type_id, chong_min, bao_max]

    if year_target:
        sql += " AND CAST(ps.year AS INTEGER) = ?"
        params.append(year_target)
    else:
        # 默认:只看 min_year 及以后,且取每个 (school_id, special_group) 在该范围内的最新一年
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

    chong, wen, bao = [], [], []
    for r in rows:
        # 选科匹配
        if not matches_sg_info(r["sg_info"], user_subjects):
            continue
        s = r["section_int"]
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
        }
        if chong_min <= s < chong_max:
            chong.append(item)
        elif wen_min <= s <= wen_max:
            wen.append(item)
        elif bao_min < s <= bao_max:
            bao.append(item)

    # 截断 + 排序(冲按位次降序找极限,稳保按位次升序拿性价比高的)
    chong = sorted(chong, key=lambda x: x["min_section"])[:top_per_tier]
    wen = sorted(wen, key=lambda x: x["min_section"])[:top_per_tier]
    bao = sorted(bao, key=lambda x: x["min_section"], reverse=True)[:top_per_tier]

    return {
        "input": {
            "rank": rank,
            "subject_type": subject_type,
            "combo": combo,
            "user_subjects": sorted(user_subjects),
            "filters": {
                "only_985": only_985,
                "only_211": only_211,
                "zslx": zslx_filter,
                "year_target": year_target,
            },
        },
        "windows": {
            "冲": [chong_min, chong_max],
            "稳": [wen_min, wen_max],
            "保": [bao_min, bao_max],
        },
        "chong": chong,
        "wen": wen,
        "bao": bao,
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
        out.append("")
    return "\n".join(out)


def main() -> int:
    p = argparse.ArgumentParser(description="湖北志愿候选院校召回")
    p.add_argument("--rank", type=int, required=True, help="考生全省位次")
    p.add_argument("--type", choices=["物理类", "历史类"], required=True)
    p.add_argument(
        "--combo",
        type=str,
        required=True,
        help="选科组合(物化生/物化政/物化地/物生政/物生地/物政地/史化生/史化政/史化地/史生政/史生地/史政地)",
    )
    p.add_argument("--top", type=int, default=10, help="每档最多展示数(默认 10)")
    p.add_argument("--only-985", action="store_true")
    p.add_argument("--only-211", action="store_true")
    p.add_argument(
        "--zslx",
        type=str,
        default=None,
        help="招生类型过滤(普通类/国家专项计划/地方专项计划/民族班等)",
    )
    p.add_argument("--year", type=int, default=None, help="只看指定年份(覆盖 --min-year)")
    p.add_argument(
        "--min-year",
        type=int,
        default=2023,
        help="最早可用年份(默认 2023,过滤新高考首两年噪音数据)",
    )
    p.add_argument("--json", action="store_true", help="JSON 输出(给 agent 调用)")

    args = p.parse_args()

    try:
        result = query(
            rank=args.rank,
            subject_type=args.type,
            combo=args.combo,
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
