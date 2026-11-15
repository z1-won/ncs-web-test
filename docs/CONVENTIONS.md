# 검수 패키지 공통 규약

검수 패키지 11개(F02 구성요소 10개 `ncs_position`, `ncs_toc`, `ncs_overview`, `ncs_knowledge`, `ncs_perform`, `ncs_teaching`, `ncs_evaluation`, `ncs_references`, `ncs_colophon`, `ncs_misc`와 개발계획서 점검 `ncs_plan`)과 앞으로 추가될 패키지는 이 규약을 따른다.

## 구조
- 공통 코어 `ncs_core`: 문서 읽기, 문자 정규화·판정, 입력 역할 판별, 모듈 코드, 규칙 실행기, 저장. **판정 정책을 두지 않는다.**
- 공통 파서 `ncs_core.manuscript`: 차례 면(`parse_toc`, `parse_plan_toc`), 개요·내용체계(`parse_overview` — 표 우선, 네 엔진 공용, `parse_plan`),
  본문(`parse_body`), 꼬리 섹션(`section_presence`), 양식 인식 패턴(`patterns`), 학습명 비교(`names`: `norm`/`same`/`diff_list`/`pua_note`).
  임계값은 `ParseConfig`로 받는다. 양식 구조를 읽는 코드는 여기에 두고, 검수 패키지는 자기 항목에만 필요한 추출만 가진다.
- **계층 규칙**: 검수 패키지는 `ncs_core`만 import한다. 다른 검수 패키지를 import하지 않으며, `ncs_core`는 검수 패키지·`ncs_service`를 모른다.
  `tests/contract/test_layering.py`가 이를 검사한다. 두 패키지가 같은 추출이 필요해지면 `ncs_core.manuscript`로 올린다.
- 검수 패키지의 **뼈대 파일 8개는 고정**이다. 모든 패키지가 같은 이름으로 갖는다(`tests/contract/test_engines.py`가 검사).
  `config.py`(양식 가정, frozen dataclass; 공통 파서를 쓰면 `parse_config() -> ParseConfig`) · `models.py`(`ReviewContext`) ·
  `rules/<규칙>.py`(판정, I/O 없음) · `registry.py`(`DEFAULT_RULES`, `ALL_ITEM_IDS`) · `pipeline.py` ·
  `reporting.py`(`REPORT_NAME`, `ITEM_FILES`, `summary(result)`, `save_results`) · `sheet.py`(확인서 항목 `ITEMS`·`COMPONENT`) · `__main__.py`(`run_cli(check, 설명)` 한 줄 — 인자·저장은 `ncs_service.cli`가 한다).
- 필요할 때만 두는 파일: `patterns.py`(그 패키지 판정에만 쓰는 정규식·라벨) · `text.py`(`norm, same = make_normalizer(접두 패턴)`; 공통 `ncs_core.manuscript.names`로 충분하면 없음) · `compare.py`(목록 비교 도우미).
- 그 패키지 고유의 **추출 모듈**(원고에서 자기 항목에 필요한 구조를 읽는 코드, I/O 없음)은 읽는 대상을 드러내는 이름으로 둔다.
  지금 있는 것: 위치 `parsers` · 차례 `evaluation`(평가 표) · 필요 지식 `figtab`(그림·표 번호)·`plan`·`structure`(뒤 둘은 코어로 옮긴 파서의 이름 유지용) ·
  수행·교수학습 `blocks` · 평가 `region` · 참고 자료 `entries`·`templates`(F14 서지 골격) · 판권 `tables`.
  새 패키지는 추출이 한 덩어리면 `parsers.py`, 대상이 여럿이면 대상별 이름으로 나눈다. 판정(O/X/△를 정하는 코드)은 추출 모듈이 아니라 `rules/`에 둔다.
- 단어 지식이 필요한 판정(행동명사 등)은 `ncs_core.lexicon`이 한다: 저장 목록(`ncs_core/data/*.txt`) → 없으면 국립국어원 표준국어대사전 API 조회 → 결과를 목록에 기록. 외부 호출은 이 한 곳에만 두고, 조회 불가(인증키 없음·오류)는 X가 아니라 △로 낸다. 운용 전에 `scripts/data/build_action_nouns.py`로 목록을 채워 검수 중 조회는 예외로 만든다. 목록 파일은 git으로 이력을 남긴다. 테스트는 가짜 resolver를 주입해 네트워크를 쓰지 않는다.
- **원고 없이 도는 엔진**: `ncs_plan`(REQ-02-001 개발계획서 점검)은 `Engine("ncs_plan", ("plan",))`로 등록해 계획서만 필수다. `prepare_review(manuscript, plan, …)`의 첫 인자는 `None`일 수 있다(`ncs_service.service`가 `documents.get("manuscript")`를 넘긴다). 확인서 구성요소는 F02가 아니라 `ncs_core.plan_items.PLAN_ITEMS`("개발계획서" ①~⑩)이며, F02 확인서 내보내기(`ncs_service.export.full_sheet`)는 이 구성요소를 건너뛴다. 계획서 표 읽기는 `ncs_plan.parsers`(1~3쪽 기본 정보·대조표·총괄표·위치, 모듈 표 NCS 수정 금지 ⇰ NCS학습모듈)에 있고, 원고 엔진이 쓰는 `ncs_core.manuscript.plan_table`과는 별개다(합칠 때는 코어로 올린다).
- 입력 역할은 셋이다: `manuscript`(hwp/hwpx), `plan`(hwp/hwpx), `print`(PDF 출력본, 선택). PDF는 언제나 `print`이고 원고·계획서가 될 수 없다(`ncs_core.inputs.select_documents`). hwp/hwpx의 역할은 호출자가 `roles`로 정하고, 없으면 넣은 순서(원고 → 개발계획서)다 — 내용으로 추측하지 않는다. 선택 입력을 받는 엔진은 `Engine(optional=("print",))`로 선언하고 `prepare_review(manuscript, plan, *, print=None, …)`로 받는다. 선언하지 않은 엔진에는 넘어가지 않는다.
- 엔진 목록(check 이름)의 원본은 `ncs_service.registry.ENGINES` 하나다. 다른 코드(DB 저장, 이관, SQL 제약)에 엔진 이름을 다시 적지 않고 `ENGINES`를 순회하거나 엔진 `reporting`의 `REPORT_NAME`을 읽는다.
- 규칙은 `Rule(key, item_prefix, run)`으로 등록한다. `run`은 `ReviewContext` 하나를 받아 체크리스트 행 목록을 돌려주고, 행의 `item_id`는 `item_prefix`로 시작해야 한다.

## `ncs_core` 모듈 지도
코어는 한 층에 모듈이 많다. 역할로 묶으면 다음과 같고, 새 모듈은 자기 묶음을 정한 뒤 추가한다. (하위 패키지로 나누는 것은 열려 있는 작업들과 import 경로가 충돌하므로 보류 — `docs/CONSISTENCY_REVIEW.md` §6.)

| 묶음 | 모듈 | 하는 일 |
|---|---|---|
| 문서 읽기 | `documents` · `hwp` · `hwpx` · `numbering` · `tables` | 파일을 한 번 읽어 `Document`로. 구역 정규화, 자동 번호 복원, 표 도우미 |
| 원고 구조 | `manuscript/`(`toc` · `overview` · `body` · `units` · `presence` · `plan_table` · `plan_goals` · `names` · `patterns` · `config`) | 차례·개요·본문·꼬리·개발계획서 블록을 읽는 공통 파서 |
| 입력 확인 | `inputs` · `module_code` | 파일 역할 판별, 모듈 코드 추출·검증 |
| 판정 도우미 | `text` · `goals` · `sentences` · `notes` | 정규화·비교·`verdict`/`worst`, 구역 표기 맞춤(`actual_sections`), 목표 문장 비교, 종결 판정, 비고 문장 틀. 정책은 두지 않는다 |
| 규칙·결과 | `rules` · `models` · `sheet` · `f02_items` · `reporting` | 규칙 등록·실행(예외·행 없음 → 판단불가), 진단의 규칙 범위(`coverage`), 결과 계약, 확인서 접기, F02 항목 원문, 파일 저장 |
| 기준 데이터 | `lexicon` · `ncs_catalog` · `field_terms` · `brands` · `pictures`(해상도 기준) · `layout`(용지·여백·글꼴 기준과 읽기) · `data/` | 행동명사 목록, NCS 분류·수준 표, 분야별 공용 명칭, 상호·상품명 사전(수행 ②·기타 ③ 공용), 그림 해상도 선택지(150/300 DPI), F02 양식 |
| 출력본 | `pdf` · `manuscript/pages` | PDF 쪽별 본문·띠·쪽 번호 읽기, 차례가 가리키는 제목의 실제 시작 쪽 찾기. PDF는 `Document`가 아니라 `PdfDocument`(역할 `print`, 선택 입력) |
| 외부 호출 | `lexicon`(사전) · `llm` · `ncs_api` | 표준국어대사전, 생성형 AI, 공공데이터포털. 검수 중 호출은 승인·키가 있을 때만, 실패는 △ |

## 판정 원칙 (2026-11-15 확정 — 기준 문서: 「PoC② 검수 자료 안내서」)
판정을 정하는 기준은 하나다. 새 규칙도 이 순서로 정한다.

1. **자동 판정 CASE만 부적합(X)을 낸다.** 안내서가 '자동 판정'으로 둔 오류 유형(글자·형식·개수처럼 규칙으로 확정되는 것)은 어긋나면 X다.
   띄어쓰기 하나만 달라도 불일치(X)다. 순서 변경과 명백한 오타 수정만 허용한다.
2. **후보 제시 CASE는 판단불가(△)까지만 낸다.** 내용 판단, 낱말 찾기, 그림 판독, LLM처럼 사람·에디팅 기관이 확정해야 하는 것은
   아무리 강한 신호여도 X로 올리지 않는다. 비고에 후보와 근거, 확인할 자리를 적는다.
3. **확인하지 못한 것은 적합이 아니라 판단불가다.** 기준 문서(개발계획서·출력본)가 없어 대조하지 못함, 구역을 읽지 못함,
   규칙이 돌았는데 검사 대상을 찾지 못함(`ncs_core.rules.no_target_rows`), 규칙 실행 오류 — 모두 △.
   **미검사**는 규칙이 아예 없는 항목과 실행하지 않은 구성요소에만 쓴다(지금 규칙이 없는 F02 항목은 없다).
4. 체크리스트에는 없지만 사람 검수를 통과한 최종본에 있는 표현은 △로 둔다. 다만 항목별로 사용자가 정한 결정이 있으면 그것이 우선한다(아래 표의 '결정').

| 안내서 CASE | 역할 | F02 항목 | 내는 판정 |
|---|---|---|---|
| A-01 학습 목표 대조 | 후보 + 사람 확인 | 필요 지식 ⑤, 평가 ② | 문구 불일치는 X(띄어쓰기 포함), 개발계획서 없으면 △ |
| A-02 명칭·코드 대조 | 자동 판정 | 차례 ③, 개요 ⑤⑥⑦, 필요 지식 ③④, 평가 ① | O / X |
| A-03 위치 표 | 자동 판정 | 위치 ①~⑤ | O / X |
| A-04 문장·제목 종결 | 자동 판정 | 차례 ①②, 개요 ①, 수행 ①④, 교수학습 ②④, 평가 ④ | O / X — **결정**: 교수학습 ②④는 '~한다.'만 적합, 수행 ④는 '~할 수 있다.'도 적합, '~이다/~없다/~가 있다.'는 X |
| A-05 개수·구성 | 자동 판정(내용 판단은 후보) | 차례 ⑤, 개요 ②③⑧, 수행 ③, 교수학습 ①③, 평가 ③⑤ | 개수·이름은 O / X, 평가 ⑤ 심화·보충 낱말 찾기는 △ |
| A-06 번호 체계·그림 표 번호 | 자동 판정 | 필요 지식 ⑥⑦ | O / X |
| A-07 쪽·배치·편집 서식 | 자동 판정 | 차례 ⑥⑦, 기타 ①, 기타 '편집'(F02에 없는 추가 항목) | O / X (출력본 PDF 없으면 ⑦은 △). 편집: 용지·여백은 O / X, KoPub이 아닌 글꼴은 △ |
| A-08 분량 비율 | 자동 판정 | 기타 ⑥ | O / X |
| A-09 제품명 통일 | 자동 판정(사전) + 후보(LLM) | 수행 ②, 기타 ③ 본문 | 사전(`ncs_core.brands`)의 명확한 이름 X, 뜻이 겹치는 이름·LLM만 찾은 것 △ |
| A-10 판권 | 자동 판정 | 판권 ① | O / X |
| B-01 출처 표기 | 자동 판정(형식) | 필요 지식 ⑧ | O / X, 대상 없음 △ |
| B-03 참고 자료 | 자동 판정(형식) | 참고 자료 ①~④ | O / X |
| D-01 그림 품질 | 후보 제시 | 기타 ②⑤⑧ | △까지 — 해상도 미달, 캡션은 있는데 그림 없음. (그림 파일이 깨져 읽히지 않는 '유실'만 X) |
| D-02 그림 속 노출 | 후보 제시 | 기타 ③ 그림, ④ | △까지 — 작업 표시줄 띠, 그림 속 상호·인물 |

**그림 해상도 기준**은 사용자가 고른다: 300 DPI(인쇄 권장, 기본) 또는 150 DPI(인쇄 최소). 선택지의 원본은 `ncs_core.pictures.DPI_CHOICES` 하나이고
검수(`MiscConfig.target_dpi`, 웹 `image_dpi`, CLI `--image-dpi`)와 업스케일링(`target_dpi`)이 같은 값을 쓴다. 화면 선택지(`frontend/src/lib/dpi.js`)는 계약 테스트가 맞춘다.

## 공개 API (모든 검수 패키지 동일)
`tests/contract/test_engines.py`가 `ncs_service.registry.ENGINES`에 등록된 모든 엔진에 대해 이 계약을 검사한다(공개 이름, frozen `CheckConfig`, 체크리스트 행 키, 확인서 행이 F02 원문 항목과 일치, `reporting.REPORT_NAME`·`summary()`와 파일 요약 일치, 저장 파일·ZIP, 빈 규칙 목록, 다른 엔진 설정 거절).
새 구성요소 엔진은 **`ENGINES`에 등록 → `src/ncs_web`의 `CheckName`(`schemas.py`)·오류 메시지(`server.py`) → `frontend/src/lib/checks.js`의 `CHECKS`·`FILE_HINTS`** 세 곳을 같이 고친다. 하나라도 빠지면 같은 테스트가 알려 준다. 화면의 **전체 실행**은 `/api/health`의 `engines` 순서를 그대로 돌리므로 따로 고칠 것이 없다(개발계획서 필요 여부도 `required`에서 읽는다).
```python
run_review(paths, *, roles=None, module_code="", config=DEFAULT_CONFIG, rules=DEFAULT_RULES) -> ReviewResult
prepare_review(manuscript: Document, plan: Document | None, *, module_code="", config=...) -> ReviewContext
evaluate_review(context, *, rules=DEFAULT_RULES) -> ReviewResult
save_results(result, out_dir="결과", *, per_run_dir=True) -> SavedReport
python -m <패키지> 경로... [--manuscript 경로] [--plan 경로] [--module-code LM...] [--front-section N] [--out 결과]
```

## 체크리스트 행 (JSON 키는 한국어, 기존 호환)
`item_id`, `region_path`, `원고`, `체크`({이름: O|X|△|-}), `판정`(적합|부적합|판단불가, `ncs_core.PASS/FAIL/UNDECIDED`), `비고`(dict 또는 list), `수정 제안`.
추가 키(`개발계획서`, `기준`, `자리`, `해당 행 근거` 등)는 패키지가 정한다. 판정은 반드시 `ncs_core.verdict`로 계산한다.

## DB 이력 (PostgreSQL 모드)
저장소 선택은 `ncs_service.store.open_store()` 한 곳에서만 한다. 웹 서버는 `store.save()`를 부르고 `store.supports_history`일 때만 이력 API를 등록한다.
검수 CLI는 `ncs_service.save_cli_review()`로 같은 선택을 탄다: `--out`을 주면 그 폴더, 안 주면 `DATABASE_URL`이 있을 때 DB 이력에만(출처 `cli`), 없을 때 `결과/` 폴더. CLI 인자 처리는 `ncs_service.cli.run_cli` 한 곳이다: 개발계획서 필수 여부는 `Engine.required`, `--body-section`은 엔진 `CheckConfig`에 `body_section`이 있을 때만 생긴다. 엔진 `__main__`에 인자·저장소 분기를 따로 적지 않는다. 저장 방식이 늘면 `store.py`에 같은 호출 모양(`prepare`·`save`·`supports_history`)의 클래스를 추가한다.
스키마 변경은 `ncs_service/migrations.py`의 `MIGRATIONS`에 `NNN_이름` 항목을 **뒤에 추가**해서만 한다. 적용된 항목은 고치지 않는다. 모든 문장은 `IF (NOT) EXISTS`로 보호해 시작마다 돌아도 안전하게 한다(`tests/service/test_migrations.py`가 검사). 엔진 이름을 SQL에 적지 않는다.

## 저장 파일
`<out>/<코드>_<YYYYMMDD-HHMMSS>_<이름>_xxxx/`(실행 시각·검수 이름 + 겹침 방지 꼬리) 아래 `<코드>_<항목 꼬리말>.json`, `<코드>_<이름>_00_요약.json`, `_지적사항.json`, `_전체.json`, `_진단.json`, `<코드>_<이름>_검수결과.zip`.
항목 꼬리말은 각 패키지 `reporting.ITEM_FILES`에 둔다.

## 코드 스타일
- 검수 엔진·실행 조정 계층은 Python 3.10+, 표준 라이브러리만. 예외 하나: PDF 읽기(`ncs_core.pdf`)는 선택 extra `pdf`(pypdf)를 함수 안에서 import하며, 없으면 `PdfUnavailable`(ValueError)을 내고 규칙은 △로 처리한다. 웹 계층은 FastAPI·Uvicorn을 사용하며 설치는 `pyproject.toml`로 통일하고 `web` extra는 `requirements/web.txt`, `test` extra는 추가로 `requirements/test.txt`의 고정 버전을 읽는다. 타입 힌트는 공개 함수와 dataclass에 붙인다.
- black 스타일, 줄 길이 120. 한 줄에 여러 문장(`if …: a; b`) 금지. 한 글자 변수는 짧은 comprehension 안에서만.
- 모듈 첫 줄은 한국어 docstring 한 문단. 사용자에게 보이는 문자열(비고·오류)은 한국어.
- 오류는 `ValueError`로 올리고, 웹 서버·CLI가 잡아서 메시지를 보여준다. 규칙·파서는 `print`하지 않는다.

## 실행과 수정
프로젝트를 가상환경에 설치한 뒤 실행한다(`pip install -e ".[web]"`, 테스트는 `.[test]`). 런타임 `sys.path` 주입과 `--src`는 사용하지 않는다. 검수 CLI는 `ncs-position` 등 설치 명령 또는 기존 `python -m ncs_position`을 사용한다.
검수 엔진의 수정 원본은 `src/`이다. 웹 서버와 검수 CLI는 모두 `ncs_service.execute_review()`로 검수하고, 저장은 `ncs_service.store`(웹은 `store.save()`, CLI는 `save_cli_review()`)를 거친다. 파일로 쓰는 경우 둘 다 `persist_review()`에 닿는다.
`ncs_service`는 파일 경로를 받아 문서 선택·엔진 실행·저장을 조정하며 HTTP 요청이나 업로드 객체를 받지 않는다.
`ReviewRequest.config`에는 선택한 엔진의 `CheckConfig`, `rules`에는 사용자 지정 `Rule` 목록을 전달할 수 있다. 둘 다 `None`이면 엔진 기본값을 사용하며 `rules=()`는 규칙을 실행하지 않는다. 다른 엔진의 설정 객체는 `ValueError`로 거절한다.
각 엔진의 기존 `run_review()` 공개 API는 Python 호출자와의 호환성을 위해 유지한다.
FastAPI 요청·응답 모델은 `src/ncs_web/schemas.py`, 오류 응답은 `common.py`(`error_response`)와 `server.py`(예외 처리기)에서 관리한다. 경로는 기능별로 `src/ncs_web/routes/`에 둔다. 기존 `/api/review`의 입력 오류는 400, 저장 I/O 오류 등은 500을 유지한다.
결과 저장 경로(`--out`)와 정적 화면 경로(`--dist`)는 서버 코드 위치에서 유도하지 않는다. 상대 경로는 앱 생성 시 실행 위치를 기준으로 확정한다. `--out` 기본값은 실행 위치의 `결과/`, `--dist` 생략 시 API 전용이다.
웹 화면은 `frontend/src/`에서 수정하고, 프런트엔드 폴더에서 `npm run build`로 `frontend/dist/`를 생성한다.

## 변경 검증
정책을 바꾸지 않는 리팩토링은 `tests/contract/test_golden.py`가 통과함으로써(현재 결과 == `tests/golden/*.json`) 검수 결과가 동일함을 보인다. 이때 `tests/make_golden.py`를 실행하지 않는다.
정책을 바꾸면 `docs/CONSISTENCY_REVIEW.md`의 "의도적으로 바꾼 동작" 표에 적는다.
