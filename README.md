# F02 검수 웹앱·Python 패키지

HWP/HWPX 원고와 개발계획서를 읽어 위치·차례·개요·필요 지식을 검수합니다.
검수 엔진은 Python 3.10 이상과 표준 라이브러리만 사용하며, 웹 백엔드는 FastAPI·Uvicorn, 화면은 React·Vite 기반입니다.
개발·수정 기준은 `src/`의 Python 소스입니다. 웹 서버와 CLI는 `ncs_service`를 통해 같은 검수·저장 경로를 사용합니다.

## 폴더 구조

- `src/ncs_core/`: 공통 문서 읽기·입력 검증·규칙 실행·결과 저장
- `src/ncs_core/manuscript/`: 차례·개요·본문·개발계획서 구조 파서와 명칭 비교 도우미. 네 검수 패키지가 공유합니다.
- `src/ncs_position/`, `src/ncs_toc/`, `src/ncs_overview/`, `src/ncs_knowledge/`: 검수 패키지. 서로를 import하지 않고 `ncs_core` 위에 평행하게 섭니다(`tests/test_layering.py`가 검사).
- `src/ncs_service/`: HTTP와 독립적인 검수 실행·저장 조정
- `webapp/`: FastAPI 서버와 React 화면. [실행 안내](webapp/README.md)
- `webapp/frontend/dist/`: 웹 화면 빌드 결과
- `tests/`: 합성 입력 생성, 기존 구현 비교, 서비스·웹 API 검증, 패키지 계층(`test_layering.py`)과 엔진 계약(`test_engines.py`) 검사
- `original/`: 리팩토링 전 비교용 Python 소스
- `docs/CONVENTIONS.md`: 공통 개발 규약
- `docs/CONSISTENCY_REVIEW.md`: 통합 리팩토링 기록

## 웹 실행

저장소 루트에서 API 서버를 실행합니다.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r webapp/requirements.txt
.venv/bin/python webapp/server.py
```

별도 터미널에서 화면을 실행합니다.

```bash
cd webapp/frontend
npm install
npm run dev
```

화면은 기본 `http://localhost:5173`, API는 `http://127.0.0.1:8765`입니다.
프런트엔드 폴더에서 `npm run build`를 실행하면 Python 서버가 빌드된 화면도 제공합니다.
API 문서는 `http://127.0.0.1:8765/docs`에서 확인합니다.
검수 결과 JSON·ZIP은 기본 `webapp/결과/`의 실행별 폴더에 저장합니다.

## CLI 실행

저장소 루트에서 실행하며, 입력 파일 경로는 실제 파일 위치로 바꿉니다.

```bash
PYTHONPATH=src python3 -m ncs_toc 원고.hwpx 개발계획서.hwpx --out 결과
PYTHONPATH=src python3 -m ncs_position 원고.hwpx 개발계획서.hwpx --out 결과
PYTHONPATH=src python3 -m ncs_overview 원고.hwpx 개발계획서.hwpx --out 결과
PYTHONPATH=src python3 -m ncs_knowledge 원고.hwpx 개발계획서.hwpx --out 결과
```

## 검수 범위

| 검수 | 구현 항목 | 개발계획서 |
|---|---|---|
| 위치 | ①~⑤ | 필수 |
| 차례 | ①·③·④·⑤·⑥ | 선택 |
| 개요 | ①·②·⑤·⑥·⑧ | 선택 |
| 필요 지식 | ①~⑧ | ⑤ 대조에 필요 |

종합 판정은 실행된 규칙의 결과입니다. 미구현 항목은 확인서의 미검사 및 진단 정보로 확인합니다.
HWP는 글꼴·음영을 읽지 않아 위치 ⑤가 판단불가입니다.
차례·필요지식의 기본 양식은 section0=차례·개요, section1=본문이며 Python API와 CLI 설정으로 조정할 수 있습니다.

## 변경 검증

실행 조정 계층·CLI·웹 API 검증:

```bash
.venv/bin/python -m pip install -r webapp/requirements-dev.txt
.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
```

기존 구현과 비교:

```bash
python3 -I tests/make_fixtures.py tests/fixtures
python3 -I tests/compare_with_original.py original src tests/fixtures
```

비교 검증은 합성 HWPX에 대한 기존 차례·위치 항목을 대상으로 합니다.
비교용 기존 위치 구현에는 `lxml`이 필요합니다. 현재 검수 엔진과 웹 서버에는 필요하지 않습니다.
