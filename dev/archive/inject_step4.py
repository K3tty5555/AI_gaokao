#!/usr/bin/env python3
"""给 30 个省 SKILL.md 注入「步骤 4:产出 HTML 报告」段落(在 ## 五、推理框架 前)。

湖北已有,跳过。模板省份相关字段从 PROVINCES 元数据生成。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
SKILL_DIR = ROOT / "skill"

# (拼音, 中文, 总分, 默认科类, 例子科类列表, 例子分数, 例子位次, 例子选科)
PROVINCES = [
    ("hunan",       "湖南",  750, "物理类", ["物理类", "历史类"],            580, 32000, ["物理", "化学", "生物"]),
    ("jiangsu",     "江苏",  750, "物理类", ["物理类", "历史类"],            615, 20000, ["物理", "化学", "生物"]),
    ("hebei",       "河北",  750, "物理类", ["物理类", "历史类"],            570, 60000, ["物理", "化学", "生物"]),
    ("guangdong",   "广东",  750, "物理类", ["物理类", "历史类"],            580, 70000, ["物理", "化学", "生物"]),
    ("chongqing",   "重庆",  750, "物理类", ["物理类", "历史类"],            560, 25000, ["物理", "化学", "生物"]),
    ("fujian",      "福建",  750, "物理类", ["物理类", "历史类"],            570, 30000, ["物理", "化学", "生物"]),
    ("liaoning",    "辽宁",  750, "物理类", ["物理类", "历史类"],            550, 25000, ["物理", "化学", "生物"]),
    ("anhui",       "安徽",  750, "物理类", ["物理类", "历史类", "理科", "文科"], 590, 50000, ["物理", "化学", "生物"]),
    ("jiangxi",     "江西",  750, "物理类", ["物理类", "历史类", "理科", "文科"], 560, 35000, ["物理", "化学", "生物"]),
    ("guangxi",     "广西",  750, "物理类", ["物理类", "历史类", "理科", "文科"], 530, 30000, ["物理", "化学", "生物"]),
    ("guizhou",     "贵州",  750, "物理类", ["物理类", "历史类", "理科", "文科"], 540, 35000, ["物理", "化学", "生物"]),
    ("heilongjiang","黑龙江",750, "物理类", ["物理类", "历史类", "理科", "文科"], 500, 18000, ["物理", "化学", "生物"]),
    ("jilin",       "吉林",  750, "物理类", ["物理类", "历史类", "理科", "文科"], 500, 12000, ["物理", "化学", "生物"]),
    ("gansu",       "甘肃",  750, "物理类", ["物理类", "历史类", "理科", "文科"], 520, 28000, ["物理", "化学", "生物"]),
    ("henan",       "河南",  750, "理科",   ["理科", "文科", "物理类", "历史类"], 580, 80000, ["物理", "化学", "生物"]),
    ("shanxi",      "山西",  750, "理科",   ["理科", "文科", "物理类", "历史类"], 540, 30000, ["物理", "化学", "生物"]),
    ("sichuan",     "四川",  750, "理科",   ["理科", "文科", "物理类", "历史类"], 580, 60000, ["物理", "化学", "生物"]),
    ("shaanxi",     "陕西",  750, "理科",   ["理科", "文科", "物理类", "历史类"], 510, 35000, ["物理", "化学", "生物"]),
    ("yunnan",      "云南",  750, "理科",   ["理科", "文科", "物理类", "历史类"], 560, 35000, ["物理", "化学", "生物"]),
    ("neimenggu",   "内蒙古",750, "理科",   ["理科", "文科", "物理类", "历史类"], 510, 18000, ["物理", "化学", "生物"]),
    ("qinghai",     "青海",  750, "理科",   ["理科", "文科", "物理类", "历史类"], 430, 6000,  ["物理", "化学", "生物"]),
    ("ningxia",     "宁夏",  750, "理科",   ["理科", "文科", "物理类", "历史类"], 470, 8000,  ["物理", "化学", "生物"]),
    ("xinjiang",    "新疆",  750, "理科",   ["理科", "文科"],                    470, 18000, ["物理", "化学", "生物"]),
    ("xizang",      "西藏",  750, "理科",   ["理科", "文科"],                    480, 5000,  ["物理", "化学", "生物"]),
    ("shanghai",    "上海",  660, "综合",   ["综合"],                            520, 18000, ["物理", "化学", "生物"]),
    ("beijing",     "北京",  750, "综合",   ["综合"],                            580, 18000, ["物理", "化学", "生物"]),
    ("tianjin",     "天津",  750, "综合",   ["综合"],                            580, 18000, ["物理", "化学", "生物"]),
    ("zhejiang",    "浙江",  750, "综合",   ["综合"],                            600, 60000, ["物理", "化学", "生物"]),
    ("shandong",    "山东",  750, "综合",   ["综合"],                            570, 130000, ["物理", "化学", "生物"]),
    ("hainan",      "海南",  900, "综合",   ["综合"],                            650, 13000, ["物理", "化学", "生物"]),
]


STEP4_TEMPLATE = """### 步骤 4:产出 HTML 报告(持久化 + 可视化 ★)

终端 markdown 输出**会随对话散掉,家长拿不走**。完成步骤 3 的 markdown 卡片后,**必须再产出一份自包含 HTML 报告**,让用户保存 / 转发 / 打印。

**做法**:把核心判断 + 推荐 + 避坑 + 完整志愿表 + 必聊 整理成一个 JSON,写到临时文件,然后调用渲染脚本(默认 Bloomberg 财经媒体风,数据 ticker + 等宽数字 + 信息密度高):

```bash
# 1) 把咨询结果整理成 JSON,字段对照 scripts/report_schema.md
cat > /tmp/zhiyuan.json <<'JSON'
{
  "meta": {"省份": "__PROV_ZH__", "省份代码": "__PROV_CODE__", "总分制": __TOTAL__, "生成时间": "2026-XX-XX HH:MM"},
  "用户画像": {"分数": __SAMPLE_SCORE__, "位次": __SAMPLE_RANK__, "百分位": "X.X%", "科类": "__SUBJECT__",
                "选科": __SUBJECTS__, "批次": "本科批 / 本科特控批",
                "标签": ["普通工薪", "想留__PROV_ZH__", "..."],
                "位次说明": "用户自报 vs 实测不一致时填(可选)"},
  "核心判断": "3-5 句 narrative...",
  "推荐": [{"档位": "冲", "院校": "...", "专业组": "...", "历年录取": [...], "推理": "...", "提醒": ["..."]}],
  "避坑": [{"档位": "避坑", "院校": "...", "专业组": "...", "推理": "...",
            "替代": "想做 X 路径建议选 Y(可选,告诉家长正确替代方向)"}],
  "完整志愿": [{"序号":1, "档位":"冲", "院校":"...", "专业组":"...",
                "院校代码": null, "组号": null,
                "参考位次":"...", "一句话":"..."}, ...],
  "必聊": ["...", "...", "..."]
}
JSON

# 2) 渲染 HTML(默认 bloomberg 主题)
python3 scripts/render_report.py --json /tmp/zhiyuan.json \\
  --output output/zhiyuan___PROV_CODE___SAMPLE_SCORE___$(date +%Y%m%d_%H%M).html

# 3) 告诉用户路径,让他双击打开 / 转发家长群 / 打印
```

**完整 schema 参考**:`scripts/report_schema.md`(字段定义 + 档位枚举 + 调用样例)
**视觉参考**:`output/playground/bloomberg.html`(已渲染的样例)/ `output/playground/index.html`(4 主题对比)

#### HTML 报告纪律

1. **每次 L5 输出后必产出**,不是用户主动要才产出
2. **JSON 内容要跟 markdown 输出一致** — 不要 markdown 写一套 JSON 写另一套
3. **完整志愿数填 ≥ 12 条**(覆盖冲稳保 3 档),让用户拿到能直接对照填报顺序的全表
4. **告诉用户产出的文件路径**,让他知道去哪里找
5. **不要把 JSON 文件保留在仓库** — `/tmp/` 是临时区,只有 HTML 落到 `output/` 持久化

#### ❗ 严禁编造的字段

- **`完整志愿[].院校代码` / `组号` 严禁编**:招办章程的院校代码 / 专业组组号是各省招办每年 6 月才发布,**掌上高考数据库不含这些**。agent 编一个出来 = 害用户填错院校。
- **正确做法**:这两个字段**默认填 `null`**(或省略),renderer 会自动在表上方显示"代码以招生章程为准"警告,引导家长去查章程。
- **位次说明使用场景**:
  - 用户自报位次 vs `score_to_rank.py` 实测不一致 → 填 `位次说明` 解释口径
  - 跨年度数据(如 2024 → 2025 切新高考)→ 填 `位次说明` 提醒
- **替代建议**:避坑卡片的 `替代` 字段,**家长看完"不要选 X"会茫然**,补一句"那该选什么"价值很大。每张避坑卡片都尽量给替代。

---

"""


def render_step4(prov_code, prov_zh, total_score, default_subject, sample_score, sample_rank, sample_subjects):
    import json as _json
    out = STEP4_TEMPLATE
    replaces = {
        "__PROV_CODE__": prov_code,
        "__PROV_ZH__": prov_zh,
        "__TOTAL__": str(total_score),
        "__SUBJECT__": default_subject,
        "__SAMPLE_SCORE__": str(sample_score),
        "__SAMPLE_RANK__": str(sample_rank),
        "__SUBJECTS__": _json.dumps(sample_subjects, ensure_ascii=False),
    }
    for k, v in replaces.items():
        out = out.replace(k, v)
    return out


def inject(skill_path: Path, prov_meta) -> bool:
    """在 SKILL.md 里 ## 五、推理框架 前插入步骤 4。返回是否修改。"""
    text = skill_path.read_text(encoding="utf-8")
    if "步骤 4:产出 HTML 报告" in text:
        return False  # 已有

    anchor = "## 五、推理框架"
    if anchor not in text:
        print(f"  [WARN] {skill_path.parent.name}: 找不到锚点 '{anchor}'", file=sys.stderr)
        return False

    step4 = render_step4(*prov_meta)
    new_text = text.replace(anchor, step4 + anchor, 1)
    skill_path.write_text(new_text, encoding="utf-8")
    return True


def main():
    n_done = 0
    n_skipped = 0
    n_failed = 0
    for prov_code, prov_zh, total, default, types, score, rank, subjects in PROVINCES:
        skill_path = SKILL_DIR / f"{prov_code}-zhiyuan" / "SKILL.md"
        if not skill_path.exists():
            print(f"  [MISS] {prov_code}: SKILL.md 不存在", file=sys.stderr)
            n_failed += 1
            continue
        meta = (prov_code, prov_zh, total, default, score, rank, subjects)
        if inject(skill_path, meta):
            print(f"  ✓ {prov_zh:<5} ({prov_code})")
            n_done += 1
        else:
            print(f"  - {prov_zh:<5} ({prov_code}) 已有,跳过")
            n_skipped += 1
    print(f"\n注入 {n_done},跳过 {n_skipped},失败 {n_failed}")


if __name__ == "__main__":
    main()
