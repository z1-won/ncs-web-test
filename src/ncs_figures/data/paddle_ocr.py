"""PaddleOCR로 그림 속 글자를 읽는 따로 도는 스크립트 — 설치만 하면 외부 전송 없음(모델 파일은 처음 한 번 내려받는다).

ncs_figures.marks.PaddleOcr이 다른 파이썬으로 부른다. paddlepaddle이 검수 서버의 파이썬(3.14)용으로는 나오지 않아
PaddleOCR을 깐 파이썬(3.13 이하)을 따로 두기 때문이다. 그래서 이 파일은 ncs_* 패키지를 import하지 않는다.

    python paddle_ocr.py --list 목록.txt --out 결과.json [--lang korean] [--det 모델] [--rec 모델] [--engine onnxruntime]

목록.txt: 줄마다 그림 경로(UTF-8). 결과.json: {경로: [읽은 줄, …]}. 읽지 못한 그림은 ["__ERROR__ 까닭"] (win_ocr.ps1과 같은 약속).
--lang korean이면 PaddleOCR 3.7 기준으로 검출 PP-OCRv5_server_det + 인식 korean_PP-OCRv5_mobile_rec을 쓴다(한국어는 PP-OCRv6에 없음).
--det·--rec 가운데 하나라도 주면 두 모델 이름을 직접 정한다(주지 않은 쪽은 위 기본값) — 그때 PaddleOCR은 lang을 보지 않는다.
--engine: 모델을 돌리는 엔진(PaddleOCR의 engine 인자 — paddle, onnxruntime 등). 비우면 PaddleOCR 기본(paddle).
리눅스 ARM64(Apple Silicon의 도커 포함)에서는 paddle 엔진이 읽는 도중 Segmentation fault로 죽는다(paddlepaddle 3.2.2에서 확인,
PaddleOCR 이슈 #16609·#16685 등) — 그 환경에서는 onnxruntime을 쓴다. 같은 모델의 ONNX 판(_onnx)을 받아 쓴다.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_DET = "PP-OCRv5_server_det"
DEFAULT_REC = "korean_PP-OCRv5_mobile_rec"


def build(lang: str, det: str, rec: str, engine: str = ""):
    from paddleocr import PaddleOCR
    # 문서 방향·펴기·줄 방향 보조 모델은 끈다 — 원고 속 그림은 바로 선 그림이고, 모델을 셋 더 올리면 느려지기만 한다
    options = {"use_doc_orientation_classify": False, "use_doc_unwarping": False, "use_textline_orientation": False}
    if engine:
        options["engine"] = engine
    if det or rec:
        return PaddleOCR(text_detection_model_name=det or DEFAULT_DET, text_recognition_model_name=rec or DEFAULT_REC, **options)
    return PaddleOCR(lang=lang, **options)


def lines_of(results) -> list[str]:
    """predict 결과(그림 하나에 dict 하나, 'rec_texts'에 읽은 줄) → 빈 줄을 뺀 글 목록."""
    out: list[str] = []
    for result in results or []:
        for text in result.get("rec_texts") or []:
            text = str(text).strip()
            if text:
                out.append(text)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--list", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--lang", default="korean")
    parser.add_argument("--det", default="")
    parser.add_argument("--rec", default="")
    parser.add_argument("--engine", default="")
    args = parser.parse_args(argv)
    paths = [line for line in Path(args.list).read_text(encoding="utf-8").splitlines() if line]
    try:
        ocr = build(args.lang, args.det, args.rec, args.engine)
    except Exception as error:  # noqa: BLE001 — 설치 안 됨·모델을 못 받음: 그림마다 같은 까닭을 남긴다
        message = f"__ERROR__ PaddleOCR을 올리지 못함: {type(error).__name__}: {error}"[:300]
        Path(args.out).write_text(json.dumps({path: [message] for path in paths}, ensure_ascii=False), encoding="utf-8")
        return 1
    out: dict[str, list[str]] = {}
    for path in paths:
        try:
            out[path] = lines_of(ocr.predict(path))
        except Exception as error:  # noqa: BLE001 — 그림 하나 때문에 나머지를 버리지 않는다
            out[path] = [f"__ERROR__ {type(error).__name__}: {error}"[:300]]
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
