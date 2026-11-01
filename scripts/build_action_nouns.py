"""운용 전에 행동명사 목록(src/ncs_core/data/action_nouns.txt)을 미리 채운다.

검수 중에도 처음 보는 단어는 같은 조회(ncs_core.lexicon)가 자동으로 일어나지만, 운용 전에 후보를 한꺼번에
확인해 두면 검수 중 조회는 예외가 된다. 판정·기록 방식은 검수 때와 완전히 같다(같은 코드).

사용 (저장소 루트, .env의 STDICT_API_KEY 필요):
  set -a; source .env; set +a
  python scripts/build_action_nouns.py 분석 설계 구현            # 단어 직접
  python scripts/build_action_nouns.py --from-file scripts/action_noun_candidates.txt
  python scripts/build_action_nouns.py --from-plans 개발계획서폴더   # 개발계획서들의 학습 내용명 머리어(이 사업의 어휘)
  python scripts/build_action_nouns.py --from-manuscripts 원고폴더  # 원고 차례의 학습 내용명 머리어
  python scripts/build_action_nouns.py --from-manuscripts a.hwpx b.hwpx  # 파일을 직접 골라서(폴더·파일 섞어도 됨)
결과: 행동명사 → action_nouns.txt(stdict), 아님 → action_nouns_rejected.txt(stdict, X). 둘 다 git으로 관리한다.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))  # 설치 없이도 저장소에서 바로 실행할 수 있게

from ncs_core import load_document  # noqa: E402
from ncs_core.lexicon import ActionNounLexicon, stdict_resolver  # noqa: E402
from ncs_core.manuscript import parse_plan_toc, parse_toc  # noqa: E402
from ncs_core.module_code import resolve_module_code  # noqa: E402
from ncs_toc.rules.action_nouns import head_word  # noqa: E402


def heads_from_plans(folder: Path) -> set[str]:
    """개발계획서들의 모듈 블록에서 학습 내용명 머리어. 블록은 코드별이라 파일명에서 코드를 읽는다."""
    words = set()
    for path in sorted(list(folder.glob("*.hwp")) + list(folder.glob("*.hwpx"))):
        try:
            document = load_document(path)
            code = resolve_module_code(path, "")
        except ValueError as error:
            print(f"  건너뜀 {path.name}: {error}", file=sys.stderr)
            continue
        plan = parse_plan_toc(document.sections, code)
        if plan:
            words |= {head_word(item["text"]) for item in plan["내용명"]}
    return words


def _hwp_files(paths: list[Path]) -> list[Path]:
    """폴더면 바로 아래 .hwp/.hwpx, 파일이면 그대로."""
    out: list[Path] = []
    for path in paths:
        out += sorted(list(path.glob("*.hwp")) + list(path.glob("*.hwpx"))) if path.is_dir() else [path]
    return out


def heads_from_manuscripts(paths: list[Path]) -> set[str]:
    words = set()
    for path in _hwp_files(paths):
        print(f"  읽음 {path.name}", file=sys.stderr)
        try:
            document = load_document(path)
        except ValueError as error:
            print(f"  건너뜀 {path.name}: {error}", file=sys.stderr)
            continue
        toc = parse_toc([document.sections[0], document.sections[1] if len(document.sections) > 1 else []])
        if toc:
            words |= {head_word(item["text"]) for item in toc["내용"]}
    return words


def main() -> None:
    parser = argparse.ArgumentParser(description="행동명사 목록을 운용 전에 채운다")
    parser.add_argument("words", nargs="*")
    parser.add_argument("--from-file", type=Path, help="한 줄 한 단어")
    parser.add_argument("--from-plans", type=Path, help="개발계획서(.hwp/.hwpx) 폴더")
    parser.add_argument("--from-manuscripts", type=Path, nargs="+", help="원고(.hwp/.hwpx) 폴더 또는 파일들")
    parser.add_argument("--lexicon-dir", type=Path, help="목록 파일 위치(기본: src/ncs_core/data)")
    args = parser.parse_args()

    key = os.getenv("STDICT_API_KEY")
    if not key:
        parser.exit(2, "STDICT_API_KEY 환경 변수가 필요합니다 (.env에 넣고 set -a; source .env; set +a)\n")
    candidates = {w.strip() for w in args.words if w.strip()}
    if args.from_file:
        candidates |= {l.strip() for l in args.from_file.read_text(encoding="utf-8").splitlines()
                       if l.strip() and not l.startswith("#")}
    if args.from_plans:
        candidates |= heads_from_plans(args.from_plans)
    if args.from_manuscripts:
        candidates |= heads_from_manuscripts(args.from_manuscripts)

    lexicon = ActionNounLexicon(args.lexicon_dir or ROOT / "src" / "ncs_core" / "data", stdict_resolver(key))
    todo = sorted(w for w in candidates if w and w not in lexicon.accepted and w not in lexicon.rejected)
    if not todo:
        parser.exit(0, f"새로 조회할 단어가 없습니다 (후보 {len(candidates)}개 모두 기록됨)\n")
    results = {"O": [], "X": [], "△": []}
    for word in todo:
        value, note = lexicon.judge(word)
        results[value].append((word, note or ""))
    print(f"조회 {len(todo)}단어")
    if results["O"]:
        print(f"\n행동명사 → action_nouns.txt에 추가 {len(results['O'])}: " + " ".join(w for w, _ in results["O"]))
    if results["X"]:
        print(f"\n사전에 '-하다' 없음 → action_nouns_rejected.txt에 기록 {len(results['X'])} (검수에서 X):")
        for w, note in results["X"]:
            print(f"  {w}")
        print("  → 외래어·전문용어인데 행동명사가 맞으면 rejected에서 그 줄을 지우고 action_nouns.txt에 manual로 추가")
    if results["△"]:
        print(f"\n조회 실패 {len(results['△'])} (다시 실행하면 재시도):")
        for w, note in results["△"]:
            print(f"  {w}\t{note}")
    print("\ngit diff로 두 목록 파일을 확인한 뒤 커밋하세요.")


if __name__ == "__main__":
    main()
