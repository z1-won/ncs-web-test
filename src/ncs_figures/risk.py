"""⑤ 위험도 — 점검 결과를 입력으로 받는 규칙표(2026-11-21 다시 설계). 모델이 위험도를 정하지 않는다.

점검을 세 갈래로 나눠 무게를 다르게 둔다.
  권리        남의 것을 근거 없이 썼나 — ② 마크·워터마크, ④ DB 같은 그림과 그 권리, ⑨ 제3자 원본, ⑧ AI 결과물 유사
  사실 일치   적은 것과 실제가 같나 — ④ 출처와 DB의 원래 출처, ③ 캡션, ⑥ 수록 현황·증빙, ⑦ 서약서 대조, ① 필수 요소
  표기 형식   ① 출처 양식(F14), ⑦ AI 표기 양식 — 편집 문제라 위험도에 넣지 않고 비고에만 남긴다
규칙을 모두 보고 가장 높은 단계를 쓴다. 근거는 그 단계에 걸린 규칙을 모두 [갈래]와 함께 남긴다.

고위험
  H1 출처 없음 + (DB에 같은 그림 또는 그림 속 저작권 문구)      남의 그림을 출처 없이 씀
  H2 DB에 같은 그림이 있는데 그 권리가 재사용 불가·미확인        권리 범위 밖 재사용
  H3 출처는 '집필진 제작'인데 DB의 다른 그림과 같음              출처 표기가 사실과 다름
  H4 남의 원본을 AI로 고쳤는데 출처에 이용허락 근거 없음(⑨)
  H5 그림 속 스톡 워터마크 글자(shutterstock 등)
확인 필요
  M1 출처 없음
  M2 DB 그림과 같고 권리도 되는데 출처가 DB의 원래 출처와 다름   (④ △)
  M3 ⑥·⑦·⑧·②·⑨·① 필수 요소에 X·△
  M4 ③ 캡션과 다를 수 있음(mismatch만 — 근거 부족·검증 실패는 비고에만)
판정 안 함
  꼭 해야 하는 점검(cfg.required_checks, 기본 ③ 캡션 일치)이 미실행 — 위험도를 정하지 않는다(2026-11-21).
  그때까지 찾은 문제는 근거에 '[판독 전]'으로 남긴다.
문제없음  나머지. DB 재사용인데 권리·출처가 맞으면 그 사실을 근거에 적는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ncs_core.text import TRI, X

from .db import licensed
from .models import CheckOutcome, FigureItem, Match

LEVELS = ("문제없음", "확인 필요", "고위험")
BLOCKED = "판정 안 함"

# 체크 이름 → 갈래(화면·검수표의 근거 앞에 붙는다)
CATEGORY = {
    "①출처 있음": "출처", "①출처 요건": "출처", "④DB 대조": "권리", "②마크·워터마크": "권리", "⑨제3자 원본": "권리",
    "⑧AI 결과물 유사": "권리", "③캡션 일치": "그림 내용", "⑥수록 현황": "제출 서류", "⑥증빙": "제출 서류",
    "⑦AI 현황 대조": "제출 서류", "⑦생성·수정 구분": "AI 활용",
}
# M3에서 X·△를 보는 점검(①출처 있음·④·③은 따로 규칙이 있다. 표기 형식(①출처 형식·⑦AI 표기)은 넣지 않는다)
REVIEW_CHECKS = ("①출처 요건", "②마크·워터마크", "⑨제3자 원본", "⑥수록 현황", "⑥증빙", "⑦AI 현황 대조", "⑧AI 결과물 유사",
                 "⑦생성·수정 구분")
RISK_CHECKS = ("①출처 있음", "④DB 대조", "③캡션 일치", *REVIEW_CHECKS)   # 위험도에 들어가는 점검(다른 모듈이 참조)


@dataclass(frozen=True)
class Facts:
    """규칙의 입력. checks: 이름 → 결과, matches: ④가 찾은 같은 그림, prior: 점검이 남긴 값(OCR 결과·캡션 판정)."""

    checks: dict
    matches: tuple[Match, ...]
    item: FigureItem
    prior: dict

    def value(self, name: str) -> str | None:
        outcome = self.checks.get(name)
        return outcome.value if outcome else None

    def note(self, name: str) -> str:
        outcome = self.checks.get(name)
        return outcome.note if outcome else ""

    @property
    def no_source(self) -> bool:
        return self.value("①출처 있음") == X

    @property
    def marks(self) -> dict:
        return self.prior.get("marks_found") or {}


@dataclass(frozen=True)
class RiskRule:
    name: str
    level: str                       # 고위험 · 확인 필요
    category: str
    reason: Callable[[Facts], str | None]   # 걸리면 근거 문장, 아니면 None


def _db_where(m: Match) -> str:
    return f"{m.module} {m.figure_label or '(캡션 없음)'}"


def _h1(f: Facts):
    if not f.no_source:
        return None
    if f.matches:
        return f"출처 표기가 없는데 기존 그림({_db_where(f.matches[0])})과 같음"
    if f.marks.get("copyright"):
        return f"출처 표기가 없는데 그림 속에 저작권 문구가 있음: {', '.join(f.marks['copyright'])}"
    return None


def _h2(f: Facts):
    bad = [m for m in f.matches if not licensed(m.rights_status)]
    if bad and not f.no_source:
        return f"기존 그림({_db_where(bad[0])})과 같은데 그 권리가 '{bad[0].rights_status or '미확인'}' — 재사용 근거 없음"
    return None


def _h3(f: Facts):
    source = f.item.source
    if f.matches and source is not None and source.kind == "집필진 제작" and all(licensed(m.rights_status) for m in f.matches):
        return f"출처를 집필진 제작으로 적었으나 기존 그림({_db_where(f.matches[0])})과 같음 — 출처 표기가 사실과 다를 수 있음"
    return None


def _h4(f: Facts):
    source = f.item.source
    if f.value("⑨제3자 원본") == TRI and not (source and (source.kogl_type or "이용허락" in source.text)):
        return "남의 원본을 AI로 고쳤는데 출처에 이용허락 근거가 없음"
    return None


def _h5(f: Facts):
    if f.marks.get("stock"):
        return f"그림 속에 스톡 사진 워터마크 글자: {', '.join(f.marks['stock'])} — 유료 이미지일 가능성"
    return None


def _m1(f: Facts):
    return "출처 표기 없음" if f.value("①출처 있음") in (X, TRI) else None


def _m2(f: Facts):
    return f"출처가 DB의 원래 출처와 다름 — {f.note('④DB 대조')}" if f.value("④DB 대조") == TRI else None


def _m4(f: Facts):
    if f.prior.get("caption_verdict") == "mismatch":
        return f.note("③캡션 일치")
    return None


def _m3_rules() -> tuple[RiskRule, ...]:
    def make(name):
        return lambda f: f"{name[1:]}: {f.note(name)}" if f.value(name) in (X, TRI) else None
    return tuple(RiskRule(f"M3{name[0]}", "확인 필요", CATEGORY[name], make(name)) for name in REVIEW_CHECKS)


DEFAULT_RULES: tuple[RiskRule, ...] = (
    RiskRule("H1", "고위험", "권리", _h1),
    RiskRule("H2", "고위험", "권리", _h2),
    RiskRule("H3", "고위험", "출처", _h3),
    RiskRule("H4", "고위험", "권리", _h4),
    RiskRule("H5", "고위험", "권리", _h5),
    RiskRule("M1", "확인 필요", "출처", _m1),
    RiskRule("M2", "확인 필요", "출처", _m2),
    *_m3_rules(),
    RiskRule("M4", "확인 필요", "그림 내용", _m4),
)


def assess(checks: list[CheckOutcome], matches: tuple[Match, ...], item: FigureItem, *,
           rules: tuple[RiskRule, ...] = DEFAULT_RULES, required: frozenset[str] = frozenset(),
           prior: dict | None = None) -> tuple[str, tuple[str, ...]]:
    """(위험도, 근거). 양식·양식 후보는 부르지 않는다. 근거는 '[갈래] 문장' 꼴."""
    facts = Facts(checks={c.name: c for c in checks}, matches=tuple(matches), item=item, prior=prior or {})
    hits = []
    for rule in rules:
        reason = rule.reason(facts)
        if reason:
            hits.append((rule, reason))
    skipped = [c for c in checks if c.value is None]
    missing = [c for c in skipped if c.name in required]
    if missing:
        reasons = [f"[미실행] {c.name}({c.skipped}) — 이 점검 없이는 위험도를 정하지 않음" for c in missing]
        reasons += [f"[판독 전] {rule.level}: [{rule.category}] {reason}" for rule, reason in
                    sorted(hits, key=lambda h: -LEVELS.index(h[0].level))]
        return BLOCKED, tuple(dict.fromkeys(reasons))
    level = max((LEVELS.index(r.level) for r, _ in hits), default=0)
    if level:
        reasons = [f"[{rule.category}] {reason}" for rule, reason in hits if LEVELS.index(rule.level) == level]
        return LEVELS[level], tuple(dict.fromkeys(reasons))
    reasons = ["확인한 점검에서 문제 없음"]
    if matches:
        reasons.append(f"[권리] 기존 그림 재사용 — 권리·출처 맞음({_db_where(matches[0])}, {matches[0].rights_status})")
    if facts.value("①출처 형식") == X or facts.value("⑦AI 표기") in (X, TRI):
        reasons.append("[표기 형식] 출처·AI 표기 양식 문제만 있음(편집 문제 — 위험도에 넣지 않음)")
    caption = prior.get("caption_verdict") if prior else None
    if caption in ("uncertain", "검증 실패"):
        reasons.append("[그림 내용] 캡션 판정을 모델이 못 함(위험도에 넣지 않음)")
    if skipped:
        reasons.append("미실행: " + ", ".join(f"{c.name}({c.skipped})" for c in skipped))
    return "문제없음", tuple(reasons)
