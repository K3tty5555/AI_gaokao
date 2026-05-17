"""共享:DB 连接 + 选科组合解析 + sg_info 匹配 (跨省通用)"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Optional

# 数据目录:项目根/data/
# 路径推导:scripts → _shared → skill → 项目根 → data/
DATA_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent / "data"
)


def _latest_db(prov: str = "hubei") -> Path:
    """自动找 data/ 里某省最新的 gaokao_<prov>_<YYYY>.db。

    支持按年份归档:多个年份共存时取年份最大的。
    """
    candidates = sorted(DATA_DIR.glob(f"gaokao_{prov}_*.db"))
    # 兜底:旧版无年份后缀的文件名(早期湖北版)
    legacy = DATA_DIR / f"gaokao_{prov}.db"
    if legacy.exists():
        candidates.append(legacy)
    if not candidates:
        raise FileNotFoundError(
            f"未找到 {prov} 数据库文件。预期路径:{DATA_DIR}/gaokao_{prov}_<YYYY>.db。"
            f"运行 `python3 crawl.py --prov {prov}` 爬取数据。"
        )
    return candidates[-1]


# 默认省份从环境变量读取(每省 skill 在调用 scripts 前设 GAOKAO_PROV=hunan 等)
# 默认 hubei 保持向后兼容
PROVINCE = os.environ.get("GAOKAO_PROV", "hubei")
DB_PATH = _latest_db(PROVINCE)

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


def compute_risk(history_ranks):
    """
    给一个 (school_id, special_group, type_id) 历年最低位次序列(按年份升序),
    计算大小年风险标签。

    Args:
        history_ranks: 列表,如 [(year, rank), ...] 按年份升序

    Returns:
        dict: {
            "level": stable / low_risk / moderate / high_risk / unknown,
            "cv": 变异系数,
            "mean": 历年均值位次,
            "std": 标准差,
            "trend": rising_score / dropping_score / stable,
            "note": 一句话解读(给用户看)
        }
    """
    ranks = [r for _, r in history_ranks if r is not None and r > 0]
    if len(ranks) < 2:
        return {
            "level": "unknown",
            "cv": None,
            "mean": ranks[0] if ranks else None,
            "std": None,
            "trend": "unknown",
            "note": "近 3 年数据不足,无法判断大小年",
        }

    mean = sum(ranks) / len(ranks)
    variance = sum((r - mean) ** 2 for r in ranks) / len(ranks)
    std = variance ** 0.5
    cv = std / mean if mean > 0 else 0

    # EWMA（指数加权移动平均）：对趋势型院校比等权均值更贴近近年实际
    # alpha=0.4：最近年权重最高，越早年份权重指数衰减
    ewma_val = float(ranks[0])
    for r in ranks[1:]:
        ewma_val = 0.4 * r + 0.6 * ewma_val

    # 风险等级阈值
    if cv < 0.05:
        level = "stable"
        note_base = "近年录取位次稳定"
    elif cv < 0.10:
        level = "low_risk"
        note_base = f"位次有小波动 (±{int(std)} 名)"
    elif cv < 0.20:
        level = "moderate"
        note_base = f"位次波动 (±{int(std)} 名),有大小年苗头"
    else:
        level = "high_risk"
        note_base = f"近年位次波动极大 (±{int(std)} 名),典型大小年"

    # 趋势判断：基于最近相邻2年（而非首尾比较），防止"过山车型"误导方向
    trend = "stable"
    trend_note = ""
    if len(ranks) >= 2:
        sig = mean * 0.10  # 显著性阈值：均值的10%
        recent_delta = ranks[-1] - ranks[-2]   # 正=rank变大=分数下滑

        if len(ranks) >= 3:
            prev_delta = ranks[-2] - ranks[-3]
            recent_sig = abs(recent_delta) > sig
            prev_sig = abs(prev_delta) > sig

            if recent_sig and prev_sig:
                same_dir = (recent_delta > 0) == (prev_delta > 0)
                if not same_dir:
                    # 方向相反：震荡型大小年，不给方向建议
                    trend = "volatile"
                    trend_note = ";近年位次方向不稳定(震荡型大小年),建议保守估计"
                elif recent_delta < 0:
                    # 连续2年rank下降 = 分数飙升，越来越难进
                    trend = "rising_score"
                    trend_note = ";近2年连续位次下降(分数飙升,**今年可能继续涨,慎重冲档**)"
                else:
                    # 连续2年rank上涨 = 分数下滑，越来越容易进但可能反弹变难
                    trend = "dropping_score"
                    trend_note = ";近2年连续位次上涨(分数下滑,**今年可能继续涨,慎重冲档**)"
            elif recent_sig:
                # 只有最近一年显著变化（前期稳定后突变）
                if recent_delta < 0:
                    trend = "rising_score"
                    trend_note = ";最近一年位次猛涨(分数飙升,**今年可能反弹,稳档可考虑**)"
                else:
                    # 单年暴跌：分数下滑，但前期稳定说明基本面未变，反弹风险高
                    trend = "dropping_score"
                    trend_note = ";最近一年位次回落(分数下滑,**今年可能反弹变难,填报请参考历史均值而非今年分数**)"
        else:
            # 仅2年数据：直接看方向
            if recent_delta < -sig:
                trend = "rising_score"
                trend_note = ";最近一年位次猛涨(分数飙升,**今年可能反弹,稳档可考虑**)"
            elif recent_delta > sig:
                trend = "dropping_score"
                trend_note = ";最近一年位次回落(分数下滑,**今年可能反弹变难,填报请参考历史均值**)"

    return {
        "level": level,
        "cv": round(cv, 3),
        "mean": int(mean),
        "ewma": int(ewma_val),   # 指数加权均值，对趋势型院校比等权均值更准
        "std": int(std),
        "trend": trend,
        "note": note_base + trend_note,
    }


def compute_admission_probability(user_rank: int, history_ranks: list) -> dict:
    """
    计算用户被录取的概率（滑档概率的补集）。

    Args:
        user_rank: 用户全省位次（数字越小越靠前）
        history_ranks: [(year, min_section), ...]，min_section 是该校该年录取最低位次

    Returns:
        dict: {
            "probability": float 0-1 或 None,
            "display": 给用户看的字符串,
            "label": 安全/较稳/有风险/高风险/未知,
            "mean_rank": 历年均值位次,
            "std_rank": 标准差,
        }
    """
    from math import erf, sqrt

    ranks = [r for _, r in history_ranks if r is not None and r > 0]

    if len(ranks) < 2:
        return {
            "probability": None,
            "display": "数据不足",
            "label": "未知",
            "mean_rank": ranks[0] if ranks else None,
            "std_rank": None,
        }

    mean = sum(ranks) / len(ranks)
    variance = sum((r - mean) ** 2 for r in ranks) / len(ranks)
    std = variance ** 0.5

    # 经验概率：历史中 user_rank <= school_rank（录取线）的年份比例
    # 大小年分布往往是偏态/双峰，正态 CDF 会低估极端值概率
    emp_count = sum(1 for r in ranks if user_rank <= r)
    emp_prob = emp_count / len(ranks)

    # Laplace 收缩：样本量少时向 0.5 收缩，防止"3年全录取→显示95%安全"过度自信
    # n=2→k=0.4; n=3→k=0.6; n=4→k=0.8; n≥5→k=1.0（纯经验）
    k = min(len(ranks), 5) / 5.0
    prob = k * emp_prob + (1.0 - k) * 0.5

    # clamp to [0.05, 0.95]
    prob = max(0.05, min(0.95, prob))

    if prob >= 0.85:
        label = "安全"
    elif prob >= 0.65:
        label = "较稳"
    elif prob >= 0.35:
        label = "有风险"
    else:
        label = "高风险"

    return {
        "probability": round(prob, 4),
        "display": f"{int(round(prob * 100))}%",
        "label": label,
        "mean_rank": int(mean),
        "std_rank": int(std),
    }


_BATCH_LINES_CACHE: dict = {}


def load_batch_lines():
    """加载 data/batch_lines/{PROVINCE}.csv,返回 [{年份, 科类, 批次, 分数, 位次}, ...]"""
    global _BATCH_LINES_CACHE
    if PROVINCE in _BATCH_LINES_CACHE:
        return _BATCH_LINES_CACHE[PROVINCE]
    import csv as _csv
    path = DATA_DIR / "batch_lines" / f"{PROVINCE}.csv"
    if not path.exists():
        _BATCH_LINES_CACHE[PROVINCE] = []
        return []
    rows = []
    with path.open() as f:
        for r in _csv.DictReader(f):
            if r.get("年份", "").startswith("#"):
                continue
            try:
                year = int(r["年份"])
                score = int(r["控制线分数"])
            except (ValueError, KeyError):
                continue
            rank_raw = r.get("对应位次", "").strip()
            try:
                rank = int(rank_raw) if rank_raw and rank_raw not in ("N/A", "-", "") else None
            except ValueError:
                rank = None
            rows.append({
                "year": year,
                "subject_type": r.get("科类", ""),
                "batch": r.get("批次", ""),
                "score": score,
                "rank": rank,
            })
    _BATCH_LINES_CACHE[PROVINCE] = rows
    return rows


# 批次名别名表 — 覆盖 3+1+2 / 3+3 / 老高考 三种体系
# special_aliases:  强基/综评线，高于普通本科
# undergrad_aliases: 普通本科线
# vocational_aliases: 专科线
_SPECIAL_ALIASES = {"本科特控线", "特殊类型招生控制线", "特控线", "特殊类型", "一本"}
_UNDERGRAD_ALIASES = {"本科批", "普通类一段", "二本"}
_VOCATIONAL_ALIASES = {"专科批", "普通类二段", "专科"}


def _pick_batch(by_batch: dict, aliases: set) -> Optional[dict]:
    for name in aliases:
        if name in by_batch:
            return by_batch[name]
    return None


def classify_score(score: int, subject_type: str, year: int):
    """给定分数 + 科类 + 年份,判断处于哪个批次档位。

    兼容三种体系：
      3+1+2:  本科批 / 本科特控线 / 专科批
      3+3:    普通类一段 / 特殊类型招生控制线 / 普通类二段
      老高考:  二本(本科线) / 一本(重点线) / 专科

    Returns dict:
        bracket: "above_special" / "above_undergrad" /
                 "between_undergrad_and_vocational" / "below_vocational"
        label:   人类可读标签
        action:  推荐的产品分流
        nearby_lines: 附近批次线
    """
    lines = load_batch_lines()
    by_batch = {
        r["batch"]: r for r in lines
        if r["year"] == year and r["subject_type"] == subject_type
    }

    undergrad = _pick_batch(by_batch, _UNDERGRAD_ALIASES)
    special   = _pick_batch(by_batch, _SPECIAL_ALIASES)
    vocational = _pick_batch(by_batch, _VOCATIONAL_ALIASES)

    if not undergrad:
        return {
            "bracket": "unknown",
            "label": "无该年批次线数据",
            "action": "default",
            "nearby_lines": [],
        }

    if special and score >= special["score"]:
        return {
            "bracket": "above_special",
            "label": f"{special['batch']}以上(强基/综合评价/特殊类型可报)",
            "action": "main_skill",
            "nearby_lines": [special, undergrad],
        }
    if score >= undergrad["score"]:
        return {
            "bracket": "above_undergrad",
            "label": undergrad["batch"],
            "action": "main_skill",
            "nearby_lines": [undergrad] + ([special] if special else []),
        }
    if vocational and score >= vocational["score"]:
        return {
            "bracket": "between_undergrad_and_vocational",
            "label": f"{undergrad['batch']}线下 / {vocational['batch']}线上(差{undergrad['score'] - score}分)",
            "action": "fork_repeat_or_vocational",
            "nearby_lines": [undergrad, vocational],
        }
    return {
        "bracket": "below_vocational",
        "label": f"{vocational['batch'] if vocational else '专科'}线下",
        "action": "suggest_repeat_or_alternative",
        "nearby_lines": [vocational] if vocational else [],
    }


def get_history_ranks(conn, school_id: int, type_id: str, special_group: str = None,
                      min_year: int = 2021, extra_type_id: str = None):
    """从 province_scores 拉历年最低位次序列,按年份升序返回 [(year, rank), ...]。

    粒度选择:
    - 如果指定 special_group:返回该专业组的历年位次(精细但通常拿不到 ≥2 年,因为组号每年变)
    - 不指定 special_group:返回 (school_id, type_id) 的"年度最低位次"
      = 每年该校该科类所有专业组中最低的位次 = 该校该科类录取最难的那个组的位次
      这是稳定可比的口径,**默认推荐用法**

    只看普通类(zslx_name='普通类'),避开国家专项/民族班等特殊类别的位次跳动干扰。
    """
    type_ids = [type_id]
    if extra_type_id and extra_type_id != type_id:
        type_ids.append(extra_type_id)
    placeholders = ", ".join("?" * len(type_ids))

    if special_group:
        rows = conn.execute(
            f"""
            SELECT CAST(year AS INTEGER) AS y, CAST(min_section AS INTEGER) AS r
            FROM province_scores
            WHERE school_id=? AND type_id IN ({placeholders}) AND special_group=?
              AND CAST(year AS INTEGER) >= ?
              AND min_section IS NOT NULL AND min_section != '' AND min_section != '-'
            ORDER BY y ASC
            """,
            (school_id, *type_ids, special_group, min_year),
        ).fetchall()
    else:
        rows = conn.execute(
            f"""
            SELECT CAST(year AS INTEGER) AS y,
                   MIN(CAST(min_section AS INTEGER)) AS r
            FROM province_scores
            WHERE school_id=? AND type_id IN ({placeholders})
              AND zslx_name = '普通类'
              AND CAST(year AS INTEGER) >= ?
              AND min_section IS NOT NULL AND min_section != '' AND min_section != '-'
            GROUP BY y
            ORDER BY y ASC
            """,
            (school_id, *type_ids, min_year),
        ).fetchall()
    return [(r[0], r[1]) for r in rows if r[1] and r[1] > 0]


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
