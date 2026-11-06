"""`.github/labels.json`의 라벨을 GitHub 저장소에 맞춘다(gh CLI 필요).

    python .github/sync_labels.py [--repo z1-won/ncs-web-test] [--dry-run]

- 같은 이름이 있으면 색·설명을 고친다.
- `from`에 적힌 옛 이름이 있으면 새 이름으로 바꾼다(이슈에 붙은 라벨이 유지된다).
- 둘 다 없으면 새로 만든다. 목록에 없는 라벨은 지우지 않는다.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

LABELS = Path(__file__).with_name("labels.json")


def gh(*args: str, dry_run: bool = False) -> str:
    if dry_run:
        print("gh", *args)
        return ""
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True, encoding="utf-8").stdout


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows 콘솔(cp949)에서 이모지 출력
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="z1-won/ncs-web-test")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    existing = {item["name"] for item in json.loads(gh("label", "list", "-R", args.repo, "--limit", "200", "--json", "name"))}
    for label in json.loads(LABELS.read_text(encoding="utf-8")):
        name, old = label["name"], label.get("from")
        style = ["--color", label["color"], "--description", label["description"]]
        if name in existing:
            gh("label", "edit", name, "-R", args.repo, *style, dry_run=args.dry_run)
            print(f"수정: {name}")
        elif old in existing:
            gh("label", "edit", old, "-R", args.repo, "--name", name, *style, dry_run=args.dry_run)
            existing.discard(old)
            print(f"이름 변경: {old} → {name}")
        else:
            gh("label", "create", name, "-R", args.repo, *style, dry_run=args.dry_run)
            print(f"생성: {name}")
        existing.add(name)


if __name__ == "__main__":
    main()
