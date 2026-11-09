"""python -m ncs_overview 원고.hwpx [개발계획서.hwp] [--module-code LM...] [--out 결과]"""

from ncs_service.cli import run_cli


def main() -> None:
    run_cli("overview", "F02 학습모듈의 개요 ①·②·⑤·⑥·⑧ 검수")


if __name__ == "__main__":
    main()
