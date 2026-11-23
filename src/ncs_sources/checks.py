"""출처 하나(그림·표·본문 출처 줄)에 대한 규칙 점검. 결과는 엔진 체크리스트 행과 같은 모양({체크: O·X·△·-}, 비고, 수정 제안).

점검 이름(화면·메모에 그대로 보임)
  출처 있음                 그림은 필수, 표는 직접 만든 것이면 생략 가능('-')
  출처 형식(F14)            필요 지식 ⑧과 같은 함수(source_check)
  출처 요건(계약서 제4조)   출처 종류별 필수 요소: 저작자명·URL·확인 일자·쪽·사용 요건
  기관 명칭                 옛 명칭 '한국직업능력개발원'
  AI 표기 형식              '○○를 활용하여 생성함/수정 보완함. YYYY. M. D.' — 도구·동사·일자
  AI 표기 순서              출처 줄 → AI 활용 줄 → 그림 번호·제목(그림만)
  AI 표기 위치              AI 활용을 출처 줄 안에 섞어 쓰지 않았나
  생성·수정 구분            '생성함'·'수정 보완함'이 출처 줄과 맞나(규칙으로 볼 수 있는 만큼 — 실제 활용 유형은 LLM·서약서)
"""

from __future__ import annotations

import re

from ncs_core.source_line import (DATE, ELEMENT_NAMES, OLD_AGENCY, REQUIRED_ELEMENTS, ai_date_is_real, ai_in_source_line,
                                  ai_type_candidates, has_element, source_check)
from ncs_core.text import NA, O, TRI, X

REQUIRED = REQUIRED_ELEMENTS     # 제4조 요건 — ncs_core.source_line 한 곳(그림 검수와 같음)
ELEMENT = ELEMENT_NAMES
THIRD_PARTY = {"기존 학습모듈", "공공누리", "웹·검색", "스크린숏", "문헌"}
AI_DATE = re.compile(rf"^{DATE}$")


_has = has_element


def check_entry(entry: dict) -> tuple[dict, dict, list[str]]:
    """(체크, 비고, 수정 제안 목록)."""
    checks: dict[str, str] = {}
    notes: dict[str, str] = {}
    fixes: list[str] = []
    kind, source, line = entry["kind"], entry.get("source"), entry.get("source_line")

    # 출처 있음
    if line is None:
        if kind == "그림":
            checks["출처 있음"] = X
            notes["출처 있음"] = "그림 바로 위에 '출처:' 줄이 없음 — 집필진 제작도 '출처: 집필진 제작(연도)' 필수"
            fixes.append("캡션 위에 '출처: 집필진 제작(연도)' 또는 인용 문헌 출처 추가")
        else:
            checks["출처 있음"] = NA
            notes["출처 있음"] = "표 아래 출처 없음 — 직접 작성한 표면 생략 가능, 인용한 표면 필수"
        _ai_checks(entry, checks, notes, fixes)
        return checks, notes, fixes
    checks["출처 있음"] = O

    # 형식(F14)
    value, note = source_check(line)
    checks["출처 형식(F14)"] = value
    notes["출처 형식(F14)"] = note if value != O else f"템플릿: {note}"
    if value != O:
        fixes.append("F14 출처 형식으로 수정(저자(연도). 제목. 발행처. p.00. / 집필진 제작(연도) / 웹: 기관(URL)에서 YYYY. M. D. 검색.)")

    # 요건(제4조 3·4항)
    needed = REQUIRED.get(source.kind)
    if needed:
        missing = [ELEMENT[e] for e in needed if not _has(source, e)]
        if missing:
            checks["출처 요건(계약서 제4조)"] = X
            notes["출처 요건(계약서 제4조)"] = f"{source.kind} 출처에 {', '.join(missing)}이(가) 없음"
            fixes.append(f"출처에 {', '.join(missing)} 추가")
        else:
            checks["출처 요건(계약서 제4조)"] = O
            notes["출처 요건(계약서 제4조)"] = f"{source.kind}: " + ", ".join(ELEMENT[e] for e in needed) + " 있음"
    else:
        checks["출처 요건(계약서 제4조)"] = NA
        notes["출처 요건(계약서 제4조)"] = f"{source.kind} — 따로 요구하는 요소 없음" if source.kind != "알 수 없음" else "출처 종류를 읽지 못함"

    # 기관 명칭
    if OLD_AGENCY.search(line):
        checks["기관 명칭"] = TRI
        notes["기관 명칭"] = "'한국직업능력개발원' → 현재 명칭 '한국직업능력연구원'인지 확인"
    _ai_checks(entry, checks, notes, fixes)
    return checks, notes, fixes


def _ai_checks(entry: dict, checks: dict, notes: dict, fixes: list[str]) -> None:
    source, marker, line = entry.get("source"), entry.get("ai"), entry.get("source_line") or ""
    body = re.sub(r"^출\s*처\s*[:：]\s*", "", line)
    if marker is None:
        mixed = ai_in_source_line(body) if line else None
        if mixed == "strong":
            checks["AI 표기 위치"] = X
            notes["AI 표기 위치"] = "출처 줄 안에 AI 활용이 섞여 있음 — 출처 줄 다음에 AI 활용 줄을 따로 적어야 함"
            fixes.append("출처 줄 다음 줄에 '○○를 활용하여 생성함(또는 수정 보완함). YYYY. M. D.'")
        elif mixed == "weak":     # '생성'·'도식화' 같은 낱말뿐 — 문헌 제목일 수 있어 확정하지 않는다(필요 지식 ⑧과 같은 기준)
            checks["AI 표기 위치"] = TRI
            notes["AI 표기 위치"] = "출처 줄에 AI 활용으로 읽힐 수 있는 낱말이 있음 — AI를 활용한 것이면 출처 줄 다음에 AI 활용 줄을 따로 적어야 함. 확인"
        return
    # 형식
    missing = [name for name, value in (("도구 이름", marker.tool), ("'생성함/수정 보완함'", marker.action), ("일자", marker.date)) if not value]
    if not missing and marker.date and not AI_DATE.match(marker.date.replace(" ", "")):
        missing.append("일자 꼴(YYYY. M. D.)")
    if missing:
        checks["AI 표기 형식"] = X
        notes["AI 표기 형식"] = f"「{marker.raw[:60]}」에 {', '.join(missing)}이(가) 없거나 틀림"
        fixes.append("'○○를 활용하여 생성함(또는 수정 보완함). YYYY. M. D.' 꼴로")
    elif ai_date_is_real(marker) is False:      # 일자는 요건이다(REQ-02-008 ②) — 달력에 없는 날은 일자가 아니다. 필요 지식 ⑧과 같은 기준
        checks["AI 표기 형식"] = X
        notes["AI 표기 형식"] = f"「{marker.raw[:60]}」의 일자 {marker.date}는 달력에 없는 날짜임"
        fixes.append("AI를 활용한 실제 일자로 고침(YYYY. M. D.)")
    else:
        checks["AI 표기 형식"] = O
        notes["AI 표기 형식"] = f"{marker.tool}를 활용하여 {marker.action}함. {marker.date}"
    # 순서(그림): 출처 줄 → AI 활용 줄 → 캡션
    if entry["kind"] == "그림":
        s, a, c = entry.get("source_para"), entry.get("ai_para"), entry.get("caption_para")
        if s is None:
            checks["AI 표기 순서"] = X
            notes["AI 표기 순서"] = "출처 줄이 없음 — 출처 줄(집필진 제작(연도) 또는 원 출처) → AI 활용 줄 → 그림 번호·제목"
        elif not (s < a <= c):
            checks["AI 표기 순서"] = X
            notes["AI 표기 순서"] = "순서가 양식과 다름 — 출처 줄 → AI 활용 줄 → 그림 번호·제목"
            fixes.append("출처 줄 → AI 활용 줄 → 그림 번호·제목 순서로")
        else:
            checks["AI 표기 순서"] = O
    # 생성·수정 구분 — 출처 줄과의 짝으로 볼 수 있는 것만
    kind = source.kind if source else None
    candidates = ai_type_candidates(source, marker)
    if marker.action == "생성" and kind in THIRD_PARTY:
        checks["생성·수정 구분"] = TRI
        notes["생성·수정 구분"] = (f"원 출처({kind})가 있는데 '생성함' — 남의 자료를 AI로 고쳤다면 '수정 보완함'(표기 예 3·5), "
                               "원 출처를 참고해 새로 만들었다면 출처를 '집필진 제작'으로 두는지 확인")
    elif marker.action == "수정 보완" and source is None:
        checks["생성·수정 구분"] = TRI
        notes["생성·수정 구분"] = "'수정 보완함'인데 무엇을 고쳤는지(원 출처 줄)가 없음"
    else:
        checks["생성·수정 구분"] = O
        notes["생성·수정 구분"] = (f"출처({kind or '없음'}) + '{marker.action}함' → 표기 예 후보 {', '.join(map(str, candidates))}"
                               " — 실제 활용 유형과 맞는지는 서약서 현황·그림 확인 필요")
