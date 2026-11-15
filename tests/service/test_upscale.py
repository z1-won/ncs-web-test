"""그림 업스케일 제안본(ncs_upscale) — 엔진 없이 가짜 엔진으로 고르기·결과 검사·hwpx 다시 쓰기를 확인한다."""

import io
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock

try:
    from PIL import Image
except ImportError:  # Pillow는 업스케일 기능에만 필요하다
    Image = None

if Image is not None:
    from ncs_upscale.engine import ENGINES
    from ncs_upscale.pipeline import plan, upscale, write_hwpx

MANIFEST = ('<?xml version="1.0" encoding="UTF-8"?><opf:package xmlns:opf="http://www.idpf.org/2007/opf/"><opf:manifest>'
            '<opf:item id="header" href="Contents/header.xml" media-type="application/xml"/>'
            '<opf:item id="image1" href="BinData/image1.bmp" media-type="image/bmp" isEmbeded="1"/>'
            '<opf:item id="image2" href="BinData/image2.jpg" media-type="image/jpg" isEmbeded="1"/>'
            '</opf:manifest></opf:package>')


def picture(size, fmt, color=(30, 30, 30)):
    image = Image.new("RGB", size, "white")
    for x in range(2, size[0] - 2):          # 가운데 검은 가로줄 — 결과 비교가 의미 있게
        image.putpixel((x, size[1] // 2), color)
    buffer = io.BytesIO()
    image.save(buffer, fmt)
    return buffer.getvalue()


def record(bin_id, data, fmt, px, dpi, para=1, size=(14400, 7200)):
    return {"section": 1, "para": para, "bin_id": bin_id, "format": fmt, "px": px, "size_hwp": size,
            "mm": (51, 25), "dpi": dpi, "caption": f"[그림 1-{para}] 시험", "data": data}


def package(entries):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for name, data in entries:
            z.writestr(name, data, compress_type=zipfile.ZIP_STORED if name == "mimetype" else zipfile.ZIP_DEFLATED)
    return out.getvalue()


def fake_engine(color=None):
    """원본을 Lanczos로 키우는 가짜 엔진. color를 주면 그 색으로 채운 그림을 낸다(엔진 오류 흉내)."""
    def run(src: Path, out: Path, scale: int):
        for f in src.glob("*.png"):
            with Image.open(f) as image:
                size = (image.width * scale, image.height * scale)
                result = Image.new("RGB", size, color) if color else image.resize(size, Image.LANCZOS)
                result.save(out / f.name)
    return run


@unittest.skipIf(Image is None, "Pillow 없음")
class PlanTests(unittest.TestCase):
    def test_scale_choice_and_shared_files(self):
        engine = ENGINES["waifu2x-photo"]
        self.assertEqual(engine.pick_scale(1.4, 2), 2)
        self.assertEqual(engine.pick_scale(2.8, 2), 2)       # 상한 안에서 가장 큰 배율
        self.assertEqual(engine.pick_scale(2.8, 4), 4)
        self.assertEqual(ENGINES["esrgan-best"].pick_scale(1.2, 2), 4)   # x4만 있는 엔진
        bmp = picture((100, 50), "BMP")
        records = [record("image1", bmp, "bmp", (100, 50), 150, para=1),
                   record("image1", bmp, "bmp", (100, 50), 100, para=5),   # 같은 그림을 더 크게 출력한 자리
                   record("image2", b"x", "jpeg", (600, 300), 300),          # 목표 이상
                   record("image3", b"", None, (0, 0), None)]                # 파일 없음
        binaries = {"image1": {"href": "BinData/image1.bmp"}, "image2": {"href": "BinData/image2.jpg"}}
        jobs, skipped = plan(records, binaries, engine, target_dpi=300, max_scale=2)
        self.assertEqual([(j.bin_id, j.dpi, j.scale, len(j.uses), j.href) for j in jobs], [("image1", 100, 2, 2, "BinData/image1.bmp")])
        self.assertFalse(jobs[0].reaches_target)               # 필요 x3인데 x2까지만
        self.assertEqual([s["이유"] for s in skipped], ["그림 파일 없음"])


@unittest.skipIf(Image is None, "Pillow 없음")
class UpscaleAndWriteTests(unittest.TestCase):
    def setUp(self):
        self.bmp = picture((80, 40), "BMP")
        self.jpg = picture((60, 30), "JPEG")
        self.source = package([("mimetype", b"application/hwp+zip"), ("version.xml", b"<v/>"),
                               ("Contents/content.hpf", MANIFEST.encode()), ("BinData/image1.bmp", self.bmp),
                               ("BinData/image2.jpg", self.jpg), ("Contents/section0.xml", b"<s/>")])
        self.records = [record("image1", self.bmp, "bmp", (80, 40), 150), record("image2", self.jpg, "jpeg", (60, 30), 200, para=3)]
        self.binaries = {"image1": {"href": "BinData/image1.bmp"}, "image2": {"href": "BinData/image2.jpg"}}

    def test_bmp_becomes_png_and_package_keeps_everything_else(self):
        jobs, _ = plan(self.records, self.binaries, ENGINES["waifu2x-photo"], target_dpi=300, max_scale=2)
        upscale(jobs, ENGINES["waifu2x-photo"], runner=fake_engine(), progress=lambda _: None)
        self.assertEqual([j.status for j in jobs], ["완료", "완료"])
        first, second = jobs
        self.assertEqual((first.out_px, first.out_dpi, first.new_href), ((160, 80), 300, "BinData/image1.png"))
        self.assertEqual((second.out_px, second.new_href), ((90, 45), "BinData/image2.jpg"))   # 필요 x1.5 → 줄여서 맞춤
        content = write_hwpx(self.source, jobs)
        with zipfile.ZipFile(io.BytesIO(content)) as z, zipfile.ZipFile(io.BytesIO(self.source)) as before:
            infos = z.infolist()
            self.assertEqual(infos[0].filename, "mimetype")
            self.assertEqual(infos[0].compress_type, zipfile.ZIP_STORED)
            self.assertEqual([i.filename for i in infos],
                             ["mimetype", "version.xml", "Contents/content.hpf", "BinData/image1.png", "BinData/image2.jpg", "Contents/section0.xml"])
            for name in ("mimetype", "version.xml", "Contents/section0.xml"):
                self.assertEqual(z.read(name), before.read(name))
            manifest = z.read("Contents/content.hpf").decode()
            self.assertIn('<opf:item id="image1" href="BinData/image1.png" media-type="image/png" isEmbeded="1"/>', manifest)
            self.assertIn('<opf:item id="image2" href="BinData/image2.jpg" media-type="image/jpg" isEmbeded="1"/>', manifest)
            with Image.open(io.BytesIO(z.read("BinData/image1.png"))) as image:
                self.assertEqual(image.size, (160, 80))
                self.assertAlmostEqual(image.info["dpi"][0], 192, delta=0.5)   # 96 DPI × 2 → 원래 크기(인치) 유지
            with Image.open(io.BytesIO(z.read("BinData/image2.jpg"))) as image:
                self.assertEqual(image.format, "JPEG")

    def test_broken_engine_output_is_rejected(self):
        jobs, _ = plan(self.records[:1], self.binaries, ENGINES["waifu2x-photo"], target_dpi=300, max_scale=2)
        upscale(jobs, ENGINES["waifu2x-photo"], runner=fake_engine(color=(0, 0, 0)), progress=lambda _: None)
        self.assertEqual(jobs[0].status, "실패")
        self.assertIn("크게 다름", jobs[0].note)
        self.assertEqual(write_hwpx(self.source, jobs), write_hwpx(self.source, []))   # 실패한 그림은 바꾸지 않음

    def test_partly_broken_output_is_rejected_by_tile_check(self):
        def damaged(src, out, scale):          # 정상 확대 후 선이 지나는 칸 하나만 검게 — 전체 평균 차는 기준(40) 아래
            fake_engine()(src, out, scale)
            for f in out.glob("*.png"):
                with Image.open(f) as image:
                    image = image.copy()
                image.paste((0, 0, 0), (32, 32, 64, 64))
                image.save(f)
        jobs, _ = plan(self.records[:1], self.binaries, ENGINES["waifu2x-photo"], target_dpi=300, max_scale=2)
        upscale(jobs, ENGINES["waifu2x-photo"], runner=damaged, progress=lambda _: None)
        self.assertEqual(jobs[0].status, "실패")
        self.assertLess(jobs[0].diff, 40)
        self.assertIn("칸 최대 차", jobs[0].note)

    def test_good_output_records_small_differences(self):
        jobs, _ = plan(self.records, self.binaries, ENGINES["waifu2x-photo"], target_dpi=300, max_scale=2)
        upscale(jobs, ENGINES["waifu2x-photo"], runner=fake_engine(), progress=lambda _: None)
        for job in jobs:
            self.assertLess(job.tile_diff, 40)
            self.assertNotIn("사람 확인", job.note)

    def test_batch_failure_retries_one_by_one(self):
        calls = []

        def picky(src, out, scale):            # 여러 장을 한 번에 주면 실패, 0000.png(image1)은 혼자서도 실패
            names = sorted(f.name for f in src.glob("*.png"))
            calls.append(names)
            if len(names) > 1 or names == ["0000.png"]:
                raise RuntimeError("Vulkan 오류")
            fake_engine()(src, out, scale)
        jobs, _ = plan(self.records, self.binaries, ENGINES["waifu2x-photo"], target_dpi=300, max_scale=2)
        messages = []
        upscale(jobs, ENGINES["waifu2x-photo"], runner=picky, progress=messages.append)
        self.assertEqual(calls, [["0000.png", "0001.png"], ["0000.png"], ["0001.png"]])
        self.assertEqual([(j.bin_id, j.status) for j in jobs], [("image1", "실패"), ("image2", "완료")])
        self.assertTrue(any("한 장씩 다시 시도" in m for m in messages))

    def test_progress_is_reported_while_engine_runs(self):
        def slow(src, out, scale):
            fake_engine()(src, out, scale)
            time.sleep(0.3)
        jobs, _ = plan(self.records, self.binaries, ENGINES["waifu2x-photo"], target_dpi=300, max_scale=2)
        messages = []
        with mock.patch("ncs_upscale.pipeline.PROGRESS_EVERY", 0.05):
            upscale(jobs, ENGINES["waifu2x-photo"], runner=slow, progress=messages.append)
        self.assertTrue(any(m.strip().startswith("2/2장") for m in messages), messages)

    def test_engine_timeout_becomes_timeout_error(self):
        import subprocess
        import tempfile
        engine = ENGINES["waifu2x-photo"]
        with tempfile.TemporaryDirectory() as tools:
            exe = Path(tools) / engine.folder / engine.exe
            exe.parent.mkdir()
            exe.write_bytes(b"")
            with mock.patch("ncs_upscale.engine.subprocess.run", side_effect=subprocess.TimeoutExpired("x", 5)) as run:
                with self.assertRaises(TimeoutError):
                    engine.run(Path(tools), Path(tools), 2, Path(tools), timeout=5)
            self.assertEqual(run.call_args.kwargs["timeout"], 5)

    def test_engine_error_marks_jobs_failed(self):
        def broken(src, out, scale):
            raise RuntimeError("Vulkan 장치 없음")
        jobs, _ = plan(self.records, self.binaries, ENGINES["waifu2x-photo"], target_dpi=300, max_scale=2)
        upscale(jobs, ENGINES["waifu2x-photo"], runner=broken, progress=lambda _: None)
        self.assertEqual({(j.status, j.note) for j in jobs}, {("실패", "Vulkan 장치 없음")})


if __name__ == "__main__":
    unittest.main()
