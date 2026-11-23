"""② 그림 속 공공누리 마크·저작권 문구·스톡 워터마크 — OCR 줄 해석(흔한 오인식 포함)과 점검 값(가짜 OCR, 외부·OS 기능 안 씀)."""

import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from ncs_figures import marks
from ncs_figures.checks import run_checks
from ncs_figures.config import DEFAULT_CONFIG
from ncs_figures.marks import MarkReader, PaddleOcr, analyze, kogl_type, pick_ocr
from ncs_figures.models import Resources

from .test_review_rules import ctx, item


class FakeOcr:
    name = "fake OCR"

    def __init__(self, lines):
        self.text, self.calls = lines, 0

    def read_many(self, images):
        self.calls += 1
        return {key: (self.text if key.endswith("_full") else []) for key in images}


def outcome(lines, source="출처: 집필진 제작(2025)"):
    checks, _ = run_checks(item(ctx(source=source)), Resources(marks=MarkReader(FakeOcr(lines))), DEFAULT_CONFIG)
    return next(c for c in checks if c.name == "②마크·워터마크")


class AnalyzeTests(unittest.TestCase):
    def test_kogl_types_with_ocr_misreads(self):
        self.assertEqual(kogl_type("OPEN 공공누리 공공저작물 자유이용허락 줄저표시"), "1")          # 출처→줄저
        self.assertEqual(kogl_type("공공누리 공공저작을 자유이용혀락 출저표시 상업용금지"), "2")    # 허락→혀락이어도 0유형 아님
        self.assertEqual(kogl_type("공공누리 출처표시 변경금지"), "3")
        self.assertEqual(kogl_type("공공누리 출처표시 상업용금지 변경금지"), "4")
        self.assertEqual(kogl_type("OPEN 공공누리 공공저작물 자유이용허락 자유이용"), "0")
        self.assertEqual(kogl_type("공공누리 출처표시 상업용금시 변경금시"), "4")                       # 금지→금시(PaddleOCR)
        self.assertIsNone(kogl_type("OPEN 공공누리"))

    def test_copyright_and_stock(self):
        self.assertTrue(analyze(["㉢ 202?) Hanhit Media C.orp AII nghts resetved"])["copyright"])
        self.assertTrue(analyze(["무단 전재 및 재배포 금지"])["copyright"])
        self.assertTrue(analyze(["shutterstock"])["stock"])
        plain = analyze(["요구사항 정의서", "기능 명세", "2025년 계획"])
        self.assertFalse(plain["kogl"] or plain["copyright"] or plain["stock"])


class CheckTests(unittest.TestCase):
    def test_values(self):
        self.assertEqual(outcome(["요구사항 정의"]).value, "O")
        mismatch = outcome(["OPEN 공공누리", "출처표시 변경금지"], source="출처: 공공누리 홈페이지(https://www.kogl.or.kr)에서 2026. 1. 5. 검색. 공공누리 제1유형.")
        self.assertEqual(mismatch.value, "△")
        self.assertIn("제3유형", mismatch.note)
        same = outcome(["OPEN 공공누리", "출처표시"], source="출처: 공공누리 홈페이지(https://www.kogl.or.kr)에서 2026. 1. 5. 검색. 공공누리 제1유형.")
        self.assertEqual(same.value, "O")
        stated_none = outcome(["OPEN 공공누리", "출처표시"])
        self.assertEqual(stated_none.value, "△")
        stock = outcome(["shutterstock"])
        self.assertEqual(stock.value, "△")
        self.assertIn("워터마크", stock.note)

    def test_one_ocr_batch_for_many_figures(self):
        ocr = FakeOcr(["x"])
        reader = MarkReader(ocr)
        reader.prefetch([item(ctx()), item(ctx(caption="[그림 1-2] 나"))])
        self.assertEqual(ocr.calls, 1)

    def test_no_ocr_means_skipped(self):
        checks, _ = run_checks(item(ctx()), Resources(), DEFAULT_CONFIG)
        self.assertIsNone(next(c for c in checks if c.name == "②마크·워터마크").value)


# 가짜 paddleocr 패키지 — data/paddle_ocr.py를 진짜 다른 프로세스로 돌리되 모델은 쓰지 않는다
FAKE_PADDLEOCR = '''
import os
class PaddleOCR:
    def __init__(self, **options):
        if os.environ.get("FAKE_PADDLE_BROKEN"):
            raise RuntimeError("모델을 받지 못함")
        self.options = options
    def predict(self, path):
        if "bad" in os.path.basename(path):
            raise ValueError("깨진 그림")
        names = self.options.get("text_recognition_model_name") or self.options.get("lang")
        engine = self.options.get("engine")
        return [{"rec_texts": ["OPEN 공공누리", " ", "출처표시 변경금지", f"모델:{names}" + (f"@{engine}" if engine else "")],
                 "rec_scores": [0.9, 0.1, 0.8, 1.0]}]
'''


def png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (40, 30), "white").save(buffer, "PNG")
    return buffer.getvalue()


class PaddleOcrTests(unittest.TestCase):
    """PaddleOCR 엔진 — 엔진 고르기와, 따로 도는 스크립트와 주고받는 약속(목록 파일 → 결과 JSON, 캐시, 못 읽은 까닭)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        (root / "fake" / "paddleocr").mkdir(parents=True)
        (root / "fake" / "paddleocr" / "__init__.py").write_text(FAKE_PADDLEOCR, encoding="utf-8")
        self.env = {"FIG_OCR": "paddle", "FIG_OCR_PYTHON": sys.executable, "PYTHONPATH": str(root / "fake"),
                    "FIG_OCR_DET": "", "FIG_OCR_REC": "", "FIG_OCR_DOCKER": "", "FIG_OCR_ENGINE": "", "FAKE_PADDLE_BROKEN": ""}
        patches = [mock.patch.dict(os.environ, self.env), mock.patch.object(marks, "CACHE", root / "cache")]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def test_reads_through_the_script_and_caches(self):
        ocr, reason = pick_ocr()
        self.assertEqual(reason, "")
        self.assertIsInstance(ocr, PaddleOcr)
        read = ocr.read_many({"a_full": png(), "bad_full": png(), "broken_full": b"not an image"})
        self.assertEqual(read["a_full"], ["OPEN 공공누리", "출처표시 변경금지", "모델:korean"])       # 빈 줄은 빠진다
        self.assertIsNone(read["bad_full"])
        self.assertIn("깨진 그림", ocr.last_error)
        self.assertIsNone(read["broken_full"])                                                       # 열 수 없는 그림은 보내지 않는다
        self.assertTrue((ocr.cache / "a_full.json").is_file())
        self.assertFalse((ocr.cache / "bad_full.json").exists())
        with mock.patch.object(marks.subprocess, "run", side_effect=AssertionError("캐시가 있으면 다시 돌리지 않는다")):
            self.assertEqual(PaddleOcr().read_many({"a_full": png()})["a_full"], read["a_full"])

    def test_check_uses_the_lines(self):
        source = "출처: 공공누리 홈페이지(https://www.kogl.or.kr)에서 2026. 1. 5. 검색. 공공누리 제1유형."
        checks, _ = run_checks(item(ctx(source=source)), Resources(marks=MarkReader(PaddleOcr())), DEFAULT_CONFIG)
        found = next(c for c in checks if c.name == "②마크·워터마크")
        self.assertEqual(found.value, "△")
        self.assertIn("제3유형", found.note)
        self.assertIn("PaddleOCR", found.model)

    def test_model_names_change_the_cache_folder(self):
        self.assertEqual(PaddleOcr().cache, marks.CACHE / "paddle")
        with mock.patch.dict(os.environ, {"FIG_OCR_DET": "PP-OCRv5_mobile_det"}):
            ocr = PaddleOcr()
            self.assertNotEqual(ocr.cache, marks.CACHE / "paddle")                # 모델이 다르면 읽은 글도 다르다
            self.assertEqual(ocr.read_many({"a_full": png()})["a_full"][-1], "모델:korean_PP-OCRv5_mobile_rec")

    def test_engine_that_cannot_start_says_why(self):
        with mock.patch.dict(os.environ, {"FAKE_PADDLE_BROKEN": "1"}):
            checks, _ = run_checks(item(ctx()), Resources(marks=MarkReader(PaddleOcr())), DEFAULT_CONFIG)
        found = next(c for c in checks if c.name == "②마크·워터마크")
        self.assertIsNone(found.value)
        self.assertIn("PaddleOCR을 올리지 못함", found.skipped)
        self.assertIn("모델을 받지 못함", found.skipped)

    def test_python_without_paddleocr_says_why(self):
        broken = Path(self.tmp.name) / "none"
        broken.mkdir()
        (broken / "paddleocr.py").write_text('raise ImportError("paddleocr 없음")\n', encoding="utf-8")
        with mock.patch.dict(os.environ, {"PYTHONPATH": str(broken)}):
            ocr = PaddleOcr()
            self.assertIsNone(ocr.read_many({"a_full": png()})["a_full"])
            self.assertIn("paddleocr 없음", ocr.last_error)
            self.assertFalse((ocr.cache / "a_full.json").exists())                 # 못 읽은 것은 캐시에 남기지 않는다

    def test_picking_an_engine(self):
        with mock.patch.dict(os.environ, {"FIG_OCR": "0"}):
            self.assertEqual(pick_ocr(), (None, "FIG_OCR=0으로 꺼 둠"))
            self.assertIsNone(marks.open_marks())
        with mock.patch.dict(os.environ, {"FIG_OCR_PYTHON": str(Path(self.tmp.name) / "없는파이썬")}):
            ocr, reason = pick_ocr()
            self.assertIsNone(ocr)
            self.assertIn("FIG_OCR_PYTHON", reason)
            self.assertEqual(marks.why_not(), reason)
        with mock.patch.dict(os.environ, {"FIG_OCR": "1"}), mock.patch.object(marks.sys, "platform", "darwin"):
            self.assertIsInstance(pick_ocr()[0], PaddleOcr)                      # Windows가 아니면 PaddleOCR
        with mock.patch.dict(os.environ, {"FIG_OCR": "1"}), mock.patch.object(marks.sys, "platform", "win32"):
            self.assertIsInstance(pick_ocr()[0], marks.WindowsOcr)               # Windows는 전부터 쓰던 내장 OCR 그대로
        with mock.patch.dict(os.environ, {"FIG_OCR": "windows"}), mock.patch.object(marks.sys, "platform", "darwin"):
            self.assertEqual(pick_ocr(), (None, "Windows가 아님"))
        with mock.patch.dict(os.environ, {"FIG_OCR": "1", "FIG_OCR_PYTHON": ""}), mock.patch.object(marks.sys, "platform", "darwin"), \
                mock.patch.object(marks, "ROOT", Path(self.tmp.name)), mock.patch.object(marks.importlib.util, "find_spec", return_value=None):
            ocr, reason = pick_ocr()
            self.assertIsNone(ocr)
            self.assertIn(".venv-ocr", reason)


# 가짜 docker 명령 — 받은 인자를 적어 두고, 컨테이너가 하는 일(붙인 폴더 안에서 스크립트 실행)을 호스트에서 흉내 낸다
FAKE_DOCKER = '''#!{python}
import json, os, subprocess, sys
args = sys.argv[1:]
open(os.environ["FAKE_DOCKER_LOG"], "w", encoding="utf-8").write(json.dumps(args))
if os.environ.get("FAKE_DOCKER_DOWN"):
    sys.stderr.write("docker: Cannot connect to the Docker daemon. Is the docker daemon running?\\n")
    sys.exit(125)
mounts = dict(reversed(args[i + 1].split(":")[:2]) for i, a in enumerate(args) if a == "-v")
def host(path):
    for inner, outer in mounts.items():
        if path == inner or path.startswith(inner + "/"):
            return outer + path[len(inner):]
    return path
inner = args[args.index(os.environ["FIG_OCR_DOCKER"]) + 1:]            # python /ocr/paddle_ocr.py --list … --out …
script, options = host(inner[1]), inner[2:]
listing, out = host(options[options.index("--list") + 1]), host(options[options.index("--out") + 1])
names = open(listing, encoding="utf-8").read().splitlines()
open(listing + ".host", "w", encoding="utf-8").write("\\n".join(host(name) for name in names))
rest = [o for i, o in enumerate(options) if o not in ("--list", "--out") and options[i - 1] not in ("--list", "--out")]
done = subprocess.run([sys.executable, script, "--list", listing + ".host", "--out", out + ".host", *rest])
read = json.load(open(out + ".host", encoding="utf-8"))
json.dump({{name: read[host(name)] for name in names}}, open(out, "w", encoding="utf-8"), ensure_ascii=False)
sys.exit(done.returncode)
'''


@unittest.skipUnless(os.name == "posix", "가짜 docker 명령은 셔뱅 스크립트라 POSIX에서만 돈다")
class PaddleDockerTests(unittest.TestCase):
    """FIG_OCR_DOCKER — 컨테이너에 넘기는 인자(네트워크 차단, 붙이는 폴더)와 경로를 /work로 바꿨다 되돌리는 것."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        (root / "fake" / "paddleocr").mkdir(parents=True)
        (root / "fake" / "paddleocr" / "__init__.py").write_text(FAKE_PADDLEOCR, encoding="utf-8")
        (root / "bin").mkdir()
        docker = root / "bin" / "docker"
        docker.write_text(FAKE_DOCKER.format(python=sys.executable), encoding="utf-8")
        docker.chmod(0o755)
        self.log = root / "docker_args.json"
        env = {"FIG_OCR": "paddle", "FIG_OCR_DOCKER": "ncs-ocr", "FIG_OCR_PYTHON": str(root / "없는파이썬"), "FIG_OCR_DET": "", "FIG_OCR_REC": "",
               "FIG_OCR_ENGINE": "",
               "PATH": f"{root / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}", "PYTHONPATH": str(root / "fake"),
               "FAKE_DOCKER_LOG": str(self.log), "FAKE_DOCKER_DOWN": "", "FAKE_PADDLE_BROKEN": ""}
        for patch in (mock.patch.dict(os.environ, env), mock.patch.object(marks, "CACHE", root / "cache")):
            patch.start()
            self.addCleanup(patch.stop)

    def test_reads_in_a_container_without_network(self):
        ocr, reason = pick_ocr()                                  # 도커를 적으면 FIG_OCR_PYTHON보다 먼저다
        self.assertEqual(reason, "")
        self.assertIn("Docker", ocr.name)
        self.assertEqual(ocr.where(), "도커 이미지 ncs-ocr")
        read = ocr.read_many({"a_full": png(), "bad_full": png()})
        self.assertEqual(read["a_full"], ["OPEN 공공누리", "출처표시 변경금지", "모델:korean@onnxruntime"])   # 도커는 ONNX Runtime이 기본
        self.assertIsNone(read["bad_full"])
        self.assertIn("깨진 그림", ocr.last_error)
        args = json.loads(self.log.read_text(encoding="utf-8"))
        self.assertEqual(args[:6], ["run", "--rm", "--pull", "never", "--network", "none"])
        mounts = [args[i + 1] for i, a in enumerate(args) if a == "-v"]
        self.assertTrue(mounts[0].endswith(":/work"))
        self.assertEqual(mounts[1], f"{marks.PADDLE_SCRIPT.parent}:/ocr:ro")
        self.assertEqual(args[args.index("ncs-ocr") + 1:], ["python", "/ocr/paddle_ocr.py", "--list", "/work/list.docker.txt", "--out", "/work/out.docker.json",
                                                             "--engine", "onnxruntime"])
        self.assertTrue((ocr.cache / "a_full.json").is_file())

    def test_model_names_go_into_the_container(self):
        with mock.patch.dict(os.environ, {"FIG_OCR_REC": "en_PP-OCRv5_mobile_rec"}):
            self.assertEqual(PaddleOcr().read_many({"a_full": png()})["a_full"][-1], "모델:en_PP-OCRv5_mobile_rec@onnxruntime")
        self.assertEqual(json.loads(self.log.read_text(encoding="utf-8"))[-4:], ["--engine", "onnxruntime", "--rec", "en_PP-OCRv5_mobile_rec"])
        with mock.patch.dict(os.environ, {"FIG_OCR_ENGINE": "paddle"}):                      # 엔진을 직접 고르면 그것을 쓴다
            self.assertEqual(PaddleOcr().read_many({"b_full": png()})["b_full"][-1], "모델:korean@paddle")

    def test_segfault_is_explained(self):
        crash = mock.Mock(returncode=139, stderr="FatalError: `Segmentation fault` is detected by the operating system.".encode())
        with mock.patch.object(marks.subprocess, "run", return_value=crash):
            ocr = PaddleOcr()
            self.assertIsNone(ocr.read_many({"a_full": png()})["a_full"])
        self.assertIn("Segmentation fault", ocr.last_error)
        self.assertIn("onnxruntime", ocr.last_error)

    def test_docker_not_running_or_missing_says_why(self):
        with mock.patch.dict(os.environ, {"FAKE_DOCKER_DOWN": "1"}):
            checks, _ = run_checks(item(ctx()), Resources(marks=MarkReader(PaddleOcr())), DEFAULT_CONFIG)
        found = next(c for c in checks if c.name == "②마크·워터마크")
        self.assertIsNone(found.value)
        self.assertIn("Cannot connect to the Docker daemon", found.skipped)
        with mock.patch.object(marks.shutil, "which", return_value=None):
            ocr, reason = pick_ocr()
            self.assertIsNone(ocr)
            self.assertIn("docker 명령이 없음", reason)


if __name__ == "__main__":
    unittest.main()
