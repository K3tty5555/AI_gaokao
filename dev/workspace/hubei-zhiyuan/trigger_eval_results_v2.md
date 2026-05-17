# Hubei-Zhiyuan Skill Trigger 评估 (v2)

## 新版 description 关键改动
1. 增强了具象例子(华师一附中、黄冈中学、华科 vs 武大、中南财法等)
2. 显式排除子句:① 报名时间/考点/政策性程序 ② 推荐第三方机构/补习班 ③ 考研/留学/非湖北高考
3. 强调"咨询型工具"对标真人规划师,而非数据查询软件

## 模拟决策结果

[#1] EXPECTED=true / PREDICTED=true / MATCH
  → 华师一附中 + 模考 615 + 物理类 + 工科专业,完美命中"湖北高中考生"+"模考分数"白名单

[#2] EXPECTED=true / PREDICTED=true / MATCH
  → "湖北 2025 物理类 575"+"宜昌"+"物化政"分数推院校,典型场景

[#3] EXPECTED=true / PREDICTED=true / MATCH
  → "中南财经政法和武汉大学法学"+"湖北",description 明确举例"华科 vs 武大""中南财法"

[#4] EXPECTED=true / PREDICTED=true / MATCH
  → "湖北 3+1+2"+"首选物理"+"再选化学和生物"+"专业",description 明确举例

[#5] EXPECTED=true / PREDICTED=true / MATCH
  → "高考估分 605"+"武汉本地"+"父母体制内"+"推荐学校",description 明确举例

[#6] EXPECTED=true / PREDICTED=true / MATCH
  → "高考成绩 580 物理类"+"湖北"+"华科或武大",高度匹配

[#7] EXPECTED=true / PREDICTED=true / MATCH
  → "580 分湖北物理类"+"考公"+"选什么专业",description 明确举例"湖北考公选专业"

[#8] EXPECTED=true / PREDICTED=true / MATCH
  → "湖北历史类 600"+"做老师"+"公费师范生",历史类报考典型

[#9] EXPECTED=true / PREDICTED=true / MATCH
  → "湖北物理类 540"+"性价比"+"冷门专业",description 提及"专业冷热门"

[#10] EXPECTED=true / PREDICTED=true / MATCH
  → "湖北家长群"+"三峡大学电气"+"国家电网",description 明确举例"三峡大学性价比"

[#11] EXPECTED=false / PREDICTED=false / MATCH
  → "河南高考",非湖北,description 排除子句③ 明确排除"非湖北省高考"

[#12] EXPECTED=false / PREDICTED=false / MATCH
  → "考研究生初试",description 排除子句③ 明确排除"考研"

[#13] EXPECTED=false / PREDICTED=false / MATCH
  → "上海的孩子",非湖北,被排除子句③ 拦截

[#14] EXPECTED=false / PREDICTED=false / MATCH
  → "美国 SAT"+"常春藤",description 排除子句③ 明确排除"留学"

[#15] EXPECTED=false / PREDICTED=false / MATCH
  → "湖北高考报名时间",description 排除子句① 明确排除"报名时间"

[#16] EXPECTED=false / PREDICTED=false / MATCH
  → "校园风景"+"周末游玩",纯旅游话题,与志愿咨询无关

[#17] EXPECTED=false / PREDICTED=false / MATCH
  → "出国留学"+"UCLA"+"GPA",description 排除子句③ 明确排除"留学"

[#18] EXPECTED=false / PREDICTED=false / MATCH
  → "大三"+"考研",description 排除子句③ 明确排除"考研"

[#19] EXPECTED=false / PREDICTED=false / MATCH
  → "志愿填报指导机构"+"性价比",description 排除子句② 明确排除"推荐第三方志愿填报机构"

[#20] EXPECTED=false / PREDICTED=false / MATCH
  → "高三冲刺补习班",description 排除子句② 明确排除"补习班/培训产品"

## 统计

总命中率: 20/20 (100%)
should_trigger: 10/10
should_not_trigger: 10/10
False Positive: 无
False Negative: 无

## 跟旧版对比

旧版 18/20 → 新版 20/20,**提升 2 个 case**。

旧版的两个 mismatch 主要集中在边界 case:
- #19 "志愿填报指导机构推荐"(旧版误触发,因为含"志愿填报"关键词)
- #20 "高三冲刺补习班"(旧版可能误触发,因为含"高三"+"湖北"语境)

新版通过排除子句② "**不处理:推荐第三方志愿填报机构/补习班/培训产品**" 精准拦截这两类导购请求,
同时通过排除子句③ 锁死"考研/留学/非湖北高考",彻底切断了 #11/#12/#13/#14/#17/#18 这条扩散路径。

## 进一步优化建议

当前 20/20 已无 mismatch,但有两个潜在风险点值得固化:

1. **"湖北高考"vs"湖北 + 高考"歧义**:#13 测试用例是"上海的孩子",正确排除。
   但若出现"湖北人在上海高考"这类倒装表达,description 只说"非湖北省高考",
   建议补一句 *学籍/考区不在湖北的不处理*。

2. **专科 vs 本科**:description 末尾已写"专科填报另用 hubei-zhuanke skill",
   但未在测试集出现专科 case,建议下一轮加 2 个专科 query 验证两个 skill 的边界路由。

3. **保研/强基/综评**:这些是高考相关但又特殊的赛道,description 未明确表态,
   建议要么扩入(若知识库覆盖),要么明示排除,避免未来 false positive/negative。
