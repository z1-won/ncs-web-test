"""원고 진행 현황(REQ-02-007 '원고별 편집·내용·저작권 검수 진행도 확인') — 한 원고(모듈 코드)의 기록을 단계와 진행도로 묶는다.

DB를 읽지 않는다: 기록을 모으는 일은 postgres.progress_sources가 하고, 여기서는 그 기록을 단계 7개와 진행도 세 가지로 바꾸기만 한다.

단계는 F11 매뉴얼(2026) 제2장 개발 절차(인쇄 16~17쪽) 11단계에서 연결할 기능이 있는 것만 추린 7개다
(사전 협의·킥오프·검토 회의·사업 마무리는 뺐다, 2026-11-21 결정).
단계의 **완료**는 담당자(에디터)가 직접 표시한다(manuscript_stages — 누가·언제·메모, 되돌릴 수 있고 이력이 남는다).
기록은 완료를 판단할 근거로 단계 옆에 보일 뿐이고, 기록이 있다고 완료가 되지 않는다('기록 있음'/'기록 없음').
원고 검수는 돌릴 때 단계(초고본·수정본·최종본)를 고를 수 있다(REVIEW_STAGES). 고른 기록은 그 단계에 보이고, 고르지 않은 기록은
처음 검수한 날을 초고본 검토에, 가장 최근 전체 검수의 판정을 최종본 검수에 '단계를 고르지 않은 기록'으로 보인다.

의견 반영 검토와 권리 증빙 점검은 개수만 남긴다(summarize_opinion·summarize_rights) — 의견 문장·원고 문단·지적 내용은 저장하지 않는다.
"""

from __future__ import annotations

RECORDED, EMPTY = "기록 있음", "기록 없음"
OPINION, RIGHTS = "opinion", "rights"
FIGURES, SOURCES = "figures", "sources"      # 그림 검수(REQ-02-005)·출처 검토(REQ-02-008) — 저작권 검수 진행도에 모은다
KINDS = (OPINION, RIGHTS, FIGURES, SOURCES)
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
REVIEW_STAGES = {2: "초고본", 3: "수정본", 6: "최종본"}     # 원고 검수를 돌릴 때 고를 수 있는 단계
STAGE_NUMBERS = tuple(stage[0] for stage in STAGES)
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


def summarize_figures(result: dict) -> dict:
    """그림 검수 결과(/api/uploads/{token}/figures) → 남길 개수. 그림·출처 문구는 넣지 않는다. 정정 필요 = 확인 필요 + 고위험."""
    summary = (result.get("review") or {}).get("summary") or {}
    levels = summary.get("위험도") or {}
    counts = {"그림": summary.get("그림", 0), "검수 대상": summary.get("검수 대상", 0),
              "문제없음": levels.get("문제없음", 0), "확인 필요": levels.get("확인 필요", 0), "고위험": levels.get("고위험", 0)}
    counts["정정 필요"] = counts["확인 필요"] + counts["고위험"]
    return counts


def summarize_sources(result: dict) -> dict:
    """출처 검토 결과(ncs_sources.review_sources) → 남길 개수. 출처 원문은 넣지 않는다. 정정 필요 = 부적합 + 판단불가."""
    summary = result.get("summary") or {}
    verdicts = summary.get("판정") or {}
    counts = {"총 출처": sum(verdicts.values()), "적합": verdicts.get("적합", 0), "부적합": verdicts.get("부적합", 0), "판단불가": verdicts.get("판단불가", 0)}
    counts["정정 필요"] = counts["부적합"] + counts["판단불가"]
    for key in ("참고 자료 항목", "문장 단위 출처 후보", "AI 표기"):
        counts[key] = summary.get(key, 0)
    return counts


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
    # 담당자 확정(REQ-02-003 사람 작업 4) — 가장 최근에 확정을 적은 의견 반영 검토 기록. 의견별 값은 싣지 않는다
    confirmed = next((r["counts"]["확정"] for r in records if r["kind"] == OPINION and isinstance(r["counts"].get("확정"), dict)), None)
    return {"차수": rows, "합계": total if rows else None,
            "확정": {key: value for key, value in confirmed.items() if key != "의견별"} if confirmed else None}


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
    return {"구성요소": checks, "항목": items if checks else None, "쪽": page_progress(latest_checks),
            "적합 비율": round(items["적합"] / judged * 100, 1) if judged else None}


def page_progress(latest_checks: list[dict]) -> dict | None:
    """편집 검수 진행도의 쪽 수(REQ-02-007 사람 작업 1번 '진행완료 페이지 / 총 페이지'). 구성요소마다 가장 최근 실행이 적어 둔
    쪽 수(review_runs.pages)를 모은다: 전체 = 총 쪽(실행마다 원고가 다를 수 있어 가장 큰 값), 남음 = 부적합이 놓인 쪽(구성요소끼리 합집합),
    완료 = 전체 - 남음. 문단을 찾지 못해 쪽에 넣지 못한 부적합 항목 수를 함께 싣는다. 쪽을 적은 실행이 없으면 None(hwp 원고, 옛 기록)."""
    counted = [run["pages"] for run in latest_checks if run["check"] != "plan" and isinstance(run.get("pages"), dict) and run["pages"].get("총 쪽")]
    if not counted:
        return None
    total = max(item["총 쪽"] for item in counted)
    marked = {page for item in counted for page in item.get("지적 쪽") or [] if page <= total}
    return {"전체": total, "남음": len(marked), "완료": total - len(marked), "못 찾은 항목": sum(item.get("못 찾은 항목", 0) for item in counted),
            "센 구성요소": len(counted)}


def remaining(progress: dict) -> dict:
    """진행도 → 남은 일. 편집·내용·저작권 검수를 모두 {'남음', '전체'}로 맞춘다 — 목록에서 원고끼리 견주고, 상세의 요약도 같은 값을 쓴다.

    편집 검수: 남음 = 부적합 항목, 전체 = 판정한 항목(적합 + 부적합 + 판단불가). 판단불가는 따로 싣는다(사람이 볼 것이지 고칠 것으로 정해진 게 아니다).
    내용 검수: 담당자 확정이 있으면 남음 = 확정한 미반영, 전체 = 확정한 의견 수. 없으면 남음 = 미반영 후보, 전체 = 총 의견(확인 필요는 따로).
    저작권 검수: 남음 = 정정 필요(그림의 고위험·확인 필요 + 출처의 부적합·판단불가), 전체 = 그림 + 출처. 권리 증빙의 누락은 따로.
    기록이 없는 것은 None."""
    editing, content, rights = progress["편집 검수"], progress["내용 검수"], progress["저작권 검수"]
    items = editing.get("항목")
    out = {"편집 검수": None, "내용 검수": None, "저작권 검수": None}
    if items:
        out["편집 검수"] = {"남음": items["부적합"], "전체": items["적합"] + items["부적합"] + items["판단불가"], "판단불가": items["판단불가"],
                        **({"쪽": editing["쪽"]} if editing.get("쪽") else {})}      # 쪽 수는 센 실행이 있을 때만(REQ-02-007 사람 작업 1번)
    total, confirmed = content.get("합계"), content.get("확정")
    if confirmed:
        out["내용 검수"] = {"남음": confirmed.get("미반영", 0), "전체": confirmed.get("확정", 0), "확정": True,
                        "확인 필요": 0, "총 의견": total["총 의견"] if total else confirmed.get("확정", 0)}
    elif total:
        out["내용 검수"] = {"남음": total["미반영 후보"], "전체": total["총 의견"], "확정": False, "확인 필요": total["확인 필요"],
                        "총 의견": total["총 의견"]}
    both, evidence = rights.get("합계"), rights.get("권리 증빙")
    if both or evidence:
        out["저작권 검수"] = {"남음": both["정정 필요"] if both else None, "전체": both["총 개수"] if both else None,
                         "증빙 누락": evidence.get("누락") if evidence else None, "증빙 판정": evidence.get("판정") if evidence else None}
    return out


def build(module_code: str, sources: dict, *, name: str = "") -> dict:
    """기록 → 진행 현황. sources = postgres.progress_sources()의 값:
    {'reviews': {'count', 'first', 'last'}, 'plan': {'count', 'last', 'verdict'}, 'latest_checks': [...], 'last_group': {...}|None,
     'volume': {...}|None, 'records': [...], 'images': {'total', 'confirmed'}}"""
    records = sources.get("records", [])
    reviews, plan = sources.get("reviews") or {}, sources.get("plan") or {}
    group, volume, images = sources.get("last_group"), sources.get("volume"), sources.get("images") or {}
    rights = _latest(records, RIGHTS)
    figures, cited = _latest(records, FIGURES), _latest(records, SOURCES)

    def counted(row: dict | None) -> dict | None:
        return {"일시": row["created_at"], "원고": row["manuscript"], **row["counts"]} if row else None

    # 사람 작업 3 '저작권 검수 진행도: 총 저작권 개수 / 정정 필요 개수' — 그림 검수의 그림과 출처 검토의 출처를 합친다(둘 다 없으면 None)
    copyright_total = None
    if figures or cited:
        copyright_total = {"총 개수": (figures["counts"].get("그림", 0) if figures else 0) + (cited["counts"].get("총 출처", 0) if cited else 0),
                           "정정 필요": (figures["counts"].get("정정 필요", 0) if figures else 0) + (cited["counts"].get("정정 필요", 0) if cited else 0)}
    first = _round_records(records, lambda n: n.startswith("1차") and not _is_review(n))
    second = _round_records(records, lambda n: n.startswith("2차") and not _is_review(n))
    review = _round_records(records, _is_review)

    def opinion_note(rows: list[dict]) -> str:
        row = rows[0]
        return f"의견 {row['총 의견']}개 중 반영 후보 {row['반영 후보']}, 미반영 후보 {row['미반영 후보']}, 확인 필요 {row['확인 필요']}"

    staged = {int(k): v for k, v in (sources.get("staged_reviews") or {}).items()}
    done = {int(k): v for k, v in (sources.get("done") or {}).items()}

    def tagged(no: int) -> str:
        row = staged.get(no)
        return f"{REVIEW_STAGES[no]}으로 표시한 원고 검수 {row['count']}건, 최근 판정 {row['verdict']}" if row else ""

    def joined(*parts: str) -> str:
        return ". ".join(part for part in parts if part)

    loose = "단계를 고르지 않은 기록: "
    facts = {
        1: (bool(plan.get("count")), plan.get("last"), f"점검 {plan.get('count')}회, 최근 판정 {plan.get('verdict')}" if plan.get("count") else ""),
        2: (bool(staged.get(2) or reviews.get("count")), staged[2]["last"] if staged.get(2) else reviews.get("first"),
            tagged(2) or (f"{loose}처음 검수한 날, 검수 기록 {reviews.get('count')}건" if reviews.get("count") else "")),
        3: (bool(first or staged.get(3)), first[0]["일시"] if first else (staged[3]["last"] if staged.get(3) else None),
            joined(tagged(3), opinion_note(first) if first else "")),
        4: (bool(second), second[0]["일시"] if second else None, opinion_note(second) if second else ""),
        5: (bool(review), review[0]["일시"] if review else None, opinion_note(review) if review else ""),
        6: (bool(staged.get(6) or group), staged[6]["last"] if staged.get(6) else (group["created_at"] if group else None),
            tagged(6) or (f"{loose}가장 최근 전체 검수 판정 {group['verdict']}(구성요소 {len(group['checks'])}개)" if group else "")),
        7: (bool(volume or rights), max(filter(None, [volume and volume["created_at"], rights and rights["created_at"]]), default=None),
            ", ".join(filter(None, [f"분량 {volume['pages']}매" if volume else "",
                                    f"권리 증빙 {rights['counts'].get('판정')}" if rights else ""]))),
    }
    stages = [{"번호": no, "이름": title, "담당": who, "기능": feature, "경로": path,
               "완료": no in done, "완료한 사람": done[no]["by"] if no in done else None, "완료 시각": done[no]["at"] if no in done else None,
               "메모": done[no]["note"] if no in done else "",
               "상태": RECORDED if facts[no][0] else EMPTY, "일시": facts[no][1], "내용": facts[no][2]}
              for no, title, who, feature, path in STAGES]
    result = {
        "module_code": module_code, "학습모듈명": name,
        "단계": stages, "단계 근거": BASIS,
        "완료 단계 수": len(done),
        "단계 안내": "단계의 완료는 담당자가 직접 표시합니다. 기록은 완료를 판단할 근거로 보여 주는 것이며, 기록이 있다고 완료로 바뀌지 않습니다.",
        "이력": sources.get("history", []),
        "진행도": {
            "편집 검수": editing_progress(sources.get("latest_checks", [])),
            "내용 검수": content_progress(records),
            "저작권 검수": {"권리 증빙": {"일시": rights["created_at"], "원고": rights["manuscript"], **rights["counts"]} if rights else None,
                        "이미지 저작권 DB": {"그림": images.get("total", 0), "확정": images.get("confirmed", 0)},
                        "그림 검수": counted(figures), "출처 검토": counted(cited), "합계": copyright_total},
            "분량": volume,
        },
        "기록 수": {"원고 검수": reviews.get("count", 0), "개발계획서 점검": plan.get("count", 0),
                  "의견 반영 검토": sum(r["kind"] == OPINION for r in records), "권리 증빙 점검": sum(r["kind"] == RIGHTS for r in records),
                  "그림 검수": sum(r["kind"] == FIGURES for r in records), "출처 검토": sum(r["kind"] == SOURCES for r in records),
                  "분량 산정": sources.get("volume_count", 0)},
    }
    result["남은 일"] = remaining(result["진행도"])
    return result


def stages_recorded(kinds: set[str]) -> int:
    """목록용: 기록 종류 집합 → 기록이 있는 단계 수(완료 표시 'done:N'은 stages_done이 센다). kinds = {'plan', 'review', 'group', 'volume', 'rights', 'opinion:1차', …}."""
    rounds = {k.split(":", 1)[1] for k in kinds if k.startswith("opinion:")}
    return sum([
        "plan" in kinds, "review" in kinds,
        any(r.startswith("1차") and not _is_review(r) for r in rounds),
        any(r.startswith("2차") and not _is_review(r) for r in rounds),
        any(_is_review(r) for r in rounds),
        "group" in kinds, bool({"volume", "rights"} & kinds),
    ])


def stages_done(kinds: set[str]) -> int:
    """목록용: 담당자가 완료로 표시한 단계 수(kinds의 'done:N')."""
    return sum(1 for kind in kinds if kind.startswith("done:"))
