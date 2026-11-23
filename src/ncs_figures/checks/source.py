"""① 출처 표기 — 있음(그림 바로 위 '출처:' 줄) · 형식(F14 골격, 필요 지식 ⑧과 같은 함수) · 요건(원고 집필 계약서 제4조 3항).

제4조 3항: 인용한 원저작물의 저작자명과 출처(URL 주소, 자료 확인 일자, 페이지 수, 사용 요건 등)를 명시. 출처 종류마다
꼭 있어야 할 요소를 설정(FigureConfig.required_elements)으로 두고, 빠진 것을 X로 낸다. 집필진 제작은 해당 없음.
"""

from __future__ import annotations

from ncs_core.source_line import OLD_AGENCY, missing_elements
from ncs_core.text import NA, O, TRI, X

from ..models import CheckOutcome

ELEMENT_NAMES = {"url": "URL", "checked_date": "확인 일자", "cited_page": "쪽", "author": "저작자명", "kogl_type": "공공누리 유형(사용 요건)"}


def check_source(item, res, cfg, prior) -> list[CheckOutcome]:
    if item.kind == "캡션 없는 그림":
        return [CheckOutcome("①출처 있음", TRI, "캡션·출처 없음 — 표 안의 작은 그림이면 출처가 필요한지, 본문 그림이면 캡션·출처를 넣어야 하는지 확인",
                             suggestion="본문 그림이면 캡션([그림 N-M] 제목)과 '출처: …' 줄 추가")]
    info = item.source
    if info is None:
        return [CheckOutcome("①출처 있음", X, "그림 바로 위에 출처 줄이 없음",
                             suggestion="출처: 집필진 제작(연도) 또는 인용 문헌 형식으로 추가"),
                CheckOutcome("①출처 형식", NA), CheckOutcome("①출처 요건", NA)]
    out = [CheckOutcome("①출처 있음", O)]
    if OLD_AGENCY.search(info.text):           # 출처 검토(008)와 같은 규칙 — 표시만(위험도에 안 넣음)
        out.append(CheckOutcome("①기관 명칭", TRI, "'한국직업능력개발원' → 현재 명칭 '한국직업능력연구원'인지 확인"))   # 비고가 곧 할 일 — 제안을 따로 두지 않음
    if info.format_issues:
        out.append(CheckOutcome("①출처 형식", X, " / ".join(info.format_issues),
                                suggestion="F14 출처 형식(저자(연도). 제목. 발행처. p.00. / 집필진 제작(연도) 등)으로 수정"))
    else:
        out.append(CheckOutcome("①출처 형식", O, f"템플릿: {info.template}" if info.template else ""))
    needed, missing = missing_elements(info)            # 계약서 제4조 3·4항 — 출처 검토(008)와 같은 표
    if not needed:
        out.append(CheckOutcome("①출처 요건", NA))
        return out
    if missing:
        out.append(CheckOutcome("①출처 요건", X, f"{info.kind} 출처에 {', '.join(missing)}이(가) 없음 — 계약서 제4조 3항",
                                suggestion=f"출처에 {', '.join(missing)} 추가"))
    else:
        out.append(CheckOutcome("①출처 요건", O))
    return out
