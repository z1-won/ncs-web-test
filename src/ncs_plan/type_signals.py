"""개선 유형 판단 자료 — 기존 학습모듈 원고에서 지침이 든 '내용 수정이 필요한 경우'의 신호를 찾아 보여 준다. 유형을 정하지 않는다.

근거(지침이 매뉴얼보다 먼저다):
  F05 최소개선 유형 세부 지침('26.7.20) 1항 — 최소개선: 능력단위 코드와 기본 구조에는 변경이 없으나 내용 일부 수정·보완이 필요한 경우
      (학습목표·수행준거 정합성 보완, 본문 최신화, 법령·기준 개정 반영, 오류 수정, 사례·자료 추가·교체). 내용상 변경이 없는 정비는 양식편집.
      개발기관 의향에 따라 재집필·재구성이 필요하면 기존개선으로 변경할 수 있다. 2항 — 유형 변경은 직능연과 협의.
  F21 개발계획서 작성 매뉴얼의 양식편집 운영 기준(안) — 양식편집: 코드 변경이 없거나 경미하고 학습목표와 수행준거가 일치하며 내용을 고치지 않는 경우.
      예시표: 학습목표와 수행준거 불일치 → 개선 또는 최소개선 / 법령 기재 → 최소개선 / 유효하지 않은 URL → 최소개선 / 안전유의사항 '해당사항 없음' → 최소개선.
      직능연이 대상 학습모듈을 검토해 유형을 분류한다.

그래서 여기서는 원고에서 기계로 찾을 수 있는 신호 넷만 찾는다. 오래된 내용·시계열 자료·저해상도 사진처럼 사람이 봐야 하는 예시는 다루지 않는다.
URL은 있는지만 본다(유효한지는 확인하지 않는다). 신호가 없다고 양식편집인 것도 아니다 — 판단은 직능연이 한다.
"""

from __future__ import annotations

import re

from ncs_core.law_catalog import law_names_in

BASIS_F05 = "F05 최소개선 유형 세부 지침 1항"
BASIS_F21 = "F21 양식편집 운영 기준(안) 예시표"
URL = re.compile(r"(?:https?://|www\.)[^\s<>「」『』()\[\]]+[^\s<>「」『』()\[\].,;:]")
SAFETY_HEAD = re.compile(r"안전\s*[·ㆍ･・,]?\s*유의\s*사항")
NONE_TEXT = re.compile(r"^\W*해당\s*사항\s*없음\W*$")
NUMBER = re.compile(r"^\s*\d+\s*[.\-]\s*\d+\s*\.?\s*")
DOTS = re.compile(r"[･・•∙‧ㆍ]")
GUIDE = ("유형은 직능연이 대상 학습모듈을 검토해 분류하고, 바꿀 때는 직능연과 협의합니다(F05 2항, F21). 아래 신호는 판단에 쓰는 자료입니다.")


def _tight(text: str | None) -> str:
    return re.sub(r"\s", "", DOTS.sub("·", NUMBER.sub("", text or "")))


def type_signals(sections: list[list[str]], detail: dict | None, laws=None) -> dict:
    """sections: 원고의 구역별 문단 글(Document.sections). detail: 그 능력단위의 NCS 기준정보(Catalog.unit_detail) 또는 None.
    → {'신호': [{'신호','유형','근거','건수','예'}], '확인 못 한 것': […], '안내': …}."""
    paragraphs = [text for section in sections for text in section if text and text.strip()]
    signals, unknown = [], []

    laws = list(dict.fromkeys(name for text in paragraphs for name in law_names_in(text, laws)))
    if laws:
        signals.append({"신호": "법령 기재", "유형": "최소개선 (법령·기준 개정 반영이 필요한지 확인)", "근거": f"{BASIS_F21}: 학습모듈 교재에 법령이 기재된 경우 / {BASIS_F05}: 법령·기준 개정 반영",
                        "건수": len(laws), "예": laws[:10]})
    urls = list(dict.fromkeys(m.group(0) for text in paragraphs for m in URL.finditer(text)))
    if urls:
        signals.append({"신호": "URL 기재", "유형": "유효하지 않은 URL이 있으면 최소개선 (유효한지는 확인하지 않았음)", "근거": f"{BASIS_F21}: 본문에 유효하지 않은 URL이 포함된 경우",
                        "건수": len(urls), "예": urls[:10]})
    empty_safety = sum(1 for i, text in enumerate(paragraphs) if SAFETY_HEAD.search(text) and len(text) < 30
                       and any(NONE_TEXT.match(following) for following in paragraphs[i + 1:i + 3]))
    empty_safety += sum(1 for text in paragraphs if SAFETY_HEAD.search(text) and re.search(r"해당\s*사항\s*없음", text))
    if empty_safety:
        signals.append({"신호": "안전·유의 사항 ‘해당 사항 없음’", "유형": "최소개선", "근거": f"{BASIS_F21}: 안전유의사항은 필수 기재사항으로 '해당사항 없음'으로 작성된 원고는 수정 필요",
                        "건수": empty_safety, "예": []})
    if detail is None:
        unknown.append("이 능력단위의 NCS 기준정보를 받아 두지 않아 학습 목표를 수행준거와 대조하지 못함")
    else:
        body = _tight(" ".join(paragraphs))
        missing = [f"{element['code']}: {criterion}" for element in detail.get("elements") or [] for criterion in element.get("criteria") or []
                   if _tight(criterion) and _tight(criterion) not in body]
        if missing:
            signals.append({"신호": "학습 목표와 NCS 수행준거 불일치", "유형": "기존 개선 또는 최소개선 (양식 편집 요건인 ‘학습목표와 수행준거 일치’에 맞지 않음)",
                            "근거": f"{BASIS_F21}: 학습목표와 NCS의 수행준거가 불일치하는 경우 / {BASIS_F05}: 학습목표 또는 수행준거 정합성 보완",
                            "건수": len(missing), "예": [f"원고에 같은 글이 없는 수행준거 — {text}" for text in missing[:10]]})
    if signals:
        guide = GUIDE
    else:
        guide = ("기계로 찾는 신호(법령, URL, 안전·유의 사항, 학습 목표–수행준거)는 없습니다. 양식 편집 요건(코드 변경이 없거나 경미, 학습목표와 수행준거 일치, 내용 수정 없음)에 맞는지는 "
                 "오래된 내용·자료·사진처럼 사람이 봐야 하는 것까지 확인해 직능연이 판단합니다. " + GUIDE)
    return {"신호": signals, "확인 못 한 것": unknown, "안내": guide}


def type_signals_file(path, module_code: str = "") -> dict:
    """기존 학습모듈 원고 파일(hwp, hwpx) → 신호. 모듈 코드는 주면 그것을, 없으면 파일명에서 찾는다(못 찾으면 수행준거 대조만 건너뛴다)."""
    from pathlib import Path

    from ncs_core import load_document
    from ncs_core.module_code import CODE_IN_NAME, validate_module_code
    from ncs_core.ncs_catalog import catalog

    code = ""
    if module_code.strip():
        code = validate_module_code(module_code if module_code.strip().startswith("LM") else "LM" + module_code.strip())
    else:
        found = list(dict.fromkeys(CODE_IN_NAME.findall(Path(path).name)))
        code = found[0] if len(found) == 1 else ""
    document = load_document(path)
    cat = catalog()
    detail = cat.unit_detail(code) if cat is not None and code else None
    if detail is not None and detail.get("code") != code.replace("LM", ""):
        detail = None        # 버전이 다른 기준정보와는 대조하지 않는다
    from ncs_core.law_catalog import law_catalog

    result = type_signals(document.sections, detail, law_catalog())
    if not code:
        result["확인 못 한 것"] = ["모듈 코드를 알 수 없어 학습 목표를 수행준거와 대조하지 못함(파일명에 LM 코드가 없음 — 코드를 적어 주세요)"]
    result["파일"], result["모듈 코드"] = Path(path).name, code
    return result
