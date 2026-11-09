"""법령명 표(src/ncs_core/data/law_names.tsv) 만들기 — 법제처 Open API로 현행 여부·연혁을 조회해 기록한다.

  set -a; source .env; set +a            # LAW_API_OC
  python scripts/data/build_law_names.py --from-documents 원고.hwpx 계획서.hwp …   # 문서에서 법령명을 뽑아 조회
  python scripts/data/build_law_names.py --names "화학물질관리법" "개인정보 보호법"   # 이름을 직접
  python scripts/data/build_law_names.py --probe "화학물질관리법"                     # 응답 원문 확인(첫 실행 때)
이미 표에 있는 이름은 건너뛴다(--refresh로 다시 조회). 조회 결과는 표에 바로 덧붙인다.
판정: 현행 목록에 같은 이름 → 현행 / 연혁에만 있고 제개정구분이 폐지 → 폐지 / 연혁의 법령ID로 현행 이름이 다르면 → 명칭변경 /
아무 데도 없음 → 미검색 / 연혁 서비스를 못 쓰면 → 현행목록없음(폐지·명칭 변경·오기 중 하나).
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ncs_core import load_document  # noqa: E402
from ncs_core.law_api import LawApiError, history, raw, search  # noqa: E402
from ncs_core.law_catalog import LAW_FILE, LawCatalog, extract_law_names, normalize  # noqa: E402

TABLE = ROOT / "src" / "ncs_core" / "data" / LAW_FILE
HEADER = "# 법령명 표 — 법제처 Open API(open.law.go.kr) 조회 결과. 갱신: scripts/data/build_law_names.py\n# 표기\t정식명칭\t법령ID\t시행일자\t제개정구분\t상태\t현행명칭\t조회일\n"


def judge(name: str) -> tuple[str, str, str, str, str, str]:
    """→ (정식명칭, 법령ID, 시행일자, 제개정구분, 상태, 현행명칭)"""
    key = normalize(name)
    current = [r for r in search(name) if normalize(r.name) == key or normalize(r.abbreviation) == key]
    if current:
        r = sorted(current, key=lambda x: x.effective)[-1]
        return r.name, r.law_id, r.effective, r.revision, "현행", r.name
    try:
        past = [r for r in history(name) if normalize(r.name) == key]
    except LawApiError:
        # 연혁 서비스를 못 쓰면 '현행 목록에 없음'까지만 안다(폐지·명칭 변경·오기 중 무엇인지는 사람이 확인)
        return "", "", "", "", "현행목록없음", ""
    if not past:
        return "", "", "", "", "미검색", ""
    last = sorted(past, key=lambda x: (x.promulgated, x.serial))[-1]
    if last.repealed:
        return last.name, last.law_id, last.effective, last.revision, "폐지", ""
    # 같은 법령ID의 현행 이름을 찾는다(명칭 변경)
    renamed = [r for r in search(last.name[:6]) if r.law_id == last.law_id and normalize(r.name) != key]
    if renamed:
        return last.name, last.law_id, last.effective, last.revision, "명칭변경", renamed[0].name
    return last.name, last.law_id, last.effective, last.revision, "연혁만", ""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--from-documents", nargs="*", default=[], help="법령명을 뽑을 문서(hwp/hwpx)")
    parser.add_argument("--names", nargs="*", default=[], help="직접 지정할 법령명")
    parser.add_argument("--probe", help="이 이름으로 조회한 응답 원문을 출력하고 끝낸다")
    parser.add_argument("--refresh", action="store_true", help="표에 있는 이름도 다시 조회")
    parser.add_argument("--table", default=str(TABLE))
    args = parser.parse_args()

    if args.probe:
        for target in ("law", "eflaw", "lsHistory", "lsHstInf", "lsAbrv"):
            print(f"===== target={target} query={args.probe}")
            try:
                print(raw({"target": target, "query": args.probe, "display": 5})[:3000])
            except LawApiError as error:
                print("오류:", error)
        return

    names: list[str] = list(args.names)
    for path in args.from_documents:
        document = load_document(path)
        text = "\n".join(line for section in document.sections for line in section)
        text += "\n".join(v for t in document.tables for v in t["cells"].values())
        names += [n for n, _quoted in extract_law_names(text)]
    names = list(dict.fromkeys(n.strip() for n in names if n.strip()))
    if not names:
        sys.exit("조회할 법령명이 없습니다 (--names 또는 --from-documents)")

    table = Path(args.table)
    if not table.exists():
        table.write_text(HEADER, encoding="utf-8")
    known = LawCatalog(table).entries if not args.refresh else {}
    added, today = 0, date.today().isoformat()
    with table.open("a", encoding="utf-8") as handle:
        for name in names:
            if normalize(name) in known:
                continue
            try:
                official, law_id, effective, revision, status, current = judge(name)
            except LawApiError as error:
                print(f"[오류] {name}: {error}")
                continue
            handle.write("\t".join([name, official, law_id, effective, revision, status, current, today]) + "\n")
            added += 1
            print(f"{status:4s} {name}" + (f" → {current}" if current and current != name else ""))
    print(f"{len(names)}개 중 {added}개 추가 → {table}")


if __name__ == "__main__":
    main()
