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

## 6. 남은 과제 (이번 범위 밖)

- 기존 `docs/REVIEW.md`의 위치 ⑤ 정확성 과제(코드 번호 기반 행 선택 등)는 그대로다.
- 설치형 Python 패키지 구성은 `pyproject.toml`로 반영했다. 웹은 `src/ncs_web`, 엔진·서비스는 기존 `src/ncs_*`에서 설치하며, `--src`와 런타임 검색 경로 주입은 제거했다. 기본 엔진·웹·테스트 의존성을 구분하고 결과·화면 경로는 별도로 지정한다.
- 라인 길이 120자 기준 `black -l 120` 적용(이 환경에는 black이 없어 수동 정리).
- `ncs_overview/compare.py`의 `diff_list`는 `ncs_core.manuscript.names.diff_list`와 본체가 같고 정규화 규칙만 다르다. 정규화 함수를 인자로 받게 하면 하나로 합칠 수 있다.
