#!/usr/bin/env python3
"""
修复 13 个 zhiyuan SKILL.md 里的悬空引用：
  references/00_核心方法论/低分场景分流.md 待写
→ skill/_shared/references/00_核心方法论/低分场景分流.md

幂等：已修复的文件跳过。
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = ROOT / "skill"

OLD = "references/00_核心方法论/低分场景分流.md` 待写)"
NEW = "skill/_shared/references/00_核心方法论/低分场景分流.md`)"


def patch(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    if OLD not in text:
        return False
    path.write_text(text.replace(OLD, NEW), encoding="utf-8")
    return True


def main():
    patched = 0
    for skill_dir in sorted(SKILL_DIR.glob("*-zhiyuan")):
        if skill_dir.name == "gaokao-zhiyuan":
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue
        if patch(skill_md):
            print(f"  ✓ {skill_dir.name}")
            patched += 1
    print(f"\n完成：{patched} 个文件已修复")


if __name__ == "__main__":
    main()
