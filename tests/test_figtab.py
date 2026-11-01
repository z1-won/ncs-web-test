"""필요 지식 ⑦ 그림·표 번호: 학습 묶음별 행, 재사용/중복 삽입/누락/역행 분류, 표 없는 학습 건너뛰기, 메모 안 캡션 제외."""

import unittest

from ncs_knowledge.figtab import _flatten, check_figtab, collect_labels, sequence_problems


def body(*lines):
    return [["차례", "학습 1. 하나", "학습 2. 둘", "학습 3. 셋", "학습 4. 넷"], list(lines)]


def run(sections, exclude=None):
    flat = _flatten(sections, exclude=exclude)
    caps, refs, bare = collect_labels(flat)
    # 학습 경계: 본문의 '학습 N' 줄로 직접 준다(파이프라인은 내비게이터 기반 구간을 준다)
    heads = [(k, int(t.split()[1].rstrip('.'))) for k, (s, i, t) in enumerate(flat) if s == 1 and t.startswith("학습 ")]
    spans = [(no, k, heads[j + 1][0] if j + 1 < len(heads) else len(flat)) for j, (k, no) in enumerate(heads)]
    return check_figtab(sections, spans, labels={"flat": flat, "caps": caps, "refs": refs, "bare": bare, "lesson_spans": spans})


class SequenceProblemTests(unittest.TestCase):
    def caps(self, *labels_titles):
        return [{"kind": "그림", "major": 1, "minor": m, "label": f"[그림 1-{m}]", "text": f"[그림 1-{m}] {t}"} for m, t in labels_titles]

    def test_reuse_duplicate_missing_backward(self):
        group = self.caps((1, "a"), (2, "b"), (4, "d"), (3, "c"), (2, "b"), (4, "x"))
        self.assertEqual(sequence_problems(group), {
            "재사용": ["[그림 1-4]"], "중복 삽입": ["[그림 1-2]"], "누락": [], "역행": ["[그림 1-3]"]})
        self.assertEqual(sequence_problems(self.caps((1, "a"), (3, "c")))["누락"], ["[그림 1-2]"])
        self.assertEqual(sequence_problems(self.caps((1, "a"), (2, "b"))), {"재사용": [], "중복 삽입": [], "누락": [], "역행": []})


class CheckFigtabTests(unittest.TestCase):
    def test_no_captions_is_not_applicable(self):
        [row] = run(body("학습 1", "그림 없는 본문"))
        self.assertEqual((row["판정"], row["체크"]), ("적합", {"그림·표 캡션": "-"}))

    def test_rows_per_lesson_and_table_lessons_may_be_skipped(self):
        rows = run(body("학습 1", "[그림 1-1] 가", "〈표 1-1〉 표가", "[그림 1-2] 나",
                        "학습 2", "[그림 2-1] 다",
                        "학습 3", "본문만",
                        "학습 4", "〈표 4-1〉 표나", "[그림 4-1] 라"))
        self.assertEqual([(r["위치"], r["region_path"].split(" > ")[-1], r["판정"]) for r in rows],
                         [("학습 1", "그림", "적합"), ("학습 2", "그림", "적합"), ("학습 4", "그림", "적합"),
                          ("학습 1", "표", "적합"), ("학습 4", "표", "적합")])  # 표 1-1 다음 표 4-1: 정상

    def test_inserted_figures_without_renumbering(self):
        rows = run(body("학습 1", "[그림 1-1] 가", "[그림 1-2] 끼워 넣음", "[그림 1-2] 나", "[그림 1-3] 다", "[그림 1-3] 다",
                        "학습 2", "[그림 2-1] 라"))
        [one, two] = rows
        self.assertEqual(one["판정"], "부적합")
        self.assertEqual(one["비고"]["번호 연속"], "그림 1-x 5개 중 재사용 1([그림 1-2]) · 중복 삽입 1([그림 1-3])")
        self.assertEqual([d["문제"] for d in one["상세"]], ["재사용", "중복 삽입"])
        self.assertIn("같은 그림은 하나만 남김", one["수정 제안"])
        self.assertEqual(two["판정"], "적합")

    def test_misplaced_caption_and_brackets(self):
        rows = run(body("학습 1", "[그림 1-1] 가", "학습 2", "[그림 1-2] 학습 1 번호인데 학습 2에 놓임", "<표 2-1> 괄호 틀림"))
        by = {(r["위치"], r["region_path"].split(" > ")[-1]): r for r in rows}
        self.assertEqual(by[("학습 2", "그림")]["체크"]["놓인 학습 일치"], "X")
        self.assertIn("[그림 1-2]", by[("학습 2", "그림")]["비고"]["놓인 학습 일치"])
        self.assertEqual(by[("학습 2", "표")]["체크"]["괄호 표기"], "X")
        self.assertIn("〈 〉 로 묶음", by[("학습 2", "표")]["수정 제안"])

    def test_references_and_memo_captions(self):
        sections = body("학습 1", "[그림 1-1] 가", "[그림 1-1] 메모 안 복사본", "본문은 [그림 1-3]을 보라고 한다.", "그림 1-1 괄호 없이")
        rows = run(sections, exclude={(1, 2)})  # 문단 2는 메모(본문 밖)
        kinds = {r["region_path"]: r for r in rows}
        self.assertEqual(kinds["section1 > 학습 1 > 그림"]["판정"], "적합", "메모 안 캡션은 중복으로 세지 않음")
        self.assertEqual(kinds["section1 > 본문 그림 참조"]["체크"]["참조 대상 캡션 존재"], "X")
        self.assertEqual(kinds["section1 > 본문"]["판정"], "판단불가")


if __name__ == "__main__":
    unittest.main()
