#!/usr/bin/env python3
"""
查特定院校 / 专业组的历年湖北录取数据。

用法:
  python3 query_major.py --school 武汉大学
  python3 query_major.py --school 武汉大学 --type 物理类
  python3 query_major.py --school 武汉大学 --type 物理类 --year 2024
  python3 query_major.py --school-id 42 --json

输出:列出该校所有专业组(默认所有年份)的录取情况,按 year DESC, special_group ASC 排。
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from lib import get_db


def query(
    school: Optional[str] = None,
    school_id: Optional[int] = None,
    subject_type: Optional[str] = None,
    year: Optional[int] = None,
    zslx_filter: Optional[str] = None,
):
    if not school and not school_id:
        raise ValueError("必须指定 --school 或 --school-id")

    conn = get_db()

    if school and not school_id:
        row = conn.execute(
            "SELECT school_id FROM schools WHERE name=? OR name LIKE ?",
            (school, f"%{school}%"),
        ).fetchone()
        if not row:
            return {"error": f"未找到学校: {school}"}
        school_id = row[0]

    s = conn.execute(
        "SELECT * FROM schools WHERE school_id=?", (school_id,)
    ).fetchone()
    if not s:
        return {"error": f"未找到 school_id={school_id}"}

    sql = """
        SELECT year, type_id, special_group, sg_name, sg_info, zslx_name,
               local_batch_name, min_score, min_section, filing, proscore, diff
        FROM province_scores
        WHERE school_id = ?
    """
    params: list = [school_id]
    if subject_type:
        params.append("2073" if subject_type == "物理类" else "2074")
        sql += " AND type_id = ?"
    if year:
        sql += " AND CAST(year AS INTEGER) = ?"
        params.append(year)
    if zslx_filter:
        sql += " AND zslx_name = ?"
        params.append(zslx_filter)
    sql += " ORDER BY CAST(year AS INTEGER) DESC, special_group ASC"

    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    for r in rows:
        r["subject_type_name"] = "物理类" if r["type_id"] == "2073" else "历史类"

    return {
        "school": {
            "school_id": school_id,
            "name": s["name"],
            "province": s["province_name"],
            "city": s["city_name"],
            "type": s["type_name"],
            "f985": s["f985"] == 1,
            "f211": s["f211"] == 1,
            "dual_class": s["dual_class_name"],
        },
        "rows": rows,
    }


def fmt_human(result: dict) -> str:
    if "error" in result:
        return f"ERROR: {result['error']}"
    s = result["school"]
    out = []
    tags = []
    if s["f985"]:
        tags.append("985")
    elif s["f211"]:
        tags.append("211")
    if s["dual_class"] and "双一流" in (s["dual_class"] or ""):
        tags.append("双一流")
    out.append(f"# {s['name']} [{'/'.join(tags) if tags else '无'}]")
    out.append(f"  地点: {s['province']}{s['city'] or ''}  类型: {s['type']}")
    out.append("")
    out.append(f"湖北历年录取记录(共 {len(result['rows'])} 条):")
    out.append("")

    # 按 (year, type) 分组
    by_year: dict = {}
    for r in result["rows"]:
        key = (r["year"], r["subject_type_name"])
        by_year.setdefault(key, []).append(r)

    for (yr, st), items in sorted(by_year.items(), reverse=True):
        out.append(f"## {yr} {st}")
        for r in items:
            out.append(
                f"  - {r['sg_name']} [{r['zslx_name']}] {r['local_batch_name']}"
                f"  | 位次 {r['min_section']} 分 {r['min_score']}"
                f"  | {r['sg_info']}"
            )
        out.append("")
    return "\n".join(out)


def main() -> int:
    p = argparse.ArgumentParser(description="查院校历年湖北录取")
    p.add_argument("--school", type=str, help="学校名(支持模糊)")
    p.add_argument("--school-id", type=int, help="学校 ID(精确)")
    p.add_argument("--type", choices=["物理类", "历史类"])
    p.add_argument("--year", type=int)
    p.add_argument("--zslx", type=str)
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    try:
        result = query(
            school=args.school,
            school_id=args.school_id,
            subject_type=args.type,
            year=args.year,
            zslx_filter=args.zslx,
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
