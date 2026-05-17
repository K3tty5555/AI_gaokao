#!/usr/bin/env python3
"""
L1-A 出分前方向性建议 → HTML 报告渲染。

读 JSON(由 skill agent 在出分前 L5 输出后整理),生成自包含 HTML。
跟 render_report.py 区别:出分前没真实位次,所以不出 7 字段志愿卡片 / 不出完整志愿表 /
不出历年录取数据。改为输出"方向性建议"叙事(主推方向 + 避坑 + 高三冲刺空间 +
意向冲突 reality check)。

用法:
  python3 renderer/render_l1a_report.py --json /tmp/zhiyuan_l1a.json --output output/x.html
  python3 renderer/render_l1a_report.py --json renderer/schemas/sample_l1a_report.json --output output/sample.html
  cat /tmp/x.json | python3 renderer/render_l1a_report.py --output output/x.html
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import sys
from pathlib import Path

THEMES_DIR = Path(__file__).parent / "themes"


def _load_theme(name: str) -> str:
    p = THEMES_DIR / f"{name}.css"
    if not p.exists():
        raise FileNotFoundError(f"theme '{name}' not found at {p}")
    return p.read_text(encoding="utf-8")


# L1-A 专属样式 override(不依赖具体主题,在主题 CSS 之后 append)
L1A_EXTRA_CSS = """
/* L1-A 出分前方向性建议专属样式 */
.l1a-banner {
  display: inline-block;
  padding: 4px 10px;
  font-size: 0.7rem;
  letter-spacing: 0.15em;
  text-transform: uppercase;
  background: var(--ink, #111);
  color: var(--paper, #fff);
  font-weight: 600;
  margin-bottom: 12px;
}

/* 双口径估算 */
.dual-estimate {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
  margin: 18px 0 14px;
}
.estimate-box {
  border: 1px solid var(--hairline, #ccc);
  padding: 14px 16px;
  background: var(--surface, #fafafa);
}
.estimate-box .est-label {
  font-size: 0.72rem;
  letter-spacing: 0.15em;
  text-transform: uppercase;
  color: var(--ink-mute, #666);
  margin-bottom: 8px;
}
.estimate-box .est-name {
  font-size: 0.95rem;
  font-weight: 600;
  margin-bottom: 6px;
}
.estimate-box .est-rank {
  font-size: 1.5rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  margin: 6px 0;
}
.estimate-box .est-tier {
  font-size: 0.85rem;
  color: var(--ink-soft, #444);
  margin-bottom: 6px;
}
.estimate-box .est-meta {
  font-size: 0.78rem;
  color: var(--ink-mute, #777);
  font-variant-numeric: tabular-nums;
  margin: 4px 0;
}
.estimate-box .est-note {
  font-size: 0.78rem;
  color: var(--ink-mute, #777);
  margin-top: 6px;
  font-style: italic;
}
.calibration {
  background: var(--surface, #f5f5f5);
  border-left: 3px solid var(--accent, #d97757);
  padding: 12px 16px;
  margin-bottom: 14px;
}
.calibration .calib-result {
  font-size: 1.05rem;
  font-weight: 600;
  margin-bottom: 4px;
}
.calibration .calib-final {
  font-size: 0.92rem;
}
.calibration .calib-examples {
  margin-top: 8px;
  font-size: 0.85rem;
  color: var(--ink-soft, #444);
}

/* 学科画像 */
.subject-grid {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 8px;
  margin: 12px 0;
}
@media (max-width: 720px) {
  .subject-grid { grid-template-columns: repeat(3, 1fr); }
}
.subject-cell {
  border: 1px solid var(--hairline, #ccc);
  padding: 10px 8px;
  text-align: center;
  background: var(--surface, #fafafa);
}
.subject-cell .subj-name {
  font-size: 0.8rem;
  color: var(--ink-mute, #666);
  margin-bottom: 6px;
}
.subject-cell .subj-score {
  font-size: 1.4rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  line-height: 1;
}
.subject-cell .subj-frac {
  font-size: 0.7rem;
  color: var(--ink-mute, #888);
  margin-top: 2px;
}
.subject-cell .subj-tag {
  font-size: 0.72rem;
  margin-top: 6px;
  color: var(--ink-soft, #555);
}
.subject-cell.is-strong {
  background: oklch(95% 0.06 75);
  border-color: oklch(70% 0.15 75);
}
.subject-cell.is-strong .subj-tag {
  color: oklch(40% 0.16 30);
  font-weight: 600;
}
.observations {
  margin-top: 10px;
  padding-left: 18px;
}
.observations li {
  font-size: 0.92rem;
  margin-bottom: 4px;
  color: var(--ink-soft, #333);
}

/* 主推方向卡片 */
.direction-card {
  border: 1px solid var(--hairline, #ccc);
  border-left: 4px solid var(--accent, #d97757);
  margin-bottom: 18px;
  padding: 16px 20px;
  background: var(--paper, #fff);
}
.direction-card.priority-5 { border-left-color: oklch(52% 0.20 25); }
.direction-card.priority-4 { border-left-color: oklch(55% 0.18 75); }
.direction-card.priority-3 { border-left-color: oklch(50% 0.10 145); }
.direction-card .dir-meta {
  font-size: 0.72rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--ink-mute, #666);
  margin-bottom: 6px;
  display: flex;
  gap: 12px;
  align-items: center;
}
.direction-card .dir-stars {
  color: oklch(70% 0.18 75);
  letter-spacing: 0.05em;
}
.direction-card .dir-title {
  font-size: 1.2rem;
  font-weight: 700;
  margin-bottom: 8px;
}
.direction-card .dir-reason {
  font-size: 0.94rem;
  color: var(--ink-soft, #333);
  margin-bottom: 12px;
  line-height: 1.65;
}
.direction-card .school-list {
  border-top: 1px dashed var(--hairline, #ccc);
  padding-top: 10px;
}
.direction-card .school-row {
  display: grid;
  grid-template-columns: minmax(140px, 1.2fr) auto 3fr;
  gap: 6px 10px;
  padding: 8px 0;
  font-size: 0.88rem;
  border-bottom: 1px dotted var(--hairline, #e5e5e5);
  align-items: baseline;
}
.direction-card .school-row:last-child { border-bottom: none; }
.direction-card .school-row .sch-name { font-weight: 600; }
.direction-card .school-row .sch-fit { color: oklch(70% 0.18 75); white-space: nowrap; }
.direction-card .school-row .sch-reason { color: var(--ink-soft, #555); }
.direction-card .school-row .sch-majors {
  grid-column: 1 / -1;
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-top: 2px;
}
.direction-card .major-tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 3px;
  font-size: 0.78rem;
  font-weight: 500;
  background: oklch(95% 0.04 250);
  color: oklch(40% 0.14 250);
  border: 1px solid oklch(80% 0.08 250);
  white-space: nowrap;
}
@media (max-width: 720px) {
  .direction-card .school-row {
    grid-template-columns: 1fr;
    gap: 3px;
  }
  .direction-card .school-row .sch-majors {
    grid-column: 1;
  }
}

/* 避坑方向 */
.avoid-card {
  background: var(--surface, #f5f5f5);
  border-left: 3px solid #999;
  padding: 10px 14px;
  margin-bottom: 8px;
  font-size: 0.9rem;
}
.avoid-card .av-direction {
  font-weight: 600;
  margin-bottom: 4px;
  color: var(--ink, #222);
}
.avoid-card .av-direction::before { content: "❌ "; color: oklch(55% 0.20 25); }
.avoid-card .av-reason { color: var(--ink-soft, #444); }

/* 意向 reality check */
.intent-quote {
  font-style: italic;
  font-size: 1rem;
  padding: 10px 16px;
  border-left: 3px solid var(--ink-mute, #999);
  background: var(--surface, #fafafa);
  margin-bottom: 14px;
}
.intent-table {
  width: 100%;
  border-collapse: collapse;
  margin-bottom: 12px;
  font-size: 0.9rem;
}
.intent-table th, .intent-table td {
  text-align: left;
  padding: 8px 10px;
  border-bottom: 1px solid var(--hairline, #e5e5e5);
  vertical-align: top;
}
.intent-table th {
  background: var(--surface, #f5f5f5);
  font-size: 0.78rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--ink-mute, #666);
}
.intent-table .intent-status { white-space: nowrap; font-weight: 600; }
.intent-table .data-cell { color: var(--ink-soft, #333); font-variant-numeric: tabular-nums; }
.intent-conclusion {
  margin-top: 8px;
  padding: 10px 14px;
  background: oklch(95% 0.04 75);
  border-left: 3px solid oklch(60% 0.18 75);
  font-size: 0.92rem;
}

/* 好校 vs 强专业 */
.tradeoff-judge {
  background: var(--surface, #f5f5f5);
  padding: 12px 16px;
  margin-bottom: 10px;
  font-size: 1rem;
  font-weight: 600;
  border-left: 3px solid var(--accent, #d97757);
}
.tradeoff-reason {
  font-size: 0.92rem;
  color: var(--ink-soft, #333);
  margin-bottom: 10px;
  line-height: 1.65;
}
.tradeoff-examples {
  padding-left: 18px;
}
.tradeoff-examples li {
  font-size: 0.9rem;
  margin-bottom: 4px;
}

/* 高三冲刺空间 */
.sprint-main { font-size: 0.88rem; color: var(--ink-mute, #666); margin-bottom: 8px; }
.sprint-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.88rem;
  font-variant-numeric: tabular-nums;
  margin-bottom: 12px;
}
.sprint-table th, .sprint-table td {
  text-align: center;
  padding: 8px 6px;
  border: 1px solid var(--hairline, #ccc);
}
.sprint-table th {
  background: var(--surface, #f5f5f5);
  font-size: 0.78rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--ink-mute, #666);
}
.sprint-table .sprint-tier {
  font-weight: 600;
  text-align: left;
  padding-left: 12px;
}
.sprint-table .total-cell { font-size: 1.05rem; font-weight: 700; }
.sprint-table .schools { text-align: left; color: var(--ink-soft, #555); font-size: 0.82rem; }
.sprint-tier-保底 { background: oklch(96% 0.02 240); }
.sprint-tier-常规 { background: oklch(96% 0.03 145); }
.sprint-tier-冲档 { background: oklch(96% 0.04 30); }
.sprint-actions {
  margin-top: 10px;
  padding: 12px 16px;
  background: var(--surface, #f5f5f5);
  font-size: 0.9rem;
}
.sprint-actions .actions-title {
  font-size: 0.78rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--ink-mute, #666);
  margin-bottom: 6px;
}
.sprint-actions ol {
  padding-left: 22px;
  margin: 0;
}
.sprint-actions li { margin-bottom: 4px; }

/* 必聊 */
.discuss-list {
  list-style: none;
  padding-left: 0;
  counter-reset: discuss;
}
.discuss-list li {
  counter-increment: discuss;
  padding: 10px 14px 10px 44px;
  margin-bottom: 8px;
  background: var(--surface, #fafafa);
  border-left: 3px solid var(--accent, #d97757);
  position: relative;
  font-size: 0.94rem;
  line-height: 1.65;
}
.discuss-list li::before {
  content: counter(discuss);
  position: absolute;
  left: 12px;
  top: 12px;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--ink, #222);
  color: var(--paper, #fff);
  text-align: center;
  font-size: 0.78rem;
  font-weight: 700;
  line-height: 22px;
  font-variant-numeric: tabular-nums;
}

@media print {
  body { font-size: 11pt; background: white !important; }
  header { page-break-after: avoid; }
  .card { page-break-inside: avoid; break-inside: avoid; border: 1px solid #ccc !important; margin-bottom: 12pt; }
  .avoid-card { page-break-inside: avoid; }
  footer { page-break-before: avoid; font-size: 8pt; }
  a[href]::after { content: none; }
}

/* 下次再来 */
.next-step {
  background: oklch(96% 0.03 145);
  border-left: 3px solid oklch(50% 0.16 145);
  padding: 12px 16px;
  font-size: 0.92rem;
  color: var(--ink-soft, #333);
  line-height: 1.65;
}
.next-step .next-label {
  font-size: 0.74rem;
  letter-spacing: 0.15em;
  text-transform: uppercase;
  color: oklch(50% 0.16 145);
  font-weight: 700;
  margin-bottom: 6px;
}
"""


def esc(s) -> str:
    if s is None:
        return ""
    return html.escape(str(s))


def render_profile(p: dict) -> str:
    """L1-A 画像:学校 + 学校层次 + 户籍 + 排名 + 选科,不含分数 / 位次。"""
    items = []
    for label, key in [
        ("学校", "学校"),
        ("学校层次", "学校层次"),
        ("户籍", "户籍"),
        ("年级排名", "年级排名"),
        ("科类", "科类"),
    ]:
        v = p.get(key)
        if v:
            items.append(
                f'<div class="profile-item text"><div class="k">{esc(label)}</div>'
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
    note = p.get("画像备注")
    if note:
        out += f'<div class="profile-note">{esc(note)}</div>'
    return out


def render_dual_estimate(d: dict) -> str:
    if not d:
        return ""
    k1 = d.get("口径1", {})
    k2 = d.get("口径2", {})

    def _box(box_data: dict, label: str) -> str:
        if not box_data:
            return ""
        meta_parts = []
        if box_data.get("模考分"):
            scores = box_data["模考分"]
            if isinstance(scores, list):
                meta_parts.append(f"模考 {' / '.join(str(s) for s in scores)}")
            else:
                meta_parts.append(f"模考 {scores}")
        if box_data.get("中位数") is not None:
            meta_parts.append(f"中位 {box_data['中位数']}")
        if box_data.get("基准年"):
            meta_parts.append(f"基准 {box_data['基准年']}")
        if box_data.get("百分位"):
            pct = str(box_data["百分位"])
            meta_parts.append(pct if pct.startswith("前") else f"前 {pct}")

        parts = [
            f'<div class="est-label">{esc(label)}</div>',
            f'<div class="est-name">{esc(box_data.get("名称", ""))}</div>',
            f'<div class="est-rank">{esc(box_data.get("估算位次", "—"))}</div>',
        ]
        if box_data.get("估算档位"):
            parts.append(f'<div class="est-tier">{esc(box_data["估算档位"])}</div>')
        if meta_parts:
            parts.append(f'<div class="est-meta">{" · ".join(esc(m) for m in meta_parts)}</div>')
        if box_data.get("备注"):
            parts.append(f'<div class="est-note">{esc(box_data["备注"])}</div>')
        return f'<div class="estimate-box">{"".join(parts)}</div>'

    boxes = _box(k1, "口径 1") + _box(k2, "口径 2")

    cal_parts = []
    if d.get("校准结论"):
        cal_parts.append(f'<div class="calib-result">校准:{esc(d["校准结论"])}</div>')
    if d.get("最终定位"):
        cal_parts.append(
            f'<div class="calib-final">最终定位 → <strong>{esc(d["最终定位"])}</strong></div>'
        )
    if d.get("代表院校举例"):
        sch = d["代表院校举例"]
        if isinstance(sch, list):
            sch = " / ".join(sch)
        cal_parts.append(
            f'<div class="calib-examples">代表院校:{esc(sch)}</div>'
        )
    cal_html = (
        f'<div class="calibration">{"".join(cal_parts)}</div>' if cal_parts else ""
    )

    return f'<div class="dual-estimate">{boxes}</div>{cal_html}'


def render_subject_profile(s: dict) -> str:
    if not s:
        return ""
    cells = []
    for sub in s.get("科目分数", []):
        is_strong = "🔥" in sub.get("档", "") or "强" in sub.get("档", "")
        cls = "subject-cell is-strong" if is_strong else "subject-cell"
        score = sub.get("分数", "—")
        full = sub.get("满分", "—")
        cells.append(
            f'<div class="{cls}">'
            f'<div class="subj-name">{esc(sub.get("科目", ""))}</div>'
            f'<div class="subj-score">{esc(score)}</div>'
            f'<div class="subj-frac">/{esc(full)} · {esc(sub.get("百分比", ""))}</div>'
            f'<div class="subj-tag">{esc(sub.get("档", ""))}</div>'
            f"</div>"
        )
    grid = f'<div class="subject-grid">{"".join(cells)}</div>'

    total = ""
    if s.get("总分") is not None:
        total = (
            f'<div class="est-meta" style="text-align:right;margin-top:4px;">'
            f'总分 <strong>{esc(s["总分"])}</strong></div>'
        )

    obs = ""
    if s.get("关键观察"):
        items = "".join(f"<li>{esc(o)}</li>" for o in s["关键观察"])
        obs = f'<ul class="observations">{items}</ul>'

    return grid + total + obs


def render_directions(directions: list) -> str:
    if not directions:
        return ""
    cards = []
    for d in directions:
        priority = d.get("适配星级", 3)
        stars = "★" * priority + "☆" * (5 - priority)
        rows = []
        for sch in d.get("代表院校", []):
            majors = sch.get("推荐专业", [])
            majors_html = ""
            if majors:
                tags = "".join(
                    f'<span class="major-tag">{esc(m)}</span>' for m in majors
                )
                majors_html = f'<div class="sch-majors">{tags}</div>'
            rows.append(
                f'<div class="school-row">'
                f'<span class="sch-name">{esc(sch.get("院校", ""))}</span>'
                f'<span class="sch-fit">{esc(sch.get("适配度", ""))}</span>'
                f'<span class="sch-reason">{esc(sch.get("理由", ""))}</span>'
                f"{majors_html}"
                f"</div>"
            )
        schools_html = (
            f'<div class="school-list">{"".join(rows)}</div>' if rows else ""
        )
        cards.append(
            f'<div class="direction-card priority-{priority}">'
            f'<div class="dir-meta">'
            f'<span class="dir-stars">{stars}</span>'
            f'<span>适配星级 {priority} / 5</span>'
            f"</div>"
            f'<div class="dir-title">{esc(d.get("方向", ""))}</div>'
            f'<div class="dir-reason">{esc(d.get("适配理由", ""))}</div>'
            f"{schools_html}"
            f"</div>"
        )
    return "".join(cards)


def render_avoids(avoids: list) -> str:
    if not avoids:
        return ""
    return "".join(
        f'<div class="avoid-card">'
        f'<div class="av-direction">{esc(a.get("方向", ""))}</div>'
        f'<div class="av-reason">{esc(a.get("不推理由", ""))}</div>'
        f"</div>"
        for a in avoids
    )


def render_intent_check(intent: dict) -> str:
    if not intent:
        return ""
    parts = []
    if intent.get("意向"):
        parts.append(f'<div class="intent-quote">{esc(intent["意向"])}</div>')

    rows = intent.get("可达性判断", [])
    if rows:
        head = "<tr><th>意向项</th><th>判断</th><th>数据</th></tr>"
        body = "".join(
            f'<tr>'
            f'<td><strong>{esc(r.get("意向项", ""))}</strong></td>'
            f'<td class="intent-status">{esc(r.get("档", ""))}</td>'
            f'<td class="data-cell">{esc(r.get("数据", ""))}</td>'
            f"</tr>"
            for r in rows
        )
        parts.append(f'<table class="intent-table">{head}{body}</table>')

    if intent.get("冲突结论"):
        parts.append(
            f'<div class="intent-conclusion">{esc(intent["冲突结论"])}</div>'
        )
    return "".join(parts)


def render_school_vs_major(t: dict) -> str:
    if not t:
        return ""
    parts = []
    if t.get("判断"):
        parts.append(f'<div class="tradeoff-judge">判断:{esc(t["判断"])}</div>')
    if t.get("理由"):
        parts.append(f'<div class="tradeoff-reason">{esc(t["理由"])}</div>')
    if t.get("举例对比"):
        items = "".join(f"<li>{esc(x)}</li>" for x in t["举例对比"])
        parts.append(f'<ul class="tradeoff-examples">{items}</ul>')
    return "".join(parts)


def render_sprint(sp: dict) -> str:
    if not sp:
        return ""
    parts = []
    if sp.get("主战场"):
        parts.append(f'<div class="sprint-main">主战场:{esc(sp["主战场"])}</div>')

    paths = sp.get("路径", [])
    if paths:
        head = (
            "<tr>"
            "<th>档</th><th>语</th><th>数</th><th>英</th><th>物</th>"
            "<th>化</th><th>生</th><th>总分</th><th>档位</th><th>代表校</th>"
            "</tr>"
        )
        rows = []
        for p in paths:
            tier = p.get("档", "")
            sub = p.get("科目分数", {})
            schools = p.get("代表校", [])
            sch_str = " / ".join(schools) if isinstance(schools, list) else str(schools)
            rows.append(
                f'<tr class="sprint-tier-{esc(tier)}">'
                f'<td class="sprint-tier">{esc(tier)}<br>'
                f'<span style="font-size:0.74rem;color:var(--ink-mute);font-weight:400;">'
                f'{esc(p.get("描述", ""))}</span></td>'
                f'<td>{esc(sub.get("语", "—"))}</td>'
                f'<td>{esc(sub.get("数", "—"))}</td>'
                f'<td>{esc(sub.get("英", "—"))}</td>'
                f'<td>{esc(sub.get("物", "—"))}</td>'
                f'<td>{esc(sub.get("化", "—"))}</td>'
                f'<td>{esc(sub.get("生", "—"))}</td>'
                f'<td class="total-cell">{esc(p.get("总分", "—"))}</td>'
                f'<td>{esc(p.get("档位", ""))}</td>'
                f'<td class="schools">{esc(sch_str)}</td>'
                f"</tr>"
            )
        parts.append(f'<table class="sprint-table">{head}{"".join(rows)}</table>')

    if sp.get("执行建议"):
        items = "".join(f"<li>{esc(a)}</li>" for a in sp["执行建议"])
        parts.append(
            f'<div class="sprint-actions">'
            f'<div class="actions-title">执行建议</div>'
            f"<ol>{items}</ol>"
            f"</div>"
        )

    return "".join(parts)


def render(data: dict, theme: str = "bloomberg") -> str:
    css = _load_theme(theme) + L1A_EXTRA_CSS

    meta = data.get("meta", {})
    profile = data.get("用户画像", {})
    dual = data.get("双口径估算", {})
    subj = data.get("学科画像", {})
    judgment = data.get("核心判断", "")
    directions = data.get("主推方向", [])
    avoids = data.get("避坑方向", [])
    intent = data.get("意向冲突", {})
    tradeoff = data.get("好校弱专业_vs_弱校强专业", {})
    sprint = data.get("高三冲刺空间", {})
    discuss = data.get("必聊", [])
    next_step = data.get("下次再来", "")
    disclaimer = data.get(
        "免责声明",
        "出分前的方向性建议精度 ±2000 名,可能跨档,不要过度依赖;实际填报请结合招生章程和省级招办公布的一分一段表。",
    )

    prov = meta.get("省份", "")
    title = f"{prov}志愿规划 · 出分前方向性建议"
    gen_time = meta.get("生成时间", dt.datetime.now().strftime("%Y-%m-%d %H:%M"))

    eyebrow_parts = [
        "AI 志愿规划报告 · L1-A 出分前",
    ]
    if meta.get("数据版本"):
        eyebrow_parts.append(f"数据 {meta['数据版本']}")
    eyebrow_parts.append(gen_time.split(" ")[0] if " " in gen_time else gen_time)

    deck_parts = []
    if profile.get("学校层次"):
        deck_parts.append(profile["学校层次"])
    if profile.get("科类"):
        deck_parts.append(profile["科类"])
    if dual.get("最终定位"):
        deck_parts.append(f"定位:{dual['最终定位']}")
    deck = " · ".join(esc(x) for x in deck_parts)

    sections = []

    sections.append(
        f'<section><div class="l1a-banner">出分前 · 方向性建议</div>'
        f'{render_profile(profile)}</section>'
    )

    if dual:
        sections.append(
            f'<section><h2>双口径估算</h2>{render_dual_estimate(dual)}</section>'
        )

    if subj:
        sections.append(
            f'<section><h2>学科画像</h2>{render_subject_profile(subj)}</section>'
        )

    if judgment:
        sections.append(
            f'<section><h2>核心判断</h2>'
            f'<div class="judgment">{esc(judgment)}</div></section>'
        )

    if intent:
        sections.append(
            f'<section><h2>意向 Reality Check</h2>{render_intent_check(intent)}</section>'
        )

    if directions:
        sections.append(
            f'<section><h2>主推方向<span class="count">{len(directions)} 个</span></h2>'
            f'{render_directions(directions)}</section>'
        )

    if tradeoff:
        sections.append(
            f'<section><h2>好校弱专业 vs 弱校强专业</h2>{render_school_vs_major(tradeoff)}</section>'
        )

    if avoids:
        sections.append(
            f'<section><h2>明确避坑<span class="count">{len(avoids)} 项</span></h2>'
            f'{render_avoids(avoids)}</section>'
        )

    if sprint:
        sections.append(
            f'<section><h2>高三冲刺空间</h2>{render_sprint(sprint)}</section>'
        )

    if discuss:
        items = "".join(f"<li>{esc(d)}</li>" for d in discuss)
        sections.append(
            f'<section><h2>必须跟父母 / 自己聊的事</h2>'
            f'<ul class="discuss-list">{items}</ul></section>'
        )

    if next_step:
        sections.append(
            f'<section><div class="next-step">'
            f'<div class="next-label">下次再来</div>'
            f'{esc(next_step)}'
            f"</div></section>"
        )

    eyebrow_html = "".join(f"<span>{esc(p)}</span>" for p in eyebrow_parts)
    body = (
        f'<header>'
        f'<div class="eyebrow">{eyebrow_html}</div>'
        f'<h1>{esc(title)}</h1>'
        f'<div class="deck">{deck}</div>'
        f'</header>'
        + "".join(sections)
        + f'<footer>'
        f'<p>{esc(disclaimer)}</p>'
        f'<p>AI 志愿规划师 · 仅供参考 · 不构成填报承诺 · 出分前精度 ±2000 名</p>'
        f'</footer>'
    )

    return (
        f'<!DOCTYPE html>\n'
        f'<html lang="zh-CN" data-theme="{esc(theme)}" data-mode="l1a"><head>'
        f'<meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>{esc(title)}</title>'
        f'<style>{css}</style>'
        f'</head><body>{body}</body></html>'
    )


def main() -> int:
    p = argparse.ArgumentParser(
        description="L1-A 出分前 JSON → HTML 方向性建议报告渲染"
    )
    p.add_argument("--json", help="输入 JSON 文件路径(不传则从 stdin 读)")
    p.add_argument("--output", "-o", required=True, help="输出 HTML 文件路径")
    p.add_argument(
        "--theme",
        default="bloomberg",
        help="主题 CSS:bloomberg(默认)/ editorial / stripe / spotify",
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
    print(f"✓ 已生成出分前方向性建议报告:{out_path}")
    print(f"  双击打开:open {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
