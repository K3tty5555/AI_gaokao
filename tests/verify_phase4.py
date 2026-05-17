#!/usr/bin/env python3
"""Phase 4 全省结构性验证 — 31 省 SKILL/refs/scripts/data/score_to_rank 全检查。"""
import os
import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PROVINCES = [
    # (拼音, 中文, 政策, 总分, 主要科类列表)
    ("hubei",      "湖北",  "3+1+2",  750, ["物理类", "历史类"]),
    ("hunan",      "湖南",  "3+1+2",  750, ["物理类", "历史类"]),
    ("jiangsu",    "江苏",  "3+1+2",  750, ["物理类", "历史类"]),
    ("hebei",      "河北",  "3+1+2",  750, ["物理类", "历史类"]),
    ("guangdong",  "广东",  "3+1+2",  750, ["物理类", "历史类"]),
    ("chongqing",  "重庆",  "3+1+2",  750, ["物理类", "历史类"]),
    ("fujian",     "福建",  "3+1+2",  750, ["物理类", "历史类"]),
    ("liaoning",   "辽宁",  "3+1+2",  750, ["物理类", "历史类"]),
    ("anhui",      "安徽",  "混合",   750, ["文科","理科","物理类","历史类"]),
    ("jiangxi",    "江西",  "混合",   750, ["文科","理科","物理类","历史类"]),
    ("guangxi",    "广西",  "混合",   750, ["文科","理科","物理类","历史类"]),
    ("guizhou",    "贵州",  "混合",   750, ["文科","理科","物理类","历史类"]),
    ("heilongjiang","黑龙江","混合",  750, ["文科","理科","物理类","历史类"]),
    ("jilin",      "吉林",  "混合",   750, ["文科","理科","物理类","历史类"]),
    ("gansu",      "甘肃",  "混合",   750, ["文科","理科","物理类","历史类"]),
    ("henan",      "河南",  "混合",   750, ["文科","理科","物理类","历史类"]),
    ("shanxi",     "山西",  "混合",   750, ["文科","理科","物理类","历史类"]),
    ("sichuan",    "四川",  "混合",   750, ["文科","理科","物理类","历史类"]),
    ("shaanxi",    "陕西",  "混合",   750, ["文科","理科","物理类","历史类"]),
    ("yunnan",     "云南",  "混合",   750, ["文科","理科","物理类","历史类"]),
    ("neimenggu",  "内蒙古","混合",   750, ["文科","理科","物理类","历史类"]),
    ("qinghai",    "青海",  "混合",   750, ["文科","理科","物理类","历史类"]),
    ("ningxia",    "宁夏",  "混合",   750, ["文科","理科","物理类","历史类"]),
    ("xinjiang",   "新疆",  "老高考", 750, ["文科","理科"]),
    ("xizang",     "西藏",  "老高考", 750, ["文科","理科"]),
    ("shanghai",   "上海",  "3+3",    660, ["综合"]),
    ("beijing",    "北京",  "3+3",    750, ["综合"]),
    ("tianjin",    "天津",  "3+3",    750, ["综合"]),
    ("zhejiang",   "浙江",  "3+3",    750, ["综合"]),
    ("shandong",   "山东",  "3+3",    750, ["综合"]),
    ("hainan",     "海南",  "3+3",    900, ["综合"]),
]

REQUIRED_SHARED = ["00_核心方法论", "10_行业就业潜规则", "30_家庭背景_决策匹配",
                   "40_未来锚点决策", "50_反常识洞察"]


def check_skill_md(prov, zh):
    p = ROOT / "skill" / f"{prov}-zhiyuan" / "SKILL.md"
    if not p.exists():
        return False, "SKILL.md 不存在"
    c = p.read_text(encoding="utf-8")
    issues = []
    if "name:" not in c[:300]:
        issues.append("缺 frontmatter name")
    if f"GAOKAO_PROV={prov}" not in c:
        issues.append(f"缺 GAOKAO_PROV={prov}")
    if zh not in c:
        issues.append(f"缺中文省名 {zh}")
    return len(issues) == 0, "; ".join(issues)


def check_references(prov, zh):
    base = ROOT / "skill" / f"{prov}-zhiyuan" / "references"
    if not base.exists():
        return False, "references 目录不存在"
    issues = []
    for shared in REQUIRED_SHARED:
        sub = base / shared
        if not sub.exists():
            issues.append(f"缺 {shared}")
        elif not sub.is_symlink():
            issues.append(f"{shared} 非软链")
    yuan_dir = base / f"20_院校潜规则_{zh}视角"
    if not yuan_dir.exists():
        issues.append(f"缺 20_院校潜规则_{zh}视角")
    else:
        n = len(list(yuan_dir.glob("*.md")))
        if n < 4:
            issues.append(f"院校档案仅 {n} 篇")
    local_dirs = list(base.glob("90_*"))
    if not local_dirs:
        issues.append("缺 90_本地化")
    elif len(list(local_dirs[0].glob("*.md"))) < 2:
        issues.append("90_本地化 < 2 篇")
    return len(issues) == 0, "; ".join(issues)


def check_scripts(prov):
    p = ROOT / "skill" / f"{prov}-zhiyuan" / "scripts"
    if not p.exists():
        return False, "scripts 不存在"
    if not p.is_symlink():
        return False, "scripts 非软链"
    return True, ""


def check_data(prov, types):
    issues = []
    csv_dir = ROOT / "data" / "yifenduyiduan"
    csvs = list(csv_dir.glob(f"*_{prov}.csv"))
    expected_min = 5 if types == ["综合"] else 8
    if len(csvs) < expected_min:
        issues.append(f"CSV {len(csvs)} 个 (<{expected_min})")
    bl = ROOT / "data" / "batch_lines" / f"{prov}.csv"
    if not bl.exists():
        issues.append("批次线缺")
    db = list((ROOT / "data").glob(f"gaokao_{prov}_*.db"))
    if not db:
        issues.append("掌上高考 DB 缺")
    return len(issues) == 0, "; ".join(issues)


def check_score_to_rank(prov, types):
    """试 2024+2025 × 所有科类,任一成功即 pass(各省政策不同,2024 vs 2025 科类口径不同)"""
    last_msg = "全部尝试失败"
    env = os.environ.copy()
    env["GAOKAO_PROV"] = prov
    for year in ["2024", "2025"]:
        for sc_type in types:
            cmd = ["python3", str(ROOT / "skill" / "_shared" / "scripts" / "score_to_rank.py"),
                   "--score", "500", "--type", sc_type, "--year", year]
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=10)
                if r.returncode == 0 and "位次" in r.stdout and "fallback_no_data" not in r.stdout:
                    return True, f"({year} {sc_type})"
                last_msg = f"({year} {sc_type}): {r.stdout[:60].strip() or r.stderr[:60].strip()}"
            except Exception as e:
                last_msg = f"({year} {sc_type}) 异常: {e}"
    return False, last_msg


def main():
    fails = 0
    summary = []
    print(f"{'省份':<24} {'政策':<8} {'SKILL':<6} {'refs':<6} {'scripts':<8} {'data':<6} {'rank脚本':<8}")
    print("-" * 80)
    for prov, zh, kind, _, types in PROVINCES:
        ok_s, m_s = check_skill_md(prov, zh)
        ok_r, m_r = check_references(prov, zh)
        ok_sc, _ = check_scripts(prov)
        ok_d, m_d = check_data(prov, types)
        ok_rk, m_rk = check_score_to_rank(prov, types)
        marks = ["✓" if x else "✗" for x in [ok_s, ok_r, ok_sc, ok_d, ok_rk]]
        all_ok = all([ok_s, ok_r, ok_sc, ok_d, ok_rk])
        if not all_ok:
            fails += 1
            summary.append((prov, zh, kind, m_s, m_r, m_d, m_rk))
        print(f"{zh:<10}({prov:<12}) {kind:<8} {marks[0]:<6} {marks[1]:<6} {marks[2]:<8} {marks[3]:<6} {marks[4]:<8}")

    print("\n=== 失败汇总 ===")
    if not summary:
        print("✓ 31 省全部通过")
    else:
        for prov, zh, kind, ms, mr, md, mrk in summary:
            print(f"\n{zh}({prov}, {kind})")
            for label, m in [("SKILL", ms), ("refs", mr), ("data", md), ("rank", mrk)]:
                if m:
                    print(f"  [{label}] {m}")
    print(f"\n通过 {len(PROVINCES)-fails}/{len(PROVINCES)},失败 {fails}")
    sys.exit(0 if fails == 0 else 1)


if __name__ == "__main__":
    main()
