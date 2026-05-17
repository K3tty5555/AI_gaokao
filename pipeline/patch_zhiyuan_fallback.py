#!/usr/bin/env python3
"""
为所有 31 个 {prov}-zhiyuan/SKILL.md 在"步骤 1:召回候选"后插入
query_school 零结果回退指引。

幂等：已插入过的文件不重复插入。
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = ROOT / "skill"

ANCHOR = "### 步骤 2:"

FALLBACK_BLOCK = """\
**query_school 返回 0 结果时，按顺序处理：**

1. **检查参数**：确认 `--rank`/`--score` 数值正确；3+1+2 的 `--combo` 是否填对
2. **去掉 combo 重试**（仅 3+1+2）：去掉 `--combo` 召回"不限选科"院校，输出卡片里标注"⚠ 选科要求需考生自行核对"
3. **扩大范围**：加 `--top 50` 扩大位次窗口
4. **仍为空 → 明确告知**：说明"当前位次段暂无历史数据（首届招生 / 新增专业 / 数据缺失）"，给出方向性建议（参考 ±5000 位次内院校，或查省招考院官网），**不得捏造数据**

"""

def patch(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    if "query_school 返回 0 结果" in text:
        return False  # 已插入，跳过
    idx = text.find(ANCHOR)
    if idx == -1:
        print(f"  ⚠ 未找到锚点: {path.name}")
        return False
    new_text = text[:idx] + FALLBACK_BLOCK + text[idx:]
    path.write_text(new_text, encoding="utf-8")
    return True


def main():
    patched = 0
    skipped = 0
    for skill_dir in sorted(SKILL_DIR.glob("*-zhiyuan")):
        if skill_dir.name == "gaokao-zhiyuan":
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue
        if patch(skill_md):
            print(f"  ✓ {skill_dir.name}")
            patched += 1
        else:
            skipped += 1
    print(f"\n完成：{patched} 个已更新，{skipped} 个跳过（已有或无锚点）")


if __name__ == "__main__":
    main()
