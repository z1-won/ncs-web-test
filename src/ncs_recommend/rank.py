"""후보 그림에 점수를 매겨 순서를 정하고, 집필자가 봐야 할 권리·출처·화질 안내를 붙인다.

점수(높을수록 앞):
  핵심어가 그림의 키워드에 있으면 3, 제목·캡션에 있으면 2, 그림 사용 문장에 있으면 1 — 핵심어마다 가장 높은 것 하나.
  앞 순위 핵심어일수록 조금 더 쳐 준다(첫 핵심어 ×1.0 … 마지막 ×0.6).
  수행준거 연결: 같은 능력단위 2, 같은 능력단위요소 +1, 같은 수행준거 +3.
  핵심어도 연결도 맞지 않는 그림은 추천하지 않는다.
  정부 귀속 + 전체 재사용 자산은 +1 — 비슷하게 맞는 그림 가운데서는 이것이 앞에 온다
  (원고 집필 계약서 제12조, 사진·삽화 제작 계약서 제11조. 관련이 훨씬 높은 다른 그림을 밀어내지는 않는다).
"""

import re

from .context import Context, squash

KEYWORD_POINTS = (("keywords", 3.0), ("titles", 2.0), ("contexts", 1.0))
PRIORITY_BONUS = 1.0
PRINT_DPI = 300
LOW_WIDTH_MM = 40            # 300dpi로 가로 40mm도 못 싣는 그림(약 470px 미만)은 '화질 낮음'
CONDITION_NAMES = (("attribution", "출처표시"), ("non_commercial", "상업적 이용금지"), ("no_derivatives", "변경금지"),
                   ("share_alike", "동일조건 변경허락"))
AI_GUIDANCE = (
    "맞는 그림이 없거나 화질이 낮으면 생성형 AI로 새로 만들거나 수정 보완할 수 있습니다(REQ-02-006).",
    "그렇게 만든 그림에는 「AI 도구 사용 표기 예」(2026. 9.)에 따라 그림 아래에 AI 활용 표기를 넣어야 합니다.",
    "「생성형 AI 결과물 집필자 서약서」의 결과물 현황(결과물명·쪽수·활용 AI)에도 올려야 합니다 — 권리 증빙 점검에서 대조합니다.",
)


def unit_base(code) -> str:
    """'LM1203020201_24v3'·'1203020201' → '1203020201'(능력단위 숫자 10자리). 꼴이 다르면 빈 글."""
    found = re.search(r"\d{10}", str(code or ""))
    return found.group(0) if found else ""


def _element_no(code) -> str:
    """'1203020201_24v3.1' → '1'."""
    return str(code or "").rpartition(".")[2] if "." in str(code or "") else ""


def _link_level(links: list[dict], unit: str, criterion_no: str) -> str:
    """가장 가깝게 맞는 연결: 'criterion' > 'element' > 'unit' > ''."""
    level = ""
    element = criterion_no.split(".")[0] if criterion_no else ""
    for link in links or []:
        if not unit or unit_base(link.get("unit_code")) != unit:
            continue
        if criterion_no and str(link.get("criterion_no") or "") == criterion_no:
            return "criterion"
        if element and _element_no(link.get("element_code")) == element:
            level = "element"
        elif not level:
            level = "unit"
    return level


LINK_POINTS = {"": 0.0, "unit": 2.0, "element": 3.0, "criterion": 6.0}


def conditions(row: dict) -> list[str]:
    return [name for key, name in CONDITION_NAMES if row.get(key)]


def _notes(row: dict) -> list[str]:
    notes = []
    if row.get("kogl_ai"):
        notes.append(f"AI유형이 함께 표시돼 있지만 그것은 AI 학습 목적에만 해당합니다. 원고에 싣는 데는 제{row.get('kogl_type')}유형 조건이 그대로 적용됩니다.")
    if row.get("license_scheme") == "kogl" and row.get("kogl_type") == 0:
        notes.append("제0유형은 공공누리상 출처표시 의무가 없지만, 원고에는 계약서 제4조에 따라 출처를 적습니다.")
    if row.get("non_commercial"):
        notes.append("상업적 이용금지 조건이 있습니다 — 학습모듈의 배포·판매 방식에 맞는지 확인하세요.")
    if row.get("no_derivatives"):
        notes.append("변경금지 조건이 있습니다 — 자르기·합성·색 보정 없이 원본 그대로 실어야 합니다.")
    return notes


def describe(row: dict) -> dict:
    """후보 1건에 집필자가 볼 안내를 붙인다(점수와 무관한 부분)."""
    width = row.get("upscaled_width_px") or row.get("width_px")
    max_width_mm = round(width / PRINT_DPI * 25.4) if width else None
    credit = (row.get("credit_line") or "").strip()
    return {
        "priority": row.get("ownership") == "government" and row.get("reuse_scope") == "all",
        # 이용허락 한정 자산은 '범위 확인 필요'로 표시한다
        "scope_check_needed": row.get("ownership") == "licensed" or row.get("reuse_scope") == "module_only",
        "conditions": conditions(row),
        "notes": _notes(row),
        "credit": f"출처: {credit}" if credit else None,
        "credit_note": "" if credit else "출처 문구가 DB에 없습니다 — 이미지 저작권 DB에서 출처를 채운 뒤 쓰세요.",
        "max_width_mm": max_width_mm,
        "low_quality": max_width_mm is not None and max_width_mm < LOW_WIDTH_MM,
    }


def score(row: dict, context: Context, unit: str = "", criterion_no: str = "") -> tuple[float, list[str], str]:
    """(관련 점수, 맞은 핵심어, 연결 수준). 우선 자산 가산은 넣지 않은 값이다."""
    fields = {"keywords": [squash(k) for k in row.get("keywords") or []],
              "titles": [squash(t) for t in [row.get("title"), *(row.get("captions") or [])] if t],
              "contexts": [squash(t) for t in row.get("contexts") or [] if t]}
    total, matched = 0.0, []
    count = len(context.keywords)
    for position, keyword in enumerate(context.keywords):
        key = squash(keyword)
        if len(key) < 2:
            continue
        points = next((value for name, value in KEYWORD_POINTS if any(key in text or (len(text) >= 2 and text in key) for text in fields[name])), 0.0)
        if points:
            total += points * (1.0 - 0.4 * position / max(count - 1, 1))
            matched.append(keyword)
    level = _link_level(row.get("links") or [], unit, criterion_no)
    return total + LINK_POINTS[level], matched, level


def rank(candidates: list[dict], context: Context, *, unit_code: str = "", criterion_no: str = "", limit: int = 10) -> list[dict]:
    """관련 있는 후보만 점수순으로. 각 항목은 후보의 값 + describe() + score·matched·link_level."""
    unit = unit_base(unit_code)
    criterion_no = (criterion_no or "").strip()
    ranked = []
    for row in candidates:
        relevance, matched, level = score(row, context, unit, criterion_no)
        if relevance <= 0:
            continue
        extra = describe(row)
        final = relevance + (PRIORITY_BONUS if extra["priority"] else 0.0)
        ranked.append({**row, **extra, "score": round(final, 2), "matched": matched, "link_level": level})
    ranked.sort(key=lambda item: (-item["score"], not item["priority"], item["low_quality"], str(item.get("id"))))
    return ranked[:limit]


def guidance(items: list[dict]) -> list[str]:
    """추천할 그림이 없거나 모두 화질이 낮을 때의 안내(AI 생성·수정 보완으로 연계). 아니면 빈 목록."""
    if not items:
        return ["조건에 맞는 그림이 이미지 저작권 DB에 없습니다.", *AI_GUIDANCE]
    if all(item["low_quality"] for item in items):
        return ["추천된 그림이 모두 화질이 낮습니다.", *AI_GUIDANCE]
    return []
