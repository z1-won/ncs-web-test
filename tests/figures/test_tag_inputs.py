"""009 태깅 — hwp·PDF 입력, 쪽, 규칙 유형 후보, AI 활용 유형(F08 표기 예 1~5) 좁히기, 제출 서류(수록 현황·제작 목록·AI 결과물 현황) 대응."""

import io
import random
import struct
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from ncs_core.figure_context import FigureContext
from ncs_core.source_line import parse_ai_marker, parse_source
from ncs_figures.export import manuscripts_in
from ncs_figures.models import FigureItem
from ncs_figures.submissions import AiEntry, StatusEntry, Submissions
from ncs_figures.tagging import ai_type, pixel_type, submission_part

ROOT = Path(__file__).resolve().parents[2]
HWP = Path(r"C:\ncs\테스트 데이터\LM2001021701_25v1_AIoT 운영 플랫폼 요구사항 분석-원본.hwp")      # 저장소 밖 자료
FINALS = ROOT / "samples" / "최종본_SW제품기획"


def png(draw) -> bytes:
    image = Image.new("RGB", (200, 120), "white")
    draw(image)
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def boxes(image):
    for x in range(20, 80):
        for y in range(20, 60):
            image.putpixel((x, y), (30, 60, 160))


def noise(image):
    rng = random.Random(1)
    for x in range(200):
        for y in range(120):
            image.putpixel((x, y), (rng.randrange(256), rng.randrange(256), rng.randrange(256)))


def item(source="출처: 집필진 제작(2026)", ai="ChatGPT를 활용하여 생성함. 2026. 7. 20.", label="그림 1-1", title="가"):
    ctx = FigureContext(section=1, para=10, bin_id="B", format="png", px=(200, 120), size_hwp=(0, 0), mm=(150, 80), dpi=150,
                        data=png(boxes), caption=f"[{label}] {title}", figure_label=label, figure_title=title,
                        source_line=source, ai_marker_line=ai)
    return FigureItem(ctx=ctx, image_id="i", file_sha256="", phash=None, kind="본문 그림",
                      source=parse_source(source) if source else None, ai=parse_ai_marker(ai) if ai else None,
                      transfer="허용", transfer_reason="")


class AiTypeTests(unittest.TestCase):
    def test_third_party_edit_is_3(self):
        cited = "출처: 교육부(2018). 공급망 공정계획(LM0204010404_16v2). 한국직업능력연구원. p.6."
        decided = ai_type(item(source=cited, ai="ChatGPT를 활용하여 수정 보완함. 2026. 7. 20."), "도표·삽화")
        self.assertEqual(decided["type"], 3)

    def test_own_edit_by_picture_kind(self):
        edited = item(ai="ChatGPT를 활용하여 수정 보완함. 2026. 7. 20.")
        self.assertEqual(ai_type(edited, "사진")["type"], 5)                 # 원본 사진 AI 수정
        self.assertEqual(ai_type(edited, "도표·삽화 후보")["type"], 2)       # 집필진 삽화 AI 수정 보완
        self.assertIsNone(ai_type(edited, None)["type"])

    def test_own_generation_needs_words(self):
        made = item()
        self.assertIsNone(ai_type(made, "도표·삽화")["type"])                       # 1·2·4 — 문구 없이는 못 정함
        self.assertEqual(ai_type(made, "도표·삽화", "AI 창작 이미지")["type"], 4)
        self.assertEqual(ai_type(made, "도표·삽화", "집필진 삽화를 AI로 보완")["type"], 2)
        self.assertEqual(ai_type(made, "도표·삽화", "학습 내용을 바탕으로 흐름도 생성")["type"], 1)
        self.assertIsNone(ai_type(item(ai=None), "사진"))


class PixelTypeTests(unittest.TestCase):
    def test_flat_diagram_and_noisy_photo(self):
        self.assertEqual(pixel_type(png(boxes)), "도표·삽화")
        self.assertEqual(pixel_type(png(noise)), "사진")
        self.assertIsNone(pixel_type(b"not an image"))


class PairingTests(unittest.TestCase):
    def test_pdf_of_same_module_is_print(self):
        folder = Path(tempfile.mkdtemp())
        for name in ("LM2001010401_19v4_가.hwpx", "LM2001010401_19v4_가.pdf", "LM2001010402_19v4_나.pdf", "LM2001010403_19v4_다.hwp"):
            (folder / name).write_bytes(b"")
        pairs = {m.name: (p.name if p else None) for m, p in manuscripts_in([folder])}
        self.assertEqual(pairs, {"LM2001010401_19v4_가.hwpx": "LM2001010401_19v4_가.pdf",   # hwpx가 원고, PDF는 쪽 번호
                                 "LM2001010402_19v4_나.pdf": None,                          # PDF만 있으면 PDF가 원고
                                 "LM2001010403_19v4_다.hwp": None})


class SubmissionTests(unittest.TestCase):
    def test_lists_and_mismatches(self):
        sub = Submissions(status=[StatusEntry("[그림 1-1] 가", "그림 1-1", "집필자 직접제작", "삽화")],
                          ai=[AiEntry("[그림 1-1] 가", "그림 1-1", "12", "Gemini", note="AI 창작")])
        listed, reasons = submission_part(item(), sub)
        self.assertEqual(listed["수록 현황"]["제작 방식"], "집필자 직접제작")
        self.assertEqual(listed["AI 결과물 현황"]["비고"], "AI 창작")
        self.assertTrue(any("활용 AI가 다름" in r for r in reasons))          # 원고 ChatGPT, 서약서 Gemini
        missing, reasons = submission_part(item(label="그림 1-2", title="나"), sub)
        self.assertIsNone(missing["수록 현황"])
        self.assertTrue(any(r.startswith("수록 현황 목록과 다름") for r in reasons))
        self.assertEqual(submission_part(item(), None), (None, []))


class HwpTextTests(unittest.TestCase):
    def test_surrogate_pairs_become_one_character(self):
        from ncs_core.hwp import para_text
        payload = "가".encode("utf-16-le") + "😀".encode("utf-16-le") + struct.pack("<H", 13)
        self.assertEqual(para_text(payload), "가😀 ")


@unittest.skipUnless(HWP.is_file(), "hwp 표본 없음")
class HwpPictureTests(unittest.TestCase):
    def test_pictures_with_captions(self):
        from ncs_core.documents import load_document
        from ncs_core.figure_context import figure_contexts
        document = load_document(HWP)
        contexts = figure_contexts(document)
        self.assertEqual(len(contexts), 22)
        labelled = [c for c in contexts if c.figure_label]
        self.assertEqual(len(labelled), 19)
        self.assertTrue(all(c.source_line and c.format == "bmp" for c in labelled))


@unittest.skipUnless((FINALS / "pdf_한글출력").is_dir(), "최종본 PDF 없음")
class PdfTests(unittest.TestCase):
    def test_pdf_matches_hwpx_and_gives_pages(self):
        from ncs_core.documents import load_document
        from ncs_core.figure_context import figure_contexts
        from ncs_core.pdf_figures import load_pdf_figures
        pdf = next((FINALS / "pdf_한글출력").glob("LM2001010405_*.pdf"))
        document, pages = load_pdf_figures(pdf)
        self.assertEqual(document.layout["결과"], "나눔")
        from_pdf = {c.figure_label: (c.source_line, pages[c.bin_id]["folio"]) for c in figure_contexts(document) if c.figure_label}
        from_hwpx = {c.figure_label: c.source_line for c in figure_contexts(load_document(FINALS / (pdf.stem + ".hwpx"))) if c.figure_label}
        self.assertEqual(set(from_pdf), set(from_hwpx))
        self.assertEqual({k: v[0].replace(" ", "") for k, v in from_pdf.items()}, {k: v.replace(" ", "") for k, v in from_hwpx.items()})
        self.assertTrue(all(v[1] for v in from_pdf.values()))


if __name__ == "__main__":
    unittest.main()
