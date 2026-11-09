#!/usr/bin/env python3
"""scripts/oneoff/commit_messages.tsv 대로 과거 커밋 메시지를 일괄 변경한다 (작업 트리·작성자·날짜는 그대로).

  python scripts/oneoff/rewrite_commit_messages.py --check      # 표의 해시가 현재 main 히스토리와 맞는지만 확인
  python scripts/oneoff/rewrite_commit_messages.py              # 적용 (git filter-repo 필요: pip install git-filter-repo)
  git push --force-with-lease origin main                # 적용 뒤, main 보호 규칙은 잠시 해제

표 형식(탭 구분): hash  new_subject  body_prefix
 - new_subject: 새 제목 한 줄
 - body_prefix: 제목에서 뺀 원인·상세(선택). 기존 본문 앞에 한 문단으로 붙는다.
기존 본문(Co-Authored-By 등 꼬리말 포함)은 보존한다.
"""

import argparse
import csv
import subprocess
import sys
from pathlib import Path

TSV = Path(__file__).with_name("commit_messages.tsv")


def load():
    rows = {}
    with TSV.open(encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            rows[r["hash"]] = (r["new_subject"].strip(), (r.get("body_prefix") or "").strip())
    return rows


def full_hashes():
    out = subprocess.check_output(["git", "rev-list", "--reverse", "HEAD"], text=True).split()
    return {h[:7]: h for h in out}, out


def check(rows):
    short, all_full = full_hashes()
    missing = [h for h in rows if h not in short]
    unmapped = [h[:7] for h in all_full if h[:7] not in rows]
    if missing:
        print("히스토리에 없는 해시:", ", ".join(missing))
    if unmapped:
        print("표에 없는 커밋:", ", ".join(unmapped))
    if not missing and not unmapped:
        print(f"OK — {len(rows)}개 커밋 모두 대응")
    return not missing and not unmapped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    rows = load()
    if not check(rows):
        sys.exit(1)
    if args.check:
        return
    try:
        import git_filter_repo as fr
    except ImportError:
        sys.exit("pip install git-filter-repo 후 다시 실행")

    short, _ = full_hashes()
    full_map = {short[h].encode(): v for h, v in rows.items()}

    def callback(commit, metadata):
        entry = full_map.get(commit.original_id)
        if entry is None:
            return
        subject, prefix = entry
        old = commit.message.decode("utf-8")
        body = old.split("\n", 1)[1].lstrip("\n") if "\n" in old else ""
        parts = [subject, ""]
        if prefix:
            parts += [prefix, ""]
        if body.strip():
            parts.append(body.rstrip("\n"))
        commit.message = ("\n".join(parts).rstrip("\n") + "\n").encode("utf-8")

    opts = fr.FilteringOptions.parse_args(["--force"])
    fr.RepoFilter(opts, commit_callback=callback).run()
    print("완료. git log --oneline 으로 확인한 뒤: git push --force-with-lease origin main")


if __name__ == "__main__":
    main()
