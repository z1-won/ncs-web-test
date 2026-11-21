"""세분류 건의 단계 정의표와 상태 전이(REQ-02-007) — 건 → 권 → 판본 → 사건 구조에서 '무엇이 언제 어떤 상태가 되는가'만 맡는다.

DB를 읽지 않는다. 화면과 상태 전이는 STAGES를 읽어 움직이므로, 단계가 바뀌면 이 표만 고친다
(설계: 프로젝트 문서 'PoC2_설계_세분류건_흐름과_역할' 5~7절. 근거 우선순위는 과업 안내 v0.22, F11 매뉴얼 제2장).

- 단위: 건(세분류 한 건 전체에 하나) 또는 권(학습모듈 한 권마다 하나).
- 유형: 넘기기(대기 → 완료), 왕복(대기 → 제출됨 → 보완 요청 ↔ 제출됨 → 완료), 외부 판정(대기 → 제출됨 → 판정 도착 → 완료).
- 상태는 따로 저장하지 않는다. 사건(case_events)을 시간순으로 접어서 얻는다(states) — 사건이 유일한 근거이고 지우지 않는다.
- 누가 할 수 있는가: 제출은 submit 역할, 보완 요청·판정 도착·완료·되돌림은 confirm 역할. PoC에서는 직능연·검토진·위원의 화면이 없으므로
  에디터가 그 확인을 대신 적을 수 있고, 그 사건에는 '대신 기록'이 남는다(PROXY_ROLE). 집필진은 대신 적지 못한다.
- 순서를 건너뛴 완료(제출이나 판정 없이 완료)는 막지 않되 사유(메모)를 받는다 — 일관성 규칙 2.
- 권은 단계 순서대로 흐른다: 완료가 아닌 첫 단계가 그 권이 지금 서 있는 곳이다(current). 건 단위 단계(개발계획서, 심의)는 그 건의 모든 권이 함께 지난다.

정하지 못한 것: 심의가 세분류 전체에 하나인지 권마다인지, 개선 유형별로 건너뛰는 단계. 사건은 건에도 권에도 붙을 수 있게 되어 있어
심의의 단위가 정해지면 STAGES의 unit만 바꾸면 된다. 개선 유형은 건에 적어 두기만 하고 아직 단계를 줄이지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass

CASE, VOLUME = "건", "권"
HANDOFF, ROUNDTRIP, EXTERNAL = "넘기기", "왕복", "외부 판정"
WAITING, SUBMITTED, REQUESTED, VERDICT, DONE = "대기", "제출됨", "보완 요청", "판정 도착", "완료"
SUBMIT, REQUEST, JUDGE, COMPLETE, REOPEN = "submit", "request", "verdict", "done", "reopen"
ACTIONS = {SUBMIT: "제출", REQUEST: "보완 요청", JUDGE: "판정 도착", COMPLETE: "완료", REOPEN: "되돌림"}
# 단계에 속하지 않는 사건(건을 만듦, 권을 넣음, 집필자를 정함)
CREATED, VOLUME_ADDED, AUTHOR_SET = "created", "volume_added", "author_set"
NOTES = {CREATED: "건을 만듦", VOLUME_ADDED: "권을 넣음", AUTHOR_SET: "담당 집필자를 정함"}
IMPROVEMENTS = ("기존개선", "최소개선", "양식편집")       # 과업 안내의 개선 유형. migrations 013의 CHECK와 같아야 한다(test_flow가 검사한다)
PROXY_ROLE = "editor"
MANAGER_ROLES = ("editor", "krivet")                     # 건을 만들고 권에 집필자를 붙이는 역할


class FlowError(ValueError):
    """지금 상태에서 할 수 없는 전이. 메시지는 화면에 그대로 보인다."""


class Denied(FlowError):
    """이 계정의 역할이나 담당으로는 할 수 없는 일."""


@dataclass(frozen=True)
class Stage:
    key: str
    name: str
    unit: str                     # CASE | VOLUME
    kind: str                     # HANDOFF | ROUNDTRIP | EXTERNAL
    submit: tuple[str, ...]       # 제출하는 역할
    confirm: tuple[str, ...]      # 보완 요청·판정·완료를 적는 역할
    who: str                      # 화면에 보일 담당 설명
    evidence: str                 # 근거가 되는 기록(기능)
    legacy: int | None = None     # 원고 진행 현황(모듈 코드별 7단계, ncs_service.progress)의 단계 번호
    manuscript: bool = False      # 제출할 때 원고 파일(판본)을 올리는 단계
    review: bool = False          # 그 판본으로 원고 검수를 돌리는 단계. 검수 기록 없이 보완 요청·완료를 하려면 사유를 적는다

    def public(self) -> dict:
        return {"key": self.key, "name": self.name, "unit": self.unit, "kind": self.kind, "who": self.who, "evidence": self.evidence,
                "submit": list(self.submit), "confirm": list(self.confirm), "manuscript": self.manuscript, "review": self.review}


STAGES: tuple[Stage, ...] = (
    Stage("plan", "개발계획서", CASE, ROUNDTRIP, ("krivet", "author"), ("krivet",), "직능연 전달, 집필진 정정, 직능연 확인", "개발계획서 점검", 1),
    # 초고본 편집 검수는 설계 초안에서 넘기기였으나, 집필진이 초고본을 올리고 에디터가 보완을 요청하는 왕복으로 바꿨다(2026-11-21)
    Stage("draft_edit", "초고본 편집 검수", VOLUME, ROUNDTRIP, ("author",), ("editor",), "집필진 제출, 에디터 확인(F02)", "원고 검수", 2,
          manuscript=True, review=True),
    Stage("review1", "1차 검토", VOLUME, EXTERNAL, ("author",), ("reviewer",), "집필진 제출, 검토진 판정", "1차 검토의견서"),
    Stage("revision", "수정본과 1차 의견 반영", VOLUME, ROUNDTRIP, ("author",), ("editor", "krivet"), "집필진 제출, 에디터 확인, 직능연 확정",
          "의견 반영 검토, 원고 검수", 3, manuscript=True, review=True),
    Stage("review2", "2차 검토", VOLUME, EXTERNAL, ("author",), ("reviewer",), "집필진 제출, 검토진 판정", "2차 검토의견서"),
    Stage("final", "최종본과 2차 의견 반영", VOLUME, ROUNDTRIP, ("author",), ("editor", "krivet"), "집필진 제출, 에디터 확인, 직능연 확정",
          "의견 반영 검토", 4, manuscript=True),
    Stage("deliberation", "심의", CASE, EXTERNAL, ("author",), ("committee",), "개발기관이 심의본 제출, 소위원회 위원 판정", "심의의견서"),
    Stage("polish", "심의 반영과 최종 윤문", VOLUME, ROUNDTRIP, ("author",), ("editor",), "집필진 제출, 에디터 확인", "심의의견 반영 검토, 원고 검수", 5,
          manuscript=True, review=True),
    Stage("final_f02", "최종본 검수(F02)", VOLUME, HANDOFF, ("editor",), ("editor",), "에디터", "원고 검수(전체)", 6, review=True),
    Stage("final_f03", "최종 판정(F03)", VOLUME, HANDOFF, ("editor",), ("krivet",), "직능연", "F03 검수"),
    Stage("volume", "분량", VOLUME, ROUNDTRIP, ("author",), ("krivet",), "개발기관 산정, 직능연 확인", "원고 분량", 7),
    Stage("rights", "권리 증빙", VOLUME, ROUNDTRIP, ("author",), ("editor",), "개발기관 제출(1차 검토 후 4주 이내), 에디터 확인", "권리 증빙 점검", 7),
)
BY_KEY = {stage.key: stage for stage in STAGES}
CASE_STAGES = tuple(stage for stage in STAGES if stage.unit == CASE)
VOLUME_STAGES = tuple(stage for stage in STAGES if stage.unit == VOLUME)
BASIS = "과업 안내 v0.22와 F11 매뉴얼(2026) 제2장 개발 절차. 설계 문서 6절의 단계 정의표"

# 유형마다 (지금 상태, 행동) → 다음 상태. 여기에 없는 완료는 '건너뛴 완료'로 사유를 받는다(next_state)
TRANSITIONS: dict[str, dict[tuple[str, str], str]] = {
    HANDOFF: {(WAITING, COMPLETE): DONE, (DONE, REOPEN): WAITING},
    ROUNDTRIP: {(WAITING, SUBMIT): SUBMITTED, (REQUESTED, SUBMIT): SUBMITTED, (SUBMITTED, SUBMIT): SUBMITTED,
                (SUBMITTED, REQUEST): REQUESTED, (SUBMITTED, COMPLETE): DONE, (DONE, REOPEN): SUBMITTED},
    EXTERNAL: {(WAITING, SUBMIT): SUBMITTED, (SUBMITTED, SUBMIT): SUBMITTED, (SUBMITTED, JUDGE): VERDICT,
               (VERDICT, COMPLETE): DONE, (DONE, REOPEN): VERDICT},
}


def legacy_stages(number: int) -> tuple[Stage, ...]:
    """원고 진행 현황의 단계 번호 → 이 표의 단계(7 '분량과 권리 증빙'은 둘)."""
    return tuple(stage for stage in STAGES if stage.legacy == number)


def roles_for(stage: Stage, action: str) -> tuple[str, ...]:
    return stage.submit if action == SUBMIT else stage.confirm


def allowed(stage: Stage, action: str, role: str) -> tuple[bool, bool]:
    """(할 수 있는가, 대신 기록인가)."""
    if role in roles_for(stage, action):
        return True, False
    return (role == PROXY_ROLE), (role == PROXY_ROLE)


def next_state(stage: Stage, state: str, action: str, *, note: str = "", before: str | None = None) -> str:
    """전이표를 따라 다음 상태. 순서를 건너뛴 완료는 사유(note)가 있으면 받는다.
    완료를 되돌리면 완료하기 직전의 상태(before)로 간다 — 건너뛴 완료를 되돌렸는데 '제출됨'이 되지 않게."""
    if action not in ACTIONS:
        raise FlowError("할 수 없는 행동입니다")
    if state == DONE and action == REOPEN and before:
        return before
    target = TRANSITIONS[stage.kind].get((state, action))
    if target:
        return target
    if action == COMPLETE and state != DONE:
        if not note.strip():
            raise FlowError(f"‘{stage.name}’은 지금 ‘{state}’입니다. 순서를 건너뛰어 완료하려면 사유를 적어 주세요")
        return DONE
    if action not in {a for (_, a) in TRANSITIONS[stage.kind]}:
        raise FlowError(f"‘{stage.name}’은 {stage.kind} 단계라서 ‘{ACTIONS[action]}’을 쓰지 않습니다")
    raise FlowError(f"‘{stage.name}’은 지금 ‘{state}’라서 ‘{ACTIONS[action]}’을 할 수 없습니다")


def states(events: list[dict]) -> dict[tuple[str | None, str], dict]:
    """사건(시간순, {'volume_id', 'stage', 'action', 'at', 'actor', 'note'}) → {(권 id 또는 None, 단계 key): {'state', 'at', 'by', 'note', 'before'}}
    (before는 완료하기 직전의 상태).
    단계에 속하지 않는 사건은 건너뛴다. 저장할 때 이미 전이를 검사했으므로 여기서는 표를 따르되, 표에 없는 완료는 완료로 본다."""
    out: dict[tuple[str | None, str], dict] = {}
    for event in events:
        stage = BY_KEY.get(event["stage"])
        if stage is None or event["action"] not in ACTIONS:
            continue
        key = (event.get("volume_id"), stage.key)
        last = out.get(key) or blank()
        now = last["state"]
        if now == DONE and event["action"] == REOPEN:
            target = last["before"] or TRANSITIONS[stage.kind][(DONE, REOPEN)]
        else:
            target = TRANSITIONS[stage.kind].get((now, event["action"])) or (DONE if event["action"] == COMPLETE else now)
        before = now if (target == DONE and now != DONE) else last["before"]
        out[key] = {"state": target, "at": event["at"], "by": event["actor"], "note": event.get("note", ""), "before": before}
    return out


def turn(stage: Stage, state: str) -> tuple[str, ...]:
    """지금 누구 차례인가(역할). 완료된 단계는 빈 값."""
    if state == DONE:
        return ()
    if stage.kind == HANDOFF:
        return stage.confirm
    return stage.submit if state in (WAITING, REQUESTED) else stage.confirm


def available(stage: Stage, state: str, role: str) -> list[dict]:
    """이 역할이 지금 할 수 있는 행동: [{'action', 'name', 'proxy'(대신 기록), 'needs_note'(사유가 있어야 함)}]. 되돌림은 넣지 않는다(reopenable)."""
    out = []
    for (at, action) in TRANSITIONS[stage.kind]:
        if at != state or action == REOPEN:
            continue
        ok, proxy = allowed(stage, action, role)
        if ok:
            out.append({"action": action, "name": ACTIONS[action], "proxy": proxy, "needs_note": False})
    if state != DONE and (state, COMPLETE) not in TRANSITIONS[stage.kind]:
        ok, proxy = allowed(stage, COMPLETE, role)
        if ok:
            out.append({"action": COMPLETE, "name": "사유를 적고 완료", "proxy": proxy, "needs_note": True})
    return out


def reopenable(stage: Stage, state: str, role: str) -> bool:
    return state == DONE and allowed(stage, REOPEN, role)[0]


def current(states_of: dict[str, dict]) -> Stage | None:
    """단계 순서대로 보아 아직 완료가 아닌 첫 단계 — 그 권(또는 건)이 지금 서 있는 곳. states_of = {단계 key: 상태}. 모두 끝났으면 None."""
    return next((stage for stage in STAGES if states_of.get(stage.key, {}).get("state", WAITING) != DONE), None)


def blank() -> dict:
    return {"state": WAITING, "at": None, "by": None, "note": "", "before": None}
