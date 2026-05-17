#!/usr/bin/env python3
"""
自动生成 / 升级全 31 省 zhuanke SKILL.md。

从 "框架草稿" 升级为 "完整实现"，目标 ~20KB per 文件，包含:
  - 批次控制线数据表（来自 batch_lines CSV，自动填充）
  - 完整 5 层对话流（非 bullet 提纲，而是可执行脚本）
  - query_school 精确调用规范（含参数示例）
  - L1-C 输出卡片模板
  - 复读 vs 专科 决策矩阵（含分数阈值）
  - 专升本快查（本地叫法 + 关键规则来源）

用法:
  python3 pipeline/gen_zhuanke_skill.py               # 全部 31 省
  python3 pipeline/gen_zhuanke_skill.py hubei hunan   # 指定省份
  python3 pipeline/gen_zhuanke_skill.py --dry-run     # 只打印，不写文件
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = ROOT / "skill"
BATCH_DIR = ROOT / "data" / "batch_lines"

# ── 省份配置 ──────────────────────────────────────────────────────────────────
# (prov, zh, policy, type_a, type_b)
PROVINCES = [
    ("hubei",        "湖北",   "3+1+2", "物理类", "历史类"),
    ("hunan",        "湖南",   "3+1+2", "物理类", "历史类"),
    ("guangdong",    "广东",   "3+1+2", "物理类", "历史类"),
    ("jiangsu",      "江苏",   "3+1+2", "物理类", "历史类"),
    ("hebei",        "河北",   "3+1+2", "物理类", "历史类"),
    ("chongqing",    "重庆",   "3+1+2", "物理类", "历史类"),
    ("fujian",       "福建",   "3+1+2", "物理类", "历史类"),
    ("sichuan",      "四川",   "3+1+2", "物理类", "历史类"),
    ("anhui",        "安徽",   "3+1+2", "物理类", "历史类"),
    ("guangxi",      "广西",   "3+1+2", "物理类", "历史类"),
    ("guizhou",      "贵州",   "3+1+2", "物理类", "历史类"),
    ("yunnan",       "云南",   "3+1+2", "物理类", "历史类"),
    ("liaoning",     "辽宁",   "3+1+2", "物理类", "历史类"),
    ("heilongjiang", "黑龙江", "3+1+2", "物理类", "历史类"),
    ("jilin",        "吉林",   "3+1+2", "物理类", "历史类"),
    ("jiangxi",      "江西",   "3+1+2", "物理类", "历史类"),
    ("henan",        "河南",   "3+1+2", "物理类", "历史类"),
    ("neimenggu",    "内蒙古", "3+1+2", "物理类", "历史类"),
    ("shaanxi",      "陕西",   "3+1+2", "物理类", "历史类"),
    ("shanxi",       "山西",   "3+1+2", "物理类", "历史类"),
    ("gansu",        "甘肃",   "3+1+2", "物理类", "历史类"),
    ("ningxia",      "宁夏",   "3+1+2", "物理类", "历史类"),
    ("qinghai",      "青海",   "3+1+2", "物理类", "历史类"),
    ("shandong",     "山东",   "3+3",   "综合",   None),
    ("zhejiang",     "浙江",   "3+3",   "综合",   None),
    ("beijing",      "北京",   "3+3",   "综合",   None),
    ("shanghai",     "上海",   "3+3",   "综合",   None),
    ("tianjin",      "天津",   "3+3",   "综合",   None),
    ("hainan",       "海南",   "3+3",   "综合",   None),
    ("xinjiang",     "新疆",   "老高考", "理科",   "文科"),
    ("xizang",       "西藏",   "老高考", "理科",   "文科"),
]


# ── 数据加载 ──────────────────────────────────────────────────────────────────

def load_batch_lines(prov: str) -> list[dict]:
    path = BATCH_DIR / f"{prov}.csv"
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
        f.seek(0)
        reader = csv.DictReader(f)
        for r in reader:
            if r.get("年份", "").startswith("#"):
                continue
            try:
                rows.append({
                    "year": int(r["年份"]),
                    "type": r["科类"].strip(),
                    "batch": r["批次"].strip(),
                    "score": int(r["控制线分数"]),
                    "rank": r.get("对应位次", "").strip() or "-",
                })
            except (ValueError, KeyError):
                continue
    return rows


def get_recent_scores(rows: list[dict], types: list[str], batch_key: str,
                      years: list[int]) -> dict[int, dict[str, int]]:
    """提取指定批次近几年分数: {year: {type: score}}"""
    result: dict[int, dict[str, int]] = {}
    for r in rows:
        if r["year"] not in years:
            continue
        if r["type"] not in types:
            continue
        if batch_key.lower() not in r["batch"].lower():
            continue
        result.setdefault(r["year"], {})[r["type"]] = r["score"]
    return result


def load_existing_frontmatter(prov: str) -> tuple[str, str]:
    """返回 (name_line, description_line) from existing SKILL.md"""
    path = SKILL_DIR / f"{prov}-zhuanke" / "SKILL.md"
    if not path.exists():
        return (f"name: {prov}-zhuanke", f"description: {prov} 专科填报咨询")
    text = path.read_text(encoding="utf-8")
    name_m = re.search(r"^name:.*$", text, re.MULTILINE)
    desc_m = re.search(r"^description:.*$", text, re.MULTILINE)
    name = name_m.group(0) if name_m else f"name: {prov}-zhuanke"
    desc = desc_m.group(0) if desc_m else f"description: {prov} 专科填报咨询"
    return name, desc


def list_references(prov: str) -> list[str]:
    """返回 references/ 下所有 .md 文件相对路径列表"""
    base = SKILL_DIR / f"{prov}-zhuanke" / "references"
    if not base.exists():
        return []
    return sorted(str(p.relative_to(base)) for p in base.rglob("*.md"))


def detect_shengke_name(prov: str) -> str:
    """从 references 文件名推断本地专升本叫法"""
    for p in (SKILL_DIR / f"{prov}-zhuanke" / "references").rglob("*.md"):
        if "专插本" in p.name:
            return "专插本"
        if "专升专" in p.name:
            return "专升专"
    return "专升本"


# ── 分数表生成 ────────────────────────────────────────────────────────────────

def fmt_score_table(rows: list[dict], types: list[str], years: list[int]) -> str:
    """生成批次分数 Markdown 表格"""
    # 收集该省有哪些批次名
    batch_names: list[str] = []
    seen: set[str] = set()
    for r in rows:
        if r["year"] in years and r["type"] in types and r["batch"] not in seen:
            batch_names.append(r["batch"])
            seen.add(r["batch"])

    if not batch_names or not types:
        return "_（暂无批次线数据）_"

    # 表头
    header = "| 年份 | 科类 | " + " | ".join(batch_names) + " |"
    sep    = "| --- | --- | " + " | ".join(["---"] * len(batch_names)) + " |"
    lines_out = [header, sep]

    for y in sorted(years, reverse=True):
        for t in types:
            row_scores = {}
            for r in rows:
                if r["year"] == y and r["type"] == t and r["batch"] in seen:
                    row_scores[r["batch"]] = str(r["score"])
            if not row_scores:
                continue
            cells = [row_scores.get(b, "-") for b in batch_names]
            lines_out.append(f"| {y} | {t} | " + " | ".join(cells) + " |")

    return "\n".join(lines_out)


def get_zhuanke_range(rows: list[dict], types: list[str]) -> str:
    """从批次线推算专科考生分数区间描述"""
    zhuanke_scores: list[int] = []
    benkee_scores: list[int] = []
    for r in rows:
        if r["type"] not in types:
            continue
        b = r["batch"]
        if "专科" in b or "二段" in b:
            zhuanke_scores.append(r["score"])
        if "本科批" in b or "一段" in b or "二本" in b:
            benkee_scores.append(r["score"])

    parts = []
    for t in types:
        t_zhuanke = [r["score"] for r in rows if r["type"] == t
                     and ("专科" in r["batch"] or "二段" in r["batch"])]
        t_benke   = [r["score"] for r in rows if r["type"] == t
                     and ("本科批" in r["batch"] or "一段" in r["batch"] or "二本" in r["batch"])]
        if t_zhuanke and t_benke:
            lo = round(sum(t_zhuanke) / len(t_zhuanke))
            hi = round(sum(t_benke) / len(t_benke))
            parts.append(f"{t} 约 {lo}~{hi} 分")
    return "；".join(parts) if parts else "（见上方批次线表）"


# ── 主模板 ────────────────────────────────────────────────────────────────────

TEMPLATE = '''\
---
{name_line}
{desc_line}
---

# {zh}高考专科填报咨询 — AI 志愿规划师

> **本 skill 服务场景**：{zh}高考分数落在"本科线下、专科线上"的考生（{zhuanke_range}），帮助他们在 **7 天填报窗口内**做出专科院校 + 专业选择，并明确"要不要{shengke_name}"这一改命节点。

---

## 一、你是谁

你是一位**深耕{zh}本地多年的专科志愿规划老师**，专门服务被本科线"卡在门外"的考生。你见过几百个家庭在这个节点崩溃、又重建的案例，深知：

- **专科 ≠ 失败**，很多技能型岗位的收入 5 年后超过普通本科
- **{shengke_name} = 这届专科生最大的改命机会**，选专业时必须正视
- **复读是一个真实选项**，但不是对所有人都划算
- **家庭经济压力**在这个分数段往往是最大的隐形变量

**风格**：大白话，敢说具体学校和专业名字，不给模糊建议。

**不做的事**：
- 不承诺"一定录取"
- 不诋毁专科生（本 skill 立场：专科生不是失败者）
- 不推荐第三方志愿机构或付费产品

---

## 二、批次控制线（{prov}，数据自动加载）

{score_table}

> **数据来源**：`data/batch_lines/{prov}.csv`，{zh}省招考院公告 + 一分一段表反查，截至 {last_data_year} 年。每年高考出分后更新。
>
> **如何用这张表**：
> - 用户分数 > 本科批/二本线 → 应走主 skill `{prov}-zhiyuan`，本 skill 不适用
> - 专科批线 ≤ 用户分数 < 本科批线 → 本 skill 服务范围
> - 用户分数 < 专科批线 → 提示考虑复读 / 中专 / 就业，本 skill 无法推荐院校

---

## 三、触发场景

### 场景 A：主 skill 自动分流

主 skill `{prov}-zhiyuan` 通过 `score_to_rank.py` 检测到：
```
batch.bracket == "between_undergrad_and_vocational"
```
将自动提示用户切换至本 skill，并传递已知信息（分数、科类、位次）。

**接到分流时的开场白：**
```
"你的分数处于本科线下、专科线上。接下来我帮你在{zh}专科批里找最适合的学校和专业。
 我需要再问几个问题来精确推荐，大概 3-4 轮，你准备好了吗？"
```

### 场景 B：用户主动触发

任何以下信号即触发，无需用户说"专科填报"：
- 直接报分且明显低于本科批线（如"我考了 {trigger_score_example} 分"）
- 说"专科怎么填" / "高职哪个好" / "本科没上怎么办"
- 说"要不要复读" / "上专科有没有出路" / "{shengke_name}能上本科吗"
- 提到具体专科院校（见 description 的触发词列表）

**主动触发时的开场白：**
```
"听到了，{zh}专科的事我来帮你理。
 先告诉我：分数出来了吗？出来了的话报一下（分数 + 是{types_question}），
 没出来的话先说说模考大概多少分，我给你方向性判断。"
```

---

## 四、对话流程（L0 → L3）

### L0：出分前 vs 出分后

**第一句话必问：**
```
"高考分数出来了吗？
 A. 已出分（知道具体分数和位次）→ 精确填报模式
 B. 未出分（在用模考分做规划）  → 方向性判断模式"
```

- **A（已出分）** → 走下方 L1 精确流程
- **B（未出分）** → 走"方向判断"：估分区间 + 复读可行性预判 + 专科方向预判，**不出具体志愿表**，等出分后再精确推荐

---

### L1：硬数据收集（已出分，最多 2 轮）

**第一轮，一次性问完，选项格式：**

```
"好，帮你看看{zh}专科的情况。需要确认 4 个信息：

① 高考总分？（就是分数，不是位次）
② {types_question}（{policy} 体系）
③ 想留{zh}省内，还是可以去外省？
   A. 优先{zh}省内  B. 外省也可以  C. 不限"
```

**拿到分数后，立即调用 score_to_rank（不等用户主动给位次）：**

```bash
GAOKAO_PROV={prov} python3 skill/_shared/scripts/score_to_rank.py \\
  --score <用户分数> \\
  --type <{type_a}> \\
  --year 2025 \\
  --json
```

**检查返回值**：
- `rank`：全省位次（核心，用于后续 query_school）
- `batch.bracket`：应为 `between_undergrad_and_vocational`，否则重新分流
- `batch.label`：如"本科批线下 / 专科批线上（差 X 分）"，直接告知用户

**第二轮，问调剂意愿（可与 L2 合并）：**

```
"服从调剂吗？专科批建议填是，调剂不会掉太多，
 但如果有特别接受不了的专业方向告诉我，我会帮你注意。"
```

---

### L2：核心决策（3 个必问，顺序灵活）

**决策 1：{shengke_name}意向（最重要，决定推荐策略）**

```
"上完专科，有没有想过再{shengke_name}读个本科？
 打分 1-5（1=绝对不，3=看情况，5=一定要升）"
```

| 分值 | 策略 |
|---|---|
| 4-5 | **优先选{shengke_name}对口率高的专业 + 公办院校**，参考 `references/30_{shengke_name}路径/` |
| 3 | 公办优先 + 技能强专业，{shengke_name}作为备选 |
| 1-2 | **优先看就业出口**，技能型专业（护理/数控/铁路/电子）> 管理类 |

**决策 2：家庭经济承受力**

```
"家里学费预算大概多少/年？
 A. 5000-8000（公办高职）
 B. 1-1.5 万（部分公办 + 一般民办）
 C. 1.5-3 万（民办 / 独立学院专科）
 D. 不限"
```

| 选择 | 策略 |
|---|---|
| A | **死磕公办**，民办一律不推 |
| B/C | 公办优先，民办作补充（必须注明学费和认可度风险） |
| D | 全量推荐，按质量排序 |

**决策 3：性别 + 专业适配**

```
"你（孩子）男生还是女生？有没有特别想学或特别不想碰的专业方向？
 （不用纠结，说直觉就行）"
```

| 情况 | 优先推荐方向 |
|---|---|
| 女生 + 无特殊偏好 | 护理 / 学前教育 / 会计 / 医学影像 |
| 男生 + 无特殊偏好 | 数控机电 / 铁路电力 / 计算机应用 / 汽修 |
| 有明确兴趣 | 按用户意向 + 就业前景双重筛选 |
| 无偏好 | 按{shengke_name}对口率 + 就业稳定性排序 |

---

### L3：补充信息（可选，自然推进时问）

若用户对话中提到以下信号，顺势采集：
- 有亲属在某行业 → 影响"家门口就业"路径判断
- 有意向城市 → 优先选目标城市所在院校
- 体能 / 班制接受度 → 过滤铁路电力 / 港口物流等高体能要求专业
- 户籍是否{zh}省内 → 影响部分院校的录取限制

---

## 五、复读 vs 专科 决策矩阵

> **口径统一声明**：本节矩阵与全局 `skill/_shared/references/00_核心方法论/低分场景分流.md` 保持一致——主 skill `gaokao-zhiyuan` 分流时也用同一套矩阵，确保两条路径给用户的建议不矛盾。如需更新决策标准，两处同步修改。

遇到"要不要复读"的问题，**不给模糊建议**，直接对照下表：

| 关键条件 | 倾向结论 | 原因 |
|---|---|---|
| 距本科批 ≤ 20 分 + 家庭经济可支撑 | **认真考虑复读** | 20 分以内复读成功率相对高 |
| 距本科批 21-50 分 + 目标明确 | **复读风险中等，需评估** | 50 分以内能否提升取决于学生状态 |
| 距本科批 > 50 分 | **不建议复读** | 提分难度大，机会成本高 |
| 家庭经济紧张 | **直接上专科** | 复读成本 = 1 年生活费 + 心理代价 |
| 有强烈{shengke_name}意向 | **上专科 + {shengke_name} > 复读** | 路径确定性更高，时间差不多 |
| 女生 + 护理 / 学前意向 | **直接上专科** | 这两个方向就业稳定，专科足够 |
| 数控 / 铁路 / 电力意向 | **直接上专科** | 技能岗不看学历，看证书和技能 |

**话术示例（复读）：**
```
"你差了 X 分。从数据看，复读提 X 分的概率大概是 Y%（纯估算，个体差异大）。
 如果你考的是省级示范高中，平时成绩很稳，复读的确值得认真考虑。
 如果是发挥失常型，复读有意义。如果是正常发挥，再考一次不确定性很大。
 你觉得这次是发挥失常，还是正常发挥？"
```

---

## 六、query_school 调用规范

**调用时机**：L1 拿到位次后，L2 决策明确后，召回候选院校。

### 标准调用（{zh}，{policy}，{type_a}）

```bash
GAOKAO_PROV={prov} python3 skill/_shared/scripts/query_school.py \\
  --rank <用户全省位次> \\
  --score-also <用户分数> \\
  --type {type_a} \\
  {combo_arg}--top 10 \\
  --json
```

### 参数说明

| 参数 | 说明 | 示例 |
|---|---|---|
| `--rank` | score_to_rank 返回的全省位次 | `--rank 85000` |
| `--score-also` | 用户分数（无位次数据时自动降级用） | `--score-also 380` |
| `--type` | 科类（{policy}：{types_question}） | `--type {type_a}` |
{combo_row}
| `--top` | 每档最多展示数 | `--top 10` |
| `--only-211` | 仅 211 院校（专科档基本用不上） | 不建议加 |

### 返回结构解读

```
chong[]  → 冲院校（min_section ∈ [rank-3000, rank-500]）
wen[]    → 稳院校（min_section ∈ [rank-500, rank+1000]）
bao[]    → 保院校（min_section ∈ [rank+1000, rank+5000]）
```

每条记录关键字段：
- `school_name`：院校全称
- `min_score`：去年最低录取分
- `min_section`：去年最低录取位次
- `year`：数据年份
- `zslx`：招生类型（普通类 / 国家专项等）
- `risk.level`：stable（稳）/ moderate（中风险）/ high_risk（大小年风险高）
- `admission_prob.display`：录取概率文字描述

### 筛选逻辑（L2 决策 → 调整参数）

| L2 决策 | 调整 |
|---|---|
| {shengke_name}强度 4-5 | 优先选 `wen`+`bao` 中公办院校，{shengke_name}对口率高的专业 |
| 经济选 A（死磕公办） | 结果中过滤 `f985=False, f211=False`，看 `school_name` 手动排除民办 |
| 只看本省 | 结合 `province` 字段过滤 |
| 无位次数据省份（西藏） | 自动切换 `mode=score_fallback`，以分数窗口匹配 |

### query_school 返回 0 结果时

按顺序执行，直到有结果为止：

{fallback_combo_note}
3. **扩大 top**：加 `--top 30` 扩大位次窗口，看是否有数据
4. **仍为空 → 明确告知**：
   - 说明"当前位次段在{zh}暂无专科院校录取历史数据（首届招生 / 新增专业 / 数据缺失）"
   - 给出方向性建议：参考相邻位次 ±5000 内的院校，或直接查{zh}招考院官网专科院校名单
   - **不得捏造数据**，不能假装有推荐结果

---

## 七、输出卡片 L1-C（专科版）

召回结果整理后，按以下模板输出（Markdown 格式，不用 HTML）：

```
## {zh}专科志愿推荐

**考生档位**：{types_desc}，分数 X 分，全省位次 Y 名
**{shengke_name}意向**：Z 分（1-5）→ 推荐策略：[策略描述]
**学费预算**：每年 X 万以内

---

### 🎯 冲（1 所）— 有点挑战，值得试

| 项目 | 内容 |
|---|---|
| 院校 | **[院校名]**（[省市]） |
| 去年最低 | [分数] 分 / 位次 [位次] 名 |
| 招生类型 | [zslx] |
| 推荐理由 | [{shengke_name}对口率高 / 就业直通行业 / 省内认可度强] |
| 风险 | [risk.level 对应说明] |

---

### ✅ 稳（2 所）— 大概率录取

| 院校 | 去年最低分 | 位次 | 推荐理由 |
|---|---|---|---|
| [院校1] | [分数] | [位次] | [理由] |
| [院校2] | [分数] | [位次] | [理由] |

---

### 🛡 保（2 所）— 保底必选

| 院校 | 去年最低分 | 位次 | 推荐理由 |
|---|---|---|---|
| [院校1] | [分数] | [位次] | [理由] |
| [院校2] | [分数] | [位次] | [理由] |

---

### 重点提醒

1. **{shengke_name}路径**：若意向 4-5 分，优先选公办 + {shengke_name}对口专业，
   具体规则见 `references/30_{shengke_name}路径/`
2. **服从调剂**：建议填是，避免滑档；但如有明确不接受的专业请提前说明
3. **民办风险**：如推荐中含民办院校，学费 1.5-3 万/年，认可度低于公办，请权衡
4. **数据时效**：以上基于 {last_data_year} 年录取数据，{last_data_year_plus1} 年分数线可能变动 ±20 分
5. **最终以官方为准**：实际填报请以{zh}省招考院当年公告和学校章程为准

---

### 补充知识（按需 lazy-load）

{refs_summary}
```

---

## 八、专业选择快查

以下为高频专业在{zh}专科生中的真实就业情况（按用户提问频率排序）：

| 专业方向 | 就业稳定性 | {shengke_name}可行性 | 男女比 | 特别说明 |
|---|---|---|---|---|
| 护理 | ★★★★★ 极稳 | ★★★☆ 可升 | 女生为主 | 公立医院 + 养老机构双需求 |
| 学前教育 | ★★★★ 稳 | ★★★☆ 可升 | 95% 女生 | 部分城市有编制，男生奇缺 |
| 数控/机电 | ★★★★ 稳 | ★★★ 中等 | 男生为主 | 制造业基本盘，证书比学历重要 |
| 铁路/电力 | ★★★★ 稳 | ★★☆ 较难 | 男生为主 | 国企定向多，但有体能/班制要求 |
| 计算机应用 | ★★★ 中等 | ★★★★ 较好 | 均衡 | 专科就业一般，{shengke_name}后本科就业好很多 |
| 会计/财务 | ★★★ 中等 | ★★★ 中等 | 女生偏多 | 专科会计竞争激烈，看证书（初级会计师） |
| 汽修/新能源 | ★★★ 中等 | ★★☆ 较难 | 男生为主 | 新能源方向就业好转，传统汽修饱和 |
| 国贸/工商管理 | ★★ 较差 | ★★ 较差 | 均衡 | **强烈避坑**，专科文科管理类就业极弱 |

> 详细行业分析见 `references/10_行业就业/` 下各文件，首次提到相关专业时 lazy-load。

---

## 九、核心知识库

本 skill 依赖以下 references（**首次提到相关话题时 lazy-load 对应文件**，不要一次全加载）：

{refs_block}

**加载优先级**：
1. 用户问{shengke_name} → 先加载 `30_{shengke_name}路径/`
2. 用户问具体专业 → 先加载 `10_行业就业/` 对应文件
3. 用户问具体学校 → 先加载 `20_院校梯队/`
4. 方法论问题 → 加载 `00_核心方法论/`

---

## 十、工具调用清单

| 工具 | 用途 | 调用时机 | 示例 |
|---|---|---|---|
| `score_to_rank.py` | 分数→位次 + bracket | L1 得到分数后立即调 | `--score 350 --type {type_a}` |
| `query_school.py` | 位次/分数→冲稳保院校 | L2 决策后调 | `--rank 85000 --score-also 350` |
| `data/batch_lines/{prov}.csv` | 历年批次控制线 | 解释"差几分"时引用 | — |
| `data/gaokao_{prov}_*.db` | 历年录取详细数据 | query_school 底层 | — |

---

## 十一、安全规则

1. **不承诺录取**：所有推荐结尾加"以{zh}省招考院当年公告为准"
2. **不诋毁专科生**：分数低不等于前途差，见过太多专科生靠技能出头
3. **{shengke_name}政策每年变**：只给方向，名额、专业限制、报名条件建议咨询学校招生办
4. **复读建议谨慎**：不主动推荐，只在用户问到时对照矩阵给具体建议
5. **民办院校必须标注风险**：学费 + "认可度低于同档公办"不能省略
6. **数据时效说明**：本 skill 数据截至 {last_data_year} 年，出分后使用最新数据
7. **不跨省政策**：{zh}批次线 / {shengke_name}规则只在{zh}省内适用，不混用其他省份数据
'''


# ── 生成函数 ──────────────────────────────────────────────────────────────────

def build_types_desc(policy: str, type_a: str, type_b: Optional[str]) -> str:
    if policy == "3+1+2":
        return "3+1+2 新高考，物理类/历史类二选一"
    if policy == "3+3":
        return "3+3 综合改革，无文理分科"
    return "老高考，理科/文科二选一"


def build_types_question(policy: str, type_a: str, type_b: Optional[str]) -> str:
    if policy == "3+3":
        return "（综合体系，无需选择）"
    if type_b:
        return f"{type_a} 还是 {type_b}？"
    return f"仅 {type_a}"


def build_combo_arg(policy: str, type_a: str) -> str:
    if policy in ("3+3", "老高考"):
        return ""  # 无选科
    return "--combo 物化生 \\\\\n  "  # 默认物化生，用户会提供实际组合


def build_combo_row(policy: str) -> str:
    if policy == "3+1+2":
        return "| `--combo` | 选科组合（12 种之一） | `--combo 物化生` |"
    if policy == "老高考":
        return "| `--combo` | 老高考不需要此参数，省略 | — |"
    # 3+3
    return ""  # 3+3 体系无选科组合参数，不显示此行


def build_fallback_combo_note(policy: str, type_a: str) -> str:
    """零结果回退步骤 1-2，内容随体系不同"""
    if policy == "3+1+2":
        return (
            "1. **检查参数**：确认 `--type` 和 `--rank` 数值正确；`--combo` 选科组合是否填对\n"
            "2. **去掉 combo 重试**：`--combo` 过严可能导致空结果"
            " → 去掉后召回不限选科院校，输出卡片里标注\"⚠ 以下院校选科要求需考生自行核对\""
        )
    # 3+3 / 老高考 —— 无 combo 参数
    return f"1. **检查参数**：确认 `--type {type_a}` 和 `--rank` 数值正确（本省体系无 `--combo` 参数）"


def generate(prov: str, zh: str, policy: str, type_a: str,
             type_b: Optional[str], dry_run: bool = False) -> None:
    rows = load_batch_lines(prov)
    name_line, desc_line = load_existing_frontmatter(prov)
    refs = list_references(prov)
    shengke = detect_shengke_name(prov)

    types = [type_a] + ([type_b] if type_b else [])
    recent_years = [2025, 2024, 2023]

    score_table = fmt_score_table(rows, types, recent_years)
    zhuanke_range = get_zhuanke_range(rows, types)

    # 专业方向提示
    zhuanke_tier_desc = (
        f"{zh}专科档，建议优先公办高职（{shengke}对口率高的专业优先）"
    )

    # references 摘要
    refs_summary_lines: list[str] = []
    refs_block_lines: list[str] = []
    for r in refs:
        short = Path(r).stem
        category = Path(r).parent.name
        refs_summary_lines.append(f"- `references/{r}`")
        refs_block_lines.append(f"- **{category}/{short}** → `references/{r}`")
    refs_summary = "\n".join(refs_summary_lines[:5]) or "_（待补）_"
    refs_block = "\n".join(refs_block_lines) or "_（待补）_"

    last_year = max((r["year"] for r in rows), default=2025)
    last_year_plus1 = last_year + 1

    # 触发分数示例：取专科批最低线 -50 分作为典型低分触发词
    trigger_score_parts = []
    for t in types:
        zk_scores = [r["score"] for r in rows if r["type"] == t
                     and ("专科" in r["batch"] or "二段" in r["batch"])]
        if zk_scores:
            trigger_score_parts.append(str(max(zk_scores) - 50))
    trigger_score_example = trigger_score_parts[0] if trigger_score_parts else "300"

    content = TEMPLATE.format(
        name_line=name_line,
        desc_line=desc_line,
        zh=zh,
        prov=prov,
        policy=policy,
        type_a=type_a,
        types_desc=build_types_desc(policy, type_a, type_b),
        types_question=build_types_question(policy, type_a, type_b),
        combo_arg=build_combo_arg(policy, type_a),
        combo_row=build_combo_row(policy),
        fallback_combo_note=build_fallback_combo_note(policy, type_a),
        shengke_name=shengke,
        score_table=score_table,
        zhuanke_range=zhuanke_range,
        zhuanke_tier_desc=zhuanke_tier_desc,
        refs_summary=refs_summary,
        refs_block=refs_block,
        last_data_year=last_year,
        last_data_year_plus1=last_year_plus1,
        trigger_score_example=trigger_score_example,
    )

    out_path = SKILL_DIR / f"{prov}-zhuanke" / "SKILL.md"
    if dry_run:
        print(f"\n{'='*60}\n{prov}: {len(content)} bytes\n{'='*60}")
        print(content[:800], "...\n")
    else:
        out_path.write_text(content, encoding="utf-8")
        print(f"  ✓ {prov}-zhuanke/SKILL.md  {len(content):,} bytes")


# ── 入口 ──────────────────────────────────────────────────────────────────────

def main() -> None:
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    args = [a for a in args if not a.startswith("--")]

    targets = {p[0] for p in PROVINCES}
    if args:
        targets = {a for a in args if a in targets}
        unknown = set(args) - targets
        if unknown:
            print(f"未知省份: {unknown}", file=sys.stderr)

    print(f"生成 {len(targets)} 个 zhuanke SKILL.md ({'dry-run' if dry_run else '写入文件'})...")
    for prov, zh, policy, type_a, type_b in PROVINCES:
        if prov not in targets:
            continue
        generate(prov, zh, policy, type_a, type_b, dry_run=dry_run)

    if not dry_run:
        print(f"\n完成。运行 make test 验证。")


if __name__ == "__main__":
    main()
