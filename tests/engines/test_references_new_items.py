"""새 검수 항목(2026-11-05): 기타 ③④⑤⑧, 참고자료 ④, 그림 읽기(images·jpeg).
각 항목마다 '진짜 위반이면 X'와 '최종본에서 사람이 통과시킨 꼴은 통과(또는 △)'를 함께 본다."""

import base64
import struct
import unittest
import zlib
from types import SimpleNamespace
from unittest import mock

from ncs_references.rules.old_module import check_old_module
class OldModuleTests(unittest.TestCase):
    def test_six_parts(self):
        ok = {"idx": 1, "text": "교육부(2015). SW제품 마케팅 계획 수립(LM20010410_14v2). 한국직업능력개발원. p.25.", "lm_code": None}
        no_code = {"idx": 2, "text": "교육부(2015). SW제품 마케팅 계획 수립. 한국직업능력연구원. p.25.", "lm_code": None}
        no_page = {"idx": 3, "text": "교육부(2019). SW제품 기술 검토(LM2001010403_19v4). 한국직업능력연구원.", "lm_code": None}
        other = {"idx": 4, "text": "집필진 제작(2026)", "lm_code": None}
        self.assertEqual([r["판정"] for r in check_old_module([ok, other])], ["적합"])
        rows = check_old_module([ok, no_code, no_page])
        self.assertEqual([r["판정"] for r in rows], ["부적합", "부적합"])
        self.assertIn("'(LM코드)' 없음", rows[0]["비고"]["④ 기존 학습모듈 출처 표기"])
        self.assertIn("쪽 'p.00' 없음", rows[1]["비고"]["④ 기존 학습모듈 출처 표기"])
        self.assertEqual(check_old_module([other])[0]["체크"], {"④ 기존 학습모듈 출처 표기": "-"})


if __name__ == "__main__":
    unittest.main()
