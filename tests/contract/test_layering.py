"""패키지 계층 규약 검사: 검수 패키지는 서로를 import하지 않고, ncs_core는 검수 패키지를 모른다.
검수 엔진이 아닌 기능 패키지(개발계획서 ncs_plan, 그림 업스케일 ncs_upscale, 원고 분량 ncs_volume, 검토의견서 반영 ncs_opinion, 문장 추천 ncs_suggest)도 검수 패키지를 import하지 않는다 — 함께 쓰는 코드는 ncs_core에 둔다."""

import re
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
ENGINES = ("ncs_position", "ncs_toc", "ncs_overview", "ncs_knowledge", "ncs_perform", "ncs_teaching", "ncs_evaluation", "ncs_references", "ncs_colophon", "ncs_misc")
FEATURES = ("ncs_plan", "ncs_upscale", "ncs_volume", "ncs_opinion", "ncs_suggest")   # 검수 엔진은 아니지만 같은 층(ncs_core 위)에 서는 기능 패키지
IMPORT = re.compile(r"^\s*(?:from|import)\s+(ncs_\w+)", re.MULTILINE)


def imported_packages(package: str) -> dict[str, set[str]]:
    """{상대 파일 경로: 그 파일이 import하는 ncs_* 최상위 패키지들}"""
    out = {}
    for path in sorted((SRC / package).rglob("*.py")):
        names = set(IMPORT.findall(path.read_text(encoding="utf-8")))
        if names:
            out[str(path.relative_to(SRC))] = names
    return out


class LayeringTest(unittest.TestCase):
    def test_engines_do_not_import_each_other(self):
        for engine in ENGINES:
            others = (set(ENGINES) - {engine}) | {"ncs_web"}
            for file, names in imported_packages(engine).items():
                self.assertFalse(names & others, f"{file}이(가) 다른 검수 패키지를 import합니다: {sorted(names & others)}")

    def test_feature_packages_do_not_import_engines(self):
        for feature in FEATURES:
            others = set(ENGINES) | (set(FEATURES) - {feature}) | {"ncs_web"}
            for file, names in imported_packages(feature).items():
                self.assertFalse(names & others, f"{file}이(가) 검수 패키지나 다른 기능 패키지를 import합니다: {sorted(names & others)} — 함께 쓰는 코드는 ncs_core로 옮기세요")

    def test_core_imports_no_engine_or_service(self):
        forbidden = set(ENGINES) | set(FEATURES) | {"ncs_service", "ncs_web"}
        for file, names in imported_packages("ncs_core").items():
            self.assertFalse(names & forbidden, f"{file}이(가) 상위 계층을 import합니다: {sorted(names & forbidden)}")

    def test_engine_cli_is_the_only_service_user(self):
        for engine in ENGINES:
            for file, names in imported_packages(engine).items():
                if "ncs_service" in names:
                    self.assertTrue(file.endswith("__main__.py"), f"{file}: ncs_service는 CLI(__main__)만 쓸 수 있습니다")


if __name__ == "__main__":
    unittest.main()
