"""계약서 기준 집필료(원고료) 계산 — '계약서 내용 변경 없다고 가정'(11/20 회의). 조항·원문 근거는 config.FEE_BASIS.

규칙(원문에서 확인한 것만)
1. 집필료 = 인정 매수 × 단가(F16 정산지침 인쇄 36쪽 '매수 × 단가 = 집필료').
2. 단가: 계약서(F07)에는 없다(제2조 2항 계약금액 빈칸). 제13조 1항이 가리키는 F16 지침의 원고료 50,000원/쪽은 '상한'이고
   하향 조정이 가능하므로 입력값으로 받고, 입력이 없으면 상한을 기본값으로 쓰되 '상한 기준'이라고 표시한다.
3. 계약 분량(계약서 붙임1 과업지시서 '원고 분량 ○매')을 주면 인정 매수 = min(산정 매수, 계약 분량)
   — 초과분은 추가금 없음, 미달이면 제출 분량만큼(F07 제13조 1항, F16 인쇄 17·18쪽).
4. 기존 원고가 있으면 개선 기준(변경 분량 × 단가)도 낸다(F16 인쇄 20쪽 '새로 수정한 부분만 따로 모아 산정').
5. 세금: 계약금액에 관련 세금이 포함된다(F07 제13조 1항). 원천징수율은 문서에 없어 계산하지 않는다.
"""

from __future__ import annotations

from .config import FEE_BASIS, FEE_UNIT_DEFAULT, FEE_UNIT_SOURCE, VolumeConfig


def _won(value: int) -> str:
    return f"{value:,}원"


def _line(pages: int, unit: int) -> dict:
    return {"분량": pages, "집필료": pages * unit, "산식": f"{pages:,}매 × {_won(unit)} = {_won(pages * unit)}"}


def compute_fee(pages: int, basis: str, *, config: VolumeConfig, unit: int | None = None, contract_pages: int | None = None,
                changed_pages: int | None = None, estimated: bool = False) -> dict:
    """pages: 산정 기입 분량(매), basis: 그 분량의 근거(출력본 측정·한글 줄 배치·추정), changed_pages: 변경 분량(매, 기존 원고가 있을 때)."""
    if unit is not None and unit <= 0:
        raise ValueError("원고료 단가는 0보다 커야 합니다")
    if contract_pages is not None and contract_pages <= 0:
        raise ValueError("계약 분량은 0보다 커야 합니다")
    given = unit is not None
    unit = unit if given else config.fee_unit
    notes = []
    warnings = []   # notes 가운데 금액이 달라지거나 믿기 어려운 것(화면이 경고색으로 보인다). 기본 단가로 계산했다는 안내는 넣지 않는다
    if not given:
        notes.append(f"단가를 넣지 않아 예산지침 상한 {_won(unit)}/쪽으로 계산했습니다. 계약서 제2조 계약금액의 단가가 다르면 단가를 넣으세요.")
    if unit > FEE_UNIT_DEFAULT:
        warnings.append(f"단가 {_won(unit)}은 예산지침 상한 {_won(FEE_UNIT_DEFAULT)}/쪽보다 큽니다(F16 인쇄 18쪽 — 상한선 기준).")
    if estimated:
        warnings.append("분량이 추정치(줄 배치 정보 없음)라 집필료도 참고값입니다. 한글에서 저장한 원고나 출력본 PDF로 다시 산정하세요.")
    allowed = pages
    if contract_pages is not None:
        allowed = min(pages, contract_pages)
        if pages > contract_pages:
            warnings.append(f"산정 {pages}매가 계약 분량 {contract_pages}매보다 많아 {contract_pages}매만 인정합니다(초과분 추가금 없음 — F16 인쇄 17·18쪽).")
        elif pages < contract_pages:
            warnings.append(f"산정 {pages}매가 계약 분량 {contract_pages}매에 미달해 제출 분량만큼 정산합니다(F07 제13조 1항, F16 인쇄 18쪽).")
    notes.extend(warnings)
    main = _line(allowed, unit)
    return {
        "단가": unit, "단가 입력": given, "단가 근거": "입력값" if given else FEE_UNIT_SOURCE,
        "산정 분량": pages, "분량 근거": basis, "계약 분량": contract_pages, "인정 분량": allowed,
        "집필료": main["집필료"], "산식": main["산식"],
        "개선 기준": None if changed_pages is None else {**_line(changed_pages, unit), "근거": "F16 정산지침 인쇄 20쪽 — (개선) 새로 수정한 부분만 모아 산정"},
        "세금": "계약금액(집필료)은 관련 세금을 포함한 금액(F07 제13조 1항). 원천징수율은 계약서·지침에 없어 계산하지 않음",
        "추정": estimated, "근거": [{"조항": clause, "내용": text} for clause, text in FEE_BASIS], "알림": notes, "경고": warnings,
    }
