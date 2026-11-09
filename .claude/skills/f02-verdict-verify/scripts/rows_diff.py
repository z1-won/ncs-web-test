"""엔진 결과 폴더 두 개(수정 전·후)의 체크리스트 행을 대조한다 — 확인서 판정은 같아도 그 안의 체크가 바뀐 것을 본다.

  python .claude/skills/f02-verdict-verify/scripts/rows_diff.py --before _workspace/rows_before --after _workspace/rows_after [--remarks]

입력은 엔진 CLI(`ncs-toc 원고 [계획서] --out 폴더`)가 쓴 결과 폴더다. 폴더 아래 어디에 있든 `*_전체.json`을 찾아
파일 이름(모듈 코드_구성요소)으로 짝짓고, 행은 (item_id, region_path, 같은 키 안의 순번)으로 짝짓는다.

verdict_diff.py는 확인서 항목 단위(배치 결과)만 본다. 한 항목은 여러 행·여러 체크를 접은 것이라, 부적합 3건이 1건으로
줄거나 다른 체크가 O→X로 바뀌어도 항목 판정이 그대로면 거기서는 보이지 않는다. 이 스크립트가 그 틈을 메운다.

--remarks 를 주면 비고만 바뀐 행도 적는다(비고에는 원고 문구가 있으므로 내부 확인용).
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


def load(folder: Path) -> dict[str, dict[tuple, dict]]:
    """{파일 이름: {(item_id, region_path, 순번): 행}}"""
    out: dict[str, dict[tuple, dict]] = {}
    for file in sorted(folder.rglob("*_전체.json")):
        rows = json.loads(file.read_text("utf-8"))
        seen: Counter = Counter()
        keyed = {}
        for row in rows:
            base = (row.get("item_id", ""), row.get("region_path", ""))
            keyed[(*base, seen[base])] = row
            seen[base] += 1
        if file.name in out:
            raise SystemExit(f"같은 이름의 결과가 둘 있습니다(폴더에 실행이 하나씩만 있어야 함): {file.name}")
        out[file.name] = keyed
    return out


def diff(before: dict, after: dict, remarks: bool) -> tuple[list[dict], list[str]]:
    changes, notes = [], []
    for name in sorted(set(before) | set(after)):
        if name not in before or name not in after:
            notes.append(f"{name}: {'이전' if name in before else '이후'}에만 있음")
            continue
        old_rows, new_rows = before[name], after[name]
        for key in sorted(set(old_rows) | set(new_rows), key=str):
            old, new = old_rows.get(key), new_rows.get(key)
            where = f"{key[0]} @ {key[1]}" + (f" #{key[2] + 1}" if key[2] else "")
            if old is None or new is None:
                row = old or new
                changes.append({"결과": name, "행": where, "체크": "(행 전체)", "이전": row["판정"] if old else "없음",
                                "이후": row["판정"] if new else "없음"})
                continue
            checks = defaultdict(lambda: ["없음", "없음"])
            for label, value in (old.get("체크") or {}).items():
                checks[label][0] = value
            for label, value in (new.get("체크") or {}).items():
                checks[label][1] = value
            changed = False
            for label, (a, b) in checks.items():
                if a != b:
                    changed = True
                    changes.append({"결과": name, "행": where, "체크": label, "이전": a, "이후": b})
            if old.get("판정") != new.get("판정"):
                changes.append({"결과": name, "행": where, "체크": "(행 판정)", "이전": old.get("판정"), "이후": new.get("판정")})
            elif remarks and not changed and old.get("비고") != new.get("비고"):
                changes.append({"결과": name, "행": where, "체크": "(비고만)", "이전": json.dumps(old.get("비고"), ensure_ascii=False)[:120],
                                "이후": json.dumps(new.get("비고"), ensure_ascii=False)[:120]})
    return changes, notes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--before", required=True, help="수정 전 코드로 돌린 엔진 결과 폴더")
    parser.add_argument("--after", required=True, help="수정 후 코드로 돌린 엔진 결과 폴더")
    parser.add_argument("--remarks", action="store_true", help="비고만 바뀐 행도 적는다(원고 문구 포함 — 내부 확인용)")
    parser.add_argument("--out", help="마크다운 출력 경로(없으면 표준 출력)")
    args = parser.parse_args()
    before, after = load(Path(args.before)), load(Path(args.after))
    changes, notes = diff(before, after, args.remarks)
    lines = ["# 체크 행 변화", "", f"- 대조한 결과 파일 {len(set(before) & set(after))}개, **변화 {len(changes)}건**"]
    lines += [f"- {note}" for note in notes]
    lines.append("")
    if changes:
        cols = ["결과", "행", "체크", "이전", "이후"]
        lines += ["| " + " | ".join(cols) + " |", "|" + " ---- |" * len(cols)]
        lines += ["| " + " | ".join(str(c[k]).replace("|", "¦").replace("\n", " ") for k in cols) + " |" for c in changes]
    else:
        lines.append("(체크 행 변화 없음)")
    text = "\n".join(lines) + "\n"
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text, "utf-8")
        print(f"저장: {args.out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
