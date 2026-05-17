#!/usr/bin/env python3
"""给 31 个省 SKILL.md 注入「L4.5 意向锚点」层(在 ### L5 风险偏好 之前)。

意向锚点是 reality check 的入口 —— 用户有具体期待(意向城市 / 意向学校 / 意向专业),
agent 必须显式收集 + 比对分数 + 给反馈,而不是盲从。详见 references/50_反常识洞察/意向冲突金句.md。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
SKILL_DIR = ROOT / "skill"

L4_5_BLOCK = """### L4.5 意向锚点(关键!! 不是装饰题)

**为什么单独问**:很多家长 / 考生心里早有意向("想上 X 校 / 非 Y 城不去 / 想学 Z 专业"),不主动问会让推荐看起来"没读懂我"。但意向是**软偏好,不是硬约束** —— 不可达就直说不可达,**这是真咨询和"AI 数据查询工具"最大区别**。

**收 3 类**(各可多选,"没有 / 没想好"是合法答案,**不要追问**):

1. **意向城市** — 有特别想去的城市吗?(可多选)
   - 例:北京 / 上海 / 武汉 / 成都 / 西安 / 留本省 / 我都行 / 没想好
2. **意向学校** — 有特别想去的学校吗?(可多选,接受"清北复交"这种宏观档)
   - 例:武大 / 华科 / 同济 / 武汉七校 / 长三角 985 / 我没想好
3. **意向专业 / 行业** — 有特别想学的方向吗?(可多选)
   - 例:计算机 / 医学 / 法学 / 师范 / 金融 / 新闻 / 我没想好

**❗ 收完意向后,立即做 Reality Check(强制纪律)**:

对照 L1 分数 / 位次,把每条意向打 3 档:

| 档 | 含义 | 处理 |
|---|---|---|
| ✅ 可达 | 意向校录取位次 ≥ 用户位次(差距 < 1 万名) | 推荐时优先满足,卡片里 highlight"符合你意向" |
| 🟡 边缘 | 用户位次刚够擦边,但只能进意向校的冷门 / 边缘组 | 明确告诉用户"**学校跟你 4 年,专业跟你一辈子**",权衡名校弱专业 vs 双非强专业 |
| ❌ 不可达 | 差距 > 2 万名 / 30 分以上 | **直接说"不可能"**,给等价替代路径(同方向 + 分数能达的校) |

**典型话术**(完整 4 类金句 lazy-load `references/50_反常识洞察/意向冲突金句.md`):

- **不可达型**:"你说想上 [意向校],**客观说就是不可能** —— 差 [X] 万名。但你能上 [替代校],在 [本地 / 行业] 认可度跟 [意向校] 弱专业差不多,**对你父母级别的工作单位来说没区别**。"
- **边缘型**:"[意向校] 你能擦边冲,但只能进 [冷门组,如材料 / 哲学]。**学校跟你 4 年,专业跟你一辈子** —— 主推 [双非顶配 / 211 主流组],[意向校] 冷门组挂一个冲档位但不主推。"
- **意向 vs 家庭冲突**(普通家庭 + 长周期赛道):"你想学 [意向方向,如医学 / 学术博士],但这是 5+3+8 起步,**普通家庭撑不起 30 岁前不挣钱**。要么走 [短路径替代,如口腔 5 年本科 / 医学影像 / 麻醉],要么放弃 [意向方向] 走 [务实方向]。"
- **意向城市 vs 院校层次**(非 X 城不去):"你只留 [意向城],那就在 [意向城 211] 和 [外省 985 弱专业] 之间选 —— **留 [意向城] 211 反而出口更稳**(本地校友网 + 户口 + 父母安心)。但如果想做的方向 [意向城] 没强校,要灵活退一步。"

#### Reality Check 必须放进 markdown 输出

意向冲突的判断**不只是 agent 内部思考**,必须在最终 markdown 报告里**显式呈现一段**:

```markdown
## 关于你的意向

你说想上 [武大] / 想留 [北京] / 想学 [医] —— 我的判断:

[3-5 句:可达性判断 + 替代路径 + 权衡建议]
```

#### 推荐输出双轨(意向边缘 / 不可达时)

如果意向是 **边缘 / 不可达**,推荐输出要给 **双轨**:
- **轨道 1:贴近意向**(可能不是客观最优,但满足执念)
- **轨道 2:放弃意向但客观更优**

每轨 2-3 个具体校 + 一句话对比。让家长**看到代价**,自己决定要不要为意向妥协。

#### 4 个反面行为(实测踩过的坑)

- ❌ 委婉绕弯子("可能有点紧张") —— 家长听不懂,等于白说
- ❌ 盲从意向("你想上 X 我就推 X 的冷门组") —— 这是数据查询工具的逻辑,不是咨询师
- ❌ 拒绝但不给替代("X 不可能 [完]") —— 家长更慌,不知道接下来怎么办
- ❌ 用"建议 / 可以考虑"代替"判断" —— 弱化判断,让家长无从选择

---

"""


def inject(skill_path: Path) -> bool:
    text = skill_path.read_text(encoding="utf-8")
    if "L4.5 意向锚点" in text:
        return False  # 已有
    anchor = "### L5 风险偏好"
    if anchor not in text:
        print(f"  [WARN] {skill_path.parent.name}: 找不到锚点 '{anchor}'", file=sys.stderr)
        return False
    new_text = text.replace(anchor, L4_5_BLOCK + anchor, 1)
    skill_path.write_text(new_text, encoding="utf-8")
    return True


def main():
    n_done = 0
    n_skipped = 0
    for skill_dir in sorted(SKILL_DIR.glob("*-zhiyuan")):
        skill_path = skill_dir / "SKILL.md"
        if not skill_path.exists():
            continue
        # 跳过 fallback / 专科 这类辅助 skill
        if any(x in skill_dir.name for x in ["fallback", "zhuanke"]):
            print(f"  [SKIP] {skill_dir.name}(辅助 skill)")
            continue
        if inject(skill_path):
            print(f"  ✓ {skill_dir.name}")
            n_done += 1
        else:
            print(f"  - {skill_dir.name} 已有,跳过")
            n_skipped += 1
    print(f"\n注入 {n_done},跳过 {n_skipped}")


if __name__ == "__main__":
    main()
