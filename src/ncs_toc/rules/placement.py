"""F02 차례 ④: '교수·학습 방법'과 '평가'가 각 학습(대단원) 끝부분에 있는가. (필수 작성)

차례 면: 각 학습 블록에서 'N-M.' 내용 줄이 모두 나온 뒤 '• 교수·학습 방법', '• 평가' 줄이 있는가.
본문:   각 학습 구간에서 마지막 '필요지식 N-M.' 제목 뒤에 교수·학습 방법 제목, 그 뒤에 평가 제목이 오는가.
        제목이 글자가 아닌 배너 이미지(원본 그림 이름에 '교수'/'평가')면 그 위치를 제목으로 본다.
"""

import re

from ncs_core import O, PASS, TRI, X, verdict

ITEM_ID = "F02-차례-④"
KIND_TEACH, KIND_EVAL = "교수·학습 방법", "평가"
BANNER = {KIND_TEACH: re.compile(r"교수"), KIND_EVAL: re.compile(r"평가")}


def _toc_lines(toc: dict, no: int) -> dict[str, dict]:
    """해당 학습의 차례 줄 {'교수·학습 방법': 줄, '평가': 줄}. 같은 종류가 둘이면 첫 줄."""
    out: dict[str, dict] = {}
    for line in toc["줄"]:
        if line["lesson"] == no and line["kind"] not in out:
            out[line["kind"]] = line
    return out


def _toc_check(toc: dict, no: int) -> tuple[str, str | None]:
    """차례 줄 유무와 위치 → (체크값, 비고)."""
    lines = _toc_lines(toc, no)
    n_contents = sum(1 for s in toc["내용"] if s["no"] == no)
    missing = [kind for kind in (KIND_TEACH, KIND_EVAL) if kind not in lines]
    if missing:
        return X, f"차례 학습 {no} 블록에 {' / '.join(missing)} 줄이 없음"
    # 'after': 그 줄이 나올 때까지 읽은 이 학습의 내용 줄 수. 내용 줄 전체 수보다 적으면 중간에 끼어 있다.
    early = [kind for kind, line in lines.items() if line.get("after", n_contents) < n_contents]
    if early:
        return X, f"차례 학습 {no} 블록에서 {' / '.join(early)} 줄이 내용(N-M.) 줄 앞에 있음 — 블록 끝으로 이동"
    if lines[KIND_TEACH].get("after", 0) > lines[KIND_EVAL].get("after", 0):
        return X, f"차례 학습 {no} 블록에서 평가 줄이 교수·학습 방법 줄보다 앞에 있음"
    return O, None


def _banner_positions(images, raw_span: tuple[int, int], kind: str) -> list[int]:
    """학습 구간(raw 문단 범위) 안에서 kind 제목에 해당하는 배너 이미지의 raw 문단 인덱스."""
    a, b = raw_span
    pattern = BANNER[kind]
    return [p for p, name in images if a <= p < b and pattern.search(name.replace(" ", ""))]


def _heading(lesson: dict, images, kind: str) -> tuple[int | None, str]:
    """제목 위치(raw 문단 인덱스)와 근거. 글자 제목 우선, 없으면 배너 이미지."""
    lines_index = lesson["teach"] if kind == KIND_TEACH else lesson["eval"]
    if lines_index:
        return lines_index[0], "제목 텍스트"
    banners = _banner_positions(images, lesson["raw_span"], kind)
    if banners:
        return banners[0], "배너 이미지"
    return None, "없음"


def check_toc4(toc: dict, body: dict, images, *, lines_to_raw) -> list[dict]:
    """images: 본문 섹션의 (raw 문단 인덱스, 원본 그림 이름). lines_to_raw: lines 인덱스 → raw 문단 인덱스."""
    by_no = {lesson["no"]: lesson for lesson in body["lessons"]}
    rows = []
    for entry in toc["학습"]:
        no, name = entry["no"], entry["text"]
        label_toc = "④ 차례 줄(교수·학습 방법/평가) 위치"
        label_teach = "④ 본문 교수·학습 방법 제시"
        label_eval = "④ 본문 평가 제시"
        label_order = "④ 본문 끝부분 배치(필요지식 → 교수·학습 방법 → 평가)"
        notes: dict[str, str] = {}
        checks = {label_toc: O, label_teach: O, label_eval: O, label_order: O}
        evidence: dict = {"학습": f"학습 {no}. {name}"}

        toc_value, toc_note = _toc_check(toc, no)
        checks[label_toc] = toc_value
        if toc_note:
            notes[label_toc] = toc_note

        lesson = by_no.get(no)
        if lesson is None:
            checks[label_teach] = checks[label_eval] = checks[label_order] = TRI
            notes[label_order] = f"본문에서 학습 {no} 구간을 읽지 못함(내비게이터 기준) — 사람 확인"
            evidence["본문"] = None
        else:
            # lines 인덱스를 raw 문단 인덱스로 통일해 비교한다.
            teach_lines, teach_basis = _heading(lesson, images, KIND_TEACH)
            eval_lines, eval_basis = _heading(lesson, images, KIND_EVAL)
            teach_pos = lines_to_raw(teach_lines) if teach_basis == "제목 텍스트" else teach_lines
            eval_pos = lines_to_raw(eval_lines) if eval_basis == "제목 텍스트" else eval_lines
            last_sub = max((lines_to_raw(s["k"]) for s in lesson["subs"]), default=None)
            evidence["본문"] = {
                "구간": f"section1 p{lesson['raw_span'][0]}~p{lesson['raw_span'][1] - 1}",
                "마지막 필요지식 제목": f"p{last_sub}" if last_sub is not None else None,
                KIND_TEACH: f"p{teach_pos} ({teach_basis})" if teach_pos is not None else None,
                KIND_EVAL: f"p{eval_pos} ({eval_basis})" if eval_pos is not None else None,
            }
            if teach_pos is None:
                checks[label_teach] = X
                notes[label_teach] = f"학습 {no} 구간에 '교수·학습 방법' 제목(텍스트·배너)이 없음 (필수 작성)"
            if eval_pos is None:
                checks[label_eval] = X
                notes[label_eval] = f"학습 {no} 구간에 '평가' 제목(텍스트·배너)이 없음 (필수 작성)"
            if teach_pos is None or eval_pos is None:
                checks[label_order] = TRI if (teach_pos is None) != (eval_pos is None) else X
                notes.setdefault(label_order, "제목이 없어 배치를 판단할 수 없음")
            else:
                problems = []
                if eval_pos < teach_pos:
                    problems.append("평가가 교수·학습 방법보다 앞에 있음")
                if last_sub is not None and last_sub > min(teach_pos, eval_pos):
                    problems.append(f"필요지식 제목(p{last_sub})이 교수·학습 방법/평가 뒤에 있음 — 학습 끝부분이 아님")
                if not lesson["subs"]:
                    checks[label_order] = TRI
                    notes[label_order] = f"학습 {no} 구간에서 필요지식 N-M. 제목을 읽지 못해 '끝부분'을 확정할 수 없음"
                elif problems:
                    checks[label_order] = X
                    notes[label_order] = "; ".join(problems)

        result = verdict(checks)
        rows.append(
            {
                "item_id": ITEM_ID,
                "region_path": f"section1 > 학습 {no}",
                "원고": evidence,
                "체크": checks,
                "판정": result,
                "비고": notes,
                "수정 제안": None
                if result == PASS
                else "각 학습의 필요지식 뒤에 '교수·학습 방법' → '평가' 순으로 제시하고 차례에도 같은 순서로 줄을 둘 것",
            }
        )
    if not rows:
        rows.append(
            {
                "item_id": ITEM_ID,
                "region_path": "section0 > 차례",
                "원고": None,
                "체크": {"④ 교수·학습 방법/평가 위치": TRI},
                "판정": verdict({"x": TRI}),
                "비고": {"④ 교수·학습 방법/평가 위치": "차례에서 학습을 읽지 못해 판단할 수 없음"},
                "수정 제안": None,
            }
        )
    return rows
