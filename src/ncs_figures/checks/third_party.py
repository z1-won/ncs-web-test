"""⑨ 제3자 원본 AI 수정 — AI 활용 표기가 '수정 보완'이고 출처가 집필진 제작이 아니면(표기 예 3: 기존 이미지 보정)
원 출처의 이용허락 확인이 필요하다고 표시한다. 이용허락 여부를 판정하지 않는다(사람 확인)."""

from __future__ import annotations

import re

from ncs_core.source_line import ai_type_candidates
from ncs_core.text import NA, O, TRI

from ..models import CheckOutcome


THIRD_PARTY = {"기존 학습모듈", "공공누리", "웹·검색", "스크린숏", "문헌"}   # 출처 검토(008)와 같은 묶음


def check_ai_action(item, res, cfg, prior) -> list[CheckOutcome]:
    """⑦ 생성·수정 구분 — '생성함'·'수정 보완함'이 실제 활용 유형과 맞는가(REQ-02-008). 근거 세 가지를 모은다(모두 규칙, 모델 호출 없음):
      ① 출처 줄과의 짝(규칙)          원 출처가 있는데 '생성함' / 원 출처 없이 '수정 보완함'
      ② 서약서 결과물 현황 비고        비고에 '생성'·'수정'이 적혀 있으면 표기와 맞대기(제출 서류를 올렸을 때)
      ③ 그림 DB(④·⑧)                 '생성함'인데 기존 그림과 같거나 비슷함 → 기존 그림을 고친 것일 수 있음
    하나라도 어긋나면 △(사람 확인).
    (11-21 그림 모델 추정은 뺐음 — 눈으로 보는 추정이라 근거가 약하고 그림마다 호출 비용이 듦)"""
    marker = item.ai
    if marker is None:
        return [CheckOutcome("⑦생성·수정 구분", NA)]
    action = marker.action
    kind = item.source.kind if item.source else None
    problems, agree, fixes = [], [], []
    # ① 출처 줄과의 짝
    if action == "생성" and kind in THIRD_PARTY:
        problems.append(f"원 출처({kind})가 있는데 '생성함' — 남의 자료를 AI로 고쳤다면 '수정 보완함', 참고만 해 새로 만들었다면 출처를 '집필진 제작'으로")
        fixes.append("AI 활용 줄을 '수정 보완함'으로 고치거나 출처를 '집필진 제작'으로")
    elif action == "수정 보완" and item.source is None:
        problems.append("'수정 보완함'인데 무엇을 고쳤는지(원 출처 줄)가 없음")
        fixes.append("고친 원본의 출처 줄 추가")
    # ② 서약서 비고
    sub = getattr(res, "submissions", None)
    entry = sub.ai_of(item.ctx.figure_label, item.ctx.caption) if sub and sub.ai else None
    stated = None
    if entry and entry.note:
        stated = "수정 보완" if re.search(r"수정|보완|보정", entry.note) else "생성" if re.search(r"생성|창작", entry.note) else None
    if stated and stated != action:
        problems.append(f"서약서 비고는 '{entry.note}'인데 원고 표기는 '{action}함'")
    elif stated:
        agree.append("서약서 비고와 같음")
    # ③ 그림 DB
    if action == "생성":
        same = prior.get("matches") or ()
        close = [m for m, _ in prior.get("similar_matches") or ()]
        hit = (same or close or [None])[0]
        if hit is not None:
            problems.append(f"'생성함'인데 기존 그림({hit.module} {hit.figure_label or ''})과 {'같음' if same else '비슷함'} — "
                            "기존 그림을 AI로 고쳤다면 '수정 보완함'과 원 출처가 필요")
            fixes.append("기존 그림을 바탕으로 했는지 확인하고, 그렇다면 '수정 보완함'과 원 출처 표기")
    if problems:
        return [CheckOutcome("⑦생성·수정 구분", TRI, " / ".join(problems), suggestion=" / ".join(dict.fromkeys(fixes)) or None)]
    note = f"'{action}함' — 출처({kind or '없음'})와 짝이 맞음" + (f" · {', '.join(agree)}" if agree else "")
    return [CheckOutcome("⑦생성·수정 구분", O, note)]


def check_third_party(item, res, cfg, prior) -> list[CheckOutcome]:
    if item.ai is None or item.ai.action != "수정 보완":
        return [CheckOutcome("⑨제3자 원본", NA)]
    if ai_type_candidates(item.source, item.ai) == (3,):
        origin = item.source.text if item.source else "출처 없음"
        return [CheckOutcome("⑨제3자 원본", TRI, f"제3자 원본을 AI로 수정 보완함 — 원 출처의 이용허락 확인 필요: 「{origin[:60]}」",
                             suggestion="원 저작물의 이용허락 증빙 확인(공공누리·공유마당은 해당 유형 조건 확인)")]
    return [CheckOutcome("⑨제3자 원본", NA, "집필진 제작 원본을 AI로 수정 보완함")]
