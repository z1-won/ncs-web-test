"""업스케일(화질 보정)에서 변경금지 원본 제외 — REQ-02-006 ⑥: 공공누리 제3·4유형 원본은 AI 수정 보완 대상에서 제외(검증: 변경금지 원본의 수정 보완 0건)."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import rights_samples as S  # noqa: E402

KOGL = "출처: 고용노동부(2025). 직업훈련 통계. 공공누리 홈페이지(https://www.kogl.or.kr)에서 2026. 7. 1. 검색. 공공누리 제{}유형."
FIGURES = [("그림 1-1", "변경금지 그림", KOGL.format(3), ""), ("그림 1-2", "비상업 그림", KOGL.format(2), ""), ("그림 1-3", "집필진 그림", "출처: 집필진 제작(2026)", "")]


class LockedOriginalTests(unittest.TestCase):
    def test_no_derivative_pictures_are_listed_as_locked_and_refused(self):
        from ncs_upscale import service

        with tempfile.TemporaryDirectory() as folder:
            path = S.manuscript(Path(folder), FIGURES, name="LM1203020201_24v3_잠금.hwpx")
            listed = service.list_pictures(path, Path(folder) / "work")
            by_label = {picture["caption"].split("]")[0].strip("[ "): picture for picture in listed["pictures"]}
            self.assertEqual(set(by_label), {"그림 1-1", "그림 1-2", "그림 1-3"})
            self.assertEqual(by_label["그림 1-1"]["locked"]["유형"], "3")
            self.assertIn("변경금지", by_label["그림 1-1"]["locked"]["이유"])
            self.assertIsNone(by_label["그림 1-2"]["locked"])
            self.assertIn("비상업", by_label["그림 1-2"]["terms"])            # 제2유형 원본: 결과물에 비상업 조건을 표시해야 한다
            self.assertIsNone(by_label["그림 1-3"]["locked"])
            self.assertEqual(listed["counts"]["변경금지 제외"], 1)
            with self.assertRaises(service.PictureError) as caught:
                service.upscale_one(path, by_label["그림 1-1"]["bin_id"], Path(folder) / "work", runner=lambda *a, **k: self.fail("엔진을 부르면 안 된다"))
            self.assertIn("변경금지", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
