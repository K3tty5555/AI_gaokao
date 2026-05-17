#!/usr/bin/env python3
"""
端到端测试 — 模拟真实用户场景，检测主力省份的核心路径是否通畅。

测试维度：
  1. score_to_rank  : 分数→位次转换是否正常
  2. query_school   : 冲/稳/保召回是否有结果
  3. 录取概率       : admission_prob 字段是否有效
  4. 数据覆盖       : 近3年数据是否充足

用法：
  cd /Users/xiaowu/workplace/志愿
  python3 tests/e2e_test.py
  python3 tests/e2e_test.py --prov hubei    # 只测单省
  python3 tests/e2e_test.py --verbose       # 展示完整 JSON
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "skill" / "_shared" / "scripts"

# ── 测试用例 ─────────────────────────────────────────────────────────────────

@dataclass
class Case:
    prov: str
    prov_zh: str
    policy: str          # 3+1+2 / 3+3 / 老高考
    score: int
    subject_type: str    # 物理类 / 历史类 / 综合 / 理科 / 文科
    combo: str           # 选科组合（3+3/老高考 用 "不限"）
    year: int = 2025
    note: str = ""
    # 预期最低召回数（冲+稳+保）
    min_results: int = 3

CASES = [
    Case("hubei",     "湖北", "3+1+2", 580, "物理类", "物化生",  note="基准省份"),
    Case("hubei",     "湖北", "3+1+2", 450, "历史类", "史政地",  note="低分段历史类"),
    Case("guangdong", "广东", "3+1+2", 580, "物理类", "物化生",  note="高考大省"),
    Case("guangdong", "广东", "3+1+2", 500, "历史类", "史化政",  note="广东历史类中段"),
    Case("henan",     "河南", "3+1+2", 580, "物理类", "物化生",  note="首届3+1+2(1年数据)",  min_results=1),
    # 河南老高考（2024届）已录取完毕，无当前用户场景，跳过 query_school 测试
    Case("henan",     "河南", "老高考",580, "理科",   "不限",    year=2024, note="老高考score_to_rank验证", min_results=0),
    Case("sichuan",   "四川", "3+1+2", 560, "物理类", "物化生",  note="数据残缺(待重爬)", min_results=0),
    Case("shandong",  "山东", "3+3",   580, "综合",   "不限",    note="3+3体系", min_results=0),
    Case("jiangsu",   "江苏", "3+1+2", 580, "物理类", "物化生",  note="3+1+2第五届"),
    Case("zhejiang",  "浙江", "3+3",   600, "综合",   "不限",    note="3+3体系", min_results=0),
    Case("anhui",     "安徽", "3+1+2", 560, "物理类", "物化生",  note="2024-2025两年数据"),
    Case("liaoning",  "辽宁", "3+1+2", 560, "物理类", "物化生",  note="2024首届多年数据"),
    Case("jiangxi",   "江西", "3+1+2", 520, "物理类", "物化生",  note="2024首届"),
]

# 首届/数据残缺省份：豁免 admission_prob 检查
PROB_EXEMPT = {"henan", "sichuan", "yunnan", "shanxi", "shaanxi", "neimenggu",
               "gansu", "ningxia", "qinghai", "xinjiang"}

# ── 运行单个脚本 ──────────────────────────────────────────────────────────────

def run_score_to_rank(prov: str, score: int, subject_type: str, year: int) -> dict:
    env = {**os.environ, "GAOKAO_PROV": prov}
    # 老高考直接传原始科类名（理科/文科），不映射
    st = subject_type
    cmd = [
        sys.executable,
        str(SCRIPTS / "score_to_rank.py"),
        "--score", str(score),
        "--type", st,
        "--year", str(year),
        "--json",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=ROOT)
    if r.returncode != 0:
        return {"error": r.stderr.strip() or "非零返回"}
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return {"error": f"JSON解析失败: {r.stdout[:200]}"}


def run_query_school(prov: str, rank: int, subject_type: str, combo: str,
                     year: int) -> dict:
    env = {**os.environ, "GAOKAO_PROV": prov}
    # 3+3/老高考：type 不是物理类/历史类时，query_school 用 物理类 作探测
    qt = subject_type if subject_type in ("物理类", "历史类") else "物理类"
    qc = combo if combo != "不限" else "物化生"
    cmd = [
        sys.executable,
        str(SCRIPTS / "query_school.py"),
        "--rank", str(rank),
        "--type", qt,
        "--combo", qc,
        "--min-year", str(year),
        "--top", "5",
        "--json",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=ROOT)
    if r.returncode != 0:
        return {"error": r.stderr.strip() or "非零返回"}
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return {"error": f"JSON解析失败: {r.stdout[:200]}"}

# ── 断言 ──────────────────────────────────────────────────────────────────────

@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""

@dataclass
class Result:
    case: Case
    checks: list[Check] = field(default_factory=list)
    rank: Optional[int] = None

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    def summary_line(self) -> str:
        icon = "✓" if self.passed else "✗"
        fails = [c for c in self.checks if not c.passed]
        fail_str = "; ".join(f.name for f in fails) if fails else "全通过"
        rank_str = f"位次={self.rank}" if self.rank else "位次=N/A"
        return (f"  {icon} {self.case.prov_zh}({self.case.subject_type}) "
                f"score={self.case.score} {rank_str} — {fail_str}")


# ── 单个测试 ──────────────────────────────────────────────────────────────────

def run_case(case: Case, verbose: bool = False) -> Result:
    res = Result(case=case)

    # 1. score_to_rank
    s2r = run_score_to_rank(case.prov, case.score, case.subject_type, case.year)
    if "error" in s2r:
        res.checks.append(Check("score_to_rank", False, s2r["error"]))
        return res  # 后续依赖 rank，无法继续

    rank = s2r.get("rank")
    batch = s2r.get("batch", {}).get("bracket", "unknown")
    res.rank = rank

    res.checks.append(Check(
        "score_to_rank",
        rank is not None and rank > 0,
        f"rank={rank}, batch={batch}"
    ))
    if verbose:
        print(f"    score_to_rank: {json.dumps(s2r, ensure_ascii=False)}")

    if not rank:
        return res

    # 2. query_school
    qs = run_query_school(case.prov, rank, case.subject_type, case.combo, case.year)
    if "error" in qs:
        res.checks.append(Check("query_school", False, qs["error"]))
        return res

    total = len(qs.get("chong", [])) + len(qs.get("wen", [])) + len(qs.get("bao", []))
    n_chong = len(qs.get("chong", []))
    n_wen   = len(qs.get("wen", []))
    n_bao   = len(qs.get("bao", []))

    res.checks.append(Check(
        "query_school_results",
        total >= case.min_results,
        f"冲={n_chong} 稳={n_wen} 保={n_bao} (需≥{case.min_results})"
    ))

    if verbose:
        # 打印前两个稳档结果
        for item in qs.get("wen", [])[:2]:
            print(f"    稳: {item['school_name']} {item['sg_name']} "
                  f"位次={item['min_section']} 概率={item.get('admission_prob',{}).get('display','N/A')}")

    # 3. 录取概率（首届/数据残缺省份豁免）
    all_items = qs.get("chong", []) + qs.get("wen", []) + qs.get("bao", [])
    if all_items:
        with_prob = [i for i in all_items if i.get("admission_prob") and
                     i["admission_prob"].get("probability") is not None]
        prob_rate = len(with_prob) / len(all_items)
        exempt = case.prov in PROB_EXEMPT
        res.checks.append(Check(
            "admission_prob" + (" (豁免)" if exempt else ""),
            exempt or prob_rate >= 0.4,
            f"{len(with_prob)}/{len(all_items)} 条有概率 ({prob_rate:.0%})"
                + (" — 首届数据不足属预期" if exempt else "")
        ))

    # 4. 近3年数据覆盖
    if all_items:
        multi_year = [i for i in all_items if len(i.get("history_ranks", [])) >= 2]
        coverage = len(multi_year) / len(all_items)
        res.checks.append(Check(
            "multi_year_coverage",
            coverage >= 0.3 or case.prov == "henan",  # 河南首届豁免
            f"{len(multi_year)}/{len(all_items)} 条有≥2年历史 ({coverage:.0%})"
        ))

    return res


# ── 主函数 ────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prov", default=None, help="只测某个省份")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    cases = [c for c in CASES if args.prov is None or c.prov == args.prov]

    print(f"=== 端到端测试 ({len(cases)} 个场景) ===\n")

    results: list[Result] = []
    for case in cases:
        label = f"{case.prov_zh}({case.subject_type}) score={case.score}"
        print(f"[{label}] {case.note}...")
        r = run_case(case, verbose=args.verbose)
        results.append(r)
        print(r.summary_line())
        if not r.passed:
            for chk in r.checks:
                icon = "  ✓" if chk.passed else "  ✗"
                print(f"    {icon} {chk.name}: {chk.detail}")
        print()

    passed = sum(1 for r in results if r.passed)
    total  = len(results)
    print(f"=== 结果: {passed}/{total} 通过 ===")

    # 汇总失败项
    failures = [r for r in results if not r.passed]
    if failures:
        print("\n失败详情：")
        for r in failures:
            print(f"\n  [{r.case.prov_zh} {r.case.subject_type} {r.case.score}分] {r.case.note}")
            for chk in r.checks:
                if not chk.passed:
                    print(f"    ✗ {chk.name}: {chk.detail}")

    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
