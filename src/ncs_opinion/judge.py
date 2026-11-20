"""LLM 없이 도는 1차 판정 — 의견 하나와 원고 범위로 '반영 후보 / 미반영 후보 / 확인 필요 / 조치 불필요'를 정한다. I/O 없음.

판정 원칙(docs/CONVENTIONS.md '판정 원칙' 2·3번을 따른다 — 이 기능은 전부 후보 제시 CASE다)
- 핵심어가 의견이 가리키는 범위(표·그림 캡션 범위 또는 학습·구성 구간)에 모두 있으면 '반영 후보', 원고 어디에도 없으면 '미반영 후보'.
  일부만 있거나, 범위를 정하지 못해 원고 전체에서 찾았거나, 핵심어를 뽑지 못했으면 '확인 필요'.
- 용어 변경 의견은 새 용어가 있어도 '확인 필요'로 두고 집필자에게 물을 문장을 붙인다(REQ-02-003).
- 형식(정렬·줄 간격·오탈자)·그림 속 내용·개발계획서 의견은 원고 글만으로 확인할 수 없어 '확인 필요'.
- 반영 전 원고가 있으면, 반영 후보의 핵심어가 반영 전에도 같은 범위에 있었을 때 '확인 필요'로 낮춘다(원래 있던 표현).
최종 판단은 사람이 한다. 결과는 판정 후보와 근거 문장, 확인할 자리다.
"""

from __future__ import annotations

from .config import (CHECK, DEFAULT_CONFIG, KIND_FIGURE, KIND_FORM, KIND_NONE, KIND_TERM, NO_ACTION, NOT_REFLECTED, PLAN,
                     REFLECTED, SUMMARY, OpinionConfig)
from .keys import Reading
from .regions import Manuscript, find, part_region, print_page, ref_region
from .sheet import Opinion


def locate(opinion: Opinion, reading: Reading, manuscript: Manuscript, config: OpinionConfig = DEFAULT_CONFIG) -> tuple[list[int], str, list[str]]:
    """찾을 범위 → (문단 번호, 범위 설명, 알림). 범위를 못 정하면 원고 전체와 '원고 전체'."""
    notes: list[str] = []
    found: list[int] = []
    labels = []
    for ref in reading.refs:
        region = ref_region(manuscript, ref, config)
        if region is None:
            notes.append(f"원고에 {ref.label} 캡션이 없음 — 번호가 바뀌었거나 빠졌을 수 있음")
            continue
        found += [i for i in region if i not in found]
        labels.append(f"{ref.label} 캡션 주변")
    if found:
        return found, ", ".join(labels), notes
    if opinion.group not in (SUMMARY, PLAN):
        region = part_region(manuscript, opinion.lesson, opinion.part, opinion.group)
        if region:
            where = opinion.group + (f" {opinion.part}" if opinion.part else "")
            return region, f"{where} 구간", notes
        where = (opinion.group + " " + (opinion.part or "")).strip()
        notes.append(f"원고에서 '{where}' 구간을 찾지 못함")
    return manuscript.everything, "원고 전체", notes


def _evidence(manuscript: Manuscript, indexes: list[int], key: str, pages, config: OpinionConfig) -> dict:
    para = manuscript.paras[indexes[0]]
    text = para.text if len(para.text) <= config.evidence_chars else para.text[: config.evidence_chars] + "…"
    item = {"핵심어": key, "문단": text, "위치": para.where, "문단 번호": para.index}
    if pages:
        item["출력본 쪽"] = print_page(pages, para.text)
    return item


def judge(opinion: Opinion, reading: Reading, manuscript: Manuscript, *, previous: Manuscript | None = None, pages=None,
          config: OpinionConfig = DEFAULT_CONFIG) -> dict:
    """의견 하나의 판정 후보. 돌려주는 키: 판정, 근거(list), 찾은 범위, 비고(list), 집필자 확인, 수정 제안, 범위(문단 번호 — 내부용)."""
    out = {"판정": CHECK, "근거": [], "찾은 범위": "", "비고": [], "집필자 확인": "", "수정 제안": "", "범위": []}
    if reading.kind == KIND_NONE:
        out["판정"] = NO_ACTION
        out["비고"].append("수정·보완을 요구하지 않는 의견(적합 확인·칭찬)")
        return out
    region, where, notes = locate(opinion, reading, manuscript, config)
    out["찾은 범위"], out["범위"] = where, region
    out["비고"] += notes
    whole = where == "원고 전체"

    if opinion.group == PLAN:
        out["비고"].append("개발계획서에 대한 의견 — 원고만으로 반영 여부를 정하지 않음(개발계획서에서 확인)")
        return out

    if reading.kind == KIND_TERM:
        return _term(out, reading, manuscript, region, whole, pages, config)

    if reading.kind == KIND_FORM:
        out["비고"].append("편집·형식 의견 — 글자만으로는 반영 여부를 알 수 없음, 출력본에서 눈으로 확인")
        for old in reading.old_terms:
            left = find(manuscript, old, region, config)
            out["비고"].append(f"고칠 말 '{old}': 범위 안에 {len(left)}곳 남음")
        return out

    if reading.kind == KIND_FIGURE:
        for ref in reading.refs:
            at = manuscript.captions.get((ref.kind, ref.number))
            if at is not None:
                out["근거"].append(_evidence(manuscript, [at], ref.label, pages, config))
                if previous is not None:
                    before = previous.captions.get((ref.kind, ref.number))
                    if before is not None and previous.compacts[before] != manuscript.compacts[at]:
                        out["비고"].append(f"캡션이 바뀜: '{previous.paras[before].text}' → '{manuscript.paras[at].text}'")
        out["비고"].append("그림 속 내용에 대한 의견 — 그림 속 글은 원고 글에 없어 그림을 눈으로 확인")
        for key in reading.keys:
            hits = find(manuscript, key, region, config)
            out["비고"].append(f"'{key}': 캡션 주변 글에 {'있음' if hits else '없음'}")
        return out

    keys = reading.keys or reading.sentences
    if not keys:
        out["비고"].append("원고에서 찾을 핵심어를 뽑지 못함 — 의견을 읽고 해당 범위를 직접 확인")
        return out
    inside, elsewhere, missing = [], [], []
    for key in keys:
        hits = find(manuscript, key, region, config)
        if hits:
            inside.append(key)
            out["근거"].append(_evidence(manuscript, hits, key, pages, config))
            continue
        hits = [] if whole else find(manuscript, key, None, config)
        if hits:
            elsewhere.append(key)
            out["근거"].append(_evidence(manuscript, hits, key, pages, config))
        else:
            missing.append(key)
    if inside:
        out["비고"].append(f"범위 안에 있음: {', '.join(inside)}")
    if elsewhere:
        out["비고"].append(f"범위 밖에서만 찾음: {', '.join(elsewhere)}")
    if missing:
        out["비고"].append(f"원고에서 찾지 못함: {', '.join(missing)}")

    if opinion.group == SUMMARY:
        out["비고"].append("종합 의견 — 가리키는 자리가 없어 판정 후보를 내지 않음, 근거를 보고 확인")
    elif missing and not inside and not elsewhere:
        out["판정"] = NOT_REFLECTED
        out["수정 제안"] = f"{where.replace(' 구간', '').replace(' 캡션 주변', '')}에 {', '.join(repr(k) for k in missing)} 내용을 넣을지 검토"
    elif inside and not elsewhere and not missing and not whole:
        out["판정"] = REFLECTED
        if previous is not None:
            before_region, _, _ = locate(opinion, reading, previous, config)
            if all(find(previous, key, before_region, config) for key in inside):
                out["판정"] = CHECK
                out["비고"].append("반영 전 원고에도 같은 범위에 있던 표현 — 의견에 따라 바뀐 것인지 확인")
            else:
                out["비고"].append("반영 전 원고에 없던 표현이 생김")
    elif whole and inside and not missing:
        out["비고"].append("의견이 가리키는 자리를 정하지 못해 원고 전체에서 찾음 — 자리를 확인")
    return out


def _term(out: dict, reading: Reading, manuscript: Manuscript, region: list[int], whole: bool, pages, config: OpinionConfig) -> dict:
    """용어 변경 의견: 새 용어·옛 용어가 범위와 원고 전체에 몇 곳 있는지 세고 집필자에게 묻는다(근거는 범위 안 것을 먼저)."""
    inside_counts, all_counts, remain = [], [], []
    for label, terms in (("새 용어", reading.new_terms), ("옛 용어", reading.old_terms)):
        for term in terms:
            near = [] if whole else find(manuscript, term, region, config)
            every = find(manuscript, term, None, config)
            if near or every:
                out["근거"].append(_evidence(manuscript, near or every, term, pages, config))
            if not whole:
                inside_counts.append(f"{label} '{term}' {len(near)}곳")
            all_counts.append(f"{label} '{term}' {len(every)}곳")
            if label == "옛 용어" and every:
                remain.append(f"'{term}' {len(every)}곳({', '.join(sorted({manuscript.paras[i].where for i in every}))})")
    out["비고"].append("용어 변경 의견 — 즉시 반영으로 보지 않고 집필자에게 확인(REQ-02-003)")
    if any(ref.kind == "그림" for ref in reading.refs):
        out["비고"].append("그림 속 글일 수 있음 — 원고 글에 없으면 그림을 눈으로 확인")
    if inside_counts:
        out["비고"].append(f"{out['찾은 범위']}: " + ", ".join(inside_counts))
    out["비고"].append("원고 전체: " + ", ".join(all_counts))
    pair = " → ".join(filter(None, ["/".join(reading.old_terms), "/".join(reading.new_terms)]))
    out["집필자 확인"] = f"용어 변경({pair})을 원고에 적용할지 확인해 주세요." + (f" 옛 용어가 남은 곳: {'; '.join(remain)}" if remain else "")
    if remain and reading.new_terms:
        out["수정 제안"] = f"남은 '{reading.old_terms[0]}'을(를) '{reading.new_terms[0]}'(으)로 바꿀지 검토"
    return out
