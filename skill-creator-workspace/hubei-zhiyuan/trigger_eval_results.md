# hubei-zhiyuan Trigger Eval Results

## 逐条判断

[#1] EXPECTED=true / PREDICTED=true / MATCH ✓ (华师一附中 + 物理类 + 选科 + 模考,description 明确列举)
[#2] EXPECTED=true / PREDICTED=true / MATCH ✓ (湖北 + 物理类分数 + 选科,核心场景)
[#3] EXPECTED=true / PREDICTED=true / MATCH ✓ (中南财法 vs 武大 是 description 原文举例)
[#4] EXPECTED=true / PREDICTED=true / MATCH ✓ (3+1+2 物理类 + 专业 + 就业,description 列举)
[#5] EXPECTED=true / PREDICTED=true / MATCH ✓ (高考估分 + 武汉 + 体制内/家庭背景,description 涵盖)
[#6] EXPECTED=true / PREDICTED=true / MATCH ✓ (湖北 + 物理类 + 华科 vs 武大,description 原文举例)
[#7] EXPECTED=true / PREDICTED=true / MATCH ✓ (湖北物理类 + 考公选专业,description 原文举例)
[#8] EXPECTED=true / PREDICTED=true / MATCH ✓ (湖北历史类 + 公费师范,3+1+2 历史类范畴)
[#9] EXPECTED=true / PREDICTED=true / MATCH ✓ (湖北物理类 + 专业冷热门,description 原文举例)
[#10] EXPECTED=true / PREDICTED=true / MATCH ✓ (湖北 + 院校专业就业,本地潜规则知识库范畴)
[#11] EXPECTED=false / PREDICTED=false / MATCH ✓ (河南高考,description 明确"湖北 only")
[#12] EXPECTED=false / PREDICTED=false / MATCH ✓ (考研非高考,description 限"高考志愿")
[#13] EXPECTED=false / PREDICTED=false / MATCH ✓ (上海高一选科,非湖北)
[#14] EXPECTED=false / PREDICTED=false / MATCH ✓ (美国 SAT,完全境外)
[#15] EXPECTED=false / PREDICTED=true / MISMATCH ✗ (含"湖北高考",description 写"只要用户提到湖北高考...必须触发",但实际是报名时间咨询非志愿规划。description 边界没排除程序性问题)
[#16] EXPECTED=false / PREDICTED=false / MATCH ✓ (校园游玩非志愿/选科话题)
[#17] EXPECTED=false / PREDICTED=false / MATCH ✓ (出国留学非湖北高考)
[#18] EXPECTED=false / PREDICTED=false / MATCH ✓ (考研选方向非高考志愿)
[#19] EXPECTED=false / PREDICTED=true / MISMATCH ✗ (含"湖北高考志愿填报",description 强触发关键词命中,但实际是问"机构推荐"而非咨询本身。description 没排除"找第三方机构"场景)
[#20] EXPECTED=false / PREDICTED=false / MATCH ✓ (补习班非志愿,description 限志愿/选科/院校)

## Summary

总命中率: 18/20 (90%)
should_trigger 命中率: 10/10
should_not_trigger 命中率: 8/10
False Positive(误触发): 2 个 (#15, #19)
False Negative(漏触发): 0 个

## 建议改进

1. 在 description 末尾加显式排除条款:"不处理:湖北高考报名时间/考点/政策性程序问题(走官方渠道)、推荐第三方志愿填报机构/补习班(本 skill 本身就是 AI 规划师不做导购)、考研/留学/非湖北省高考。" — 解决 #15(报名时间)、#19(机构推荐)、隐性的 #20 类边界。
2. 把"只要用户提到湖北高考...必须触发"改为"只要用户提到湖北高考志愿/选科/分数/院校/专业相关咨询...必须触发",避免"湖北高考"四字本身被当成万能开关误触发程序性问题。
3. 显式声明"本 skill 是咨询服务提供方,不推荐其他志愿填报机构/补习班/培训产品",防止 #19/#20 类导购询问命中。
