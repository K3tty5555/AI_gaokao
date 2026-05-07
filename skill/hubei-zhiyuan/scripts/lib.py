"""共享:DB 连接 + 选科组合解析 + sg_info 匹配"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

# 数据库位置:项目根目录下的 data/gaokao_hubei.db
# 路径推导:scripts → hubei-zhiyuan → skill → 项目根 → data/gaokao_hubei.db
DB_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent / "data" / "gaokao_hubei.db"
)

# 单字符 → 全名(用户输入"物化生"等)
SUBJECT_MAP = {
    "物": "物理",
    "史": "历史",
    "化": "化学",
    "生": "生物",
    "政": "思想政治",
    "地": "地理",
}

VALID_COMBOS = {
    # 物理类
    "物化生", "物化政", "物化地", "物生政", "物生地", "物政地",
    # 历史类
    "史化生", "史化政", "史化地", "史生政", "史生地", "史政地",
}


def get_db() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"数据库未找到: {DB_PATH} (爬虫还没跑完?)")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def parse_combo(combo: str) -> set[str]:
    """'物化生' → {'物理','化学','生物'}"""
    if combo not in VALID_COMBOS:
        raise ValueError(f"不合法的选科组合: {combo}。合法值: {sorted(VALID_COMBOS)}")
    return {SUBJECT_MAP[c] for c in combo}


def matches_sg_info(sg_info: Optional[str], user_subjects: set[str]) -> bool:
    """
    判断用户的选科 set 是否满足 sg_info 的要求。
    sg_info 形如:
        '首选物理，再选不限'
        '首选物理，再选化学'
        '首选物理，再选化学/生物(2选1)'
        '首选物理，再选化学、生物(2科必选)'
        '首选历史，再选思想政治'
    """
    if not sg_info:
        return True

    # --- 首选 ---
    if "首选物理" in sg_info:
        if "物理" not in user_subjects:
            return False
    elif "首选历史" in sg_info:
        if "历史" not in user_subjects:
            return False
    else:
        # 没有首选要求(罕见),默认放过
        pass

    # --- 再选 ---
    if "，" not in sg_info:
        return True
    rest = sg_info.split("，", 1)[1]
    if rest.startswith("再选"):
        rest = rest[2:].strip()

    # 不限
    if "不限" in rest:
        return True

    # 2选1: "化学/生物(2选1)"
    if "2选1" in rest:
        choices = rest.split("(")[0].strip()
        # 分隔符可能是 "/"
        items = [s.strip() for s in choices.split("/")]
        return any(_subject_in(it, user_subjects) for it in items)

    # 2科必选: "化学、生物(2科必选)"
    if "2科必选" in rest:
        choices = rest.split("(")[0].strip()
        items = [s.strip() for s in choices.split("、")]
        return all(_subject_in(it, user_subjects) for it in items)

    # 单科:"化学"  /  "思想政治"  /  "地理"
    single = rest.split("(")[0].strip()
    return _subject_in(single, user_subjects)


def _subject_in(name: str, user_subjects: set[str]) -> bool:
    """处理 思想政治 ↔ 政治 等别名"""
    if name in user_subjects:
        return True
    aliases = {
        "思想政治": "政治",
        "政治": "思想政治",
    }
    return aliases.get(name) in user_subjects


def latest_year(conn, school_id: int, type_id: str) -> Optional[int]:
    """该学校该科类已有的最新年份"""
    row = conn.execute(
        "SELECT MAX(CAST(year AS INTEGER)) AS y FROM province_scores "
        "WHERE school_id=? AND type_id=?",
        (school_id, type_id),
    ).fetchone()
    return row[0] if row and row[0] else None


def school_attrs(conn, school_id: int) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT name, province_name, city_name, type_name, "
        "f985, f211, dual_class_name FROM schools WHERE school_id=?",
        (school_id,),
    ).fetchone()


# === 自测 ===
if __name__ == "__main__":
    cases = [
        ("首选物理，再选不限", "物化生", True),
        ("首选物理，再选不限", "史政地", False),
        ("首选物理，再选化学", "物化生", True),
        ("首选物理，再选化学", "物生政", False),
        ("首选物理，再选化学/生物(2选1)", "物化政", True),
        ("首选物理，再选化学/生物(2选1)", "物生政", True),
        ("首选物理，再选化学/生物(2选1)", "物政地", False),
        ("首选物理，再选化学、生物(2科必选)", "物化生", True),
        ("首选物理，再选化学、生物(2科必选)", "物化政", False),
        ("首选历史，再选思想政治", "史政地", True),
        ("首选历史，再选思想政治", "史化生", False),
        ("首选历史，再选不限", "史政地", True),
    ]
    print("=== sg_info matcher 自测 ===")
    pass_n = 0
    for sg, combo, expected in cases:
        actual = matches_sg_info(sg, parse_combo(combo))
        ok = "✓" if actual == expected else "✗"
        if ok == "✓":
            pass_n += 1
        print(f"  {ok} sg='{sg}', combo='{combo}', expected={expected}, got={actual}")
    print(f"通过: {pass_n}/{len(cases)}")
