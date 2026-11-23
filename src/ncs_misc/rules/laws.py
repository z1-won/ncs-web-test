"""법령 현행화 후보(F02에 없는 추가 항목): 원고에 적힌 법령 이름이 현행인가 — 원고당 1행.

근거: 요구사항정의서 V0.23 REQ-02-002 사람 작업 3 '준수 점검 — … 법령 용어 현행화 후보를 확인한다', REQ-02-001 표준 지침
'법령 용어 현행화 대상 표시(매뉴얼 수록 기준, 변경은 수행준거 준용 범위·내용 전문가 판단: 준용 집필 기준 2-2)'.
F02 검수 확인서에는 이 항목이 없어 '편집'처럼 화면·결과에만 보이고 확인서 파일에는 넣지 않는다.

모두 후보(△)까지만 낸다 — 원고의 법령 이름은 학습 목표(수행준거)에서 온 것일 수 있고, 바꿀지는 내용 전문가가 판단한다. X는 없다.
  법령 현행화 후보  △  폐지, 명칭 변경, 현행 목록에 없음, 법제처 정식 명칭과 띄어쓰기만 다름(F11 참고 자료 작성 방법: 공식 명칭, 법제처 권고 띄어쓰기)
                   O  찾은 이름이 모두 현행(약칭은 참고로만)      -  법령 이름이 없음
  법령명 조회       △  법령명 표(law_names.tsv)에 없어 현행 여부를 확인하지 못한 이름이 있음, 또는 표 자체가 없음
법령 이름은 ncs_core.law_catalog.law_names_in으로 찾는다(따옴표로 묶인 이름, 표에 있는 이름, 이름 꼴이 뚜렷한 것).
"""

import re

from ncs_core import NA, O, TRI
from ncs_core.law_catalog import law_catalog, law_names_in
from ncs_core.notes import lines

from .common import row

NO = "법령"
LABEL = "법령 현행화 후보"
CHECKED = "법령명 조회"
JUDGE = "바꿀지는 수행준거 준용 범위와 내용 전문가 판단(F04 준용 집필 기준 2-2)"
MAX_SHOWN = 10


def _spacing_only(written: str, official: str) -> bool:
    words = lambda text: re.sub(r"[「」『』]", "", text or "").split()
    return bool(official) and "".join(words(written)) == "".join(words(official)) and words(written) != words(official)


def check_manuscript_laws(context, catalog="default") -> list[dict]:
    laws = law_catalog() if catalog == "default" else catalog
    names = []
    for section in context.manuscript.sections:
        for text in section:
            for name in law_names_in(text, laws):
                if name not in names:
                    names.append(name)
    if not names:
        return [row(NO, "원고", "", None, {LABEL: NA}, {LABEL: "법령 이름이 없음"})]
    shown = ", ".join(f"「{name}」" for name in names[:MAX_SHOWN])
    if laws is None:
        note = "법령명 표(law_names.tsv)가 없어 현행 여부를 확인하지 못함: " + shown
        return [row(NO, "원고", "", names, {LABEL: TRI}, {LABEL: note})]
    candidates, unknown = [], []
    for name in names:
        entry = laws.lookup(name)
        if entry is None or entry.status == "미검색":
            unknown.append(name)
        elif entry.status == "명칭변경":
            candidates.append(f"원고 「{name}」 — 현행 명칭 「{entry.current_name}」")
        elif entry.status == "폐지":
            candidates.append(f"원고 「{name}」 — 폐지({entry.revision}, 시행 {entry.effective})")
        elif entry.status == "현행목록없음":
            candidates.append(f"원고 「{name}」 — 현행 법령 목록에 없음(폐지·명칭 변경·오기 중 하나)")
        elif entry.status == "현행" and _spacing_only(name, entry.name):
            candidates.append(f"원고 「{name}」 / 법제처 정식 명칭 「{entry.name}」 — 띄어쓰기만 다름")
        elif entry.status != "현행":
            candidates.append(f"원고 「{name}」 — 연혁만 있고 현행 목록에 없음(법제처 확인)")
    checks, notes = {LABEL: TRI if candidates else O, CHECKED: TRI if unknown else O}, {}
    if candidates:
        more = [f"외 {len(candidates) - MAX_SHOWN}건"] if len(candidates) > MAX_SHOWN else []
        notes[LABEL] = lines(candidates[:MAX_SHOWN] + more) + f"\n— {JUDGE}"
    if unknown:
        more = f" 외 {len(unknown) - MAX_SHOWN}개" if len(unknown) > MAX_SHOWN else ""
        notes[CHECKED] = ("법령명 표에 없어 현행 여부를 확인하지 못함(scripts/data/build_law_names.py로 조회): "
                          + ", ".join(f"원고 「{name}」" for name in unknown[:MAX_SHOWN]) + more)
    return [row(NO, "원고", "", names, checks, notes, "현행화 대상인지 확인해 개발기관에 알림" if candidates else None)]
