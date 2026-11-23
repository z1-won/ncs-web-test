"""④ DB 대조 — 그림 DB(스텁 또는 010 DB)에서 원고 그림과 같은 그림(완전 일치·지각 해시 거리 10 이하)을 찾고,
그 그림의 권리와 원래 출처를 원고 출처 줄과 맞댄다. 찾은 그림(prior['matches'])은 위험도 규칙의 입력이 된다.

  같은 그림 없음                                   → O
  같은 그림 있음, 출처 없음                         → X  (위험도 H1)
  같은 그림 있음, 권리가 재사용 불가·미확인          → X  (위험도 H2)
  같은 그림 있음, 출처는 '집필진 제작'               → X  (위험도 H3 — 출처 표기가 사실과 다름)
  같은 그림 있음, 권리는 되는데 출처가 DB와 다름     → △  (위험도 M2 — 출처 정정)
  같은 그림 있음, 권리·출처 모두 맞음               → O  (재사용 — 권리 확인됨)
모델을 쓰지 않는다. 바꿔 쓸 그림 찾기(같은 주제)는 판정과 따로 pipeline.replacements_for가 한다.
"""

from __future__ import annotations

from ncs_core.text import O, TRI, X

from ..db import licensed
from ..models import CheckOutcome

NAME = "④DB 대조"
KIND = {"exact": "완전히 같음", "near": "거의 같음"}


def where(match) -> str:
    title = f" {match.figure_title}" if match.figure_title else ""
    return f"{match.module} {match.figure_label or '(캡션 없음)'}{title}"


def same_module(a: str | None, b: str | None) -> bool:
    return bool(a and b) and a.replace("LM", "")[:10] == b.replace("LM", "")[:10]


def source_problem(source, matches) -> str | None:
    """권리는 되는 재사용일 때 원고 출처가 DB의 원래 출처와 맞는가. 맞으면 None, 다르면 이유."""
    best = matches[0]
    if source.cited_module:
        if any(same_module(source.cited_module, m.module) or same_module(source.cited_module, m.source_text or "") for m in matches):
            return None
        return f"출처는 {source.cited_module}인데 DB에서는 {where(best)}과 같음"
    if source.kind == "공공누리" and best.license_type and best.license_type.startswith("KOGL-") and source.kogl_type:
        db_type = best.license_type.split("-", 1)[1]
        if db_type not in ("?", source.kogl_type):
            return f"출처는 공공누리 제{source.kogl_type}유형인데 DB의 원 그림은 제{db_type}유형"
        return None
    if best.source_text and source.text.strip() == best.source_text.strip():
        return None
    if best.source_kind in ("집필진 제작", "기존 학습모듈") and source.kind not in ("기존 학습모듈",):
        return f"출처는 '{source.kind}'인데 DB에서는 학습모듈 그림({where(best)})과 같음 — 기존 학습모듈 인용으로 적어야 함"
    if best.source_kind and best.source_kind != source.kind:
        return f"출처는 '{source.kind}'인데 DB의 원래 출처는 '{best.source_kind}'"
    return None


def check_db(item, res, cfg, prior) -> list[CheckOutcome]:
    pairs = res.lookup.find(item.image_id, item.phash, exclude_module=prior.get("module_code", ""))
    matches = tuple(m for m, _ in pairs)
    prior["matches"] = matches
    if not matches:
        size = res.lookup.size() if hasattr(res.lookup, "size") else {}
        return [CheckOutcome(NAME, O, f"그림 DB({size.get('그림', '?')}개)에 같은 그림 없음")]
    best = matches[0]
    found = "; ".join(f"{KIND[m.match_type]}: {where(m)} — 권리 {m.rights_status or '미확인'}"
                      + (f", 원래 출처 「{m.source_text}」" if m.source_text else "") for m in matches[:3])
    source = item.source
    if source is None:
        return [CheckOutcome(NAME, X, f"출처 줄이 없는데 기존 그림과 같음 — {found}",
                             suggestion=f"출처를 원 그림 기준으로 적기(예: {best.module} 인용)")]
    if not all(licensed(m.rights_status) for m in matches):
        return [CheckOutcome(NAME, X, f"기존 그림과 같은데 그 권리가 재사용 가능한지 확인되지 않음 — {found}",
                             suggestion="원 그림의 이용허락(권리자·범위)을 확인하거나 다른 그림으로 바꾸기")]
    if source.kind == "집필진 제작":
        return [CheckOutcome(NAME, X, f"출처를 집필진 제작으로 적었으나 기존 그림과 같음 — {found}",
                             suggestion="새로 만든 그림인지 확인하고, 기존 그림이면 출처를 그 그림 기준으로 고치기")]
    problem = source_problem(source, matches)
    if problem:
        return [CheckOutcome(NAME, TRI, f"{problem} — {found}", suggestion="출처를 원 그림 기준으로 고치기")]
    return [CheckOutcome(NAME, O, f"기존 그림 재사용 — 권리·출처 맞음: {found}")]
