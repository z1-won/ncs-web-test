# F02 차례(v2) · 위치(v1.2) 리팩토링본 일관성 평가와 통합 리팩토링

대상: 리팩토링 전 차례 검수(`ncs_toc`)와 위치 검수(`ncs_position`) Python 소스.
결과: 공통 코어 `ncs_core`를 뽑아내고 두 패키지를 같은 구조·규약으로 재구성했다.
판정 정책과 JSON 키는 바꾸지 않았다(합성 원고 6종 × 개발계획서 유무 = 18건에서 체크리스트가 원본과 동일).

## 1. 평가 — 두 패키지가 서로 달랐던 점

| 영역 | ncs_toc (차례 v2) | ncs_position (위치 v1.2) | 문제 |
|---|---|---|---|
| 의존성 | 표준 라이브러리만 (`xml.etree`) | `lxml`, `olefile` 필수 | 같은 HWPX를 두 가지 파서로 읽음. 외부 의존성 설치 여부에 따라 실행 가능 환경이 달라짐 |
| HWP(CFB) 로더 | `_read_cfb` 사본 A: 순환 체인 검출, 레코드 잘림 검출, 섹터 오프셋 `(n+1)*ssz` | 사본 B: `512 + n*ssz`, 순환 검출 없음(`len(out) < 10**6`), 잘림 검출 없음 | **동일 함수의 두 사본이 미묘하게 다름.** 섹터 크기 4096인 파일에서 B는 틀린 오프셋(CFB 규격은 `(n+1)*ssz`). 버그 수정이 한쪽에만 들어가는 구조 |
| HWPX 문단 텍스트 | `_hwpx_para_text` (ET) | `_hwpx_para_text` (lxml) + 표 전용 `_hwpx_text` | 세 사본. 중첩 표 셀 처리가 다름(차례: 자기 셀 문단만, 위치: 중첩 포함) |
| 형식 판별 | 머리 8바이트만 | OLE면 `FileHeader` 서명까지 확인 | 엄격도가 다름 |
| 정규화 `norm` | `^(학습 )?\d+(-\d+)?\.\s*` 제거 + 공백 축약 | `^\d+\.\s*` 제거만 | 정책 차이는 정당하지만, 함수 본체가 중복 |
| `_verdict`, `visible`, `PUA`, `flatten` | `common.py` + `reporting.py` | `common.py` | 완전히 같은 코드가 두 곳 |
| 모듈 코드 | `pipeline.resolve_module_code` (`findall`, 형식만 검사) | `module_code.py` (경계 lookaround, 01 이상 검사) | 같은 입력에 다른 결과 가능 |
| 입력 검증 | 역할 자동 판별 `detect_role`, 중복 경로 검출 | 경로 존재·크기·SHA-256 동일 파일 검출 | 서로 유용한 검사를 한쪽만 가짐 |
| 공개 API | `inspect_files(paths, roles=)`, `inspect_documents(ms, plan)` | `prepare_review(plan, ms)`, `evaluate_review(ctx)`, `run_review(plan, ms)` | 이름·인자 순서·단계 분리 방식이 다름 |
| 결과 모델 | `InspectionResult(code, checklist, findings, diagnostics, context)` | `ReviewResult(code, checklist, findings)` + `SavedReport` | 진단 정보가 한쪽에만 있음 |
| 규칙 등록 | `registry.py` `Rule(item_id, run)` + item_id 검증 | `pipeline.py` 안 `Rule(key, evaluate)` + key 중복 검증 | 위치는 한 규칙이 여러 item_id(`⑤`, `⑤-세분류`)를 내므로 차례 방식으로는 등록 불가 |
| 규칙 배치 | `rules/` 하위 패키지 | `content_rules.py`, `emphasis_rules.py` 평면 | 폴더 구조 불일치 |
| 설정 | `CheckConfig`(섹션·임계값) | 없음(하드코딩) | 양식 변경 대응력이 다름 |
| 저장 | `save_results(checklist, findings, code, out_dir, diagnostics=)` → `(summary, zip 경로 str)`, **out_dir에 덮어씀** | `save_results(result, out_dir)` → `SavedReport`, **실행별 하위 폴더** | 시그니처·반환형·덮어쓰기 정책이 다름 |
| CLI | `paths...` 위치 인자 + `--manuscript/--plan` 역할 지정, `--out-dir` | `--plan/--manuscript` 필수, `--out` | 옵션 이름이 다름 |
| 코드 스타일 | 한 줄 압축(`if …: a; b`), 한 글자 변수, 타입 힌트 거의 없음 | black 스타일, 타입 힌트·TypedDict | 읽는 사람이 두 가지 규약을 익혀야 함 |

요약: 두 구현은 각각은 "확장성/수정가능성"을 고려해 모듈화됐지만, **같은 일을 하는 코드(문서 읽기, 판정, 저장, 모듈 코드)가 서로 다른 사본으로 존재**하고 공개 API·저장 정책·스타일이 어긋나 있었다. 한쪽에서 고친 로더 버그가 다른 쪽에 전파되지 않는 구조가 가장 큰 위험이었다.

## 2. 통합 리팩토링 — 무엇을 어디로 옮겼나

```
src/
  ncs_core/            두 검수가 공유 (정책 없음)
    documents.py       Document(path, format, sections, tables, images), load_document, detect_format
    hwp.py             CFB 리더(차례의 안전한 버전 + 규격 오프셋), 문단·표 추출
    hwpx.py            ET 기반 문단·표(셀 텍스트+서식)·그림 이름 추출 (섹션당 1회 순회)
    text.py            PUA/O/X/△/-, make_normalizer(prefix) → (norm, same), visible, verdict, flatten
    inputs.py          detect_role, select_documents(paths, roles, required=), validate_distinct(SHA-256)
    module_code.py     validate_module_code, resolve_module_code (위치의 엄격한 버전)
    rules.py           Rule(key, item_prefix, run), run_rules — key 중복·item_id 접두 검증
    reporting.py       save_report(result, out_dir, name=, item_files=, other_tail=, per_run_dir=)
    tables.py          column, column_cells, header_columns, find_table
    models.py          ReviewResult(code, checklist, findings, diagnostics, context), SavedReport
  ncs_toc/  ncs_position/      동일한 파일 구성
    __init__.py  __main__.py  config.py  patterns.py  text.py  compare.py
    parsers.py  models.py(ReviewContext)  registry.py(DEFAULT_RULES)  pipeline.py  reporting.py
    rules/<규칙별 모듈>.py
    (ncs_toc만: presence.py, evaluation.py)
tests/make_fixtures.py    합성 HWPX 생성
tests/compare_with_original.py   원본 패키지와 체크리스트 동일성 비교 (18/18 동일)
```

양쪽에 같은 이름으로 존재하는 것: `CheckConfig`, `ReviewContext`, `DEFAULT_RULES`, `prepare_review`/`evaluate_review`/`run_review(paths, *, roles, module_code, config, rules)`, `save_results(result, out_dir, *, per_run_dir=True) -> SavedReport`, CLI(`python -m <패키지> 경로... [--manuscript] [--plan] [--module-code] [--front-section] [--out]`).

## 3. 의도적으로 바꾼 동작 (정책은 아님)

| 변경 | 이유 | 영향 |
|---|---|---|
| 위치 검수에서 `lxml`·`olefile` 제거 | 차례와 같은 표준 라이브러리 파서로 통일 | 외부 의존성 설치 없이 실행 가능 |
| HWP 섹터 오프셋을 `(n+1)*ssz`로 통일 | CFB 규격. 512바이트 섹터에서는 두 식이 같음 | 4096바이트 섹터 HWP에서 위치 검수가 올바르게 읽힘 |
| HWPX 중첩 표: 바깥 셀에 안쪽 표 텍스트를 합치지 않음(차례 방식) | 중첩 표는 자체 표로 따로 나옴. HWP 로더도 원래 이 방식 | 위치 표 안에 표를 중첩한 비정형 원고에서 셀 텍스트가 달라질 수 있음 |
| 위치 검수 `norm`이 연속 공백을 하나로 축약 | 공통 `make_normalizer`. 로더가 이미 공백을 정리하므로 실질 차이 없음 | — |
| 위치 검수 모듈 코드 추출을 차례에도 적용(경계 lookaround, 01 이상) | 한 규칙으로 통일 | 파일명에 코드가 다른 영숫자에 붙어 있으면 차례 검수가 "코드 없음"으로 멈춤 → `MODULE_CODE` 지정 |
| 차례 결과 저장도 실행별 하위 폴더(`per_run_dir=True`) | 위치와 통일, 이전 ZIP 재사용 방지. 덮어쓰기가 필요하면 `per_run_dir=False` | 결과 경로가 `결과/<코드>_xxxx/`로 바뀜 |
| 위치 검수에도 `*_진단.json` 추가(경고·개수·미구현) | 차례와 통일 | 파일 1개 추가 |
| 판정 표현을 반영/미반영 → **적합/부적합**(판단불가 유지)으로, 요약 JSON에 항목별·전체 `검수결과` 추가 | 검수 확인서의 검수결과 표현과 일치 (피드백 반영) | `판정`·`verdict` 값과 `*_00_요약.json` 구조가 바뀜. 원본 비교 테스트는 표현을 맞춘 뒤 비교 |
| 위치 검수 입력도 역할 자동 판별 + 동일 파일 검출, 차례도 동일 파일 검출 | 양쪽 검사를 모두 적용 | 업로드 순서 무관 |
| HWP에서도 표 셀을 읽음 → 차례 ③ 평가 대조가 HWP에서도 표 기반으로 동작 가능 | 공통 로더가 HWP 표를 지원 | 원래는 HWP면 문단 휴리스틱(△)만. 실제 HWP로 확인 필요(합성 HWP 픽스처 없음) |
| `header_columns`가 같은 머리글이 두 열에 있으면 먼저 나온 열 사용 | 원본 dict comprehension은 마지막 열 | 머리글이 중복된 비정형 표에서만 차이 |

## 4. 검증

- `python3 -I tests/make_fixtures.py fixtures` : 원고 6종(정상, PUA 문자, 학습명 불일치, 소분류 불일치, 세분류 순서 바뀜, 평가 표 불일치) + 개발계획서.
- `python3 -I tests/compare_with_original.py original src fixtures` : 차례(계획서 유/무) 12건 + 위치 6건 = 18건, 체크리스트 JSON 완전 일치.
- 미검증: 실제 HWP(바이너리) 파일. CFB 로더는 원본 코드를 합친 것이지만 합성 HWP를 만들지 못해 픽스처 비교는 HWPX만 했다. 실제 원고·개발계획서 쌍으로 한 번 돌려본 뒤 운영에 쓸 것.

## 5. 공통 파서 승격 — `ncs_core.manuscript` (2026-10-31)

문제: 필요 지식 검수(`ncs_knowledge`)가 형제 패키지의 내부 모듈을 직접 썼다.
`ncs_toc.parsers/presence/text/compare/config`, `ncs_overview.parsers/patterns`. 차례 파서를 고치면 필요 지식이 깨지는데 그 사실을 차례 쪽 테스트는 모르는 구조였다.

조치: "원고 구조를 읽는 코드"는 정책이 아니라 메커니즘이므로 코어로 올렸다. 판정 정책과 JSON 키는 바꾸지 않았다.

| 원래 자리 | 새 자리 (`src/ncs_core/manuscript/`) |
|---|---|
| `ncs_toc/parsers.py` `parse_toc`, `parse_plan_toc`, `parse_overview` | `toc.py` (`parse_overview` → `parse_overview_lines`로 개명: 표를 우선 읽는 개요 파서와 구분) |
| `ncs_toc/parsers.py` `parse_body` | `body.py` |
| `ncs_toc/presence.py` | `presence.py` |
| `ncs_toc/patterns.py` + `ncs_overview/patterns.py`의 양식 인식 패턴 | `patterns.py` (차례의 `OV_SUB`는 명칭이 같은 줄에 있어야 하므로 `OV_SUB_NAMED`로, 개요의 `OV_SUB`는 그대로) |
| `ncs_toc/text.py` `norm`/`same`, `ncs_toc/compare.py` `diff_list`/`pua_note` | `names.py` |
| `ncs_overview/parsers.py` `parse_overview`, `parse_plan`, `ncs_overview/text.py` `split_items` | `overview.py` |
| `ncs_toc.CheckConfig`의 파서 임계값 5개 | `config.py` `ParseConfig` (`ncs_toc.CheckConfig.parse_config()`가 만들어 넘김) |

- `ncs_knowledge.CheckConfig.toc_config()` → `parse_config()` (기본 `ParseConfig`; 종전에도 차례 기본 임계값을 썼다).
- `ncs_overview/patterns.py`에는 판정용 패턴(`GOAL_END`, `DEFINITION_*`, `TERM_PREDICATE`)만 남는다. `ncs_overview/text.py`의 `norm`/`same`은 개요 고유 규칙(‘학습 N.’ 접두를 지우지 않음)이므로 그대로 둔다.
- 삭제: `ncs_toc/{parsers,patterns,presence,text,compare}.py`, `ncs_overview/parsers.py`, `ncs_knowledge/text.py`.
- 추가: `tests/test_layering.py` — 검수 패키지 간 import, `ncs_core`→상위 계층 import, CLI 밖의 `ncs_service` 사용을 금지한다.

검증: 네 엔진 × 합성 원고 6종 × 계획서 유/무 = 42건의 체크리스트·지적사항·확인서·진단 JSON이 전후 동일. `tests/compare_with_original.py` 18/18 동일. `tests/test_service.py` 7건 통과.

### 5.1 표 안 문단 정보를 `Document`에 싣기 (2026-10-31)

문제: `ncs_knowledge/structure.py`의 `cell_paragraphs`가 hwpx zip을 다시 열어 본문 섹션 XML을 두 번째로 순회했다. "문서는 한 번 읽는다"는 `ncs_core.documents`의 약속을 깨고, 같은 정보를 두 코드가 각자 계산했다.

조치: `ncs_core.hwpx.parse_section`이 이미 갖고 있는 문단 위치 정보로 표(중첩 포함) 안 문단 인덱스 집합을 함께 돌려주고, `Document.table_paragraphs: list[frozenset[int]] | None`(섹션별, hwp는 None)에 싣는다.
`Document.section_table_paragraphs(index)`로 읽는다. `cell_paragraphs`와 `structure.py`의 `zipfile`·`ElementTree` 의존을 제거했다.

검증: 42건 스냅샷 동일, 원본 비교 18/18 동일.

### 5.2 엔진 계약 테스트 (2026-10-31)

문제: 엔진이 제공해야 할 공개 API(`CheckConfig`, `DEFAULT_RULES`, `prepare_review`, `evaluate_review`, `run_review`, `save_results`)와 결과 형식은 CONVENTIONS에만 적혀 있었고, `ncs_service`는 모듈에 그 이름이 있다고 믿고 호출했다. 기존 `tests/test_service.py`는 엔진 이름 넷을 하드코딩해서 다섯 번째 엔진을 등록해도 자동으로 검사하지 않았다.

조치: `tests/test_engines.py` 추가. `ncs_service.registry.ENGINES`를 순회하므로 엔진을 등록하면 자동으로 검사 대상이 된다. 검사 내용: 등록 항목 형식, 공개 이름과 `__all__`, frozen `CheckConfig`, 규칙 key 중복, 체크리스트 행 키·판정값·item_id 접두, 확인서 행이 `f02_items`의 해당 구성요소 항목 번호·문구와 일치, `findings == flatten(checklist)`, 진단 키, `rules=()` → 전부 미검사, 다른 엔진의 설정 거절, 저장 폴더·표준 JSON 5종·ZIP 내용, 그리고 `webapp/server.py`·`App.jsx`의 check 목록이 `ENGINES`와 같은지.

하지 않은 것: `typing.Protocol` 타입 도입. 정적 검사기(mypy/pyright)가 없는 현재는 이름 존재만 확인할 수 있어 실행 기반 테스트보다 덜 잡고, 엔진별로 다른 `ReviewContext`·`CheckConfig` 때문에 `Any` 또는 제네릭이 필요해 계약을 바꿀 때 비용만 늘린다. 정적 검사기를 도입할 때 함께 검토한다.

### 5.3 `original/` 제거 — 골든 결과로 대체 (2026-10-31)

`original/`(리팩토링 전 차례·위치 소스)은 `tests/compare_with_original.py`가 "전후 결과 동일"을 보이는 기준으로만 쓰였다. 소스라서 `lxml`이 필요했고, 매 비교마다 옛 코드를 다시 돌렸으며, 개요·필요지식은 덮지 못했다.

조치: 제거 직전 `original` 대 `src` 18/18 동일을 마지막으로 확인한 뒤, 현재 `src/`가 내는 결과를 `tests/golden/*.json` 42건(네 엔진 × 원고 6종 × 계획서 유/무)으로 저장했다. 이 42건은 이날 리팩토링(§5·5.1·5.2) 시작 전 결과와도 동일하므로, 골든은 곧 `original`의 답이다. `tests/test_golden.py`가 현재 결과와 골든을 비교하고 사례에 없는 골든 파일도 잡는다. `tests/make_golden.py`는 정책을 의도적으로 바꿀 때만 실행한다. `original/`과 `compare_with_original.py`는 삭제했고 `lxml`은 어디에도 필요하지 않다.

골든에서 제외한 것: 진단의 `inputs`(입력 파일 경로 — 실행 환경마다 다름).

### 5.4 엔진 목록 단일화·스키마 마이그레이션 (2026-11-01)

문제: PostgreSQL 이력 저장(`db71258`)이 엔진 목록을 두 곳에 더 적었다. `postgres.py`의 `REPORTS` 사전(check → reporting 모듈·한국어 이름)과 SQL의 `CHECK (check_name IN (…))`. 전자는 `ENGINES`와 각 엔진 `reporting.py`에 이미 있는 정보의 복사였고, 후자는 `CREATE TABLE IF NOT EXISTS`로는 기존 DB에 반영되지 않아 다섯 번째 엔진 추가 시 기존 설치에서만 INSERT가 실패하는 함정이었다. 또 `save_report`가 `report_summary`와 같은 요약 계산을 따로 갖고 있었다.

조치:
- 각 엔진 `reporting.py`에 `REPORT_NAME`과 `summary(result)` 노출. `postgres.py`·`postgres_cli.py`는 `REPORTS` 대신 `ENGINES`를 순회하고 `reporting_for(check)`로 모듈을 얻는다.
- SQL에서 `check_name` CHECK 제약 제거. `migrate()`를 번호 마이그레이션(`MIGRATIONS` + `schema_version` 표)으로 바꾸고, `002_drop_check_name_constraint`가 기존 설치의 제약을 뗀다. 이미 테이블이 있던 DB는 재시작 한 번으로 맞춰진다.
- `save_report`가 `report_summary`를 호출하고 `_buckets`를 공유. 요약 계산은 한 곳.
- 테스트: `test_engines.py`에 `REPORT_NAME`·`summary()`·파일 요약 일치·이름 중복 금지 추가, `test_migrations.py` 신설(번호 연속·중복 금지·SQL에 엔진 이름 금지·`IF (NOT) EXISTS` 보호).

검증: 골든 42건 동일(요약 통합이 출력을 바꾸지 않음).

### 5.5 저장소 추상화 — `ncs_service.store` (2026-11-01)

문제: 웹 서버가 `if database_url:` 분기 세 곳(시작 시 migrate, 저장, 이력 API 등록)에서 시그니처가 다른 두 함수(`persist_review(execution, out_dir)` / `save_review(dsn, execution, inputs)`)를 골라 불렀고, ZIP 재생성·입력 메타데이터 계산도 서버 안에 있었다. 저장을 건드리는 다음 작업("업로드 한 번 → 확인서 한 장")에서 분기가 늘어날 자리였다.

조치: `ncs_service/store.py`에 `FileStore`·`PostgresStore`(같은 호출 모양: `prepare()`·`save(review, uploads) -> StoredReview`·`supports_history`)와 `open_store(out_dir, database_url)`. 이력 조회(`list_reviews`·`get_review`·`export_zip`)는 `PostgresStore`만 갖고, 서버는 `supports_history`로 등록 여부를 정한다. ZIP 재생성과 `input_metadata` 호출이 서버에서 저장소로 이동. 서버의 `database_url`은 `open_store`에 넘기는 한 줄만 남았다. `psycopg`는 `PostgresStore` 메서드 호출 시점에만 import하므로 파일 모드는 `web` extra 없이도 뜬다.
부수: SQL 스키마·`MIGRATIONS`를 `migrations.py`로 분리(psycopg 없이 import 가능 → `test_migrations.py`가 엔진만 설치한 환경에서도 돈다).
테스트: `test_store.py` 신설(저장소 선택, 두 구현의 호출 모양, FileStore 저장, PostgresStore 위임·ZIP 재생성). `test_webapp.py`의 저장 실패 패치 지점을 `ncs_service.store.persist_review`로 이동.

### 5.6 차례 모듈 로직 점검 1차 — 파서 견고성 (2026-11-01)

F02 차례 ①~⑦ 문구와 규칙 코드를 대조한 결과(판정 논리는 문구와 일치), 실제 원고에서 깨질 수 있는 파서 지점을 고쳤다. 판정 정책은 바꾸지 않았다(골든 42건 동일).

| 지점 | 문제 | 조치 |
|---|---|---|
| 본문 `N-M.` 제목 수집 (`parse_body`) | 표 셀 문단(평가·수행 내용 표의 "1-1. 명")도 제목으로 잡혀, ③ 필요지식 자리는 `(no, sub)` 중복 제거에서 **마지막**(표 사본)이 남고 ④는 "마지막 필요지식 제목"이 평가 표 안의 것이 되어 거짓 X 가능 | 같은 번호는 하나만, **표 밖 문단 우선 → 먼저 나온 것**. `table_paragraphs`(`Document.section_table_paragraphs`) 인자 추가. hwp(표 정보 없음)는 먼저 나온 것 |
| 차례 학습 번호 건너뜀 (`parse_toc`) | `학습 N.`이 이어지지 않으면 이후 학습이 조용히 사라지고 간접 증상만 남음 | `toc["건너뜀"]`에 기록, 차례·필요지식 진단 `warnings`에 경고 |
| ③ 개요 내용체계 자리 | toc만 문단 기준 `parse_overview_lines`(명칭이 같은 줄에 있어야 인식), 개요·필요지식은 표 우선 `parse_overview`. 셀 안에서 "1-1."과 명칭이 두 문단으로 갈리면 toc가 거짓 "누락" | toc도 `parse_overview(document, section)["내용체계"]`로 통일. `parse_overview_lines` 삭제 |

테스트: `tests/test_manuscript.py` 신설(문단 목록으로 직접 — 표 사본 선후, 표 정보 없을 때, ④용 마지막 제목 위치, 건너뜀 기록).

점검에서 남긴 것(결정 또는 실제 원고 필요): ①의 "개발계획서 학습명 일치" 체크가 ③ 차례 자리와 같은 원인을 두 번 보고함(①은 요소명 준용·'~하기'만 묻는 것이 문구에 충실) · ② 행동명사 종결의 부분 구현(명백한 동사형 종결만 X) · 제목 셀이 "학습 1 교수⋅학습 방법" 한 문단인 원고와 학습 1개 모듈의 내비게이터 오인 가능성 · ⑦은 hwpx에 쪽 번호가 없어 불가(확인서 비고에 사유 표기 권장).

### 5.7 차례 ② 행동명사 종결 구현 — 사전 기반 (2026-11-01, 판정 정책 변경)

②(‘학습 내용명’은 행동명사로 종결하였는가)는 글자 모양으로 판정할 수 없는 단어 지식 문제라 미검사였다. 검사의 본질은 "머리어 W에 대해 사전에 ‘W하다’ 동사가 있는가"이며, 이를 **미리 조회해 패키지에 실은 목록**으로 판정한다. 검수 실행은 네트워크를 쓰지 않는다.

| 판정 | 조건 |
|---|---|
| O | 머리어가 `ncs_core/data/action_nouns.txt`에 있음 |
| △ | 목록에 없음. 비고 "행동명사 여부 확인 필요: 'W'". 머리어는 진단 `행동명사 미확인`에 모임 |

**결정(2026-11-01, 사용자)**: 두 값만 쓴다. X(부적합)는 내지 않는다 — "사전에 없음"은 "행동명사가 아님"이 아니라 "사전이 모름"이기 때문(후보 113단어 중 10단어가 사전에 ‘-하다’가 없는데도 행동명사: 디버깅·코딩·품질관리 등). 동사형 종결(‘정의하기’)·복합어(‘안전관리’)도 목록에 없으면 △로 두고 사람이 본다. 복합어 뒷부분 재시도는 거짓 O 위험(제조사→조사, 조회수→회수)이 있어 넣지 않았다.

머리어: 끝 괄호 설명·문장부호를 떼고 나열 표지(공백 · / , 및, 조사 와/과)로 나눈 마지막 조각(‘데이터 수집·정리’ → ‘정리’).

목록(`단어 \t 출처 \t 날짜 \t 근거`)은 `scripts/build_action_nouns.py`가 국립국어원 표준국어대사전 API로 키운다: ‘W하다’를 정확 검색해 동사 표제어가 있으면 `stdict`로 추가하고 근거에 target_code를 적는다. 사전에 없는 단어는 자동으로 넣지 않고 사람이 `manual`로 결정한다(근거 열 필수). `view.do`(상세)는 명사 항목의 `lexical_info`에 반대말·비슷한말만 있고 ‘-하다’ 파생어가 없음을 확인해 쓰지 않는다. 후보 입력: 단어 직접 / `--from-file` / `--from-results`(차례 진단 JSON의 `행동명사 미확인`). 응답 캐시 `scripts/.stdict_cache.json` 커밋.

현재 목록 110단어: 103 `stdict` + 7 `manual`(초기 3 + 외래어 디버깅·모델링·코딩·프로그래밍). 알려진 한계: 동형이의어(도장 塗裝/印章)는 글자로 구분 불가 — ② 목적이 종결형 검사라 영향 작음, 기록만.

골든: toc 12건에 ② 행 추가, 확인서 ② 미검사→판정. 다른 행은 동일. 테스트 `tests/test_toc_action_nouns.py`.

**결정(2026-11-01, 사용자)**: ①의 ‘개발계획서 학습명 일치’ 체크는 ③ 차례 자리와 같은 원인을 두 번 보고하지만 **유지**한다. 검수자가 ①을 볼 때 학습명이 계획서와 다르다는 사실을 바로 봐야 한다는 판단. 중복이라는 이유로 빼지 말 것.

## 6. 남은 과제 (이번 범위 밖)

- 기존 `docs/REVIEW.md`의 위치 ⑤ 정확성 과제(코드 번호 기반 행 선택 등)는 그대로다.
- 설치형 Python 패키지 구성은 `pyproject.toml`로 반영했다. 웹은 `src/ncs_web`, 엔진·서비스는 기존 `src/ncs_*`에서 설치하며, `--src`와 런타임 검색 경로 주입은 제거했다. 기본 엔진·웹·테스트 의존성을 구분하고 결과·화면 경로는 별도로 지정한다.
- 라인 길이 120자 기준 `black -l 120` 적용(이 환경에는 black이 없어 수동 정리).
- `ncs_overview/compare.py`의 `diff_list`는 `ncs_core.manuscript.names.diff_list`와 본체가 같고 정규화 규칙만 다르다. 정규화 함수를 인자로 받게 하면 하나로 합칠 수 있다.

## 평가 ① 엔진 추가 (2026-11-01)

의도적으로 추가한 동작: `evaluation` / `ncs_evaluation`은 개발계획서의 학습 내용명을 기준으로
차례·개요·본문·평가 준거·평가 방법을 비교한다. 평가 ②~⑤는 미검사이며 기존 엔진 정책은 변경하지 않는다.
번호 기반 연결과 정확 문자열 비교를 사용한다. 번호 없는 평가표는 식별된 학습 범위에서 명칭 목록을 비교한다.
계획서 부재, 표 미인식, 중복 번호/명칭, 분할 표, 본문 영역 연결 실패는 판단불가로 처리한다.
기존 42건 골든은 변경하지 않았으며 평가 ①의 12건을 추가했다. 전용 테스트는 누락·추가·오명칭,
준거/방법 독립 검사, 학습 소속 오류, 중복·분할·미인식 표, 계획서 부재, 섹션 변경, 웹 업로드를 검증한다.

### 평가 ①의 불필요한 판단불가 축소

동일 명칭 반복과 번호 유무 혼용은 계획서의 번호에 정확하고 유일하게 연결되면 검사한다.
완전한 명칭 목록을 가진 동일 종류의 여러 평가표도 각각 검사한다. 분할/누락 구별이 어려운
부분 목록은 계속 판단불가로 남기되, 명백한 오명칭·번호 불일치는 부적합으로 유지한다.
판정 기준을 완화한 것이 아니라 동일 명칭 반복과 번호 연결을 지원한 변경이다.
실제 사용자 결과는 아직 확보하지 못했으며 합성 사례로 검증했다.
