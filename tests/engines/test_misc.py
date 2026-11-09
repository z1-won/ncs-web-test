"""기타 ①(새 쪽 시작)·②(그림 누락·유실)·⑥(필요 지식:수행 내용 비율)·⑦(활용 서식·부록 참조)."""

import unittest
from types import SimpleNamespace

from ncs_misc.config import CheckConfig
from ncs_misc.rules.page_starts import check_page_starts, starts_new_page
from ncs_misc.rules.pictures import check_pictures
from ncs_misc.rules.ratio import check_ratio, section_lengths
from ncs_misc.rules.references import check_references


def context(paragraphs, *, page_breaks=frozenset(), table_paragraphs=frozenset(), pictures=(), binaries=None,
            lessons=(), presence=None, fmt="hwpx", body=None, units=(), front=("학습모듈의 개요",)):
    manuscript = SimpleNamespace(
        format=fmt, sections=[list(front), list(paragraphs)],
        section_page_breaks=lambda i: (frozenset() if i == 0 else page_breaks) if fmt == "hwpx" else None,
        section_table_paragraphs=lambda i: frozenset() if i == 0 else table_paragraphs,
        section_pictures=lambda i: list(pictures) if i == 1 else [],
        section_aside_paragraphs=lambda i: frozenset(),
        binaries=binaries or {},
    )
    return SimpleNamespace(manuscript=manuscript, config=CheckConfig(), body=body or {"lessons": list(lessons), "lines": []},
                           units=list(units), presence=presence or {})


class PageStartTests(unittest.TestCase):
    def test_starts_new_page_rules(self):
        paragraphs = ["글", "", "", "머리", "표셀", "표머리"]
        self.assertTrue(starts_new_page(3, paragraphs, frozenset({1})))         # 앞 빈 문단에 쪽 나누기
        self.assertTrue(starts_new_page(3, paragraphs, frozenset({3})))         # 자신에 쪽 나누기
        self.assertFalse(starts_new_page(3, paragraphs, frozenset()))           # 없음
        self.assertTrue(starts_new_page(0, paragraphs, frozenset()))            # 섹션 첫 문단
        # 틀(표) 안 머리: 같은 틀의 앞 셀('학습 1')은 건너뛰고 틀 앞 문단의 쪽 나누기를 본다
        self.assertTrue(starts_new_page(5, paragraphs, frozenset({3}), table_paragraphs=frozenset({4, 5})))
        self.assertFalse(starts_new_page(5, paragraphs, frozenset(), table_paragraphs=frozenset({4, 5})))

    def test_rows_for_heads_and_hwp(self):
        body = ["학습 1", "본문", "", "교수·학습 방법", "글", "평 가", "", "참고 자료"]
        lessons = [{"no": 1, "raw_span": (0, 7)}]
        presence = {"참고 자료": {"있음": True, "k": 7}, "활용 서식": {"있음": False}, "부록": {"있음": False}}
        rows = check_page_starts(context(body, page_breaks=frozenset({0, 2, 6}), lessons=lessons, presence=presence))
        self.assertEqual([(r["원고"]["머리"], r["판정"]) for r in rows],
                         [("학습모듈의 개요", "적합"), ("내비게이터(학습 1)", "적합"), ("교수·학습 방법", "적합"), ("평가", "부적합"), ("참고 자료", "적합")])
        self.assertEqual(rows[3]["위치"], "학습 1")
        hwp = check_page_starts(context(body, lessons=lessons, presence=presence, fmt="hwp"))
        self.assertEqual({r["판정"] for r in hwp}, {"판단불가"})


class PictureTests(unittest.TestCase):
    def test_pairing_missing_drawn_and_lost(self):
        body = ["학습 1", "", "", "출처: 집필진 제작(2026)", "[그림 1-1] 가", "", "출처: 집필진 제작(2026)", "[그림 1-2] 나",
                "표 셀 글", "표 셀 글", "출처: 집필진 제작(2026)", "[그림 1-3] 표로 그린 양식",
                "", "", "출처: 집필진 제작(2026)", "[그림 1-4] 파일 없는 그림",
                "", "", "", "[그림 1-5] 그림 없음"]
        pictures = [(2, "image1"), (5, "image2"), (13, "image9")]
        binaries = {"image1": {"href": "BinData/image1.jpg", "bytes": 631}, "image2": {"href": "BinData/image2.jpg", "bytes": 0}}
        [row] = check_pictures(context(body, pictures=pictures, binaries=binaries, lessons=[{"no": 1, "raw_span": (0, len(body))}]))
        self.assertEqual(row["체크"], {"캡션에 그림 있음": "X", "그림 파일 존재": "X"})
        problems = {d.get("캡션") or d.get("BinData"): d["문제"] for d in row["상세"]}
        self.assertEqual(problems["[그림 1-5] 그림 없음"], "캡션 위에 그림 개체 없음")
        self.assertIn("표·텍스트만", problems["[그림 1-3] 표로 그린 양식"])
        self.assertEqual(problems["image2"], "그림 파일 0바이트")
        self.assertEqual(problems["image9"], "그림 파일 없음")
        self.assertEqual(row["원고"], {"캡션": 5, "그림": 3})

    def test_side_by_side_pictures_pair_with_two_captions(self):
        body = ["학습 1", "", "", "출처: a", "[그림 1-1] 가", "", "출처: b", "[그림 1-2] 나"]
        rows = check_pictures(context(body, pictures=[(1, "i1"), (2, "i2")], binaries={"i1": {"bytes": 1}, "i2": {"bytes": 1}},
                                      lessons=[{"no": 1, "raw_span": (0, len(body))}]))
        self.assertEqual(rows[0]["판정"], "적합")


class RatioTests(unittest.TestCase):
    def body(self, knowledge, perform):
        lines = [(0, "학습 1"), (1, "1-1. 제목"), (2, "필요 지식"), (3, "가" * knowledge), (4, "수행 내용 1"), (5, "나" * perform), (6, "교수·학습 방법")]
        unit = {"no": 1, "sub": 1, "text": "제목", "k0": 1, "k1": 7, "lesson": 1, "goal": [], "goal_k": None}
        return {"lines": lines, "lessons": []}, unit

    def test_lengths_and_verdicts(self):
        body, unit = self.body(300, 700)
        self.assertEqual({k: v for k, v in section_lengths(body, unit, frozenset()).items() if k != "found"}, {"필요 지식": 300, "수행 내용": 700})
        for k, p, expect in ((300, 700, "적합"), (500, 500, "적합"), (600, 400, "부적합")):
            body, unit = self.body(k, p)
            [row] = check_ratio(context([], body=body, units=[unit]))
            self.assertEqual(row["판정"], expect, (k, p))
        self.assertIn("5:5", check_ratio(context([], body=self.body(500, 500)[0], units=[self.body(500, 500)[1]]))[0]["비고"]["필요 지식:수행 내용 비율(참고)"])

    def test_missing_head_is_undecided(self):
        body = {"lines": [(0, "학습 1"), (1, "1-1. 제목"), (2, "필요 지식"), (3, "글")], "lessons": []}
        unit = {"no": 1, "sub": 1, "text": "제목", "k0": 1, "k1": 4, "lesson": 1, "goal": [], "goal_k": None}
        [row] = check_ratio(context([], body=body, units=[unit]))
        self.assertEqual(row["판정"], "판단불가")


class ReferenceTests(unittest.TestCase):
    def test_reference_required_only_when_section_exists(self):
        body = ["본문 (활용 서식 참조)", "본문", "활용 서식", "서식 내용"]
        presence = {"활용 서식": {"있음": True, "k": 2}, "부록": {"있음": False}}
        rows = check_references(context(body, presence=presence))
        self.assertEqual([(r["region_path"], r["판정"]) for r in rows], [("section1 > 활용 서식", "적합"), ("section1 > 부록", "적합")])
        self.assertEqual(rows[1]["체크"], {"'부록 참조' 기재": "-"})
        rows = check_references(context(["본문", "활용 서식", "서식 내용"], presence={"활용 서식": {"있음": True, "k": 1}, "부록": {"있음": False}}))
        self.assertEqual(rows[0]["판정"], "부적합")


if __name__ == "__main__":
    unittest.main()
