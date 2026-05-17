#!/usr/bin/env python3
"""
全省端到端测试 — 31 省本科+专科双路径全覆盖。

测试维度：
  A1. 本科 SKILL.md 结构（name / GAOKAO_PROV / 省名中文）
  A2. 本科 references 七大目录完整性
  B1. 专科 SKILL.md 存在且含省名
  B2. 专科 references 四目录完整性
  C.  数据文件（DB + 批次线 + 一分一段 CSV≥5）
  D1. score_to_rank 高分 → rank 有效, method≠fallback_no_data
  D2. score_to_rank 低分 → bracket=between_undergrad_and_vocational（仅 3+1+2）
  E.  query_school 召回 → 冲/稳/保合计≥min_results（首届/3+3/老高考设为0）

用法：
  cd /Users/xiaowu/workplace/志愿
  python3 tests/e2e_all_provinces.py
  python3 tests/e2e_all_provinces.py --prov hubei
  python3 tests/e2e_all_provinces.py --only-fail
  python3 tests/e2e_all_provinces.py --skip-slow      # 跳过 query_school
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

# ── 省份配置表 ────────────────────────────────────────────────────────────────
# (prov, zh, policy, primary_type, high_score, low_score, combo, year,
#  min_qs_results, bracket_test)
#
# bracket_test=True  → 测低分专科分流（仅 3+1+2 省份，批次线数据可靠）
# min_qs_results=0   → 跳过 query_school 结果数检查（首届/3+3/老高考）
PROVINCES = [
    # 3+1+2 — 2021 首届（4+年录取数据）
    ("hubei",        "湖北",   "3+1+2", "物理类", 560, 350, "物化生", 2025, 3,  True),
    ("hunan",        "湖南",   "3+1+2", "物理类", 560, 350, "物化生", 2025, 3,  True),
    ("guangdong",    "广东",   "3+1+2", "物理类", 560, 350, "物化生", 2025, 3,  True),
    ("jiangsu",      "江苏",   "3+1+2", "物理类", 560, 350, "物化生", 2025, 3,  True),
    ("hebei",        "河北",   "3+1+2", "物理类", 560, 350, "物化生", 2025, 3,  True),
    ("chongqing",    "重庆",   "3+1+2", "物理类", 560, 350, "物化生", 2025, 3,  True),
    ("fujian",       "福建",   "3+1+2", "物理类", 560, 350, "物化生", 2025, 3,  True),
    # 3+1+2 — 2022 首届（四川/云南 type_id 过渡期已修复，理科数据可召回）
    ("sichuan",      "四川",   "3+1+2", "物理类", 560, 350, "物化生", 2025, 1,  True),
    ("anhui",        "安徽",   "3+1+2", "物理类", 560, 350, "物化生", 2025, 1,  True),
    # 3+1+2 — 2024 首届（1年数据）
    ("guangxi",      "广西",   "3+1+2", "物理类", 520, 350, "物化生", 2025, 1,  True),
    ("guizhou",      "贵州",   "3+1+2", "物理类", 510, 350, "物化生", 2025, 1,  True),
    ("yunnan",       "云南",   "3+1+2", "物理类", 520, 350, "物化生", 2025, 1,  True),
    ("liaoning",     "辽宁",   "3+1+2", "物理类", 520, 350, "物化生", 2025, 1,  True),
    ("heilongjiang", "黑龙江", "3+1+2", "物理类", 480, 350, "物化生", 2025, 1,  True),
    ("jilin",        "吉林",   "3+1+2", "物理类", 480, 250, "物化生", 2025, 1,  True),
    ("jiangxi",      "江西",   "3+1+2", "物理类", 520, 350, "物化生", 2025, 1,  True),
    ("henan",        "河南",   "3+1+2", "物理类", 560, 350, "物化生", 2025, 1,  True),
    # 3+1+2 — 2025 首届（DB 老数据通过 type_id=1 可召回历史院校）
    ("neimenggu",    "内蒙古", "3+1+2", "物理类", 500, 350, "物化生", 2025, 1,  True),
    ("shaanxi",      "陕西",   "3+1+2", "物理类", 520, 350, "物化生", 2025, 1,  True),
    ("shanxi",       "山西",   "3+1+2", "物理类", 520, 350, "物化生", 2025, 1,  True),
    ("gansu",        "甘肃",   "3+1+2", "物理类", 480, 350, "物化生", 2025, 1,  True),
    ("ningxia",      "宁夏",   "3+1+2", "物理类", 450, 280, "物化生", 2025, 1,  True),
    ("qinghai",      "青海",   "3+1+2", "物理类", 420, 260, "物化生", 2025, 1,  True),
    # 3+3（shandong/zhejiang 有普通类二段，bracket 可测；京津沪琼无专科批线，跳过 D2）
    ("shandong",     "山东",   "3+3",   "综合",   560, 300, "不限",   2025, 1,  True),
    ("zhejiang",     "浙江",   "3+3",   "综合",   600, 380, "不限",   2025, 1,  True),
    ("beijing",      "北京",   "3+3",   "综合",   580, 400, "不限",   2025, 1,  False),
    ("shanghai",     "上海",   "3+3",   "综合",   500, 380, "不限",   2025, 1,  False),
    ("tianjin",      "天津",   "3+3",   "综合",   560, 380, "不限",   2025, 1,  False),
    ("hainan",       "海南",   "3+3",   "综合",   700, 460, "不限",   2025, 1,  False),
    # 老高考（xinjiang/xizang 均有专科批线，bracket 可测）
    ("xinjiang",     "新疆",   "老高考","理科",   450, 270, "不限",   2025, 1,  True),
    ("xizang",       "西藏",   "老高考","理科",   530, 270, "不限",   2024, 1,  True),
]

# ── 工具函数 ──────────────────────────────────────────────────────────────────

def run_json(cmd: list[str], prov: str) -> dict:
    env = {**os.environ, "GAOKAO_PROV": prov}
    r = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=ROOT, timeout=20)
    if r.returncode != 0:
        return {"error": r.stderr.strip() or r.stdout.strip() or "非零返回"}
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return {"error": f"JSON解析失败: {r.stdout[:120]}"}


@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class ProvResult:
    prov: str
    zh: str
    policy: str
    checks: list[Check] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def fail_count(self) -> int:
        return sum(1 for c in self.checks if not c.passed)


# ── 各维度检查 ────────────────────────────────────────────────────────────────

def check_a1_skill_md(prov: str, zh: str) -> Check:
    p = ROOT / "skill" / f"{prov}-zhiyuan" / "SKILL.md"
    if not p.exists():
        return Check("A1_zhiyuan_SKILL", False, "SKILL.md 不存在")
    c = p.read_text(encoding="utf-8")
    issues = []
    if "name:" not in c[:400]:
        issues.append("缺 name: 字段")
    if f"GAOKAO_PROV={prov}" not in c:
        issues.append(f"缺 GAOKAO_PROV={prov}")
    if zh not in c:
        issues.append(f"缺省名 {zh}")
    return Check("A1_zhiyuan_SKILL", not issues, "; ".join(issues) if issues else "OK")


def check_a2_references(prov: str, zh: str) -> Check:
    base = ROOT / "skill" / f"{prov}-zhiyuan" / "references"
    if not base.exists():
        return Check("A2_zhiyuan_refs", False, "references 目录不存在")
    issues = []
    required_dirs = [
        "00_核心方法论",
        "10_行业就业潜规则",
        "30_家庭背景_决策匹配",
        "40_未来锚点决策",
        "50_反常识洞察",
    ]
    for d in required_dirs:
        if not (base / d).exists():
            issues.append(f"缺 {d}")
    yuan = base / f"20_院校潜规则_{zh}视角"
    if not yuan.exists():
        issues.append(f"缺 20_院校潜规则_{zh}视角")
    else:
        n = len(list(yuan.glob("*.md")))
        if n < 4:
            issues.append(f"院校档案仅{n}篇(<4)")
    local = list(base.glob("90_*"))
    if not local:
        issues.append("缺 90_本地化")
    elif len(list(local[0].glob("*.md"))) < 2:
        issues.append("90_本地化 <2 篇")
    return Check("A2_zhiyuan_refs", not issues, "; ".join(issues) if issues else "OK")


def check_b1_zhuanke_skill(prov: str, zh: str) -> Check:
    p = ROOT / "skill" / f"{prov}-zhuanke" / "SKILL.md"
    if not p.exists():
        return Check("B1_zhuanke_SKILL", False, "SKILL.md 不存在")
    c = p.read_text(encoding="utf-8")
    issues = []
    if f"name: {prov}-zhuanke" not in c:
        issues.append("缺 name: 字段")
    if zh not in c:
        issues.append(f"缺省名 {zh}")
    return Check("B1_zhuanke_SKILL", not issues, "; ".join(issues) if issues else "OK")


def check_b2_zhuanke_refs(prov: str) -> Check:
    base = ROOT / "skill" / f"{prov}-zhuanke" / "references"
    if not base.exists():
        return Check("B2_zhuanke_refs", False, "references 目录不存在")
    required = ["00_核心方法论", "10_行业就业", "20_院校梯队", "30_专升本路径"]
    missing = [d for d in required if not (base / d).exists()]
    return Check("B2_zhuanke_refs", not missing,
                 "缺: " + ", ".join(missing) if missing else "OK")


def check_c_data(prov: str, primary_type: str) -> Check:
    issues = []
    db = list((ROOT / "data").glob(f"gaokao_{prov}_*.db"))
    if not db:
        issues.append("DB 缺失")
    bl = ROOT / "data" / "batch_lines" / f"{prov}.csv"
    if not bl.exists():
        issues.append("批次线 CSV 缺")
    csv_dir = ROOT / "data" / "yifenduyiduan"
    csvs = list(csv_dir.glob(f"*_{prov}.csv"))
    min_csv = 5 if primary_type == "综合" else 8
    if len(csvs) < min_csv:
        issues.append(f"一分一段 CSV {len(csvs)} 个 (<{min_csv})")
    detail = f"DB={'✓' if db else '✗'} 批次线={'✓' if bl.exists() else '✗'} CSV={len(csvs)}"
    return Check("C_data", not issues, detail + ("; " + "; ".join(issues) if issues else ""))


def check_d1_score_to_rank(prov: str, primary_type: str, high_score: int, year: int) -> Check:
    cmd = [sys.executable, str(SCRIPTS / "score_to_rank.py"),
           "--score", str(high_score), "--type", primary_type, "--year", str(year), "--json"]
    d = run_json(cmd, prov)
    if "error" in d:
        return Check("D1_score_to_rank", False, d["error"])
    rank = d.get("rank")
    method = d.get("method", "")
    if not rank or rank <= 0:
        return Check("D1_score_to_rank", False, f"rank={rank} 无效")
    if method == "fallback_no_data":
        return Check("D1_score_to_rank", False, f"fallback_no_data（无锚点数据）")
    return Check("D1_score_to_rank", True, f"rank={rank:,} method={method}")


def check_d2_bracket(prov: str, primary_type: str, low_score: int, year: int) -> Check:
    cmd = [sys.executable, str(SCRIPTS / "score_to_rank.py"),
           "--score", str(low_score), "--type", primary_type, "--year", str(year), "--json"]
    d = run_json(cmd, prov)
    if "error" in d:
        return Check("D2_bracket", False, d["error"])
    bracket = d.get("batch", {}).get("bracket", "unknown")
    expected = "between_undergrad_and_vocational"
    ok = bracket == expected
    return Check("D2_bracket", ok,
                 f"score={low_score} bracket={bracket}" + ("" if ok else f" (期望{expected})"))


def check_e_query_school(prov: str, primary_type: str, high_score: int,
                         year: int, min_results: int) -> Check:
    # 先拿位次
    cmd_s2r = [sys.executable, str(SCRIPTS / "score_to_rank.py"),
               "--score", str(high_score), "--type", primary_type,
               "--year", str(year), "--json"]
    s2r = run_json(cmd_s2r, prov)
    rank = s2r.get("rank")
    if not rank:
        return Check("E_query_school", min_results == 0,
                     f"score_to_rank 无位次，跳过召回" + (" (已豁免)" if min_results == 0 else ""))

    qt = primary_type if primary_type in ("物理类", "历史类", "综合", "理科", "文科") else "物理类"
    combo = "物化生" if qt in ("物理类", "历史类", "理科") else "物化生"
    # 传 --rank 同时带上 --score-also，供无位次数据的省份（如西藏）自动降级为分数模式
    qs_args = ["--rank", str(rank), "--score-also", str(high_score),
               "--type", qt, "--top", "10", "--json"]
    if qt not in ("综合", "文科", "理科"):
        qs_args += ["--combo", combo]
    cmd_qs = [sys.executable, str(SCRIPTS / "query_school.py")] + qs_args
    d = run_json(cmd_qs, prov)
    if "error" in d:
        if min_results == 0:
            return Check("E_query_school", True, f"rank={rank:,} 召回出错(已豁免): {d['error'][:60]}")
        return Check("E_query_school", False, d["error"])

    total = len(d.get("chong", [])) + len(d.get("wen", [])) + len(d.get("bao", []))
    ok = total >= min_results
    mode = d.get("input", {}).get("mode", "rank")
    mode_tag = "[分数模式]" if mode == "score_fallback" else ""
    exempt = "(已豁免)" if min_results == 0 else f"(需≥{min_results})"
    return Check("E_query_school", ok,
                 f"rank={rank:,} 冲={len(d.get('chong',[]))} 稳={len(d.get('wen',[]))} 保={len(d.get('bao',[]))} {mode_tag}{exempt}")


# ── 单省测试 ──────────────────────────────────────────────────────────────────

def test_province(prov: str, zh: str, policy: str, primary_type: str,
                  high_score: int, low_score: int, combo: str, year: int,
                  min_qs: int, bracket_test: bool, skip_slow: bool) -> ProvResult:
    res = ProvResult(prov=prov, zh=zh, policy=policy)

    res.checks.append(check_a1_skill_md(prov, zh))
    res.checks.append(check_a2_references(prov, zh))
    res.checks.append(check_b1_zhuanke_skill(prov, zh))
    res.checks.append(check_b2_zhuanke_refs(prov))
    res.checks.append(check_c_data(prov, primary_type))
    res.checks.append(check_d1_score_to_rank(prov, primary_type, high_score, year))

    if bracket_test:
        res.checks.append(check_d2_bracket(prov, primary_type, low_score, year))

    if not skip_slow:
        res.checks.append(check_e_query_school(prov, primary_type, high_score, year, min_qs))

    return res


# ── 主函数 ────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prov", default=None, help="只测某个省份")
    ap.add_argument("--only-fail", action="store_true", help="只显示失败省份")
    ap.add_argument("--skip-slow", action="store_true", help="跳过 query_school（E检查）")
    args = ap.parse_args()

    target = [p for p in PROVINCES if args.prov is None or p[0] == args.prov]
    if not target:
        print(f"未找到省份: {args.prov}")
        sys.exit(1)

    mode_hint = " [--skip-slow: 已跳过E]" if args.skip_slow else ""
    print(f"=== 全省端到端测试 ({len(target)} 省 × 本专科){mode_hint} ===\n")
    print(f"{'省份':<10} {'政策':<7} {'A1':<4} {'A2':<4} {'B1':<4} {'B2':<4} "
          f"{'C':<4} {'D1':<4} {'D2':<4} {'E':<4} 状态")
    print("─" * 80)

    results: list[ProvResult] = []
    for row in target:
        prov, zh, policy, primary_type, high, low, combo, year, min_qs, bracket_test = row
        label = f"{zh:<6}({prov:<12})"
        print(f"  {label} {policy:<7} ", end="", flush=True)
        r = test_province(prov, zh, policy, primary_type, high, low, combo,
                          year, min_qs, bracket_test, args.skip_slow)
        results.append(r)

        # 按固定顺序打印各检查 mark
        check_map = {c.name: c for c in r.checks}
        for dim in ["A1_zhiyuan_SKILL", "A2_zhiyuan_refs", "B1_zhuanke_SKILL",
                    "B2_zhuanke_refs", "C_data", "D1_score_to_rank",
                    "D2_bracket", "E_query_school"]:
            c = check_map.get(dim)
            if c is None:
                print("─   ", end="")
            else:
                print(("✓   " if c.passed else "✗   "), end="")
        status = "OK" if r.passed else f"FAIL({r.fail_count}项)"
        print(status)

    # ── 汇总 ────────────────────────────────────────────────────────────────
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    fails = [r for r in results if not r.passed]

    print(f"\n{'─'*80}")
    print(f"=== 结果: {passed}/{total} 省通过 ===\n")

    if fails:
        print("【失败详情】")
        for r in fails:
            print(f"\n  ◉ {r.zh}({r.prov}, {r.policy})")
            for c in r.checks:
                if not c.passed:
                    print(f"    ✗ {c.name}: {c.detail}")

    if not args.only_fail:
        # 打印通过省份汇总
        ok_provs = [r.zh for r in results if r.passed]
        if ok_provs:
            print(f"\n【全通过】{'  '.join(ok_provs)}")

    total_checks = sum(len(r.checks) for r in results)
    passed_checks = sum(sum(1 for c in r.checks if c.passed) for r in results)
    print(f"\n检查项合计: {passed_checks}/{total_checks} 通过")

    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
