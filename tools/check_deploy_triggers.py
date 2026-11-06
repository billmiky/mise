#!/usr/bin/env python3
"""Check that every workflow that pushes to main also triggers the Pages deploy.

Pushes made with GITHUB_TOKEN don't start other workflows, so deploy.yml lists those
workflows under `on.workflow_run` instead. This fails if one is missing (or listed
under a name that doesn't exist), so a new workflow can't silently stop deploying.

Run: python3 tools/check_deploy_triggers.py
"""
import re
import sys
from pathlib import Path

import yaml

WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"
# A push to main: git-auto-commit-action (pushes the checked-out branch, main for these
# dispatch-only workflows) or an explicit `git push ... main`.
PUSHES_MAIN = re.compile(r"git-auto-commit-action|git push\b[^\n]*\bmain\b")


def load(path):
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    # PyYAML reads the bare key `on` as True
    return data, data.get("on", data.get(True)) or {}


def main():
    deploy, deploy_on = load(WORKFLOWS / "deploy.yml")
    listed = set((deploy_on.get("workflow_run") or {}).get("workflows") or [])

    names, pushers = set(), set()
    for path in sorted(WORKFLOWS.glob("*.yml")):
        if path.name == "deploy.yml":
            continue
        data, _ = load(path)
        names.add(data["name"])
        if PUSHES_MAIN.search(path.read_text(encoding="utf-8")):
            pushers.add(data["name"])

    errors = []
    for name in sorted(pushers - listed):
        errors.append(f"'{name}' pushes to main but isn't in deploy.yml's workflow_run list, so its changes won't deploy")
    for name in sorted(listed - names):
        errors.append(f"deploy.yml's workflow_run list names '{name}', but no workflow has that name")
    for e in errors:
        print("ERROR", e)
    print(f"{len(pushers)} workflows push to main; {len(listed)} listed in deploy.yml")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
