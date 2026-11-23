"""F03 직능연 검수 체크리스트로 옮기기 — F02 검수 확인서의 항목별 결과를 F03 문항에 묶는다(REQ-02-002 사람 작업 5 '검수표 전달 | F02, F03').

F03(「최종검수표_직능연 수행」 엑셀)은 세분류 시트 하나에 학습모듈을 열로 두고 문항마다 적합/부적합을 적는 표다.
여기서 다루는 것은 원고로 볼 수 있는 두 묶음이다: '01 검수 완료 파일'(20문항)과 '03 PDF'(13문항).
  - 문항마다 대응하는 F02 항목들의 결과를 접는다: 하나라도 부적합이면 부적합, 부적합 없이 판단불가·미검사가 있으면 '확인 필요', 모두 적합이면 적합.
  - 대응하는 F02 항목이 없는 문항(평가 준거 기본 문구, 표지, 유의 사항 쪽, ISBN, PDF 변환 등)은 프로그램이 보지 않는다 — '확인 필요'로 두고 그렇게 적는다.
  - F03은 문항마다 '양식 편집에 적용' 표시가 있다. 원고 유형이 기존양식편집이면 표시가 있는 문항만 보고 나머지는 '해당 없음'이다.
'04 PDF 업로드 및 서비스', '05 용역 부속 서류 확인'과 맨 위의 원고 평가(직능연 내부, 외부 유출 금지)는 원고 검수의 범위가 아니라 만들지 않는다.
F03에 적는 값은 적합/부적합 둘뿐이다 — '확인 필요'는 사람이 확인해 둘 중 하나로 바꿔 적는다.
"""

from __future__ import annotations

import io
import re

FAIL_TEXT, PASS_TEXT, CHECK, NA_TEXT = "부적합", "적합", "확인 필요", "해당 없음"
APPLY_ALL = ("신규개발", "기존개선")          # F03 '원고 유형': 신규개발, 기존개선, 기존양식편집 중 1개
FORM_EDIT = "기존양식편집"
FILE, PDF = "01 검수 완료 파일", "03 PDF"

# (대상, 구분, 번호, 문항, 양식 편집에 적용, 대응하는 F02 항목 [(구성요소, 번호)])
ITEMS = [
    (FILE, "NCS-학습모듈의 위치", "①", "NCS-학습모듈의 위치가 개발계획서를 따르고 있는가?", False, [("NCS-학습모듈의 위치", n) for n in "①②③④"]),
    (FILE, "NCS-학습모듈의 위치", "②", "해당 학습모듈 및 능력단위에 굵은 글씨(볼드체) 및 음영 표시를 하여 구분하였는가?", False, [("NCS-학습모듈의 위치", "⑤")]),
    (FILE, "학습모듈의 개요", "①", "선수학습에 해당 학습모듈보다 수준이 높은 학습모듈, 능력단위가 없는가?", False, [("학습모듈의 개요", "④")]),
    (FILE, "학습모듈의 개요", "②", "학습모듈의 내용체계가 개발계획서를 따르고 있는가?", False, [("학습모듈의 개요", n) for n in "⑤⑥⑦"]),
    (FILE, "학습", "①", "대단원명, 중단원명이 개발계획서를 따르고 있는가?", False, [("차례", "③"), ("필요 지식", "③"), ("필요 지식", "④")]),
    (FILE, "학습", "②", "학습목표는 개발계획서를 따르고 있는가?", False, [("필요 지식", "⑤")]),
    (FILE, "학습", "③", "수행 내용의 제목을 ‘~하기’로 종결하였는가?", False, [("수행 내용", "①")]),
    (FILE, "학습", "④", "수행 내용의 안전유의사항이 작성되었는가? (\"해당사항 없음\" 기재 불가)", False, [("수행 내용", "③")]),
    (FILE, "학습", "⑤", "필요 지식과 수행 내용에 사용된 번호체계는 올바른가?", False, [("필요 지식", "⑥")]),
    (FILE, "학습", "⑥", "그림, 표 번호가 학습 번호에 맞춰 ‘연속적’으로 기재되었는가?", False, [("필요 지식", "⑦")]),
    (FILE, "학습", "⑦", "그림, 표의 출처 표기가 지정된 형식대로 기재되었는가?", False, [("필요 지식", "⑧")]),
    (FILE, "교수·학습 방법", "①", "교수 방법과 학습 방법을 각각 3가지 이상 제시하였는가?", False, [("교수·학습 방법", "①"), ("교수·학습 방법", "③")]),
    (FILE, "평가", "①", "‘평가 준거’의 기본 문구가 일치하는가?", True, []),
    (FILE, "평가", "②", "평가 방법과 피드백을 각각 2가지 이상 제시하였는가?", True, [("평가", "③"), ("평가", "⑤")]),
    (FILE, "판권", "①", "개발이력을 지침에 맞게 작성하였는가?", True, [("개발 이력 및판권", "①")]),
    (FILE, "판권", "②", "판권은 양식에 맞춰 작성하였는가? (신규와 개선 양식이 상이)", True, [("개발 이력 및판권", "①")]),
    (FILE, "기타", "①", "사진, 삽화는 누락 또는 유실되지 않고 학습모듈 내에서 모두 확인되는가?", True, [("기타", "②")]),
    (FILE, "기타", "②", "본문 텍스트 및 그림에 특정 회사명, 상호, 상품명, 인물 얼굴 등이 노출되지는 않았는가?", False, [("기타", "③"), ("수행 내용", "②")]),
    (FILE, "기타", "③", "특정 컴퓨터 프로그램 화면을 캡처하였을 경우 작업 표시 줄을 잘라 내거나 지웠는가?", False, [("기타", "④")]),
    (FILE, "기타", "④", "사진, 삽화의 크기 및 해상도는 적절한가?", False, [("기타", "⑤")]),
    (PDF, "표지(앞면)", "①", "표지에 대분류, 중분류, 소분류의 명칭과 코드가 모두 올바르게 기재되었는가?", True, []),
    (PDF, "표지(앞면)", "②", "표지에 능력단위 코드가 올바르게 기재되었는가?", True, []),
    (PDF, "표지(앞면)", "③", "표지에 학습모듈 명칭과 LM코드가 모두 올바르게 기재되었는가?", True, []),
    (PDF, "NCS학습모듈 활용 유의 사항", "④", "NCS학습모듈 활용 시 유의 사항 페이지가 제시되어 있는가?", True, []),
    (PDF, "NCS학습모듈의 이해", "①", "NCS학습모듈의 이해 페이지가 제시되어 있는가?", True, []),
    (PDF, "표지(뒷면)", "①", "NCS학습모듈 마크가 제시되어 있는가?", True, []),
    (PDF, "차례", "①", "차례 페이지의 쪽수는 본문 페이지의 쪽수와 모두 일치하는가?", True, [("차례", "⑦")]),
    (PDF, "편집", "①", "학습모듈의 개요는 1쪽에서 시작하는가?", True, []),
    (PDF, "편집", "②", "학습1은 3쪽에서 시작하는가?", True, []),
    (PDF, "편집", "③", "개요, 학습, 교수·학습 방법, 평가, 참고 자료, 활용 서식, 부록은 새 페이지에서 시작되었는가?", True, [("기타", "①")]),
    (PDF, "판권", "①", "신규/개선의 ISBN이 바르게 기재되었는가?", True, []),
    (PDF, "변환", "①", "PDF 1쪽에 원고 1쪽이 제시되도록 변환되었는가?", True, []),
    (PDF, "변환", "②", "사진, 삽화는 누락 또는 유실되지 않고 학습모듈 내에서 모두 확인되는가?", True, []),
]


def _key(component: str) -> str:
    return re.sub(r"[\s\-·]", "", component)


def f03_rows(sheet_rows: list[dict], kind: str = "기존개선") -> list[dict]:
    """F02 확인서 행(구성요소·번호·검수결과) → F03 문항 행 [{'대상','구분','번호','문항','양식 편집 적용','결과','근거'}]. kind: F03의 원고 유형."""
    if kind not in APPLY_ALL + (FORM_EDIT,):
        raise ValueError("원고 유형은 신규개발, 기존개선, 기존양식편집 중 하나여야 합니다")
    given = {(_key(row["구성요소"]), row["번호"]): row.get("검수결과") or "" for row in sheet_rows}
    out = []
    for target, group, no, text, form_edit, sources in ITEMS:
        if kind == FORM_EDIT and not form_edit:
            result, basis = NA_TEXT, "양식 편집 원고에는 적용하지 않는 문항(F03 ‘양식 편집에 적용’ 표시 없음)"
        elif not sources:
            result, basis = CHECK, "프로그램이 보지 않는 문항 — 사람이 확인해 적합/부적합을 적을 것"
        else:
            found = [(component, number, given.get((_key(component), number)) or "미검사") for component, number in sources]
            verdicts = [verdict for _, _, verdict in found]
            result = FAIL_TEXT if "부적합" in verdicts else PASS_TEXT if all(verdict == "적합" for verdict in verdicts) else CHECK
            basis = "F02 " + ", ".join(f"{component} {number} {verdict}" for component, number, verdict in found)
        out.append({"대상": target, "구분": group, "번호": no, "문항": text, "양식 편집 적용": form_edit, "결과": result, "근거": basis})
    return out


def build_f03_xlsx(module_code: str, rows: list[dict], *, kind: str = "기존개선") -> bytes:
    """F03 문항 행 → xlsx 한 장(대상 | 구분 | 문항 | 양식 편집에 적용 | 결과 | 근거). F03 원본의 학습모듈 열 하나에 옮겨 적는 용도."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    book = Workbook()
    ws = book.active
    ws.title = "F03 옮겨 적기"
    ws.append([f"직능연 검수 체크리스트(F03)로 옮겨 적기 — {module_code} (원고 유형: {kind})"])
    ws.append(["‘확인 필요’는 사람이 확인해 적합/부적합 중 하나로 적습니다. ‘04 PDF 업로드 및 서비스’, ‘05 용역 부속 서류 확인’은 다루지 않습니다."])
    ws.append(["대상", "구분", "문항", "양식 편집에 적용", "결과", "근거"])
    for cell in ws[3]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="E6E8EA")
    colors = {FAIL_TEXT: "FDE2E2", CHECK: "FFF3CD", NA_TEXT: "F1F3F5"}
    for row in rows:
        ws.append([row["대상"], row["구분"], f"{row['번호']} {row['문항']}", "1" if row["양식 편집 적용"] else "", row["결과"], row["근거"]])
        if row["결과"] in colors:
            ws.cell(ws.max_row, 5).fill = PatternFill("solid", fgColor=colors[row["결과"]])
    for column, width in zip("ABCDEF", (20, 24, 70, 16, 12, 60)):
        ws.column_dimensions[column].width = width
    for line in ws.iter_rows(min_row=4):
        for cell in line:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.font = Font(bold=True)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()
