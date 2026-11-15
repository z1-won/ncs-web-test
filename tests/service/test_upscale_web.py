"""그림 업스케일 웹 경로 — 그림 목록 → 원본 보기 → 한 장씩 업스케일 → 결과 내려받기 → 제안본 hwpx.

엔진 대신 Lanczos로 키우는 가짜 엔진(app.state.upscale_runner)을 쓴다. 원고는 시험 원고에 그림 문단·BMP·매니페스트를 넣어 만든다.
"""

import io
import json
import re
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from urllib.parse import unquote

try:
    from PIL import Image
except ImportError:  # Pillow는 업스케일 기능에만 필요하다
    Image = None

ROOT = Path(__file__).resolve().parents[2]
MANUSCRIPT = ROOT / "tests" / "fixtures" / "원고_ok_LM1203020201_24v3.hwpx"
HC = "http://www.hancom.co.kr/hwpml/2011/core"
HPF = ('<?xml version="1.0" encoding="UTF-8"?><opf:package xmlns:opf="http://www.idpf.org/2007/opf/"><opf:manifest>'
       '<opf:item id="image1" href="BinData/image1.bmp" media-type="image/bmp" isEmbeded="1"/>'
       '<opf:item id="image2" href="BinData/image2.png" media-type="image/png" isEmbeded="1"/>'
       '</opf:manifest></opf:package>')


def picture_bytes(size, fmt):
    image = Image.new("RGB", size, "white")
    for x in range(2, size[0] - 2):
        image.putpixel((x, size[1] // 2), (20, 20, 20))
    buffer = io.BytesIO()
    image.save(buffer, fmt)
    return buffer.getvalue()


def pic(bin_id, width_hwp, height_hwp):
    return (f'<hp:p><hp:run charPrIDRef="0"><hp:pic><hp:sz width="{width_hwp}" height="{height_hwp}"/>'
            f'<hc:img binaryItemIDRef="{bin_id}"/></hp:pic></hp:run></hp:p>')


def caption(text):
    return f'<hp:p><hp:run charPrIDRef="0"><hp:t>{text}</hp:t></hp:run></hp:p>'


def manuscript_with_pictures() -> bytes:
    """image1: 200×100px BMP를 2×1인치로 출력(100 DPI, X). image2: 600×300px PNG를 2×1인치로(300 DPI, 대상 아님)."""
    out = io.BytesIO()
    with zipfile.ZipFile(MANUSCRIPT) as source, zipfile.ZipFile(out, "w") as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename == "Contents/section1.xml":
                text = data.decode("utf-8")
                text = text.replace("<hp:sec ", f'<hp:sec xmlns:hc="{HC}" ', 1)
                first = text.index("<hp:p>")
                block = pic("image1", 14400, 7200) + caption("[그림 1-1] 시험 도표") + pic("image2", 14400, 7200) + caption("[그림 1-2] 선명한 도표")
                data = (text[:first] + block + text[first:]).encode("utf-8")
            target.writestr(item, data, compress_type=item.compress_type)
        target.writestr("Contents/content.hpf", HPF, compress_type=zipfile.ZIP_DEFLATED)
        target.writestr("BinData/image1.bmp", picture_bytes((200, 100), "BMP"), compress_type=zipfile.ZIP_DEFLATED)
        target.writestr("BinData/image2.png", picture_bytes((600, 300), "PNG"), compress_type=zipfile.ZIP_DEFLATED)
    return out.getvalue()


def saved_name(response) -> str:
    """Content-Disposition의 filename*(UTF-8) — 브라우저가 저장할 이름."""
    return unquote(re.search(r"filename\*=UTF-8''(.+)$", response.headers["content-disposition"]).group(1))


def fake_engine(src: Path, out: Path, scale: int) -> None:
    for f in src.glob("*.png"):
        with Image.open(f) as image:
            image.resize((image.width * scale, image.height * scale), Image.LANCZOS).save(out / f.name)


@unittest.skipIf(Image is None, "Pillow 없음")
class UpscaleWebTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from ncs_web.server import create_app

        self.out = tempfile.TemporaryDirectory()
        app = create_app(out_dir=self.out.name)
        app.state.upscale_runner = fake_engine
        self.client = TestClient(app)
        self.client.__enter__()
        name = MANUSCRIPT.name.replace(".hwpx", "_그림.hwpx")
        response = self.client.post("/api/uploads", files=[("files", (name, manuscript_with_pictures()))])
        self.assertEqual(response.status_code, 200, response.text)
        self.token = response.json()["upload"]
        self.assertEqual(response.json()["roles"]["manuscript"], name)

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.out.cleanup()

    def url(self, tail=""):
        return f"/api/uploads/{self.token}/pictures{tail}"

    def test_list_original_upscale_download_and_proposal(self):
        listing = self.client.get(self.url())
        self.assertEqual(listing.status_code, 200, listing.text)
        body = listing.json()
        self.assertEqual([p["bin_id"] for p in body["pictures"]], ["image1"])      # 300 DPI인 image2는 대상 아님
        first = body["pictures"][0]
        self.assertEqual((first["dpi"], first["grade"], first["scale"], first["caption"]), (100, "X", 2, "[그림 1-1] 시험 도표"))
        self.assertIsNone(first["upscaled"])
        self.assertTrue(body["engine"]["available"])

        original = self.client.get(self.url("/image1/original"))
        self.assertEqual(original.headers["content-type"], "image/png")
        with Image.open(io.BytesIO(original.content)) as image:
            self.assertEqual(image.size, (200, 100))                                 # BMP → 브라우저용 PNG

        self.assertEqual(self.client.get(self.url("/image1/upscaled")).status_code, 400)   # 아직 결과 없음
        self.assertEqual(self.client.post(f"/api/uploads/{self.token}/proposal").status_code, 400)

        done = self.client.post(self.url("/image1/upscale"))
        self.assertEqual(done.status_code, 200, done.text)
        info = done.json()
        self.assertEqual((info["status"], info["out_px"], info["out_dpi"], info["new_href"]),
                         ("완료", [400, 200], 200, "BinData/image1.png"))
        self.assertIn("목표 DPI에 못 미침", info["note"])                             # 필요 x3인데 x2까지만

        result = self.client.get(self.url("/image1/upscaled"), params={"download": "LM_[그림 1-1] 시험/도표_업스케일"})
        self.assertEqual(result.headers["content-type"], "image/png")
        self.assertIn("attachment", result.headers["content-disposition"])
        self.assertEqual(saved_name(result), "LM_[그림 1-1] 시험_도표_업스케일.png")   # '/'는 '_'로, 확장자는 결과 형식
        with Image.open(io.BytesIO(result.content)) as image:
            self.assertEqual(image.size, (400, 200))

        again = self.client.get(self.url()).json()["pictures"][0]["upscaled"]        # 목록에 결과가 남는다
        self.assertEqual(again["status"], "완료")

        proposal = self.client.post(f"/api/uploads/{self.token}/proposal", data={"module_code": "LM1203020201_24v3"})
        self.assertEqual(proposal.status_code, 200, proposal.text)
        self.assertEqual(json.loads(proposal.headers["x-upscale-summary"]), {"바꾼 그림": 1, "그림": ["image1"]})
        self.assertEqual(saved_name(proposal), "원고_ok_LM1203020201_24v3_그림_업스케일제안.hwpx")
        with zipfile.ZipFile(io.BytesIO(proposal.content)) as z:
            self.assertEqual(z.infolist()[0].filename, "mimetype")
            names = z.namelist()
            self.assertIn("BinData/image1.png", names)
            self.assertNotIn("BinData/image1.bmp", names)
            self.assertIn('href="BinData/image1.png" media-type="image/png"', z.read("Contents/content.hpf").decode())
            with zipfile.ZipFile(MANUSCRIPT) as before:
                self.assertEqual(z.read("Contents/header.xml"), before.read("Contents/header.xml"))

    def test_errors_are_messages(self):
        self.assertEqual(self.client.get("/api/uploads/nope/pictures").status_code, 400)
        self.assertIn("만료", self.client.get("/api/uploads/nope/pictures").json()["error"])
        self.assertEqual(self.client.get(self.url("/image9/original")).status_code, 400)
        not_target = self.client.post(self.url("/image2/upscale"))                  # 이미 300 DPI
        self.assertEqual(not_target.status_code, 400)
        self.assertIn("대상이 아닙니다", not_target.json()["error"])

    def test_failed_upscale_is_reported_and_left_out_of_proposal(self):
        def black(src, out, scale):
            for f in src.glob("*.png"):
                with Image.open(f) as image:
                    Image.new("RGB", (image.width * scale, image.height * scale), "black").save(out / f.name)
        self.client.app.state.upscale_runner = black
        info = self.client.post(self.url("/image1/upscale")).json()
        self.assertEqual(info["status"], "실패")
        self.assertEqual(self.client.get(self.url("/image1/upscaled")).status_code, 400)
        self.assertEqual(self.client.post(f"/api/uploads/{self.token}/proposal").status_code, 400)

    def test_picture_requests_keep_the_upload_alive(self):
        store = self.client.app.state.uploads
        kept = store.get(self.token)
        kept.expires_at -= store.ttl - 1                       # 1초 뒤 만료될 상태
        self.client.get(self.url())
        self.assertGreater(kept.expires_at - time.monotonic(), store.ttl - 5)


if __name__ == "__main__":
    unittest.main()
