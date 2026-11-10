"""골든 테스트: 현재 src/의 검수 결과가 tests/golden/에 저장된 결과와 같은가.

구조를 바꾸는 리팩토링 뒤에 이 테스트가 통과하면 "검수 결과가 바뀌지 않았다"는 뜻이다.
판정 정책을 의도적으로 바꿨으면 tests/make_golden.py로 다시 생성하고 그 diff를 검토한 뒤 커밋한다.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from golden_cases import GOLDEN, cases, dumps, observe  # noqa: E402


class GoldenTests(unittest.TestCase):
    def test_every_case_has_a_golden_file_and_matches(self):
        names = set()
        for name, request in cases():
            names.add(name)
            with self.subTest(case=name):
                path = GOLDEN / f"{name}.json"
                self.assertTrue(path.is_file(), f"골든 파일이 없습니다. tests/make_golden.py 실행: {path.name}")
                expected = path.read_text(encoding="utf-8")
                actual = dumps(observe(request))
                self.assertEqual(actual, expected, f"{name}: 결과가 골든과 다릅니다. 의도한 변경이면 make_golden.py로 갱신")

    def test_no_stale_golden_files(self):
        names = {name for name, _ in cases()}
        stale = sorted(p.stem for p in GOLDEN.glob("*.json") if p.stem not in names)
        self.assertEqual(stale, [], "사례에 없는 골든 파일이 남아 있습니다(엔진·픽스처 삭제 후 정리 필요)")


if __name__ == "__main__":
    unittest.main()
