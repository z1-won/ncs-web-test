"""개발계획서 둘을 칸별로 견준다 — 사람 작업 6번 '결과 비교'(최종결과 예시나 앞 판본과 비교해 누락·불일치를 고친다). 판정은 하지 않는다.

기준(base)과 대상(target)을 ncs_plan.parsers.read_plan으로 읽어 같은 칸끼리 맞춘다:
  기본 정보 · NCS 변경 전·후 대조표 · 총괄표(능력단위 코드로) · 위치 · 모듈 표(능력단위 코드로: NCS 쪽 요소명·수행준거, 학습모듈 쪽 학습명·학습 내용명·학습 목표)
칸마다 '띄어쓰기만 다름' / '다름' / '기준에만 있음' / '대상에만 있음'을 낸다. 같은 칸은 내지 않고 세기만 한다.
따로 모아 알리는 것 둘:
  개선 유형이 바뀐 능력단위 — 유형이 바뀌면 최종 개발계획서·결과물 목록에 똑같이 반영해야 한다(F05 최소개선 유형 세부 지침 Q4)
  NCS(수정 금지) 쪽이 달라진 칸 — 능력단위 코드·명칭·정의·요소명·수행준거는 고치는 칸이 아니다
"""

from __future__ import annotations

import re

SPACE, DIFF, ONLY_BASE, ONLY_TARGET = "띄어쓰기만 다름", "다름", "기준에만 있음", "대상에만 있음"
DOTS = re.compile(r"[･・•∙‧ㆍ]")


def _norm(value) -> str:
    return " ".join(DOTS.sub("·", str(value or "")).split())


def _kind(a, b) -> str | None:
    a, b = _norm(a), _norm(b)
    if a == b:
        return None
    if not a:
        return ONLY_TARGET
    if not b:
        return ONLY_BASE
    return SPACE if a.replace(" ", "") == b.replace(" ", "") else DIFF


class _Report:
    def __init__(self):
        self.rows, self.same = [], 0

    def cell(self, area: str, where: str, name: str, a, b, *, locked: bool = False) -> None:
        kind = _kind(a, b)
        if kind is None:
            self.same += 1
            return
        self.rows.append({"구역": area, "자리": where, "칸": name, "차이": kind, "기준": _norm(a), "대상": _norm(b), "수정 금지 칸": locked})

    def texts(self, area: str, where: str, name: str, a: list, b: list, *, locked: bool = False) -> None:
        """문장 목록(수행준거, 학습 목표) — 글자가 같은 것끼리 먼저 짝짓고 남은 것은 차례로 견준다."""
        left = [_norm(x) for x in a or []]
        right = [_norm(x) for x in b or []]
        for text in list(left):
            if text in right:
                left.remove(text)
                right.remove(text)
                self.same += 1
        keys = {x.replace(" ", ""): x for x in right}
        for text in list(left):
            twin = keys.get(text.replace(" ", ""))
            if twin is not None and twin in right:
                left.remove(text)
                right.remove(twin)
                self.cell(area, where, name, text, twin, locked=locked)
        for i in range(max(len(left), len(right))):
            self.cell(area, where, name, left[i] if i < len(left) else "", right[i] if i < len(right) else "", locked=locked)


def _by(items, key) -> dict:
    return {str(item.get(key) or ""): item for item in items or [] if item.get(key)}


def compare_plans(base: dict, target: dict) -> dict:
    """read_plan 결과 둘 → {'요약', '차이': [...], '개선 유형 변경': [...], '수정 금지 칸 변경': 수}."""
    report = _Report()
    for name in sorted(set(base.get("기본") or {}) | set(target.get("기본") or {})):
        report.cell("기본 정보", "", name, (base.get("기본") or {}).get(name), (target.get("기본") or {}).get(name))

    change_a, change_b = _by(base.get("대조표"), "개선 후 코드"), _by(target.get("대조표"), "개선 후 코드")
    for code in sorted(set(change_a) | set(change_b)):
        a, b = change_a.get(code, {}), change_b.get(code, {})
        for name in ("개선 전 코드", "개선 전 명칭", "개선 후 명칭", "분석 결과"):
            report.cell("변경 전·후 대조표", code, name, a.get(name), b.get(name))

    types = []
    summary_a, summary_b = _by(base.get("총괄표"), "코드"), _by(target.get("총괄표"), "코드")
    for code in sorted(set(summary_a) | set(summary_b)):
        a, b = summary_a.get(code), summary_b.get(code)
        if a is None or b is None:
            report.cell("총괄표", code, "능력단위", f"{code} {(a or {}).get('명칭', '')}" if a else "", f"{code} {(b or {}).get('명칭', '')}" if b else "")
            continue
        for name in ("명칭", "개선 유형", "LM 코드", "LM 명칭", "집필진", "검토진"):
            report.cell("총괄표", code, name, a.get(name), b.get(name), locked=name == "명칭")
        if _norm(a.get("개선 유형")).replace(" ", "") != _norm(b.get("개선 유형")).replace(" ", "") and (a.get("개선 유형") or b.get("개선 유형")):
            types.append({"코드": code, "명칭": b.get("명칭") or a.get("명칭") or "", "기준": _norm(a.get("개선 유형")), "대상": _norm(b.get("개선 유형"))})

    place_a, place_b = base.get("위치") or {}, target.get("위치") or {}
    for name in ("대분류", "중분류", "소분류"):
        report.cell("위치", "", name, place_a.get(name), place_b.get(name), locked=True)
    report.texts("위치", "", "세분류", place_a.get("세분류") or [], place_b.get("세분류") or [], locked=True)
    report.texts("위치", "", "능력단위와 학습모듈명", [f"{m.get('능력단위', '')} / {m.get('학습모듈명', '')}" for m in place_a.get("모듈") or []],
                 [f"{m.get('능력단위', '')} / {m.get('학습모듈명', '')}" for m in place_b.get("모듈") or []])

    modules_a, modules_b = _by(base.get("모듈"), "코드"), _by(target.get("모듈"), "코드")
    for code in sorted(set(modules_a) | set(modules_b)):
        a, b = modules_a.get(code), modules_b.get(code)
        area = "모듈 표"
        if a is None or b is None:
            report.cell(area, code, "모듈 표", code if a else "", code if b else "")
            continue
        report.cell(area, code, "능력단위명", a.get("명칭"), b.get("명칭"), locked=True)
        report.cell(area, code, "능력단위 정의", a.get("정의"), b.get("정의"), locked=True)
        report.cell(area, code, "학습모듈명", a.get("학습모듈명"), b.get("학습모듈명"))
        report.cell(area, code, "학습모듈의 목표", a.get("목표"), b.get("목표"))
        elements_a, elements_b = _by(a.get("요소"), "코드"), _by(b.get("요소"), "코드")
        for element in sorted(set(elements_a) | set(elements_b)):
            ea, eb = elements_a.get(element, {}), elements_b.get(element, {})
            report.cell(area, element, "능력단위요소명", ea.get("명칭"), eb.get("명칭"), locked=True)
            report.texts(area, element, "수행준거", ea.get("수행준거"), eb.get("수행준거"), locked=True)
        lessons_a = {str(lesson.get("번호")): lesson for lesson in a.get("학습") or []}
        lessons_b = {str(lesson.get("번호")): lesson for lesson in b.get("학습") or []}
        for number in sorted(set(lessons_a) | set(lessons_b), key=lambda n: (len(n), n)):
            la, lb = lessons_a.get(number, {}), lessons_b.get(number, {})
            where = f"{code} 학습 {number}"
            report.cell(area, where, "학습명", la.get("명칭"), lb.get("명칭"))
            report.texts(area, where, "학습 내용명", [sub.get("명칭") for sub in la.get("내용") or []], [sub.get("명칭") for sub in lb.get("내용") or []])
            report.texts(area, where, "학습 목표", [goal for sub in la.get("내용") or [] for goal in sub.get("목표") or []],
                         [goal for sub in lb.get("내용") or [] for goal in sub.get("목표") or []])

    counts: dict[str, int] = {}
    for row in report.rows:
        counts[row["차이"]] = counts.get(row["차이"], 0) + 1
    locked = sum(1 for row in report.rows if row["수정 금지 칸"])
    return {"요약": {"견준 칸": report.same + len(report.rows), "같음": report.same, **{kind: counts.get(kind, 0) for kind in (SPACE, DIFF, ONLY_BASE, ONLY_TARGET)},
                    "개선 유형 변경": len(types), "수정 금지 칸 변경": locked,
                    "능력단위": {"기준": len(modules_a), "대상": len(modules_b)}},
            "차이": report.rows, "개선 유형 변경": types, "수정 금지 칸 변경": locked}


def compare_files(base_path, target_path) -> dict:
    """계획서 파일 둘(hwp, hwpx)을 읽어 견준다. 모듈 표를 하나도 읽지 못한 파일이면 ValueError."""
    from pathlib import Path

    from ncs_core import load_document

    from .parsers import read_plan

    plans = []
    for label, path in (("기준", base_path), ("대상", target_path)):
        plan = read_plan(load_document(path).tables)
        if not plan.get("모듈") and not plan.get("총괄표"):
            raise ValueError(f"{label} 파일에서 개발계획서의 표를 읽지 못했습니다: {Path(path).name}")
        plans.append(plan)
    result = compare_plans(*plans)
    result["기준 파일"], result["대상 파일"] = Path(base_path).name, Path(target_path).name
    return result
