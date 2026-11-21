"""원고 진행 현황(REQ-02-007 '원고별 편집·내용·저작권 검수 진행도 확인') — 한 원고(모듈 코드)의 기록을 단계와 진행도로 묶는다.

DB를 읽지 않는다: 기록을 모으는 일은 postgres.progress_sources가 하고, 여기서는 그 기록을 단계 7개와 진행도 세 가지로 바꾸기만 한다.

단계는 F11 매뉴얼(2026) 제2장 개발 절차(인쇄 16~17쪽) 11단계에서 연결할 기능이 있는 것만 추린 7개다
(사전 협의·킥오프·검토 회의·사업 마무리는 뺐다, 2026-11-21 결정).
단계의 상태는 담당자가 정한 값이 아니라 **남아 있는 기록으로 미룬 것**이다: 어느 기능을 돌린 기록이 있으면 '기록 있음'.
원고 검수 기록에는 초고본·수정본·최종본 구분이 없으므로, 처음 검수한 날을 초고본 검토에, 가장 최근 검수의 판정을 최종본 검수에 보인다.

의견 반영 검토와 권리 증빙 점검은 개수만 남긴다(summarize_opinion·summarize_rights) — 의견 문장·원고 문단·지적 내용은 저장하지 않는다.
"""

from __future__ import annotations

RECORDED, EMPTY = "기록 있음", "기록 없음"
OPINION, RIGHTS = "opinion", "rights"
KINDS = (OPINION, RIGHTS)
UNKNOWN_ROUND = "차수 모름"
OPINION_KEYS = ("총 의견", "조치 요구", "반영 후보", "미반영 후보", "확인 필요", "조치 불필요")
RIGHTS_KEYS = ("판정", "원고 그림", "목록 행", "적합", "부적합", "판단불가", "누락", "확인 필요")

# (번호, 이름, 누가, 이 화면에서 쓰는 기능, 기능 경로)
STAGES = (
    (1, "개발계획서", "집필진 작성, 에디터 점검", "개발계획서 점검", "/plan"),
    (2, "초고본 검토", "에디터 1차(편집, 형식)", "원고 검수", "/review"),
    (3, "수정본 검토", "에디터 2차, 1차 검토의견 반영 확인", "의견 반영 검토(1차 검토의견서)", "/opinion"),
    (4, "최종본 집필과 심의본 제출", "집필진, 2차 검토의견 반영 확인", "의견 반영 검토(2차 검토의견서)", "/opinion"),
    (5, "최종 윤문과 편집", "집필진이 심의의견 반영, 에디터 윤문", "의견 반영 검토(심의의견서)", "/opinion"),
    (6, "최종본 검수", "에디터, 직능연(적합 또는 부적합 판정)", "원고 검수(전체)", "/review"),
    (7, "분량과 권리 증빙", "개발기관 제출, 담당자 확인", "원고 분량, 권리 증빙 점검", "/volume"),
)
BASIS = "F11 매뉴얼(2026) 제2장 개발 절차(인쇄 16~17쪽)에서 연결할 기능이 있는 단계만 추림"


def summarize_opinion(result: dict) -> dict:
    """의견 반영 검토 결과(ncs_opinion.review) → 남길 개수. 의견 글·근거 문단은 넣지 않는다."""
    by_round: dict[str, dict] = {}
    for row in result.get("의견", []):
        counts = by_round.setdefault(row.get("차수") or UNKNOWN_ROUND, dict.fromkeys(OPINION_KEYS, 0))
        counts["총 의견"] += 1
        counts[row["판정"]] = counts.get(row["판정"], 0) + 1
        counts["조치 요구"] += row["판정"] != "조치 불필요"
    summary = result.get("요약", {})
    return {"전체": {key: summary.get(key, 0) for key in OPINION_KEYS}, "차수별": by_round,
            "생성형 AI": "사용" if str(result.get("LLM", "")).startswith("사용") else "미사용"}


def summarize_rights(report: dict) -> dict:
    """권리 증빙 점검 결과(ncs_rights) → 남길 개수와 판정. 현황표·지적사항은 넣지 않는다."""
    summary = report.get("요약", {})
    return {key: summary.get(key) for key in RIGHTS_KEYS}


def _latest(records: list[dict], kind: str) -> dict | None:
    return next((r for r in records if r["kind"] == kind), None)     # records는 최신순


def _round_records(records: list[dict], match) -> list[dict]:
    """차수가 match인 의견 반영 검토 기록(최신순) → [{'일시', '원고', '차수', 개수…}]."""
    out = []
    for record in records:
        if record["kind"] != OPINION:
            continue
        for name, counts in (record["counts"].get("차수별") or {}).items():
            if match(name):
                out.append({"일시": record["created_at"], "원고": record["manuscript"], "차수": name, **counts})
    return out


def _is_review(name: str) -> bool:
    return "심의" in name


def content_progress(records: list[dict]) -> dict:
    """내용 검수 진행도: 차수마다 가장 최근 의견 반영 검토의 개수(총 의견·반영 후보·미반영 후보·확인 필요)."""
    rounds: dict[str, dict] = {}
    for row in _round_records(records, lambda name: True):
        rounds.setdefault(row["차수"], row)
    rows = [rounds[name] for name in sorted(rounds)]
    total = {key: sum(row.get(key, 0) for row in rows) for key in OPINION_KEYS}
    return {"차수": rows, "합계": total if rows else None}


def editing_progress(latest_checks: list[dict]) -> dict:
    """편집 검수 진행도: 구성요소(검수 이름)마다 가장 최근 실행의 확인서 항목 판정 수."""
    items = {"적합": 0, "부적합": 0, "판단불가": 0, "그 밖": 0}
    checks = []
    for run in latest_checks:
        if run["check"] == "plan":
            continue
        own = {"적합": 0, "부적합": 0, "판단불가": 0, "그 밖": 0}
        for row in run.get("sheet") or []:
            verdict = row.get("검수결과")
            own[verdict if verdict in own else "그 밖"] += 1
        for key, value in own.items():
            items[key] += value
        checks.append({"검수": run["check"], "일시": run["created_at"], "판정": run["verdict"], **own})
    judged = items["적합"] + items["부적합"] + items["판단불가"]
    return {"구성요소": checks, "항목": items if checks else None,
            "적합 비율": round(items["적합"] / judged * 100, 1) if judged else None}


def build(module_code: str, sources: dict, *, name: str = "") -> dict:
    """기록 → 진행 현황. sources = postgres.progress_sources()의 값:
    {'reviews': {'count', 'first', 'last'}, 'plan': {'count', 'last', 'verdict'}, 'latest_checks': [...], 'last_group': {...}|None,
     'volume': {...}|None, 'records': [...], 'images': {'total', 'confirmed'}}"""
    records = sources.get("records", [])
    reviews, plan = sources.get("reviews") or {}, sources.get("plan") or {}
    group, volume, images = sources.get("last_group"), sources.get("volume"), sources.get("images") or {}
    rights = _latest(records, RIGHTS)
    first = _round_records(records, lambda n: n.startswith("1차") and not _is_review(n))
    second = _round_records(records, lambda n: n.startswith("2차") and not _is_review(n))
    review = _round_records(records, _is_review)

    def opinion_note(rows: list[dict]) -> str:
        row = rows[0]
        return f"의견 {row['총 의견']}개 중 반영 후보 {row['반영 후보']}, 미반영 후보 {row['미반영 후보']}, 확인 필요 {row['확인 필요']}"

    facts = {
        1: (bool(plan.get("count")), plan.get("last"), f"점검 {plan.get('count')}회, 최근 판정 {plan.get('verdict')}" if plan.get("count") else ""),
        2: (bool(reviews.get("count")), reviews.get("first"), f"처음 검수한 날. 검수 기록 {reviews.get('count')}건" if reviews.get("count") else ""),
        3: (bool(first), first[0]["일시"] if first else None, opinion_note(first) if first else ""),
        4: (bool(second), second[0]["일시"] if second else None, opinion_note(second) if second else ""),
        5: (bool(review), review[0]["일시"] if review else None, opinion_note(review) if review else ""),
        6: (bool(group), group["created_at"] if group else None,
            f"가장 최근 전체 검수 판정 {group['verdict']}(구성요소 {len(group['checks'])}개)" if group else ""),
        7: (bool(volume or rights), max(filter(None, [volume and volume["created_at"], rights and rights["created_at"]]), default=None),
            ", ".join(filter(None, [f"분량 {volume['pages']}매" if volume else "",
                                    f"권리 증빙 {rights['counts'].get('판정')}" if rights else ""]))),
    }
    stages = [{"번호": no, "이름": title, "담당": who, "기능": feature, "경로": path,
               "상태": RECORDED if facts[no][0] else EMPTY, "일시": facts[no][1], "내용": facts[no][2]}
              for no, title, who, feature, path in STAGES]
    return {
        "module_code": module_code, "학습모듈명": name,
        "단계": stages, "단계 근거": BASIS,
        "단계 안내": "단계의 상태는 남아 있는 기록으로 미룬 것이며 담당자가 확정한 값이 아닙니다. 원고 검수 기록에는 초고본, 수정본, 최종본 구분이 없습니다.",
        "진행도": {
            "편집 검수": editing_progress(sources.get("latest_checks", [])),
            "내용 검수": content_progress(records),
            "저작권 검수": {"권리 증빙": {"일시": rights["created_at"], "원고": rights["manuscript"], **rights["counts"]} if rights else None,
                        "이미지 저작권 DB": {"그림": images.get("total", 0), "확정": images.get("confirmed", 0)}},
            "분량": volume,
        },
        "기록 수": {"원고 검수": reviews.get("count", 0), "개발계획서 점검": plan.get("count", 0),
                  "의견 반영 검토": sum(r["kind"] == OPINION for r in records), "권리 증빙 점검": sum(r["kind"] == RIGHTS for r in records),
                  "분량 산정": sources.get("volume_count", 0)},
    }


def stages_recorded(kinds: set[str]) -> int:
    """목록용: 기록 종류 집합 → 기록이 있는 단계 수. kinds = {'plan', 'review', 'group', 'volume', 'rights', 'opinion:1차', …}."""
    rounds = {k.split(":", 1)[1] for k in kinds if k.startswith("opinion:")}
    return sum([
        "plan" in kinds, "review" in kinds,
        any(r.startswith("1차") and not _is_review(r) for r in rounds),
        any(r.startswith("2차") and not _is_review(r) for r in rounds),
        any(_is_review(r) for r in rounds),
        "group" in kinds, bool({"volume", "rights"} & kinds),
    ])
