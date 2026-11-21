"""LLM 답 검증과 판정 정책 — 의견 하나와 LLM 답으로 '반영 후보 / 미반영 후보 / 확인 필요 / 조치 불필요'를 정한다. I/O 없음.

판정은 LLM이 하고, 여기서는 정책과 검증만 적용한다(docs/CONVENTIONS.md 판정 원칙 2·3 — 이 기능은 전부 후보 제시 CASE다).
- LLM을 부르지 못함(미설정·미승인·호출 실패)·LLM이 답하지 않음 → '확인 필요'와 이유. 규칙으로 대신 판정하지 않는다.
- 조치 불필요 유형 → '조치 불필요'.
- 개발계획서·종합 의견(가리키는 자리가 없음) → '확인 필요'(유형만 LLM이 분류).
- 용어 변경 → 언제나 '확인 필요' + 집필자에게 묻는 문장(REQ-02-003). LLM이 준 옛·새 용어가 원고에 몇 곳 있는지 센다(글자 세기).
- 형식·그림 → 원고 글로 확인할 수 없어 '확인 필요'.
- 내용: LLM '반영'인데 유효한 근거 문단 번호가 없음 → '확인 필요'. 범위를 정하지 못해 원고 전체에서 고른 문단으로 물었음 → '확인 필요'.
  반영 전 원고가 있고 LLM이 '반영 전에도 있음'이라 했거나 근거 문단이 반영 전 원고에 글자 그대로 있음 → '확인 필요'.
  '미반영'이면 수정 문장 후보를 '수정 제안'에 — 의견·근거 문단에 없던 수치·영문 낱말이 들어 있으면 버린다(내용 생성 금지).
최종 판단은 사람이 한다.
"""

from __future__ import annotations

import re

from .config import (CHECK, DEFAULT_CONFIG, KIND_CONTENT, KIND_FIGURE, KIND_FORM, KIND_NONE, KIND_TERM, KIND_UNKNOWN, LLM_MISSING,
                     LLM_REFLECTED, NO_ACTION, NOT_REFLECTED, PLAN, REFLECTED, SUMMARY, WHOLE, OpinionConfig)
from .keys import refs_of
from .regions import Manuscript, find, print_page
from .sheet import Opinion

NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
LATIN = re.compile(r"[A-Za-z][A-Za-z0-9+#.\-]*")


def _evidence(manuscript: Manuscript, index: int, pages, config: OpinionConfig) -> dict:
    para = manuscript.paras[index]
    text = para.text if len(para.text) <= config.evidence_chars else para.text[: config.evidence_chars] + "…"
    item = {"문단": text, "위치": para.where, "문단 번호": para.index}
    if pages:
        item["출력본 쪽"] = print_page(pages, para.text)
    return item


def invented(suggestion: str, sources: list[str]) -> str:
    """수정 문장 후보에 의견·근거 문단에 없던 수치·영문 낱말이 있으면 그 이유(없으면 빈 글)."""
    known = " ".join(sources)
    numbers = set(NUMBER.findall(suggestion)) - set(NUMBER.findall(known))
    latin = {w.lower() for w in LATIN.findall(suggestion)} - {w.lower() for w in LATIN.findall(known)}
    found = sorted(numbers) + sorted(latin)
    return f"의견에 없던 {', '.join(found)}" if found else ""


def blank_row(where: str, notes: list[str]) -> dict:
    return {"판정": CHECK, "유형": KIND_UNKNOWN, "근거": [], "찾은 범위": where, "비고": list(notes), "집필자 확인": "",
            "수정 제안": "", "용어 변경": None, "LLM": None}


def judge(opinion: Opinion, where: str, notes: list[str], answer: dict | None, manuscript: Manuscript, *,
          previous: Manuscript | None = None, llm_off: str = "", pages=None, config: OpinionConfig = DEFAULT_CONFIG) -> dict:
    """의견 하나의 판정 후보. where·notes: regions.locate의 범위 이름과 알림. answer: llm_check.ask_all의 답(없으면 None).
    llm_off: LLM을 부르지 못한 이유(있으면 answer는 보지 않는다).

    돌려주는 키: 판정, 유형, 근거(list), 찾은 범위, 비고(list), 집필자 확인, 수정 제안, 용어 변경({'옛','새'}|None), LLM(dict|None).
    """
    out = blank_row(where, notes)
    if llm_off:
        out["비고"].append(f"{llm_off} — 의견과 원고를 사람이 대조")
        out["LLM"] = {"상태": llm_off}
        return out
    if answer is None:
        out["비고"].append("LLM이 이 의견에 답하지 않음 — 사람이 확인")
        out["LLM"] = {"상태": "답 없음"}
        return out
    if "오류" in answer:
        out["비고"].append(f"LLM 호출 실패: {answer['오류']} — 사람이 확인")
        out["LLM"] = {"상태": f"LLM 호출 실패: {answer['오류']}"}
        return out

    kind = answer["유형"] or KIND_UNKNOWN
    out["유형"] = kind
    out["LLM"] = {"상태": "사용", "모델": answer["모델"], "유형": kind, "판정": answer["판정"] or "(없음)", "이유": answer["이유"],
                  "수정 문장": answer["수정 문장"], "보낸 문단 수": answer["보낸 문단 수"], "반영 전 문단 수": answer["반영 전 문단 수"]}
    out["근거"] = [_evidence(manuscript, i, pages, config) for i in answer["근거"]]
    if answer["버린 근거 번호"]:
        out["비고"].append(f"LLM이 댄 근거 번호 중 {answer['버린 근거 번호']}개는 보낸 문단에 없어 버림")
    if answer["이유"]:
        out["비고"].append(f"LLM({answer['모델']}): {answer['이유']}")

    if kind == KIND_NONE:
        out["판정"] = NO_ACTION
        return out
    if opinion.group == PLAN:
        out["비고"].append("개발계획서에 대한 의견 — 원고만으로 반영 여부를 정하지 않음(개발계획서에서 확인)")
        return out
    if opinion.group == SUMMARY:
        out["비고"].append("종합 의견 — 가리키는 자리가 없어 판정 후보를 내지 않음, 원고를 보고 확인")
        return out
    if kind == KIND_TERM:
        return _term(out, answer, manuscript, pages, config)
    if kind == KIND_FORM:
        out["비고"].append("편집·형식 의견 — 글자만으로는 반영 여부를 알 수 없음, 출력본에서 눈으로 확인")
        return out
    if kind == KIND_FIGURE:
        return _figure(out, opinion, manuscript, previous, pages, config)
    if kind != KIND_CONTENT:
        out["비고"].append("LLM이 유형을 정하지 못함 — 사람이 확인")
        return out

    verdict = answer["판정"]
    if verdict == LLM_REFLECTED:
        if not answer["근거"]:
            out["비고"].append("LLM이 반영이라 했으나 유효한 근거 문단 번호가 없음 — 확인 필요로 낮춤")
        elif where == WHOLE:
            out["비고"].append("의견이 가리키는 자리를 정하지 못해 원고 전체에서 고른 문단으로 물음 — 자리를 확인")
        elif previous is not None and (answer["반영 전에도 있음"] or set(manuscript.compacts[i] for i in answer["근거"]) <= set(previous.compacts)):
            out["비고"].append("근거 문단이 반영 전 원고에도 있던 내용 — 의견에 따라 바뀐 것인지 확인")
        else:
            out["판정"] = REFLECTED
            if previous is not None:
                out["비고"].append("근거 문단은 반영 전 원고에 없던 문단")
    elif verdict == LLM_MISSING:
        if where == WHOLE:
            out["비고"].append("의견이 가리키는 자리를 정하지 못해 원고 일부만 보고 미반영이라 함 — 자리를 확인")
        else:
            out["판정"] = NOT_REFLECTED
        sentence = answer["수정 문장"]
        why = invented(sentence, [opinion.text] + [manuscript.paras[i].text for i in answer["근거"]]) if sentence else ""
        if why:
            out["비고"].append(f"LLM 수정 문장 후보를 버림({why} — 내용 생성 금지): {sentence}")
        elif sentence and out["판정"] == NOT_REFLECTED:
            out["수정 제안"] = sentence
    elif previous is not None and answer["반영 전에도 있음"]:
        out["비고"].append("LLM: 같은 내용이 반영 전 원고에도 있음 — 의견에 따라 바뀐 것인지 확인")
    return out


def _term(out: dict, answer: dict, manuscript: Manuscript, pages, config: OpinionConfig) -> dict:
    """용어 변경 의견: LLM이 준 옛·새 용어가 범위와 원고 전체에 몇 곳 있는지 세고 집필자에게 묻는다."""
    olds, news = answer["옛 용어"], answer["새 용어"]
    out["용어 변경"] = {"옛": olds, "새": news}
    region = [e["문단 번호"] for e in out["근거"]]
    remain, counts = [], []
    for label, terms in (("새 용어", news), ("옛 용어", olds)):
        for term in terms:
            every = find(manuscript, term)
            counts.append(f"{label} '{term}' {len(every)}곳")
            if every and not any(i in region for i in every):
                out["근거"].append(_evidence(manuscript, every[0], pages, config))
            if label == "옛 용어" and every:
                remain.append(f"'{term}' {len(every)}곳({', '.join(sorted({manuscript.paras[i].where for i in every}))})")
    out["비고"].append("용어 변경 의견 — 즉시 반영으로 보지 않고 집필자에게 확인(REQ-02-003)")
    if counts:
        out["비고"].append("원고 전체: " + ", ".join(counts))
    else:
        out["비고"].append("LLM이 옛·새 용어를 뽑지 못함 — 의견을 읽고 확인")
    pair = " → ".join(filter(None, ["/".join(olds), "/".join(news)]))
    out["집필자 확인"] = f"용어 변경({pair or '의견 참고'})을 원고에 적용할지 확인해 주세요." + (f" 옛 용어가 남은 곳: {'; '.join(remain)}" if remain else "")
    if remain and news:
        out["수정 제안"] = f"남은 '{olds[0]}'을(를) '{news[0]}'(으)로 바꿀지 검토"
    return out


def _figure(out: dict, opinion: Opinion, manuscript: Manuscript, previous: Manuscript | None, pages, config: OpinionConfig) -> dict:
    """그림 의견: 캡션 문단을 근거로 붙이고(반영 전 원고와 캡션이 바뀌었으면 알림), 그림은 사람이 눈으로 확인."""
    for ref in refs_of(opinion.text):
        at = manuscript.captions.get((ref.kind, ref.number))
        if at is None:
            continue
        if all(e["문단 번호"] != at for e in out["근거"]):
            out["근거"].insert(0, _evidence(manuscript, at, pages, config))
        before = previous.captions.get((ref.kind, ref.number)) if previous is not None else None
        if before is not None and previous.compacts[before] != manuscript.compacts[at]:
            out["비고"].append(f"캡션이 바뀜: '{previous.paras[before].text}' → '{manuscript.paras[at].text}'")
    out["비고"].append("그림 속 내용에 대한 의견 — 그림 속 글은 원고 글에 없어 그림을 눈으로 확인")
    return out
