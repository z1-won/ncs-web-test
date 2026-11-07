"""새 검수 항목(2026-11-05): 기타 ③④⑤⑧, 참고자료 ④, 그림 읽기(images·jpeg).
각 항목마다 '진짜 위반이면 X'와 '최종본에서 사람이 통과시킨 꼴은 통과(또는 △)'를 함께 본다."""

import base64
import struct
import unittest
import zlib
from types import SimpleNamespace
from unittest import mock

from ncs_misc.config import CheckConfig
from ncs_misc.images import decode_rows, image_header
from ncs_misc.jpeg import decode_jpeg_rows
from ncs_misc.rules import brand_names, form_images, resolution, screenshots
from ncs_misc.rules.screenshots import find_taskbar, is_capture_candidate
from ncs_references.rules.old_module import check_old_module

# Windows(.NET System.Drawing)로 만든 32×16 JPEG(품질 95)과 그 해독기가 낸 밝기 — 우리 해독기를 맞춰 본다
JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAIBAQIBAQICAgICAgICAwUDAwMDAwYEBAMFBwYHBwcGBwcICQsJCAgKCAcHCg0KCgsMDAwMBwkODw0MDgsMDAz/"
    "2wBDAQICAgMDAwYDAwYMCAcIDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAz/wAARCAAQACADASIAAhEBAxEB/8QAHwAA"
    "AQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRol"
    "JicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW"
    "19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdh"
    "cRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJma"
    "oqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwD2C3jry7xbrn/CSeIJp1OYU/dw/wC4Oh6A"
    "8nJ56Zx2rs/iRrn9j+HjAhxNfZjHsn8R6Y6ED/gWe1ea3l7FpGny3MxxHApY8jJ9hnuTwPevMybhmjTnguFKbUaWHSr4h7JPlvCMuyjBupJO6fNB7xP50+jzwA3y"
    "V3HV2S/X8dPvOT+K2v8A+q0yJvSWfB/75U4P4kEf3TVT4TeCv+E38ZW1o65tY/39zzj92pGR1B+YkLxyN2e1c9eX0ur6hNdTHMk7FjycD2GewHA9q+gf2ffBX/CN"
    "eDVu5Vxdattnbn7seP3Y4JHQlux+fB6V72bcTVsuynFcVUE44nFtYfBrrBNNKa7OnTUqt7OPtXGL+M/0M8a+P14R+FNbG4GXLmGL/wBnw1viVWonzVV1XsaalOMr"
    "OPtFThL40f/Z")
JPEG_ROWS = {
    0: [150, 150, 151, 151, 152, 152, 152, 153, 152, 157, 151, 126, 125, 127, 126, 128, 128, 126, 127, 130, 128, 131, 102, 100, 102, 100, 103, 103, 103, 104, 104, 104],
    7: [151, 152, 152, 152, 153, 153, 154, 154, 125, 125, 130, 122, 127, 130, 129, 128, 130, 128, 99, 102, 100, 103, 104, 102, 105, 103, 104, 105, 104, 151, 148, 151],
    15: [150, 157, 153, 155, 124, 126, 128, 124, 129, 125, 132, 124, 130, 128, 100, 103, 100, 104, 103, 105, 103, 101, 106, 102, 105, 151, 147, 151, 152, 153, 152, 152],
}


def bmp(width, height, pixel):
    """24비트 BMP(아래에서 위로 저장). pixel(x, y) → (R, G, B)."""
    stride = (width * 3 + 3) // 4 * 4
    data = bytearray()
    for y in range(height - 1, -1, -1):
        row = bytearray()
        for x in range(width):
            r, g, b = pixel(x, y)
            row += bytes((b, g, r))
        data += row + b"\0" * (stride - len(row))
    header = struct.pack("<2sIHHI", b"BM", 54 + len(data), 0, 0, 54)
    info = struct.pack("<IiiHHIIiiII", 40, width, height, 1, 24, 0, len(data), 2835, 2835, 0, 0)
    return header + info + bytes(data)


def png(width, height, pixel):
    raw = b"".join(b"\0" + bytes(c for x in range(width) for c in pixel(x, y)) for y in range(height))

    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def screen_with_taskbar(x, y, w=320, h=180, bar=10):
    """화면 캡처 흉내: 흰 창 + 맨 아래 어두운 작업 표시줄(왼쪽 시작 단추·가운데 아이콘)."""
    if y >= h - bar:
        icon = (x < 12 or 140 <= x < 152 or 160 <= x < 172) and (h - bar + 2 <= y < h - 2)
        return (230, 230, 230) if icon else (32, 32, 40)
    return (250, 250, 250) if (x // 40 + y // 30) % 2 else (235, 240, 245)


def record(data, fmt, px, caption="[그림 1-1] 프로그램 화면", dpi=200, para=1):
    return {"section": 1, "para": para, "bin_id": "image1", "format": fmt, "px": px, "size_hwp": (28346, 17008), "mm": (100, 60),
            "dpi": dpi, "caption": caption, "data": data}


class ImageReadingTests(unittest.TestCase):
    def test_headers(self):
        self.assertEqual(image_header(bmp(4, 3, lambda x, y: (0, 0, 0))), ("bmp", 4, 3))
        self.assertEqual(image_header(png(5, 2, lambda x, y: (0, 0, 0))), ("png", 5, 2))
        self.assertEqual(image_header(JPEG), ("jpeg", 32, 16))
        self.assertIsNone(image_header(b"not an image"))

    def test_bmp_and_png_rows(self):
        pix = lambda x, y: (x * 10, y * 20, 7)
        for data, fmt in ((bmp(6, 4, pix), "bmp"), (png(6, 4, pix), "png")):
            rows = decode_rows(record(data, fmt, (6, 4)), range(2, 4))
            self.assertEqual(rows[3][5], (50, 60, 7), fmt)
            self.assertEqual(rows[2][0], (0, 40, 7), fmt)

    def test_jpeg_matches_windows_decoder(self):
        """순수 파이썬 baseline JPEG 해독 — Windows 해독기와 밝기 차이 2 이하."""
        rows = decode_jpeg_rows(JPEG, range(0, 16))
        for y, expected in JPEG_ROWS.items():
            diffs = [abs(a[0] - b) for a, b in zip(rows[y], expected)]
            self.assertLessEqual(max(diffs), 2, (y, diffs))


class TaskbarTests(unittest.TestCase):
    def lines(self, pixel, w, h):
        rows = decode_rows(record(bmp(w, h, pixel), "bmp", (w, h)), range(0, h))
        return {y: [(299 * r + 587 * g + 114 * b) // 1000 for r, g, b in line] for y, line in rows.items()}

    def test_dark_taskbar_is_found(self):
        self.assertEqual(find_taskbar(self.lines(screen_with_taskbar, 320, 180), 180), 10)

    def test_no_bar_or_empty_margin_is_not_a_taskbar(self):
        plain = lambda x, y: (250, 250, 250) if (x // 40 + y // 30) % 2 else (235, 240, 245)
        self.assertIsNone(find_taskbar(self.lines(plain, 320, 180), 180))
        empty_bar = lambda x, y: (32, 32, 40) if y >= 170 else (250, 250, 250)  # 아이콘 없는 빈 띠 = 여백·장식
        self.assertIsNone(find_taskbar(self.lines(empty_bar, 320, 180), 180))

    def test_capture_candidates(self):
        self.assertTrue(is_capture_candidate(record(b"", "bmp", (1280, 720), caption=""), [""] * 5))      # 16:9 화면 크기
        self.assertFalse(is_capture_candidate(record(b"", "jpeg", (4160, 2340), caption=""), [""] * 5))   # 카메라 사진 크기
        self.assertFalse(is_capture_candidate(record(b"", "bmp", (600, 600), caption="[그림 1-2] 조직도"), [""] * 5))
        self.assertTrue(is_capture_candidate(record(b"", "bmp", (600, 600), caption=""), ["", "", "출처: 프로그램명. 2024. 8. 12. 스크린 숏."]))

    def test_rule_flags_taskbar_and_passes_clean_capture(self):
        manuscript = SimpleNamespace(format="hwpx", sections=[[], ["그림", "[그림 1-1] 프로그램 화면"]])
        with_bar = record(bmp(320, 180, screen_with_taskbar), "bmp", (320, 180))
        clean = record(bmp(320, 180, lambda x, y: (250, 250, 250)), "bmp", (320, 180))
        with mock.patch.object(screenshots, "picture_records", return_value=[with_bar]):
            [row] = screenshots.check_screenshots(SimpleNamespace(manuscript=manuscript))
            self.assertEqual(row["판정"], "부적합")
        with mock.patch.object(screenshots, "picture_records", return_value=[clean]):
            self.assertEqual(screenshots.check_screenshots(SimpleNamespace(manuscript=manuscript))[-1]["판정"], "적합")
        progressive = record(b"", "jpeg-progressive", (1280, 720))
        with mock.patch.object(screenshots, "picture_records", return_value=[progressive]):
            self.assertEqual(screenshots.check_screenshots(SimpleNamespace(manuscript=manuscript))[0]["판정"], "판단불가")


class ResolutionTests(unittest.TestCase):
    def test_thresholds(self):
        context = SimpleNamespace(manuscript=SimpleNamespace(format="hwpx"), config=CheckConfig())
        recs = [record(b"", "bmp", (100, 100), caption="[그림 1-1] 가", dpi=60),
                record(b"", "bmp", (100, 100), caption="[그림 1-2] 나", dpi=100),
                record(b"", "bmp", (100, 100), caption="[그림 1-3] 다", dpi=200)]
        with mock.patch.object(resolution, "picture_records", return_value=recs):
            rows = resolution.check_resolution(context)
        self.assertEqual([r["판정"] for r in rows], ["부적합", "판단불가"])
        # 수정 제안은 그림마다 계산 — 100×60mm를 150 DPI로: 591×355px 필요, 지금 60 DPI면 약 40×24mm(내림) 이하로 줄여야 함
        self.assertIn("591×355px 이상 필요(지금 100×100px)", rows[0]["수정 제안"])
        self.assertIn("39×24mm 이하로 줄이면", rows[0]["수정 제안"])
        with mock.patch.object(resolution, "picture_records", return_value=recs[2:]):
            self.assertEqual([r["판정"] for r in resolution.check_resolution(context)], ["적합"])
        with mock.patch.object(resolution, "picture_records", return_value=[record(b"", "bmp", (100, 100), dpi=80)]):
            # 최종본 최저(80) — 사람이 통과시킨 해상도는 X가 아니다
            self.assertEqual(resolution.check_resolution(context)[0]["판정"], "판단불가")


class FormImageTests(unittest.TestCase):
    def test_only_pictures_inside_forms(self):
        body = ["본문"] * 10 + ["활용 서식", "서식 1", "그림", "끝"]
        context = SimpleNamespace(manuscript=SimpleNamespace(format="hwpx", sections=[[], body]), config=CheckConfig(),
                                  presence={"활용 서식": {"있음": True, "k": 10}, "부록": {"있음": False}})
        recs = [record(b"", "bmp", (50, 50), caption="", dpi=50, para=3), record(b"", "bmp", (50, 50), caption="", dpi=60, para=12)]
        with mock.patch.object(form_images, "picture_records", return_value=recs):
            rows = form_images.check_form_images(context)
        self.assertEqual([(r["판정"], r["region_path"]) for r in rows], [("부적합", "section1 > 활용 서식 > 문단 12")])
        context.presence = {}
        self.assertEqual(form_images.check_form_images(context)[0]["체크"], {"⑧ 서식·부록 글자 이미지 해상도": "-"})


class BrandNameTests(unittest.TestCase):
    def run_rule(self, body, presence=None):
        manuscript = SimpleNamespace(format="hwpx", sections=[[], body], section_aside_paragraphs=lambda i: frozenset())
        context = SimpleNamespace(manuscript=manuscript, config=CheckConfig(), presence=presence or {})
        with mock.patch.object(brand_names, "picture_records", return_value=[]):
            return brand_names.check_brand_names(context)

    def test_names_ambiguous_words_and_exclusions(self):
        body = ["엑셀을 사용하여 순위를 계산한다.",                      # X — 체크리스트 예시
                "출처: 엑셀. 2024. 8. 12. 스크린 숏.",                   # 제외 — F14 스크린 숏 출처
                "메타데이터와 애플리케이션을 관리한다.",                  # 제외 — 더 긴 낱말의 앞부분
                "삼성전자 제품을 예로 든다.",                            # X — 기업명
                "보고서는 한글로 작성한다.",                              # △ — 문자인지 프로그램인지
                "Windows 환경에서 실행한다.",                            # X — 운영체제
                "NCS학습모듈 개발이력", "배춘석(LG CNS)"]                  # 제외 — 판권 소속
        rows = self.run_rule(body)
        self.assertEqual([(r["위치"], r["판정"]) for r in rows],
                         [("문단 0", "부적합"), ("문단 3", "부적합"), ("문단 4", "판단불가"), ("문단 5", "부적합")])
        self.assertIn("스프레드시트 프로그램", rows[0]["비고"]["③ 본문 상호·상품명·프로그램명"])

    def test_meta_spaced_prefix_is_ambiguous(self):
        """'메타 데이터'처럼 띄어 쓴 접두어는 회사명(메타)과 구별할 수 없어 X가 아니라 사람 확인(△)."""
        rows = self.run_rule(["메타 데이터를 관리한다.", "메타 정보를 기록한다."])
        self.assertEqual([r["판정"] for r in rows], ["판단불가", "판단불가"])

    def test_clean_text_and_references_excluded(self):
        body = ["요구사항을 분석한다.", "참고 자료", "∙Microsoft(2020). 『Guide』. Microsoft Press."]
        rows = self.run_rule(body, {"참고 자료": {"있음": True, "k": 1, "end": 2}})
        self.assertEqual([r["판정"] for r in rows], ["적합"])


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
