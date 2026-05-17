#!/usr/bin/env python3
"""
志愿咨询 → HTML 报告渲染。

读 JSON(由 skill agent 输出咨询结构化数据),生成自包含 HTML(内联 CSS,无外部依赖)。

主题:`renderer/themes/<name>.css` 单文件,默认 editorial,playground 还有 bloomberg / stripe / spotify。

用法:
  python3 renderer/render_report.py --json /tmp/zhiyuan.json --output output/x.html
  python3 renderer/render_report.py --json /tmp/x.json --theme bloomberg --output output/x.html
  cat /tmp/zhiyuan.json | python3 renderer/render_report.py --output output/x.html
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import sys
from pathlib import Path

THEMES_DIR = Path(__file__).parent / "themes"


TIER_COLORS = {
    "冲": ("#d97757", "#fdf0ec"),  # 暖红
    "稳": ("#6b9b7e", "#eef5f0"),  # 沉绿
    "保": ("#5a8ca8", "#eaf2f7"),  # 沉蓝
    "避坑": ("#9b9b9b", "#f0f0f0"),  # 灰
}

TIER_LABEL = {"冲": "冲档", "稳": "稳档", "保": "保档", "避坑": "避坑"}


def _load_theme(name: str) -> str:
    p = THEMES_DIR / f"{name}.css"
    if not p.exists():
        raise FileNotFoundError(f"theme '{name}' not found at {p}")
    return p.read_text(encoding="utf-8")


# 兼容用,默认 editorial 主题(等价于 _load_theme("editorial"))
_LEGACY_CSS = """
:root {
  /* OKLCH palette — editorial / 教育 / 教培咨询机构 */
  --ink: oklch(20% 0.015 150);
  --ink-soft: oklch(40% 0.015 150);
  --ink-mute: oklch(58% 0.012 60);
  --paper: oklch(98% 0.006 60);
  --surface: oklch(96% 0.01 60);
  --hairline: oklch(88% 0.012 60);
  --rule: oklch(75% 0.012 60);
  --accent: oklch(38% 0.10 150);     /* 深绿 accent */
  --accent-mute: oklch(60% 0.05 150);
  --tier-chong: oklch(52% 0.18 25);  /* 暖红 */
  --tier-wen: oklch(46% 0.10 145);   /* 深绿 */
  --tier-bao: oklch(48% 0.07 230);   /* 灰蓝 */
  --tier-bi: oklch(50% 0.01 60);     /* 中性灰 */
  --warn: oklch(50% 0.16 30);
}

* { box-sizing: border-box; margin: 0; padding: 0; }
html { font-size: 16px; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
               "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  background: var(--paper);
  color: var(--ink);
  line-height: 1.7;
  padding: 56px 28px 40px;
  max-width: 920px;
  margin: 0 auto;
  font-feature-settings: "kern", "palt";
  font-variant-numeric: oldstyle-nums;
}
.serif {
  font-family: "Songti SC", "STSong", "SimSun", Georgia, "Times New Roman", serif;
}
.tabular { font-variant-numeric: tabular-nums; letter-spacing: 0.01em; }
em { font-style: italic; }
strong { font-weight: 600; }

/* 头版 */
header {
  margin-bottom: 48px;
  padding-bottom: 20px;
  border-bottom: 1px solid var(--ink);
}
.eyebrow {
  font-size: 0.72rem;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--ink-mute);
  margin-bottom: 14px;
  display: flex;
  gap: 18px;
  align-items: baseline;
}
.eyebrow > span:not(:last-child)::after {
  content: "/";
  margin-left: 18px;
  color: var(--rule);
}
h1 {
  font-family: "Songti SC", "STSong", Georgia, serif;
  font-size: 2.3rem;
  font-weight: 700;
  letter-spacing: -0.01em;
  line-height: 1.15;
}
.deck {
  font-size: 1.05rem;
  color: var(--ink-soft);
  margin-top: 12px;
  max-width: 56ch;
  font-style: italic;
}

/* section 通用 */
section { margin-bottom: 56px; }
h2 {
  font-family: "Songti SC", "STSong", Georgia, serif;
  font-size: 0.78rem;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: var(--accent);
  margin-bottom: 24px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--rule);
  font-weight: 600;
}
h2 .count {
  color: var(--ink-mute);
  font-weight: 400;
  margin-left: 6px;
}

/* 用户画像 — 不再卡片,用 grid + 数字大显示 */
.profile-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 8px 32px;
  padding: 4px 0 16px;
  border-bottom: 1px solid var(--hairline);
}
.profile-item .k {
  font-size: 0.7rem;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--ink-mute);
  margin-bottom: 6px;
  font-weight: 500;
}
.profile-item .v {
  font-family: "Songti SC", Georgia, serif;
  font-size: 1.55rem;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--ink);
  line-height: 1.1;
}
.profile-item.text .v {
  font-family: -apple-system, "PingFang SC", sans-serif;
  font-size: 1.05rem;
  font-weight: 500;
}
.tag-row {
  margin-top: 18px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.tag {
  font-size: 0.78rem;
  color: var(--ink-soft);
  padding: 2px 0;
  border-bottom: 1px solid var(--rule);
  white-space: nowrap;
}

.profile-note {
  margin-top: 18px;
  padding: 12px 0 12px 16px;
  border-left: 3px solid var(--warn);
  font-size: 0.88rem;
  color: var(--ink-soft);
  font-style: italic;
}
.profile-note::before {
  content: "校准 · ";
  font-style: normal;
  font-size: 0.7rem;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  font-weight: 600;
  color: var(--warn);
}

/* 核心判断 — lead paragraph editorial */
.judgment {
  font-family: "Songti SC", "STSong", Georgia, serif;
  font-size: 1.18rem;
  line-height: 1.8;
  color: var(--ink);
  white-space: pre-wrap;
  padding: 0 0 0 32px;
  border-left: 1px solid var(--ink);
  position: relative;
}
.judgment::before {
  content: "“";
  position: absolute;
  left: -2px;
  top: -16px;
  font-size: 4rem;
  font-family: Georgia, serif;
  color: var(--accent);
  line-height: 1;
}

/* 推荐 / 避坑 卡片 — 不再外层 box,用左侧色条 + 内部 typography */
.card {
  margin-bottom: 32px;
  padding-left: 20px;
  border-left: 4px solid var(--rule);
  position: relative;
}
.card.tier-冲 { border-left-color: var(--tier-chong); }
.card.tier-稳 { border-left-color: var(--tier-wen); }
.card.tier-保 { border-left-color: var(--tier-bao); }
.card.tier-避坑 { border-left-color: var(--tier-bi); }

.card-meta-line {
  display: flex;
  gap: 14px;
  align-items: baseline;
  margin-bottom: 10px;
  font-size: 0.72rem;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--ink-mute);
  font-weight: 500;
}
.tier-label {
  letter-spacing: 0.22em;
}
.tier-label.tier-冲 { color: var(--tier-chong); }
.tier-label.tier-稳 { color: var(--tier-wen); }
.tier-label.tier-保 { color: var(--tier-bao); }
.tier-label.tier-避坑 { color: var(--tier-bi); }
.tier-label::before { content: "—  "; }

.card-title {
  font-family: "Songti SC", "STSong", Georgia, serif;
  font-size: 1.45rem;
  font-weight: 600;
  letter-spacing: -0.005em;
  line-height: 1.3;
  margin-bottom: 4px;
}
.card-subtitle {
  font-size: 0.92rem;
  color: var(--ink-soft);
  margin-bottom: 16px;
  font-style: italic;
}
.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 4px 24px;
  margin-bottom: 16px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--hairline);
  font-size: 0.85rem;
}
.card-grid .k {
  color: var(--ink-mute);
  font-size: 0.7rem;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  margin-bottom: 2px;
  font-weight: 500;
}
.card-grid .v {
  color: var(--ink);
  font-weight: 500;
  font-variant-numeric: tabular-nums;
}

.history-table {
  width: 100%;
  border-collapse: collapse;
  margin: 12px 0;
  font-size: 0.86rem;
  font-variant-numeric: tabular-nums;
}
.history-table th {
  font-weight: 500;
  font-size: 0.7rem;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--ink-mute);
  text-align: left;
  padding: 6px 12px 6px 0;
  border-bottom: 1px solid var(--ink);
}
.history-table td {
  padding: 7px 12px 7px 0;
  border-bottom: 1px solid var(--hairline);
  color: var(--ink);
}
.history-table tr:last-child td { border-bottom: none; }
.history-table th:not(:first-child),
.history-table td:not(:first-child) {
  text-align: right;
}
.history-table tr.estimated td {
  color: var(--ink-mute);
  font-style: italic;
}
.history-table tr.estimated td:first-child::after {
  content: " *";
  color: var(--warn);
  font-style: normal;
  font-weight: 600;
}
.history-estimated-note {
  font-size: 0.72rem;
  color: var(--ink-mute);
  margin-top: 4px;
  padding-left: 2px;
}

.risk {
  font-size: 0.7rem;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  font-weight: 600;
  margin-left: 12px;
}
.risk.稳 { color: var(--tier-wen); }
.risk.中 { color: oklch(50% 0.13 70); }
.risk.高 { color: var(--tier-chong); }
.risk::before { content: "· "; opacity: 0.5; }

.prob-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 0.78rem;
  font-weight: 600;
  margin-left: 8px;
}
.prob-badge.prob-安全   { background: oklch(90% 0.08 145); color: oklch(35% 0.15 145); }
.prob-badge.prob-较稳   { background: oklch(93% 0.07 80);  color: oklch(40% 0.15 80);  }
.prob-badge.prob-有风险 { background: oklch(92% 0.08 40);  color: oklch(40% 0.18 40);  }
.prob-badge.prob-高风险 { background: oklch(93% 0.08 20);  color: oklch(35% 0.20 20);  }
.prob-badge.prob-未知   { background: oklch(92% 0.00 0);   color: oklch(45% 0.00 0);   }

.reason {
  margin: 12px 0;
  font-size: 0.95rem;
  line-height: 1.75;
  white-space: pre-wrap;
  color: var(--ink);
}

.replacement {
  margin-top: 12px;
  padding: 10px 16px;
  background: var(--surface);
  font-size: 0.9rem;
  color: var(--ink-soft);
  border-left: 2px solid var(--accent-mute);
}
.replacement-label {
  font-size: 0.68rem;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  font-weight: 600;
  color: var(--accent);
  display: block;
  margin-bottom: 4px;
}

.reminders {
  list-style: none;
  margin-top: 12px;
  border-top: 1px solid var(--hairline);
  padding-top: 10px;
}
.reminders li {
  padding: 5px 0 5px 24px;
  position: relative;
  font-size: 0.88rem;
  color: var(--ink-soft);
  line-height: 1.65;
}
.reminders li::before {
  content: "→";
  position: absolute;
  left: 0;
  top: 5px;
  color: var(--ink-mute);
  font-weight: 600;
}

/* 完整志愿表 */
.code-warning {
  font-size: 0.74rem;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  font-weight: 600;
  color: var(--warn);
  border-top: 1px solid var(--warn);
  border-bottom: 1px solid var(--warn);
  padding: 10px 0;
  margin-bottom: 16px;
  line-height: 1.7;
}
.code-warning b {
  display: block;
  font-size: 0.84rem;
  margin-bottom: 4px;
  color: var(--ink);
  letter-spacing: 0.14em;
}
.code-warning .normal-text {
  text-transform: none;
  letter-spacing: normal;
  font-weight: 400;
  font-size: 0.82rem;
  color: var(--ink-soft);
}

.full-list {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.86rem;
  font-variant-numeric: tabular-nums;
}
.full-list th {
  text-align: left;
  font-weight: 500;
  font-size: 0.68rem;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--ink-mute);
  padding: 8px 12px 8px 0;
  border-bottom: 2px solid var(--ink);
}
.full-list td {
  padding: 9px 12px 9px 0;
  border-bottom: 1px solid var(--hairline);
  color: var(--ink);
  vertical-align: top;
}
.full-list tr:last-child td { border-bottom: 1px solid var(--ink); }
.full-list .num { width: 30px; color: var(--ink-mute); text-align: right; padding-right: 16px; }
.full-list .tier-cell {
  width: 56px;
  font-size: 0.66rem;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  font-weight: 700;
}
.full-list .tier-cell.tier-冲 { color: var(--tier-chong); }
.full-list .tier-cell.tier-稳 { color: var(--tier-wen); }
.full-list .tier-cell.tier-保 { color: var(--tier-bao); }
.full-list .school { font-weight: 500; }
.full-list .group { color: var(--ink-soft); }
.full-list .rank { text-align: right; font-variant-numeric: tabular-nums; }
.full-list .blurb { color: var(--ink-soft); font-style: italic; }

/* 必聊 — editorial pull-quotes */
.discuss {
  list-style: none;
  counter-reset: item;
}
.discuss li {
  padding: 18px 0 18px 80px;
  border-top: 1px solid var(--hairline);
  position: relative;
  font-size: 1rem;
  line-height: 1.75;
  color: var(--ink);
}
.discuss li:last-child { border-bottom: 1px solid var(--hairline); }
.discuss li::before {
  counter-increment: item;
  content: "§ " counter(item, decimal-leading-zero);
  position: absolute;
  left: 0;
  top: 18px;
  font-family: Georgia, serif;
  font-size: 0.78rem;
  letter-spacing: 0.18em;
  font-weight: 600;
  color: var(--accent);
  width: 64px;
}

footer {
  margin-top: 56px;
  padding-top: 18px;
  border-top: 1px solid var(--ink);
  color: var(--ink-mute);
  font-size: 0.74rem;
  line-height: 1.8;
  letter-spacing: 0.02em;
}
footer p { margin-bottom: 4px; }
footer p:last-child {
  font-size: 0.68rem;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--ink-soft);
  margin-top: 8px;
}

@media (max-width: 600px) {
  body { padding: 32px 18px 28px; max-width: 100%; }
  h1 { font-size: 1.8rem; }
  .judgment { font-size: 1.05rem; padding-left: 22px; }
  .card-title { font-size: 1.2rem; }
  .discuss li { padding-left: 0; padding-top: 36px; }
  .discuss li::before { top: 12px; }
}

@media print {
  body { font-size: 11pt; background: white !important; }
  header { page-break-after: avoid; }
  .card { page-break-inside: avoid; break-inside: avoid; border: 1px solid #ccc !important; margin-bottom: 12pt; }
  .avoid-card { page-break-inside: avoid; }
  footer { page-break-before: avoid; font-size: 8pt; }
  a[href]::after { content: none; }
}
"""

# 把内嵌 _LEGACY_CSS 当作 editorial fallback,但优先从文件加载
CSS = _LEGACY_CSS  # 兼容旧调用


def esc(s) -> str:
    if s is None:
        return ""
    return html.escape(str(s))


def render_profile(p: dict) -> str:
    """画像 grid:数字字段(分数/位次/百分位)用 serif 大字,文本字段(科类/批次/选科)用 sans-serif 中等字。"""
    items = []
    for label, key, kind in [
        ("分数", "分数", "num"),
        ("位次", "位次", "num"),
        ("百分位", "百分位", "num"),
        ("科类", "科类", "text"),
        ("批次", "批次", "text"),
    ]:
        v = p.get(key)
        if v is None or v == "":
            continue
        cls = "profile-item" if kind == "num" else "profile-item text"
        items.append(
            f'<div class="{cls}"><div class="k">{esc(label)}</div>'
            f'<div class="v">{esc(v)}</div></div>'
        )
    if p.get("选科"):
        sel = " · ".join(p["选科"]) if isinstance(p["选科"], list) else str(p["选科"])
        items.append(
            f'<div class="profile-item text"><div class="k">选科</div>'
            f'<div class="v">{esc(sel)}</div></div>'
        )
    out = f'<div class="profile-grid">{"".join(items)}</div>'
    if p.get("标签"):
        tags = "".join(f'<span class="tag">{esc(t)}</span>' for t in p["标签"])
        out += f'<div class="tag-row">{tags}</div>'
    note = p.get("位次说明")
    if note:
        out += f'<div class="profile-note">{esc(note)}</div>'
    return out


def render_history(rows) -> str:
    if not rows:
        return ""
    has_estimated = any(r.get("estimated") for r in rows)
    head = "<tr><th>年份</th><th>投档分</th><th>最低位次</th></tr>"
    body_parts = []
    for r in rows:
        cls = ' class="estimated"' if r.get("estimated") else ""
        body_parts.append(
            f"<tr{cls}><td>{esc(r.get('年份'))}</td>"
            f"<td>{esc(r.get('投档分', '—'))}</td>"
            f"<td>{esc(r.get('最低位次', '—'))}</td></tr>"
        )
    note = (
        '<p class="history-estimated-note">* 标注行为 AI 推算，非数据库实测值，误差可达 ±30 分，仅供方向参考</p>'
        if has_estimated else ""
    )
    return f'<table class="history-table">{head}{"".join(body_parts)}</table>{note}'


def render_card(card: dict, idx: int) -> str:
    tier = card.get("档位", "稳")
    school = esc(card.get("院校", ""))
    group = esc(card.get("专业组", ""))

    # meta line: 档位 / 序号 / 风险 (eyebrow 风格)
    meta_parts = [f'<span class="tier-label tier-{tier}">{TIER_LABEL.get(tier, tier)}</span>']
    meta_parts.append(f'<span class="seq">No. {idx:02d}</span>')

    risk = card.get("大小年风险", "")
    if risk:
        kind = "稳"
        for k in ["稳", "中", "高"]:
            if k in risk:
                kind = k
                break
        meta_parts.append(f'<span class="risk {kind}">{esc(risk)}</span>')

    prob = card.get("录取概率")
    if prob:
        display = esc(prob.get("display", ""))
        label = esc(prob.get("label", "未知"))
        meta_parts.append(
            f'<span class="prob-badge prob-{label}">{display} {label}</span>'
        )

    meta_line = f'<div class="card-meta-line">{"".join(meta_parts)}</div>'

    title = f'<div class="card-title serif">{school}</div>'
    subtitle = f'<div class="card-subtitle">{group}</div>' if group else ""

    # card-grid:把 地点/选科要求/招生类型/批次 作为标签对
    grid_items = []
    for label, key in [
        ("地点", "地点"),
        ("选科", "选科要求"),
        ("类型", "招生类型"),
        ("批次", "批次"),
    ]:
        v = card.get(key)
        if v:
            grid_items.append(
                f'<div><div class="k">{esc(label)}</div>'
                f'<div class="v">{esc(v)}</div></div>'
            )
    grid_html = (
        f'<div class="card-grid">{"".join(grid_items)}</div>' if grid_items else ""
    )

    reason = card.get("推理", "")
    if isinstance(reason, list):
        reason_text = "\n\n".join(str(s) for s in reason if s)
    else:
        reason_text = reason or ""
    reason_html = (
        f'<div class="reason">{esc(reason_text)}</div>' if reason_text else ""
    )

    replacement = card.get("替代", "")
    replacement_html = (
        f'<div class="replacement">'
        f'<span class="replacement-label">替代建议</span>{esc(replacement)}'
        f'</div>'
        if replacement
        else ""
    )

    reminders = card.get("提醒", [])
    if isinstance(reminders, str):
        reminders = [reminders]
    reminders_html = ""
    if reminders:
        items = "".join(f"<li>{esc(r)}</li>" for r in reminders)
        reminders_html = f'<ul class="reminders">{items}</ul>'

    return (
        f'<article class="card tier-{tier}">'
        f'{meta_line}'
        f'{title}'
        f'{subtitle}'
        f'{grid_html}'
        f"{render_history(card.get('历年录取', []))}"
        f'{reason_html}'
        f'{replacement_html}'
        f'{reminders_html}'
        f'</article>'
    )


def render_full_list(items: list, prov_zh: str = "") -> str:
    if not items:
        return ""
    has_codes = any(it.get("院校代码") or it.get("组号") for it in items)
    next_year = dt.datetime.now().year + 1
    warning = (
        f'<div class="code-warning">'
        f'<b>填报代码以招生章程为准</b>'
        f'<span class="normal-text">'
        f'下表院校 / 专业组按位次匹配,**院校代码 / 专业组组号不在数据库内**,'
        f'实际填报请查《对应院校 {next_year} 年在{esc(prov_zh)}招生章程》。'
        f'{"表中已列出的代码 / 组号仅为参考,务必跟章程交叉核对。" if has_codes else ""}'
        f'</span>'
        f'</div>'
    )
    rows = []
    for i, it in enumerate(items, 1):
        tier = it.get("档位", "稳")
        cells = [
            f"<td class='num tabular'>{esc(it.get('序号', i)):0>2s}</td>"
            if isinstance(it.get('序号', i), str)
            else f"<td class='num tabular'>{it.get('序号', i):02d}</td>",
            f"<td class='tier-cell tier-{tier}'>{esc(TIER_LABEL.get(tier, tier))}</td>",
            f"<td class='school'>{esc(it.get('院校', ''))}</td>",
        ]
        if has_codes:
            cells += [
                f"<td class='tabular'>{esc(it.get('院校代码', '—'))}</td>",
                f"<td class='group'>{esc(it.get('专业组', ''))}</td>",
                f"<td class='tabular'>{esc(it.get('组号', '—'))}</td>",
            ]
        else:
            cells.append(f"<td class='group'>{esc(it.get('专业组', ''))}</td>")
        cells += [
            f"<td class='rank'>{esc(it.get('参考位次', '—'))}</td>",
            f"<td class='blurb'>{esc(it.get('一句话', ''))}</td>",
        ]
        rows.append("<tr>" + "".join(cells) + "</tr>")

    cols = ["#", "档位", "院校", "专业组", "参考位次", "备注"]
    if has_codes:
        cols = ["#", "档位", "院校", "代码", "专业组", "组号", "参考位次", "备注"]
    head = "<tr>" + "".join(f"<th>{c}</th>" for c in cols) + "</tr>"
    return warning + f'<table class="full-list">{head}{"".join(rows)}</table>'


def render(data: dict, theme: str = "bloomberg") -> str:
    css = _load_theme(theme) if (THEMES_DIR / f"{theme}.css").exists() else CSS
    meta = data.get("meta", {})
    profile = data.get("用户画像", {})
    judgment = data.get("核心判断", "")
    recs = data.get("推荐", [])
    avoids = data.get("避坑", [])
    full = data.get("完整志愿", [])
    discuss = data.get("必聊", [])
    disclaimer = data.get(
        "免责声明",
        "实际填报请结合招生章程和省级招办公布的一分一段表;以上仅参考。",
    )

    prov = meta.get("省份", "")
    title = f"{prov}志愿规划"
    gen_time = meta.get("生成时间", dt.datetime.now().strftime("%Y-%m-%d %H:%M"))
    # eyebrow:报告类型 · 数据版本 · 日期(头版式)
    eyebrow_parts = [
        "AI 志愿规划报告",
    ]
    if meta.get("数据版本"):
        eyebrow_parts.append(f"数据 {meta['数据版本']}")
    eyebrow_parts.append(gen_time.split(" ")[0] if " " in gen_time else gen_time)

    # deck:对画像的 1-2 句概括(score + 科类 + 选科 + 主关键词)
    deck_parts = []
    if profile.get("分数") is not None:
        deck_parts.append(f"{profile['分数']} 分")
    if profile.get("科类"):
        deck_parts.append(profile["科类"])
    if profile.get("位次"):
        deck_parts.append(f"位次 {profile['位次']}")
    if meta.get("总分制"):
        deck_parts.append(f"总分 {meta['总分制']}")
    deck = " · ".join(str(x) for x in deck_parts)

    sections = []

    sections.append(f'<section>{render_profile(profile)}</section>')

    if judgment:
        sections.append(
            f'<section><h2>核心判断</h2>'
            f'<div class="judgment">{esc(judgment)}</div></section>'
        )

    if recs:
        cards_html = "".join(render_card(c, i + 1) for i, c in enumerate(recs))
        sections.append(
            f'<section><h2>核心推荐<span class="count">{len(recs)} 张</span></h2>'
            f'{cards_html}</section>'
        )

    if avoids:
        cards_html = "".join(render_card(c, i + 1) for i, c in enumerate(avoids))
        sections.append(
            f'<section><h2>明确避坑<span class="count">{len(avoids)} 张</span></h2>'
            f'{cards_html}</section>'
        )

    if full:
        sections.append(
            f'<section><h2>完整志愿表<span class="count">{len(full)} 个</span></h2>'
            f'{render_full_list(full, prov)}</section>'
        )

    if discuss:
        items = "".join(f"<li>{esc(d)}</li>" for d in discuss)
        sections.append(
            f'<section><h2>必须跟父母 / 自己聊的事</h2>'
            f'<ul class="discuss">{items}</ul></section>'
        )

    eyebrow_html = "".join(f"<span>{esc(p)}</span>" for p in eyebrow_parts)
    body = (
        f'<header>'
        f'<div class="eyebrow">{eyebrow_html}</div>'
        f'<h1>{esc(title)}</h1>'
        f'<div class="deck">{esc(deck)}</div>'
        f'</header>'
        + "".join(sections)
        + f'<footer>'
        f'<p>{esc(disclaimer)}</p>'
        f'<p>AI 志愿规划师 · 仅供参考 · 不构成填报承诺</p>'
        f'</footer>'
    )

    return (
        f'<!DOCTYPE html>\n'
        f'<html lang="zh-CN" data-theme="{esc(theme)}"><head>'
        f'<meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>{esc(title)}</title>'
        f'<style>{css}</style>'
        f'</head><body>{body}</body></html>'
    )


def main() -> int:
    p = argparse.ArgumentParser(description="JSON → HTML 志愿报告渲染")
    p.add_argument("--json", help="输入 JSON 文件路径(不传则从 stdin 读)")
    p.add_argument("--output", "-o", required=True, help="输出 HTML 文件路径")
    p.add_argument(
        "--theme",
        default="bloomberg",
        help="主题 CSS:bloomberg(默认,数据 ticker 风)/ editorial / stripe / spotify(从 renderer/themes/<name>.css 加载)",
    )
    args = p.parse_args()

    if args.json:
        data = json.loads(Path(args.json).read_text(encoding="utf-8"))
    else:
        data = json.loads(sys.stdin.read())

    html_out = render(data, theme=args.theme)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_out, encoding="utf-8")
    print(f"✓ 已生成报告:{out_path}")
    print(f"  双击打开:open {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
