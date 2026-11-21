# F02 검수 웹앱 — 실행·DB 안내

FastAPI·Uvicorn 백엔드와 React(Vite) 화면으로 구성됩니다. **화면은 저장소 루트의 `frontend/`, 서버 코드는 `src/ncs_web/`, 의존성 목록은 `requirements/`에 있습니다.** 명령은 모두 저장소 루트에서 실행합니다.

| 무엇 | 어디 |
|---|---|
| 화면(React·Vite·KRDS) | `frontend/` — 소스 `src/`, 빌드 결과 `dist/`(git 제외) |
| 웹 의존성 고정 목록 | `requirements/web.txt`·`test.txt`·`dev.txt` — `pyproject.toml`의 `web`·`test` extra가 읽음 |
| 서버(FastAPI) | `src/ncs_web/` — `server.py`가 앱을 조립하고 기능별 경로는 `routes/`(review·history·export·plan·upscale·volume). 명령은 `ncs-web` |
| 서버(FastAPI) | `src/ncs_web/` — `server.py`가 앱을 조립하고 기능별 경로는 `routes/`(review·history·export·plan·upscale·opinion). 명령은 `ncs-web` |
| 검수 실행·저장 | `src/ncs_service/` |

`src/ncs_core/`와 검수 패키지 10개는 웹 프레임워크 없이도 실행할 수 있습니다.

## 설치·실행

저장소 루트에서 프로젝트 가상환경을 만들고 프로젝트를 설치합니다. 고정된 웹 의존성은 Python 3.11 이상이 필요하며 Python 3.14.5에서 검증했습니다. 엔진만 설치할 때는 Python 3.10 이상을 지원합니다.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[web]"
.venv/bin/ncs-web
```

기본 주소는 `http://127.0.0.1:8765`입니다. 결과는 저장소 루트의 `결과/` 아래 실행별 폴더에 저장합니다(`DATABASE_URL`이 있으면 폴더 대신 DB 이력). 결과 폴더는 `결과/` 한 곳만 씁니다.
`--port`, `--out`, `--dist` 옵션을 사용합니다. `--src`는 제거하고 설치된 Python 패키지를 사용하도록 통일했습니다.
가상환경을 활성화하면 `ncs-web` 또는 `python -m ncs_web`로도 실행할 수 있습니다.
**패키지는 `.venv` 안에 설치되므로 반드시 그 Python으로 실행합니다.** `python3 -m ncs_web`처럼 시스템 Python으로 실행하면 `ModuleNotFoundError: No module named 'ncs_web'`이 납니다. `.venv/bin/ncs-web`, `.venv/bin/python …`, 또는 `source .venv/bin/activate` 뒤에 실행하세요.

별도 터미널에서 화면을 실행합니다.

```bash
cd frontend
npm install
npm run dev
```

화면은 기본 `http://localhost:5173`이며 `/api` 요청은 8765로 프록시합니다.
프런트엔드 폴더에서 `npm run build`를 실행한 뒤, 저장소 루트에서 아래처럼 시작하면 빌드된 화면도 8765에서 제공합니다.

```bash
.venv/bin/ncs-web --dist frontend/dist
```

## 업스케일링 페이지

메인 메뉴의 **업스케일링**(`/upscale`)은 원고 검수와 따로 쓰는 페이지입니다. 원고(hwpx)를 이 페이지에서 올리면 고른 해상도 기준(300 또는 150 DPI, 기본 300 — `?target_dpi=`) 미만 그림을 원고에 나오는 순서로 보여 주고, 고른 그림만 한 장씩 키웁니다. 화면은 `frontend/src/pages/UpscalePage.jsx`, 그림 목록·결과는 `components/UpscalePanel.jsx`, 서버는 `/api/uploads/{token}/pictures…` 경로와 `src/ncs_upscale/`입니다.

업스케일은 외부 실행 파일(기본 `waifu2x-ncnn-vulkan`)을 부릅니다. 실행 파일은 저장소에 없으므로 따로 내려받아 도구 폴더에 둡니다. 도구 폴더는 환경 변수 `NCS_UPSCALE_TOOLS`로 지정하고, 없으면 저장소 안 `tools/`(git 제외)를, 그다음 예전 위치인 저장소 바로 위 폴더의 `tools/`를 봅니다. 엔진을 찾지 못하면 그림 목록과 원본 보기는 되고 업스케일 버튼만 꺼집니다. 실행 파일 이름은 운영체제에 맞춰 찾습니다 — Windows는 `waifu2x-ncnn-vulkan.exe`, macOS·Linux는 `waifu2x-ncnn-vulkan`(`src/ncs_upscale/engine.py`). 2배로 기준에 닿지 않는 그림은 4배로 키우며 약 4배 오래 걸립니다. 해상도 기준을 바꾸면 이전 기준으로 키운 결과는 완료로 세지 않습니다.

## 원고 분량 페이지

메인 메뉴의 **원고 분량**(`/volume`)은 집필료 산정용 분량 산정 페이지입니다(REQ-02-013). 최종 원고(필수)와 기존 원고·출력본 PDF(선택)를 올리고, 수작업으로 센 쪽수·원고료 단가·계약 분량(선택)과 부록 포함 여부(기본 포함 — 계약서 제13조 4항 ①)를 고릅니다. 서버는 `POST /api/volume`(multipart: `manuscript`, `previous`, `print_copy`, `manual_pages`, `unit_price`, `contract_pages`, `include_appendix`)으로 `src/ncs_volume`의 산정표 JSON을 돌려주며 파일은 저장하지 않습니다. 결과의 `출력본`(PDF 측정: 전체 쪽 수, 구성별 쪽 범위, 쪽별 채움, 측정/계산 구분, 한글 계산과의 차이)·`채택 분량`(산정에 쓴 매수와 근거)·`집필료`(산식, 단가와 근거, 계약 분량 인정, 개선 기준, 근거 조항)는 새 키이고 기존 키는 그대로입니다. PDF 칸에 PDF가 아닌 파일, 0 이하 단가·계약 분량은 400입니다. pypdf가 없거나 다른 원고의 출력본이면 400이 아니라 `출력본.사유`에 판단불가로 적고 한글 값으로 산정합니다. `경고`와 `집필료.경고`는 `알림` 가운데 화면이 경고색으로 보일 문장들입니다(추정·판단불가, 단가 상한 초과, 계약 분량 초과·미달). 화면은 `frontend/src/pages/VolumePage.jsx`입니다.

DB 모드(`DATABASE_URL`)에서는 산정할 때마다 `volume_runs` 표에 산정 이력을 남기고 응답에 `id`를 싣습니다(마이그레이션 `009_volume_runs`, 서버 시작 때 자동 적용). 남기는 것은 산정표 전체(`result`), 넣은 값(`params`: 단가·계약 분량·수작업 쪽수·부록 포함), 입력 파일의 역할·이름·sha256·크기(`inputs`), 목록용 열(모듈 코드·기입 분량·단가·집필료·추정 여부)이며 **원고 파일은 보관하지 않습니다**. 이력에 쓰지 못해도 산정 결과는 200으로 돌려주고 `id: null`과 `저장 오류`로 알립니다. `GET /api/volumes`(최신순 50건, 최대 100건; `module_code`·`limit`·`offset`), `GET /api/volumes/{id}`(산정표 + `created_at`·`입력`), `DELETE /api/volumes/{id}`가 붙고, 화면 아래 **산정 이력** 표에서 다시 열거나 지웁니다. 파일 저장 모드에서는 이력을 남기지 않으며 이 경로들도 없습니다(`/api/health`의 `history`로 구분).
## 처음 화면과 원고 진행 현황 페이지

처음 화면(`/`)은 위쪽 띠(제목과 [원고 검수 시작]), 최근 원고 다섯 건의 진행 현황 미리 보기(학습모듈명, 모듈 코드, 기록이 있는 단계 수), 묶음별 기능 카드(집필, 검수, 이미지, 마무리)입니다. 묶음 구성은 정해진 것이라 배치를 맞추려고 바꾸지 않습니다. 카드 높이와 글 위치가 열마다 어긋나지 않게 줄을 묶음들이 함께 쓰고, 색·간격·글자 크기는 다른 화면처럼 KRDS 토큰만 씁니다(`frontend/src/progress.css`). 카드에는 필요한 파일과, 글 일부가 생성형 AI 서비스로 나가는 기능이면 그 표시를 적습니다(표시는 개인정보처리방침의 '외부로 보내는 내용'과 같아야 합니다). 미리 보기는 데이터베이스를 쓰는 서버에서만 보이고, 없으면 바로 가기만 보입니다. 원고 검수는 `/review`로 옮겼습니다(모르는 주소는 처음 화면으로 갑니다).

머리글 오른쪽의 **진행 현황**(`/progress`)은 원고(모듈 코드)마다 남은 기록을 단계 7개와 검수 진행도로 모아 보여 주는 페이지입니다(REQ-02-007 '원고별 편집·내용·저작권 검수 진행도 확인'). 작업 메뉴와 떨어진 자리에 둔 것은 작업 도구가 아니라 확인하는 화면이기 때문이며, 로그인이 생기면 이 자리가 '내 원고'가 됩니다. 데이터베이스를 쓰는 서버에서만 열립니다. `GET /api/manuscripts`가 기록이 있는 원고 목록(최근 기록순, 기록이 있는 단계 수)을, `GET /api/manuscripts/{모듈 코드}`가 한 원고의 단계와 진행도를 돌려줍니다. 고른 원고는 주소의 `?code=`에 남습니다.

- 단계는 F11 매뉴얼(2026) 제2장 개발 절차(인쇄 16~17쪽) 11단계에서 연결할 기능이 있는 7개만 추렸습니다: 개발계획서, 초고본 검토, 수정본 검토, 최종본 집필과 심의본 제출, 최종 윤문과 편집, 최종본 검수, 분량과 권리 증빙.
- 단계의 **완료는 담당자가 직접 표시**합니다. 진행 현황에서 [완료로 표시]를 누르고 이름과 메모를 적으면 누가 언제 표시했는지 남고, [되돌리기]로 되돌릴 수 있으며 표시와 되돌림은 이력에 남습니다(`POST /api/manuscripts/{모듈 코드}/stages/{단계}`, 본문 `{done, by, note}`, 마이그레이션 `011_manuscript_stages`). 로그인이 없어 이름은 화면에서 받습니다. 기록은 완료를 판단할 **근거**로 단계 옆에 보일 뿐이고 기록이 있다고 완료가 되지 않습니다(`src/ncs_service/progress.py`). 기록이 없는 원고도 모듈 코드로 열어 단계를 표시할 수 있습니다.
- 원고 검수를 돌릴 때 **원고 단계**(초고본, 수정본, 최종본)를 고르면 그 실행이 해당 단계의 근거 기록으로 보입니다(`POST /api/review`의 `work_stage` = 2, 3, 6). 고르지 않은 기록은 처음 검수한 날을 초고본 검토에, 가장 최근 전체 검수의 판정을 최종본 검수에 '단계를 고르지 않은 기록'으로 보입니다. 수정본 검토, 최종본, 최종 윤문에는 각각 1차·2차 검토의견서, 심의의견서로 한 의견 반영 검토의 개수가 근거로 붙습니다.
- 진행도: 편집 검수(구성요소마다 가장 최근 검수의 확인서 항목 수와 적합 비율), 내용 검수(차수마다 가장 최근 의견 반영 검토의 총 의견·반영 후보·미반영 후보·확인 필요), 저작권 검수(권리 증빙 점검 판정·누락 수, 이미지 저작권 DB의 확정 수), 원고 분량(최근 산정 매수와 집필료).
- 의견 반영 검토와 권리 증빙 점검은 결과를 보관하지 않으므로, 이 화면에 쓸 **개수만** `work_records` 표에 남깁니다(마이그레이션 `010_work_records`). 의견 문장·원고 문단·지적 내용은 저장하지 않습니다. 응답의 `진행 현황 기록`에 기록 id와 모듈 코드가 오며, 원고 파일 이름에 모듈 코드가 없으면 모듈 코드가 빈 값이라 어느 원고에도 붙지 않습니다.
- 원고 파일 이름에 모듈 코드(`LM…`)가 있는 기록만 모입니다.

## 의견 반영 검토 페이지

메인 메뉴의 **의견 반영 검토**(`/opinion`)는 검토의견서 반영 여부 검토 페이지입니다(REQ-02-003). 1차·2차 검토의견서와 심의의견서(셋 중 하나 이상), 최종 원고(필수), 출력본 PDF·반영 전 원고(선택)를 올립니다. 서버는 `POST /api/opinion`(multipart: `opinions` 여러 개, 같은 순서의 `rounds`(`1차`, `2차`, `심의`), `manuscript`, `print_pdf`, `previous`)으로 `src/ncs_opinion`의 판정 후보표 JSON을 돌려주며 파일은 저장하지 않습니다. 판정은 LLM이 하며 서버에 LLM 설정·반출 승인(`LLM_ALLOW_UPLOAD=1`)이 있으면 자동으로 부릅니다(선택 칸 없음). 없으면 모든 의견이 '확인 필요'와 이유로 오고, 화면은 결과 머리의 배지(`#opinion-llm-state`)에 'LLM: 사용(모델) · 호출 N번' 또는 'LLM 미설정 — 이유'를 보여 줍니다. 화면은 `frontend/src/pages/OpinionPage.jsx`입니다.

## 저장·화면 경로 분리

| 설정 | 생략 시 | 의미 |
|---|---|---|
| `--out` / `create_app(out_dir=...)` | 실행 위치의 `결과/` | 검수 JSON·ZIP 저장 경로 |
| `--dist` / `create_app(dist_dir=...)` | 정적 화면 제공 안 함 | React 빌드 파일 경로 |
| `--data` / `create_app(data_dir=...)` | `ncs-web`은 `NCS_DATA_DIR` 또는 실행 위치의 `기준정보/`, `create_app`은 `NCS_DATA_DIR`(없으면 쓰지 않음) | 운영 중에 받아 온 기준정보를 두는 폴더(아래 '기준정보 받아 오기') |

두 경로는 서버 파일의 설치 위치에서 계산하지 않습니다. 상대 경로는 앱 생성 시 실행 위치를 기준으로 절대 경로로 확정합니다.
다른 위치에서 실행할 때는 절대 경로를 지정하면 같은 결과 폴더와 화면 빌드를 계속 사용할 수 있습니다.
결과 폴더는 첫 저장 때 생성하며, 화면 폴더는 빌드된 파일을 읽는 용도입니다.
화면 경로가 없거나 지정되지 않으면 `/`는 안내와 함께 404를 반환하고 API·`/docs`는 계속 사용할 수 있습니다.
`DATABASE_URL`을 설정하지 않으면 기존 JSON·ZIP 파일 저장 방식을 유지합니다.

## 기준정보 받아 오기

NCS 기준정보가 바뀌거나 아직 없는 세분류를 쓸 때 터미널 작업 없이 화면에서 받아 오게 한 것입니다. 받아 온 것은 패키지의 표(`src/ncs_core/data/`)를 고치지 않고 **기준정보 폴더**(`--data`, 기본 `기준정보/`, git 제외)의 같은 이름 파일에 쌓이며, 읽을 때 패키지 표 위에 덧씌웁니다. 폴더를 지우면 패키지의 표로 돌아갑니다.

| 무엇 | 언제 | 필요한 것 | 나가는 것 |
|---|---|---|---|
| NCS 요소·수행준거(`기준정보/ncs_elements.tsv`) | **개발계획서 작성**에서 아직 받아 두지 않은 세분류를 고를 때 자동으로, 받아 둔 세분류는 [NCS에서 다시 받아 오기]를 누를 때 | `.env`의 `NCS_API_KEY`(공공데이터포털), 서버에서 `apis.data.go.kr`로 나갈 수 있을 것 | 세분류 코드 |
| 법령명 조회 결과(`기준정보/law_names.tsv`) | **개발계획서 점검** ⑩을 돌릴 때, 계획서에 적힌 법령명이 표에 없거나 조회한 지 30일이 지났으면 | `.env`의 `LAW_API_OC`(법제처, 등록한 IP에서만 됨), `www.law.go.kr`로 나갈 수 있을 것 | 법령 이름(문서 본문은 보내지 않음) |

- 키나 폴더가 없으면 조회하지 않고 지금까지처럼 패키지의 표만 씁니다(`GET /api/plan/subclasses`의 `can_fetch`가 `false`).
- 세분류는 통째로 바꿔 씁니다. 능력단위 하나라도 받지 못하면 아무것도 쓰지 않습니다. 다시 받으면 전과 달라진 능력단위(추가·삭제·변경)를 화면에 알려 줍니다.
- 법령명은 문서 하나에서 30건까지 조회하고, 연달아 2번 실패하면 그만둡니다(연결이 안 되는 곳에서 점검이 오래 걸리지 않게). 실패한 이름은 결과의 `진단.warnings`에 남고 ⑩에서 판단불가로 남습니다.
- 현행 법령이어도 띄어쓰기가 법제처 정식 명칭과 다르면 ⑩에서 띄어쓰기 오류로 표시합니다(학습모듈 쪽은 부적합과 수정 제안, NCS 원문 쪽은 확인 필요). 기준은 F11 매뉴얼(2026) 참고 자료 작성 방법의 법령 항목(인쇄 82~83쪽)입니다. 글자가 다른 약칭은 참고로만 알립니다.
- 경로: `GET /api/plan/subclasses`(세분류 전부 — `ready`, 능력단위 수) · `GET /api/plan/subclasses/{세분류코드}`(능력단위·요소 수·받아 온 날) · `POST /api/plan/subclasses/{세분류코드}/fetch[?refresh=true]`.
- 코드: `ncs_core/refdata.py`(폴더) · `ncs_core/ncs_fetch.py` · `ncs_core/law_lookup.py`. 분류·능력단위 목록(`ncs_units.tsv`)과 수준 표, 행동명사·분야 용어는 아직 `scripts/data/`로 갱신합니다.

## 문장 추천 페이지

메인 메뉴의 **문장 추천**(`/suggest`)은 집필 보조 페이지입니다(REQ-02-004). 원고를 올리면 `POST /api/suggest`(multipart: `manuscript`)가 `src/ncs_suggest`의 구성별 추천 카드 JSON을 돌려주고, 문장 하나는 `POST /api/suggest/sentence`(form: `text`, `kind`)로, 종류 목록은 `GET /api/suggest/kinds`로 받습니다. 고칠 문장과 후보는 LLM이 내며 서버에 LLM 설정·반출 승인이 있으면 자동으로 부릅니다(선택 칸 없음). 없으면 카드 없이 'AI 미설정 — 이유'(결과 머리 배지 `#suggest-ai-state`, 문장 직접 입력은 '판단불가' 카드)만 옵니다. 결과는 저장하지 않으며 채택/기각 기록과 채택률은 화면이 갖고 JSON·CSV로 내려받게 합니다. 화면은 `frontend/src/pages/SuggestPage.jsx`입니다.

## PostgreSQL 검수 이력

웹 서버에 `DATABASE_URL`을 설정하면 PostgreSQL에 검수 이력을 저장합니다. 이 모드에서 실행별 JSON·ZIP 폴더는 새로 만들지 않으며, ZIP은 이력 화면의 다운로드 링크를 누를 때 임시로 생성합니다. `DATABASE_URL`이 없으면 기존 파일 저장 방식으로 실행됩니다. 검수 CLI(`python -m ncs_position …` 등)도 같은 규칙을 따릅니다: `--out`을 주면 그 폴더에 파일로, 안 주면 셸에 `DATABASE_URL`이 있을 때 DB 이력에만(`source`=`cli`, 폴더를 만들지 않음), 없을 때 `결과/` 폴더에 저장합니다. CLI는 `.env`를 자동으로 읽지 않으므로 `set -a; source .env; set +a`로 올린 셸에서만 DB로 갑니다. 파일이 필요하면 `--out`을 지정하세요. 이미 만든 결과 폴더는 아래 `import` 명령으로 이력에 넣습니다.

저장소 루트의 `compose.yaml`은 로컬 PostgreSQL 18을 `127.0.0.1:55432`에서 실행합니다. 데이터는 `ncs-review_postgres_data` Docker 볼륨에 저장되어 컨테이너를 다시 만들어도 유지됩니다. Docker Desktop을 켜고 저장소 루트에서 실행하세요. 새로 복제한 작업 공간이라면 `.env.example`을 `.env`로 복사해 `NCS_DB_PASSWORD`와 `NCS_DB_ADMIN_PASSWORD`를 서로 다른 강한 값으로 바꾸고, `DATABASE_URL`의 비밀번호는 `NCS_DB_PASSWORD`와 같게 입력합니다. 이 작업 공간의 `.env`는 이미 생성되어 있습니다.

```bash
docker compose up -d --wait db
docker compose ps
```

앱에서 접속할 때는 같은 터미널에 `.env`를 읽어들입니다. 아래의 스키마 준비와 이관 명령은 다음 단계에서 실행합니다.

```bash
set -a
source .env
set +a
.venv/bin/python -m ncs_service.postgres_cli migrate
.venv/bin/ncs-web --dist frontend/dist
```

앱 전용 데이터베이스와 관리자 권한이 없는 `ncs_app` 계정은 PostgreSQL 볼륨을 처음 만들 때 생성됩니다. `.env`는 저장소에서 제외됩니다. `docker compose stop db`로 중지하고 `docker compose start db`로 다시 시작할 수 있습니다. `docker compose down`은 컨테이너만 제거하고 데이터 볼륨은 유지하지만, `docker compose down -v`는 데이터 볼륨도 삭제합니다. 앱 시작 시와 `postgres_cli migrate`는 `ncs_service/migrations.py`의 `MIGRATIONS`(번호 붙은 SQL 목록) 중 아직 적용되지 않은 것만 순서대로 실행하고 `schema_version` 표에 기록합니다. 스키마를 바꿀 때는 적용된 항목을 수정하지 말고 다음 번호를 뒤에 추가합니다. 코드를 올리고 서버를 재시작하면 DB가 따라옵니다. check 이름의 허용값은 DB 제약이 아니라 `ncs_service.registry.ENGINES`가 검증하므로, 엔진을 추가해도 DB 쪽 작업은 없습니다.

기존 결과를 가져올 때는 다음 명령을 실행합니다. 재실행하면 이미 가져온 폴더를 건너뛰며 원본 파일은 삭제하지 않습니다. 이관 시각은 요약 JSON의 수정 시각을 사용하고, 과거 입력 원본의 해시·엔진 버전은 복원할 수 없습니다.

```bash
.venv/bin/python -m ncs_service.postgres_cli import 결과
```

DB 모드에서는 `GET /api/reviews`(최근 50건, 최대 100건; `module_code`, `check`, `verdict`, `limit`, `offset` 필터), `GET /api/reviews/{id}`(상세), `GET /api/reviews/{id}/zip`(ZIP 다운로드)을 제공합니다. 화면에 최근 검수 이력 목록과 상세 보기·ZIP 다운로드가 표시됩니다. DB 모드의 `POST /api/review` 응답에는 `id`가 들어가고 `저장`은 `null`입니다.

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
| `image_dpi` | 선택. 그림 해상도 기준 `300`(기본) 또는 `150`. `check=misc`(기타 ⑤⑧)에만 쓰인다. 다른 값은 400. 선택지는 `GET /api/health`의 `image_dpi` |
| `roles` | 선택. `files`와 같은 순서·개수의 역할 JSON 배열(`["manuscript", "plan", "print"]`). `POST /api/uploads`와, `files`를 직접 올리는 `POST /api/review`가 받는다 |

`roles`를 주면 그 역할로 받고(화면의 업로드 칸이 이렇게 보냅니다 — 칸이 곧 역할), 주지 않으면 넣은 순서가 역할입니다(첫 hwp/hwpx가 원고, 둘째가 개발계획서. 개발계획서 점검은 첫 파일이 개발계획서). 내용으로 추측하지 않습니다. 업로드 토큰으로 실행하는 검수는 업로드 때 정한 역할을 그대로 씁니다. PDF는 출력본으로만, 출력본은 PDF로만 받습니다. 위치 검수는 계획서가 필수입니다.
업로드는 요청별 임시 폴더에 저장하고 처리 후 제거합니다. 같은 이름의 파일도 개별 하위 폴더에 저장합니다.
검수는 동기 경로 함수의 스레드풀에서 실행하며, 검사와 저장이 완료된 후 응답합니다.

성공 응답은 기존 화면과 같은 구조입니다.

```text
{id, check, module_code, 요약, 검수확인서, 진단, 지적사항, 전체, 저장}
```

- 입력·양식 오류(요청 타입 검증 포함): 400 `{error}`
- 저장 중 I/O 오류 등 예상하지 못한 오류: 500 `{error, traceback}`
- 저장 실패 시 검사 결과를 부분 반환하지 않습니다.
- 파일 모드에서는 ZIP을 로컬 파일로 저장하며 다운로드 API는 제공하지 않습니다.
- PostgreSQL 모드에서 `id`는 실행 ID, `저장`은 `null`이며 `/api/reviews/{id}/zip`으로 다운로드합니다. 파일 모드에서 `id`는 `null`, `저장`은 `{folder, zip}`입니다.
- 로컬 테스트 동작을 유지하여 CORS는 `*`, 예외 추적 정보는 오류 응답에 포함합니다.

## 실행 조정 계층

```text
FastAPI 업로드 → 임시 파일 → execute_review(ReviewRequest)
                           → store.save(ExecutedReview, uploads)      store = open_store(out_dir, database_url)
                                FileStore     → persist_review → 실행별 폴더·ZIP   (DATABASE_URL 없음)
                                PostgresStore → save_review   → 이력 행 + id        (DATABASE_URL 있음)
                           → 응답 모델 → JSON
```

`ncs_service`는 표준 라이브러리와 기존 엔진만 사용합니다.
`execute_review()`는 입력 역할·필수 파일을 확인하고 문서를 읽은 뒤 해당 엔진의 `prepare_review()`와 `evaluate_review()`를 실행합니다.
`persist_review()`는 같은 검수 종류의 `save_results()`를 호출합니다.
검수 CLI도 같은 `execute_review()`와 저장소(`save_cli_review()` → `open_store`)를 사용합니다. `--out`을 주면 그 폴더에, 안 주면 `DATABASE_URL`이 있을 때 DB 이력에만(출처 `cli`), 없을 때 `결과/` 폴더에 남깁니다.
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
.venv/bin/python -m unittest discover tests -v
```

네 엔진 × 합성 원고 6종의 결과 일치·ZIP 내용, 계획서 필수 조건, 입력 오류,
저장 실패, 임시 파일 정리, API 문서·CORS·정적 화면 및 HTTP 없는 실행을 검사합니다.
서비스·CLI 테스트는 엔진별 설정·규칙 전달, 역할·모듈 코드 지정, 섹션을 바꾼 문서 검수,
빈 규칙 목록, 잘못된 설정, CLI 실행 경로·종료 코드·저장 결과를 검사합니다.
`pyproject.toml`이 설치 진입점입니다. 기본 설치는 외부 런타임 의존성이 없는 엔진·서비스이며,
`web` extra는 `requirements/web.txt`, `test` extra는 여기에 `requirements/test.txt`를 합쳐 읽습니다.
`requirements/dev.txt`는 둘을 합친 목록입니다. 이 파일만 설치하면 프로젝트 자체는 설치되지 않으므로 위의 `pip install -e ".[test]"`를 사용하세요.

## 설치 구조

- `ncs-web`: `ncs_web.server:main`
- `ncs-position`, `ncs-toc`, `ncs-overview`, `ncs-knowledge`: 각 패키지의 CLI
- `pip install -e .`: 엔진 전용 개발 설치
- `pip install -e ".[web]"`: 웹 개발 설치
- `pip install -e ".[test]"`: 웹·테스트 개발 설치
- `pip install ".[web]"`: 소스를 복사하는 일반 설치

설치 대상은 `src/ncs_*` 패키지입니다. React 소스·빌드, 테스트 골든 결과, 검수 결과는 Python wheel에 포함되지 않습니다.
결과와 화면 경로는 위의 `--out`·`--dist` 설정을 사용하며 가상환경 설치 폴더에 자동 저장하지 않습니다.
공통 엔진·서비스는 FastAPI를 import하지 않습니다. 설치된 패키지의 사용을 검증하기 위해 일반 테스트도 `sys.path`를 주입하지 않습니다.
골든 테스트(`test_golden.py`·`make_golden.py`)는 공용 모듈 `golden_cases.py`를 찾기 위해 자기 폴더(`tests/`)만 경로에 추가하며, `src`는 주입하지 않습니다.
