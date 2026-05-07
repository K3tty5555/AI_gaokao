# 数据目录 / Data

本目录存放 **AI 志愿规划师** 使用的数据集。

## 文件清单

### `gaokao_hubei_<YYYY>.db` (SQLite 数据库,每个 ~70 MB)

**这是 SQLite 二进制数据库,不是源代码**。请勿用文本编辑器打开,会显示乱码。

**按爬取年份归档**:
- `gaokao_hubei_2026.db` — 2026 年爬的快照(包含 2021-2025 历年录取数据)
- `gaokao_hubei_2027.db` — 2027 年爬的快照(包含 2021-2026 历年录取数据,新增 2026 年高考结果)
- 以此类推

**为什么不直接覆盖**:
- 各高校官方有时会修订历史位次/分数,旧快照保留有审计价值
- 历年快照对比可做"大小年"风险分析
- git diff 一个 70MB 二进制文件没意义,**多文件归档比单文件覆盖更易追溯**

**lib.py 自动选最新**:运行查询脚本时自动用文件名最大年份的 db,无需手动指定。

#### 数据来源

爬自 **掌上高考**(中国教育在线旗下,域名 `static-data.gaokao.cn`)的**未加密静态 JSON 接口**。本身就是各省考试院公开发布的录取数据。

#### 覆盖范围

| 维度 | 范围 |
|---|---|
| 地区 | 湖北省(prov_id=42) |
| 年份 | 2021-2025(默认查询过滤 ≥ 2023,因 2021/2022 是新高考首两年噪音大) |
| 院校 | 全国 1856 所在湖北招生的本科+专科院校 |
| 科类 | 物理类(type=2073) / 历史类(type=2074) |
| 招生类型 | 普通类 / 国家专项 / 地方专项 / 民族班 等 |

#### 表结构

```sql
schools (school_id, name, province_name, city_name, type_name,
         f985, f211, dual_class_name, eol_rank, ruanke_rank, ...)
-- f985/f211 字段:1=是, 2=否, NULL=未知

province_scores (school_id, year, type_id, special_group, sg_name,
                 sg_info, zslx_name, batch, local_batch_name,
                 min_score, min_section, filing, proscore, diff, ...)
-- type_id: 2073=物理类 / 2074=历史类
-- sg_info: 选科要求,如 "首选物理，再选化学"
-- min_section: 最低录取位次

fetch_log (url, status, fetched_at, note)
-- 爬虫断点续传日志
```

#### 数据时效

- 末次爬取时间:见 `schools.fetched_at` 字段
- 数据时效约 1 年(每年 6-7 月各高校公布上一年度录取后,需重爬)
- **重新爬取**:运行项目根目录 `python3 crawl.py`(约 3-4 小时跑完全量)

#### 重要说明

- **这是公开数据**,各省考试院公开发布,法律风险低
- **使用约束**:本项目仅作个人 / 非商业研究用途
- 商业 SaaS 使用需走商务合作或改用官方源(湖北招生考试网 hbksw.cn / 阳光高考 chsi.com.cn)

## 字段速查

### `province_scores.type_id`
- `2073` = 物理类
- `2074` = 历史类
- `2292/2293` = 艺术类(历史/物理)
- `2294/2295` = 体育类(历史/物理)

### `province_scores.zslx_name`(招生类型)
- 普通类 / 国家专项计划 / 地方专项计划 / 民族班 / 高水平运动队 / 软件工程 / 中外合作办学 等

### `province_scores.local_batch_name`(批次)
- 本科批 / 专科批 / 高职高专批 / 提前批 等

## 更新流程(每年一次)

每年 6-7 月各高校发布上一年录取结果后,运行:

```bash
# 直接跑(自动写入 data/gaokao_hubei_<当前年>.db)
python3 crawl.py
# 等 3-4 小时

# 跑完会得到新一年的快照,旧快照自动保留作归档
ls data/gaokao_hubei_*.db
# data/gaokao_hubei_2026.db    ← 旧
# data/gaokao_hubei_2027.db    ← 新

# git 提交新快照
git add data/gaokao_hubei_2027.db
git commit -m "data: 2027 年高考录取数据快照"
```

**断点续爬**:中途断了直接重跑,fetch_log 表会跳过已抓 URL。

**只想清理本地**(保留 git 里的):本地 `rm` 即可,`git pull` / `git checkout` 还能找回。
