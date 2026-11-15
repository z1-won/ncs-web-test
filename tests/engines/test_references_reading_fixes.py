"""B 엔진 읽기 수정(2026-11-05) — SW제품기획 최종본 10종에서 사람이 통과시켰는데 엔진이 잘못 읽어 X·△가 나던 경우를 작게 재현한다.
각 수정마다 '진짜 위반은 여전히 잡는지'도 함께 본다."""

import unittest
from pathlib import Path
from types import SimpleNamespace

from ncs_references.entries import collect_entries, find_short_reference_run


class ShortReferenceRunTests(unittest.TestCase):
    def test_two_entries_without_title_are_found(self):
        """제목이 이미지이고 항목이 2개뿐(0404) — 코어 기준(3개)에 못 미쳐도 엔진 보조 탐색으로 찾는다."""
        body = ["4. 평가자 체크리스트", "- 부족한 부분을 설명해 준다.", "", "∙이강만(2012). 『소프트웨어 제품 마케팅』. 삼보아트.",
                "∙프로그램심의조정위원회(2005). 『알기 쉬운 소프트웨어 라이선스』.", "비용 분석표"]
        found = find_short_reference_run(body, in_table=frozenset({0, 1, 5}))
        self.assertEqual((found["k"], found["end"]), (3, 4))
        self.assertEqual(len(collect_entries(body, {"참고 자료": found})), 2)
        # 서지처럼 생긴 줄이 하나뿐이면 찾지 않는다
        self.assertIsNone(find_short_reference_run(["글", "∙이강만(2012). 『책』. 삼보아트.", "글"]))


if __name__ == "__main__":
    unittest.main()
