# F02 검수 로컬 웹앱

FastAPI·Uvicorn 백엔드와 React(Vite) 화면으로 구성됩니다.
`src/ncs_web/server.py`는 파일 업로드·요청 검증·HTTP 응답을, `src/ncs_service/`는 검수 실행·저장 조정을 담당합니다.
`src/ncs_core/`와 네 검수 패키지는 웹 프레임워크 없이도 실행할 수 있습니다.

## 설치·실행

저장소 루트에서 프로젝트 가상환경을 만들고 프로젝트를 설치합니다. 고정된 웹 의존성은 Python 3.11 이상이 필요하며 Python 3.14.5에서 검증했습니다. 엔진만 설치할 때는 Python 3.10 이상을 지원합니다.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[web]"
.venv/bin/ncs-web --out webapp/결과
```

기본 주소는 `http://127.0.0.1:8765`입니다. 위 명령은 결과를 기존 `webapp/결과/`의 실행별 폴더에 저장합니다.
`--port`, `--out`, `--dist` 옵션을 사용합니다. `--src`는 제거하고 설치된 Python 패키지를 사용하도록 통일했습니다.
프로젝트 설치 후에는 기존 `python webapp/server.py --out webapp/결과` 명령도 호환 진입점을 통해 실행됩니다. 이 파일은 설치된 `ncs_web.server`를 호출하며 검색 경로를 추가하지 않습니다.
가상환경을 활성화하면 `ncs-web` 또는 `python -m ncs_web`로도 실행할 수 있습니다.

별도 터미널에서 화면을 실행합니다.

```bash
cd webapp/frontend
npm install
npm run dev
```

화면은 기본 `http://localhost:5173`이며 `/api` 요청은 8765로 프록시합니다.
프런트엔드 폴더에서 `npm run build`를 실행한 뒤, 저장소 루트에서 아래처럼 시작하면 빌드된 화면도 8765에서 제공합니다.

```bash
.venv/bin/ncs-web --out webapp/결과 --dist webapp/frontend/dist
```

## 저장·화면 경로 분리

| 설정 | 생략 시 | 의미 |
|---|---|---|
| `--out` / `create_app(out_dir=...)` | 실행 위치의 `결과/` | 검수 JSON·ZIP 저장 경로 |
| `--dist` / `create_app(dist_dir=...)` | 정적 화면 제공 안 함 | React 빌드 파일 경로 |

두 경로는 서버 파일의 설치 위치에서 계산하지 않습니다. 상대 경로는 앱 생성 시 실행 위치를 기준으로 절대 경로로 확정합니다.
다른 위치에서 실행할 때는 절대 경로를 지정하면 같은 결과 폴더와 화면 빌드를 계속 사용할 수 있습니다.
결과 폴더는 첫 저장 때 생성하며, 화면 폴더는 빌드된 파일을 읽는 용도입니다.
화면 경로가 없거나 지정되지 않으면 `/`는 안내와 함께 404를 반환하고 API·`/docs`는 계속 사용할 수 있습니다.
기존 결과 파일은 이동하거나 삭제하지 않습니다. 기존 위치를 쓰려면 위 예시처럼 `--out webapp/결과`를 명시하세요.
데이터베이스 없이 기존 JSON·ZIP 파일 저장 방식을 유지합니다.

Uvicorn으로 직접 실행할 수도 있습니다. 다음 명령은 저장소 루트에서 실행하며, 기본 설정(API 전용·실행 위치의 `결과/` 저장)을 사용합니다. 경로를 지정할 때는 위의 서버 실행 명령을 사용하세요.

```bash
.venv/bin/python -m uvicorn ncs_web.server:create_app --factory --host 127.0.0.1 --port 8765
```

## API

- `GET /api/health`: 서버 상태 및 지원 검수 종류
- `POST /api/review`: `multipart/form-data` 업로드·검수·저장
- `GET /docs`: 대화형 API 문서
- `GET /openapi.json`: OpenAPI 스키마

업로드 필드:

| 필드 | 내용 |
|---|---|
| `files` | 원고·개발계획서 `.hwp`/`.hwpx`. 같은 필드명으로 여러 파일 전송 |
| `check` | `position`(기본), `toc`, `overview`, `knowledge` |
| `module_code` | 선택. 비우면 원고 파일명에서 추출 |

파일 역할은 내용으로 판별하며 업로드 순서는 무관합니다. 위치 검수는 계획서가 필수입니다.
업로드는 요청별 임시 폴더에 저장하고 처리 후 제거합니다. 같은 이름의 파일도 개별 하위 폴더에 저장합니다.
검수는 동기 경로 함수의 스레드풀에서 실행하며, 검사와 저장이 완료된 후 응답합니다.

성공 응답은 기존 화면과 같은 구조입니다.

```text
{check, module_code, 요약, 검수확인서, 진단, 지적사항, 전체, 저장: {folder, zip}}
```

- 입력·양식 오류(요청 타입 검증 포함): 400 `{error}`
- 저장 중 I/O 오류 등 예상하지 못한 오류: 500 `{error, traceback}`
- 저장 실패 시 검사 결과를 부분 반환하지 않습니다.
- ZIP은 로컬 파일로 저장합니다. 별도 다운로드 API는 없습니다.
- 로컬 테스트 동작을 유지하여 CORS는 `*`, 예외 추적 정보는 오류 응답에 포함합니다.

## 실행 조정 계층

```text
FastAPI 업로드 → 임시 파일 → execute_review(ReviewRequest)
                           → persist_review(ExecutedReview, out_dir)
                           → 응답 모델 → JSON
```

`ncs_service`는 표준 라이브러리와 기존 엔진만 사용합니다.
`execute_review()`는 입력 역할·필수 파일을 확인하고 문서를 읽은 뒤 해당 엔진의 `prepare_review()`와 `evaluate_review()`를 실행합니다.
`persist_review()`는 같은 검수 종류의 `save_results()`를 호출합니다.
네 CLI도 동일한 `execute_review()`·`persist_review()` 경로를 사용합니다. 기존 명령·옵션·출력 형식은 유지합니다.
각 검수 패키지의 `run_review()` 공개 API도 Python 호출자와의 호환성을 위해 유지합니다.

### 설정과 규칙 전달

Python 실행 요청에 엔진별 설정과 규칙 목록을 전달할 수 있습니다. 프로젝트를 설치한 가상환경의 Python으로 실행하며 `PYTHONPATH` 설정은 필요하지 않습니다.

```python
from pathlib import Path
from ncs_overview import CheckConfig, DEFAULT_RULES
from ncs_service import ReviewRequest, execute_review, persist_review

request = ReviewRequest(
    paths=(Path("원고.hwpx"), Path("개발계획서.hwpx")),
    check="overview",
    config=CheckConfig(max_prerequisites=3, max_terms=8),
    rules=DEFAULT_RULES[:2],  # 목표·선수학습 규칙만 실행
)
review = execute_review(request)
saved = persist_review(review, "결과")
```

- `config=None`: 선택한 엔진의 기본 설정을 사용합니다.
- `config=CheckConfig(...)`: 해당 엔진의 설정을 그대로 전달합니다. 다른 엔진의 설정 객체는 입력 오류입니다.
- `rules=None`: 엔진의 기본 규칙을 사용합니다.
- `rules=목록`: 지정한 규칙만 실행합니다. 중복 key와 item_id 접두는 기존 규칙 실행기가 검증합니다.
- `rules=()`: 규칙을 실행하지 않습니다. 전체 체크리스트는 비어 있고 확인서 항목은 미검사입니다.
- `roles`: Python 호출과 CLI에서 원고·계획서 역할을 명시할 수 있습니다.

웹 API의 입력 필드는 기존 그대로입니다. 이 설정·규칙 확장은 Python 서비스 API에 적용되며,
CLI는 기존 섹션 옵션을 설정 객체로 전달합니다. HTTP로 임의 Python 규칙을 받지 않습니다.

## 테스트

저장소 루트에서 실행합니다.

```bash
.venv/bin/python -m pip install -e ".[test]"
.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
```

네 엔진 × 합성 원고 6종의 결과 일치·ZIP 내용, 계획서 필수 조건, 입력 오류,
저장 실패, 임시 파일 정리, API 문서·CORS·정적 화면 및 HTTP 없는 실행을 검사합니다.
서비스·CLI 테스트는 엔진별 설정·규칙 전달, 역할·모듈 코드 지정, 섹션을 바꾼 문서 검수,
빈 규칙 목록, 잘못된 설정, CLI 실행 경로·종료 코드·저장 결과를 검사합니다.
`pyproject.toml`이 설치 진입점입니다. 기본 설치는 외부 런타임 의존성이 없는 엔진·서비스이며,
`web` extra는 `webapp/requirements.txt`, `test` extra는 여기에 `tests/requirements.txt`를 합쳐 읽습니다.
`requirements-dev.txt`는 기존 의존성 설치 명령을 위한 호환 목록입니다. 이 파일만 설치하면 프로젝트 자체는 설치되지 않으므로 위의 `pip install -e ".[test]"`를 사용하세요.

## 설치 구조

- `ncs-web`: `ncs_web.server:main`
- `ncs-position`, `ncs-toc`, `ncs-overview`, `ncs-knowledge`: 각 패키지의 CLI
- `pip install -e .`: 엔진 전용 개발 설치
- `pip install -e ".[web]"`: 웹 개발 설치
- `pip install -e ".[test]"`: 웹·테스트 개발 설치
- `pip install ".[web]"`: 소스를 복사하는 일반 설치

설치 대상은 `src/ncs_*` 패키지입니다. React 소스·빌드, 기존 비교용 소스, 검수 결과는 Python wheel에 포함되지 않습니다.
결과와 화면 경로는 위의 `--out`·`--dist` 설정을 사용하며 가상환경 설치 폴더에 자동 저장하지 않습니다.
공통 엔진·서비스는 FastAPI를 import하지 않습니다. 설치된 패키지의 사용을 검증하기 위해 일반 테스트도 `sys.path`를 주입하지 않습니다.
기존 두 소스 트리를 번갈아 불러오는 `compare_with_original.py`만 비교 목적의 경로 교체를 유지합니다.
