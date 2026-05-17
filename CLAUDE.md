# AI 志愿规划师 — 项目说明

## 主入口 skill

**`gaokao-zhiyuan`** 是唯一入口，已配置在 `.claude/skills/gaokao-zhiyuan/`。

用户提到任何高考志愿相关话题时，从这个 skill 开始。它会：
1. 识别省份（第一轮问）
2. 调用 `score_to_rank.py` 判断本科/专科分流
3. 自动切换到对应的 `{prov}-zhiyuan` 或 `{prov}-zhuanke` skill

**不要直接启动省级 skill**，统一走 `gaokao-zhiyuan` 做省份识别。

---

## Skill 体系结构

```
gaokao-zhiyuan          ← 入口（省份识别 + 分流）
├── {prov}-zhiyuan × 31 ← 本科志愿（分数在本科批线上）
└── {prov}-zhuanke × 31 ← 专科志愿（本科线下、专科线上）
```

所有 skill 在 `skill/` 目录下，symlink 到 `.claude/skills/gaokao-zhiyuan/`（全国枢纽）。

---

## 核心脚本（在 skill/_shared/scripts/ 下）

| 脚本 | 用途 | 环境变量 |
|---|---|---|
| `score_to_rank.py` | 分数→位次，返回 batch.bracket 判断本科/专科 | `GAOKAO_PROV=<prov>` |
| `query_school.py` | 位次/分数→冲稳保院校召回 | `GAOKAO_PROV=<prov>` |

**切换省份用 `GAOKAO_PROV` 环境变量**，不要改脚本内部配置。

---

## 数据文件

| 路径 | 内容 |
|---|---|
| `data/gaokao_{prov}_2026.db` | 各省历年录取数据（SQLite） |
| `data/batch_lines/{prov}.csv` | 批次控制线（2021-2026，出分前当年行的位次列为空，属正常） |
| `data/yifenduyiduan/` | 一分一段表（精确位次换算） |

---

## 测试

```bash
python3 tests/e2e_all_provinces.py   # 31/31 全省结构 + 功能验证
```

---

## 注意事项

- 高考政策数据只在中国大陆有效，不跨境混用
- 所有推荐必须附"以当年省招考院公告为准"
- 不承诺录取，不推荐第三方志愿机构
