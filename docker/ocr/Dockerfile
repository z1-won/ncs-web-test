# 그림 속 글자 읽기(PaddleOCR) 이미지 — 원고 이미지 검수 ② 마크·워터마크(ncs_figures/marks.py)가 docker run으로 잠깐 쓴다.
# 만들기(저장소 루트에서):  docker compose build ocr        또는  docker build -f docker/ocr/Dockerfile -t ncs-ocr .
# 쓰기: .env에 FIG_OCR_DOCKER=ncs-ocr                      설명: docs/WEB.md '그림 속 글자 읽기'
#
# 모델 파일을 만들 때 받아 이미지에 넣어 둔다. 그래서 읽을 때는 네트워크 없이(--network none) 돈다 — 그림이 밖으로 나갈 길이 없다.
# paddlepaddle이 파이썬 3.13까지만 나와서(2026-11 기준) 3.13을 쓴다. linux/arm64(Apple Silicon)·linux/amd64 모두 휠이 있다.
FROM python:3.13-slim

# 다른 모델을 넣으려면: docker compose build --build-arg OCR_DET=PP-OCRv5_mobile_det ocr  (그리고 .env의 FIG_OCR_DET도 같은 이름으로)
ARG OCR_DET=""
ARG OCR_REC=""
# 모델을 돌리는 엔진. 리눅스 ARM64에서 paddle 엔진이 읽다가 Segmentation fault로 죽어서(2026-11-23 Apple Silicon 도커에서 확인)
# ONNX Runtime으로 돌린다. 여기서 받아 두는 모델도 ONNX 판이다. paddle로 되돌리려면 --build-arg OCR_ENGINE=paddle 과 FIG_OCR_ENGINE=paddle.
ARG OCR_ENGINE="onnxruntime"

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PADDLE_PDX_CACHE_HOME=/opt/paddlex

# opencv(paddleocr가 데려옴)가 쓰는 시스템 라이브러리
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/ocr.txt /opt/ocr/requirements.txt
RUN pip install -r /opt/ocr/requirements.txt

# 모델 받아 두기 — 실행 때 쓰는 것과 같은 함수로 올려 본다(받지 못하면 여기서 빌드가 실패한다).
# 실행 때는 저장소의 paddle_ocr.py를 /ocr에 붙여 쓰므로, 이 사본은 모델을 받는 데만 쓴다.
COPY src/ncs_figures/data/paddle_ocr.py /opt/ocr/paddle_ocr.py
RUN cd /opt/ocr \
    && python -c "import os, paddle_ocr; paddle_ocr.build('korean', os.environ.get('OCR_DET', ''), os.environ.get('OCR_REC', ''), os.environ.get('OCR_ENGINE', ''))" \
    && chmod -R a+rX /opt/paddlex

# 모델이 이미 들어 있으므로 실행 때 모델 저장소에 닿는지 확인하지 않는다(네트워크 없이 바로 시작)
ENV PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True

WORKDIR /work
CMD ["python", "--version"]
