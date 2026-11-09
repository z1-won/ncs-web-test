"""python -m ncs_evaluation 원고.hwpx [개발계획서.hwp] [--module-code LM...] [--out 결과]"""

from ncs_service.cli import run_cli


def main() -> None:
    run_cli("evaluation", "F02 평가 ① 검수")


if __name__ == "__main__":
    main()
