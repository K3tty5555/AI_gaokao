#!/usr/bin/env python3
"""
掌上高考 - 湖北 录取数据爬取
- 数据源: static-data.gaokao.cn (静态 JSON, 无鉴权)
- 范围:   湖北 (prov_id=42), 2021-2025
- 节奏:   每请求间隔 ~1 秒
- 存储:   SQLite (gaokao_hubei.db)
- 断点续:从 fetch_log 跳过已抓 URL
"""

from __future__ import annotations

import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import Optional

import requests

ROOT = Path(__file__).resolve().parent
# 默认按爬取年份归档:data/gaokao_hubei_<当前年>.db
# 多次爬取同一年会断点续传(从 fetch_log 跳过已抓 URL)
from datetime import date as _date

DB_PATH = ROOT / "data" / f"gaokao_hubei_{_date.today().year}.db"
LOG_PATH = ROOT / "crawl.log"

UA = "Mozilla/5.0 (compatible; gaokao-research/0.1; +personal-use)"
HEADERS = {"User-Agent": UA, "Accept": "application/json"}
PROV_ID = 42  # 湖北
YEARS = [2021, 2022, 2023, 2024, 2025]
SLEEP = 1.0
TIMEOUT = 15

SCHEMA = """
CREATE TABLE IF NOT EXISTS schools (
    school_id INTEGER PRIMARY KEY,
    name TEXT,
    province_name TEXT,
    city_name TEXT,
    type_name TEXT,
    nature_name TEXT,
    f985 INTEGER,
    f211 INTEGER,
    dual_class_name TEXT,
    eol_rank INTEGER,
    ruanke_rank TEXT,
    fetched_at TEXT,
    info_json TEXT
);
CREATE TABLE IF NOT EXISTS province_scores (
    school_id INTEGER,
    year INTEGER,
    province_id INTEGER,
    type_id TEXT,             -- 2073 物理类 / 2074 历史类
    special_group TEXT,
    sg_name TEXT,
    sg_info TEXT,             -- 选科要求, eg "首选物理，再选化学"
    zslx TEXT,
    zslx_name TEXT,           -- 普通类 / 国家专项 / 地方专项 ...
    batch TEXT,
    local_batch_name TEXT,    -- 本科批 / 专科批 ...
    min_score TEXT,
    min_section TEXT,         -- 最低位次
    filing TEXT,              -- 投档线
    max_score TEXT,
    average TEXT,
    proscore TEXT,            -- 省控线
    diff INTEGER,             -- 高出省控线
    num TEXT,
    local_type_name TEXT,
    raw_json TEXT,
    PRIMARY KEY (school_id, year, type_id, special_group, zslx)
);
CREATE TABLE IF NOT EXISTS fetch_log (
    url TEXT PRIMARY KEY,
    status INTEGER,
    fetched_at TEXT,
    note TEXT
);
CREATE INDEX IF NOT EXISTS idx_score_year_type ON province_scores(year, type_id);
CREATE INDEX IF NOT EXISTS idx_score_school ON province_scores(school_id);
"""


def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with LOG_PATH.open("a") as f:
        f.write(line + "\n")


def init_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def already_fetched(conn, url: str) -> bool:
    row = conn.execute(
        "SELECT status FROM fetch_log WHERE url = ?", (url,)
    ).fetchone()
    return row is not None and row[0] == 200


def mark_fetched(conn, url: str, status: int, note: str = "") -> None:
    conn.execute(
        "INSERT OR REPLACE INTO fetch_log VALUES (?, ?, datetime('now'), ?)",
        (url, status, note),
    )


def get_json(url: str):
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    return r.status_code, (r.json() if r.status_code == 200 else None)


def to_int(v):
    try:
        return int(str(v).strip()) if v not in (None, "", "-") else None
    except (ValueError, TypeError):
        return None


def fetch_school_list(conn) -> list[int]:
    """翻页 api.eol.cn 获取全量 school_id"""
    log("=== Step 1: 拉院校全表 ===")
    seen: set[int] = set()
    page = 1
    while True:
        url = (
            "https://api.eol.cn/gkcx/api/?"
            f"uri=apidata/api/gkv3/school/lists&size=50&page={page}"
        )
        if already_fetched(conn, url):
            # 已抓过这一页, 跳过
            page += 1
            if page > 200:
                break
            continue
        try:
            status, data = get_json(url)
            if status != 200 or not data:
                log(f"[list] page={page} status={status}, stop")
                mark_fetched(conn, url, status, "list-end")
                break
            items = data.get("data", {}).get("item", [])
            if not items:
                log(f"[list] page={page} empty, done")
                mark_fetched(conn, url, 200, "empty")
                break
            for it in items:
                sid = to_int(it.get("school_id"))
                if sid:
                    seen.add(sid)
            mark_fetched(conn, url, 200, f"got={len(items)}")
            conn.commit()
            log(f"[list] page={page} +{len(items)} total={len(seen)}")
            page += 1
            if page > 200:
                break
            time.sleep(SLEEP)
        except Exception as e:
            log(f"[list] page={page} EXC {e}")
            mark_fetched(conn, url, 0, str(e)[:200])
            conn.commit()
            time.sleep(SLEEP * 3)
            page += 1
            if page > 200:
                break

    # 兜底: 已经抓过的 schools 表里的 ID 也算上
    seen |= {r[0] for r in conn.execute("SELECT school_id FROM schools").fetchall()}
    return sorted(seen)


def fetch_school_info(conn, sid: int) -> dict | None:
    url = f"https://static-data.gaokao.cn/www/2.0/school/{sid}/info.json"
    if already_fetched(conn, url):
        row = conn.execute(
            "SELECT info_json FROM schools WHERE school_id=?", (sid,)
        ).fetchone()
        return json.loads(row[0]) if row and row[0] else None
    try:
        status, data = get_json(url)
        if status != 200 or not data:
            mark_fetched(conn, url, status, "no-data")
            conn.commit()
            return None
        d = data.get("data") or {}
        if not d.get("name"):
            mark_fetched(conn, url, status, "empty-name")
            conn.commit()
            return None
        conn.execute(
            "INSERT OR REPLACE INTO schools VALUES "
            "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?)",
            (
                to_int(d.get("school_id")) or sid,
                d.get("name"),
                d.get("province_name"),
                d.get("city_name"),
                d.get("type_name"),
                d.get("nature_name"),
                to_int(d.get("f985")) or 0,
                to_int(d.get("f211")) or 0,
                d.get("dual_class_name"),
                to_int(d.get("eol_rank")),
                str(d.get("ruanke_rank") or ""),
                json.dumps(d, ensure_ascii=False),
            ),
        )
        mark_fetched(conn, url, 200)
        conn.commit()
        return d
    except Exception as e:
        mark_fetched(conn, url, 0, str(e)[:200])
        conn.commit()
        return None


def fetch_province_score(conn, sid: int, year: int) -> int:
    url = (
        f"https://static-data.gaokao.cn/www/2.0/schoolprovincescore/"
        f"{sid}/{year}/{PROV_ID}.json"
    )
    if already_fetched(conn, url):
        return -1  # 已抓过
    try:
        status, data = get_json(url)
        if status != 200:
            mark_fetched(conn, url, status, "")
            conn.commit()
            return 0
        if not data:
            mark_fetched(conn, url, status, "no-json")
            conn.commit()
            return 0
        body = data.get("data") or {}
        n = 0
        for type_id, payload in body.items():
            if not isinstance(payload, dict):
                continue
            for it in payload.get("item", []):
                conn.execute(
                    "INSERT OR REPLACE INTO province_scores VALUES "
                    "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        to_int(it.get("school_id")) or sid,
                        to_int(it.get("year")) or year,
                        to_int(it.get("province_id")) or PROV_ID,
                        str(it.get("type") or type_id),
                        it.get("special_group") or "",
                        it.get("sg_name"),
                        it.get("sg_info"),
                        str(it.get("zslx") or ""),
                        it.get("zslx_name"),
                        it.get("batch"),
                        it.get("local_batch_name"),
                        it.get("min"),
                        it.get("min_section"),
                        it.get("filing"),
                        it.get("max"),
                        it.get("average"),
                        it.get("proscore"),
                        to_int(it.get("diff")),
                        it.get("num"),
                        it.get("local_type_name"),
                        json.dumps(it, ensure_ascii=False),
                    ),
                )
                n += 1
        mark_fetched(conn, url, 200, f"groups={n}")
        conn.commit()
        return n
    except Exception as e:
        mark_fetched(conn, url, 0, str(e)[:200])
        conn.commit()
        return 0


def main() -> int:
    log(f"DB={DB_PATH}")
    conn = init_db()

    # Step 1: school list
    school_ids = fetch_school_list(conn)
    log(f"院校列表共 {len(school_ids)} 个 school_id")

    # 兜底:把 1..max(api) 都加进来,info.json 失败就跳过
    if school_ids:
        max_id = max(school_ids)
        full_range = set(range(1, max_id + 1)) | set(school_ids)
    else:
        full_range = set(range(1, 3001))
    candidates = sorted(full_range)
    log(f"将试探 {len(candidates)} 个 school_id (1..{max(candidates)})")

    # Step 2: 遍历
    log("=== Step 2: 抓院校信息 + 湖北历年录取数据 ===")
    n_schools = 0
    n_score_rows = 0
    n_skipped = 0
    for i, sid in enumerate(candidates):
        info = fetch_school_info(conn, sid)
        if not info:
            n_skipped += 1
            time.sleep(SLEEP)
            continue
        n_schools += 1
        if i % 50 == 0:
            log(
                f"  [{i}/{len(candidates)}] sid={sid} 累计校={n_schools} "
                f"分数行={n_score_rows} 跳过={n_skipped}"
            )
        time.sleep(SLEEP)
        for year in YEARS:
            n = fetch_province_score(conn, sid, year)
            if n > 0:
                n_score_rows += n
            time.sleep(SLEEP)

    log(
        f"DONE: 院校={n_schools} 分数行={n_score_rows} "
        f"跳过(空)={n_skipped}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
