#!/usr/bin/env python3
"""管理 demo agent 的 skills 注册表。

用法:
  python src/demo/manage_skills.py list
  python src/demo/manage_skills.py enable <skill_name>
  python src/demo/manage_skills.py disable <skill_name>
  python src/demo/manage_skills.py install <skill_name> <module> <tool>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REGISTRY_PATH = Path(__file__).resolve().parent / "skills" / "registry.json"


def load_registry() -> dict:
    if not REGISTRY_PATH.exists():
        return {"skills": {}}
    with REGISTRY_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_registry(reg: dict) -> None:
    with REGISTRY_PATH.open("w", encoding="utf-8") as f:
        json.dump(reg, f, ensure_ascii=False, indent=2)
        f.write("\n")


def cmd_list() -> int:
    reg = load_registry()
    skills = reg.get("skills", {})
    if not skills:
        print("当前没有已注册 skills。")
        return 0
    print("已注册 skills:")
    for name, meta in skills.items():
        status = "enabled" if meta.get("enabled") else "disabled"
        print(f"- {name}: {status} | {meta.get('module')}:{meta.get('tool')}")
    return 0


def cmd_enable(name: str, enable: bool) -> int:
    reg = load_registry()
    skills = reg.setdefault("skills", {})
    if name not in skills:
        print(f"skill 不存在: {name}")
        return 1
    skills[name]["enabled"] = enable
    save_registry(reg)
    print(f"{'启用' if enable else '禁用'}成功: {name}")
    return 0


def cmd_install(name: str, module: str, tool: str) -> int:
    reg = load_registry()
    skills = reg.setdefault("skills", {})
    if name in skills:
        print(f"skill 已存在: {name}")
        return 1
    skills[name] = {
        "module": module,
        "tool": tool,
        "enabled": True,
        "description": "",
    }
    save_registry(reg)
    print(f"安装成功: {name} -> {module}:{tool}")
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    cmd = sys.argv[1]
    if cmd == "list":
        return cmd_list()
    if cmd == "enable" and len(sys.argv) == 3:
        return cmd_enable(sys.argv[2], True)
    if cmd == "disable" and len(sys.argv) == 3:
        return cmd_enable(sys.argv[2], False)
    if cmd == "install" and len(sys.argv) == 5:
        return cmd_install(sys.argv[2], sys.argv[3], sys.argv[4])

    print("参数错误。")
    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
