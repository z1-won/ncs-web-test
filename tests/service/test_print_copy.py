"""출력본(PDF)이 입력 경로를 타는 방식 — 역할 판별, 엔진 전달(optional), 웹 업로드 역할 표시."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ncs_core import load_document, select_documents
from ncs_core.pdf import PdfDocument
from ncs_service import ReviewRequest, execute_review
from ncs_service.registry import ENGINES, Engine, describe_engines

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
MANUSCRIPT = FIXTURES / "원고_ok_LM1203020201_24v3.hwpx"
PLAN = FIXTURES / "개발계획서_LM1203020201_24v3.hwpx"
PRINT_COPY = FIXTURES / "출력본_ok_LM1203020201_24v3.pdf"


class SelectDocumentsTests(unittest.TestCase):
    def test_pdf_is_always_the_print_copy(self):
        documents = select_documents([PRINT_COPY, MANUSCRIPT, PLAN])
        self.assertEqual(set(documents), {"manuscript", "plan", "print"})
        self.assertIsInstance(documents["print"], PdfDocument)
        self.assertEqual(documents["print"].module_code, "LM1203020201_24v3")

    def test_print_copy_is_optional_and_cannot_replace_manuscript(self):
        self.assertEqual(set(select_documents([MANUSCRIPT])), {"manuscript"})
        with self.assertRaisesRegex(ValueError, "원고 파일이 필요합니다"):
            select_documents([PRINT_COPY])
        with self.assertRaisesRegex(ValueError, "출력본으로만"):
            select_documents([PRINT_COPY, MANUSCRIPT], roles={str(PRINT_COPY): "manuscript"})
        with self.assertRaisesRegex(ValueError, "출력본은 PDF여야"):
            select_documents([MANUSCRIPT, PLAN], roles={str(PLAN): "print"})
        with tempfile.TemporaryDirectory() as folder:
            twin = Path(folder) / "사본.pdf"
            twin.write_bytes(PRINT_COPY.read_bytes())
            with self.assertRaisesRegex(ValueError, "출력본 파일이 둘 이상"):
                select_documents([MANUSCRIPT, PRINT_COPY, twin])

    def test_load_document_refuses_pdf_with_guidance(self):
        with self.assertRaisesRegex(ValueError, "PDF는 원고로 읽지 않습니다"):
            load_document(PRINT_COPY)


class EngineDispatchTests(unittest.TestCase):
    def test_print_copy_reaches_only_engines_that_declare_it(self):
        """엔진이 optional=('print',)를 선언했을 때만 prepare_review(print_copy=…)로 넘어간다. 선언하지 않은 엔진은 PDF가 있어도 그대로 돈다."""
        for check, engine in ENGINES.items():
            with self.subTest(check=check):
                module = engine.load()
                paths = (MANUSCRIPT, PLAN, PRINT_COPY)
                with mock.patch.object(module, "prepare_review", wraps=module.prepare_review) as prepare:
                    execute_review(ReviewRequest(paths, check, "LM1203020201_24v3"))
                kwargs = prepare.call_args.kwargs
                if "print" in engine.optional:
                    self.assertIsInstance(kwargs["print_copy"], PdfDocument)
                else:
                    self.assertNotIn("print_copy", kwargs)

    def test_optional_is_passed_only_when_present(self):
        declared = Engine("ncs_toc", optional=("print",))
        with mock.patch.dict(ENGINES, {"toc": declared}):
            module = declared.load()
            with mock.patch.object(module, "prepare_review", wraps=module.prepare_review) as prepare:
                execute_review(ReviewRequest((MANUSCRIPT,), "toc", "LM1203020201_24v3"))
            self.assertNotIn("print_copy", prepare.call_args.kwargs)

    def test_describe_engines_reports_optional(self):
        for row in describe_engines():
            self.assertIn("optional", row)
            self.assertEqual(row["optional"], list(ENGINES[row["check"]].optional))


if __name__ == "__main__":
    unittest.main()
