# F02 검수 로컬 웹앱

FastAPI·Uvicorn 백엔드와 React(Vite) 화면으로 구성됩니다.
서버는 파일 업로드·요청 검증·HTTP 응답을, `src/ncs_service/`는 검수 실행·저장 조정을 담당합니다.
`src/ncs_core/`와 네 검수 패키지는 웹 프레임워크 없이도 실행할 수 있습니다.

## 설치·실행

저장소 루트에서 프로젝트 가상환경을 만듭니다. 현재 웹 서버 의존성은 Python 3.14.5에서 검증했습니다.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r webapp/requirements.txt
.venv/bin/python webapp/server.py
```

기본 주소는 `http://127.0.0.1:8765`이며 결과는 `webapp/결과/`의 실행별 폴더에 저장합니다.
기존 `--port`, `--src`, `--out` 옵션을 유지합니다. `--src`에는 `ncs_core`, 네 검수 패키지와 `ncs_service`가 있어야 합니다.
가상환경을 활성화한 경우 기존 명령 `python3 webapp/server.py`도 사용할 수 있습니다.

별도 터미널에서 화면을 실행합니다.

```bash
cd webapp/frontend
npm install
npm run dev
```

화면은 기본 `http://localhost:5173`이며 `/api` 요청은 8765로 프록시합니다.
프런트엔드 폴더에서 `npm run build`를 실행한 뒤 Python 서버를 시작하면 빌드된 화면도 8765에서 제공합니다.

Uvicorn으로 직접 실행할 수도 있습니다. 다음 명령은 저장소 루트에서 실행합니다.

```bash
.venv/bin/python -m uvicorn webapp.server:create_app --factory --host 127.0.0.1 --port 8765
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
기존 검수 패키지의 공개 API·설정·CLI는 그대로 사용할 수 있습니다.

## 테스트

저장소 루트에서 실행합니다.

```bash
.venv/bin/python -m pip install -r webapp/requirements-dev.txt
.venv/bin/python -m unittest discover -s tests -p 'test_webapp.py' -v
```

네 엔진 × 합성 원고 6종의 결과 일치·ZIP 내용, 계획서 필수 조건, 입력 오류,
저장 실패, 임시 파일 정리, API 문서·CORS·정적 화면 및 HTTP 없는 실행을 검사합니다.
`requirements.txt`는 서버 의존성, `requirements-dev.txt`는 API 테스트 의존성을 고정합니다.
