"""python -m ncs_misc 원고.hwpx [--module-code LM...] [--out 결과]"""

from ncs_service.cli import run_cli


def main() -> None:
    run_cli("misc", "F02 기타 ①②⑥⑦ 검수")


if __name__ == "__main__":
    main()
