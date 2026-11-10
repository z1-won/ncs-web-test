# F02 검수 시스템 아키텍처 — 전체 흐름과 모듈별 로직

원고 한 건이 화면에서 확인서 표가 되기까지 지나가는 길과, 각 층·모듈이 무엇을 읽고 무엇과 비교하는지 정리한 문서다.
규약(무엇을 지켜야 하나)은 `CONVENTIONS.md`, 작업 절차와 분업은 `WORKFLOW.md`, 항목별 구현 범위는 루트 `README.md`의 '검수 범위'를 본다.
(2026-11-09 프로젝트 문서 `PoC2_설계_아키텍처_소개및분석_v1-3`에서 옮김. 이후 변경은 이 파일에서 한다.)

---

## 1. 한 장 그림 — 원고 한 건이 지나가는 길

```
[사용자]  hwp/hwpx 원고 (+ 개발계획서)  ──업로드──▶  frontend (React + KRDS)
                                                      │  POST /api/review (check=position|toc|…)
                                                      ▼
                                              ncs_web/server.py (FastAPI)
                                                      │  ReviewRequest(paths, check, module_code)
                                                      ▼
                                   ncs_service: registry.ENGINES[check] → service.execute_review
                                                      │
                 ┌────────────────────────────────────┴───────────────────────────────┐
                 ▼                                                                    ▼
   ncs_core.inputs.select_documents                                     엔진 패키지 (ncs_position … ncs_misc)
   └ documents.load_document ─ hwp.py / hwpx.py ─▶ Document                prepare_review(manuscript, plan, module_code)
     └ normalize_sections: 구역 0 = 앞부분, 1 = 본문                        │  공통 파서(ncs_core.manuscript)로 구조 추출 → ReviewContext
                                                                           ▼
                                                                evaluate_review: registry.DEFAULT_RULES 차례로 실행(ncs_core.rules.run_rules)
                                                                           │  규칙 fn(context) → 행 목록 [{item_id, 체크{…}, 판정, 비고{…}, 수정 제안}]
                                                                           ▼
                                                        ReviewResult(checklist, findings=flatten, diagnostics, sheet=확인서 표)
                                                                           │
                                   ncs_core.sheet.build_sheet: 행 → F02 항목(①…) 적합/부적합/판단불가 + 비고 요약
                                                                           ▼
                      ncs_service.store: 파일(결과/…zip) 또는 PostgreSQL 이력(review_runs)  ──▶  화면: 검수 확인서 / 전체 체크리스트 / 지적사항
```

세 가지만 기억하면 된다.
1. **문서 읽기는 한 곳**(`ncs_core.documents`)에서 하고, 모든 엔진은 "구역 0 = 앞부분(위치·차례·개요), 구역 1 = 본문"이라고 가정한다. 원고가 어떻게 나뉘어 있든 `normalize_sections`가 그 모양으로 맞춘다.
2. **엔진은 서로 모르며**(import 금지, `tests/contract/test_layering.py`), 같은 구조를 읽는 코드는 `ncs_core.manuscript` 파서 하나를 공유한다. 그래서 파서 하나를 고치면 10개 엔진이 같이 좋아지고, 같이 깨진다(골든 테스트가 그 변화를 잡는다).
3. **판정은 행 단위**다. 규칙 함수는 "어디서(region_path) · 무엇을(원고) · 어떤 체크가 O/X/△/- · 왜(비고)"를 적은 행을 돌려주고, `sheet.py`가 그 행들을 F02 확인서 항목으로 접는다. 화면의 세 표(확인서·체크리스트·지적사항)는 같은 행을 세 가지 크기로 보여 줄 뿐이다.

---

## 2. 층별 역할

| 층 | 패키지 | 책임 | 의존 |
|---|---|---|---|
| 화면 | `frontend` | 업로드, 검수 종류 선택(KRDS 셀렉트, 라벨은 `/api/health`의 `engines`), 확인서·체크리스트·지적사항 표, 이력 조회·삭제 | HTTP만 |
| HTTP | `ncs_web/server.py` | 파일 수신·임시 저장, 요청 검증, 응답 JSON, zip·확인서 내려주기, 이력 API | `ncs_service` |
| 조정 | `ncs_service` | 검수 종류 ↔ 엔진 연결(`registry`), 실행(`service`), 저장(`store`: 파일/PostgreSQL), 공용 CLI(`cli`), 내보내기(`export`), 메모 원고(`annotate`) | 엔진, `ncs_core` |
| 엔진 10개 | `ncs_position` `ncs_toc`(출력본 PDF 선택 입력) `ncs_overview` `ncs_knowledge` `ncs_perform` `ncs_teaching` `ncs_evaluation` `ncs_references` `ncs_colophon` `ncs_misc` | F02 구성요소 하나씩. 구조 추출(pipeline) + 판정 규칙(rules/) + 확인서 표(sheet) + 저장 이름(reporting) | `ncs_core`만 |
| 코어 | `ncs_core` | 문서 읽기, 공통 파서, 비교·정규화, 외부 데이터(NCS 목록·수준·행동명사), 규칙 실행기, 확인서 접기, 저장 | 표준 라이브러리만 |
| 도구 | `scripts/{batch,data,probe}` | 다문서 배치 테스트, 기준 데이터 갱신, 외부 API 점검 | 코어·엔진 |
| 테스트 | `tests/{core,engines,service,contract,integration}` | 단위(규칙·파서) + 골든(합성 원고 6종 × 10엔진 스냅샷) + 계약(엔진 등록·계층·설치) + DB 통합 | |

실행 방법 세 가지가 전부 같은 코드를 지난다: 웹(`ncs-web --dist …`), CLI(`python -m ncs_toc 원고.hwpx 계획서.hwp` → `ncs_service.cli.run_cli`), 배치(`scripts/batch/batch_review.py`).

---

## 3. 코어 `src/ncs_core` — 파일별 로직

### 3.1 문서 읽기
- **`hwpx.py`** — zip 안의 `Contents/section*.xml`을 ElementTree로 읽어 문단 텍스트(변경 추적은 스택으로 삽입/삭제 처리), 표(셀 텍스트, 메모 문단 제외), 그림(BinData id·크기), 문단 스타일 이름, 본문 밖 문단(메모·머리말·꼬리말·각주 = aside), 자동 번호(`numbering.py`로 복원), 쪽 나누기 위치를 뽑는다. 스타일·번호·쪽나눔이 있어 hwpx가 "완전한 입력"이다.
- **`hwp.py`** — 바이너리 hwp의 CFB 컨테이너를 직접 읽는다. 디렉터리 트리를 따라 `BodyText/Section*`만 읽는다(`ViewText/`의 배포용 사본은 읽지 않음). 문단 텍스트와 표 셀만 얻고 스타일·번호·그림은 없다 → 관련 항목은 △.
- **`numbering.py`** — hwpx의 문단 번호 정의(`^1.` `(^2)` 같은 서식, 수준별 카운터)를 해석해 화면에 보이는 번호 문자열("1.", "(가)", "①")을 문단마다 되살린다. 필요 지식 ⑥이 쓴다.
- **`documents.py`** — 위 둘을 `Document`(path, format, sections, tables, images, figures, styles, aside_paragraphs, numbers, page_breaks, pictures, binaries)로 묶고 공백을 정리한 뒤 **`normalize_sections`**를 적용한다. 차례 제목이 있는 구역을 찾아 (a) 구역 하나짜리면 본문 시작에서 둘로, (c) 표지/차례+개요+본문이면 표지와 앞부분을 합치고 본문에서, (d) 표지/차례+개요/본문이면 앞 둘을 합친다. 본문 시작은 차례·개요 **뒤**의 첫 `큰학습` 스타일 또는 개요 뒤 첫 "학습 1" 줄. 표·그림·스타일·번호·쪽나눔 인덱스를 함께 옮긴다.
- **`inputs.py`** — 업로드된 파일이 원고인지 개발계획서인지를 머리 60문단으로 판별(`detect_role`), 같은 파일 중복·빈 파일을 막는다. PDF는 내용과 상관없이 세 번째 역할 `print`(출력본, 선택)로 읽어 `select_documents`가 `{'manuscript','plan','print'}`를 돌려준다. `ncs_service`는 `Engine.optional`에 `print`를 선언한 엔진에만 넘긴다.
- **`module_code.py`** — `LM1203020408_23v3` 꼴 검증과 파일명에서 추출.
- **`pdf.py`** — PDF 출력본·매뉴얼 읽기(선택 extra `pdf` = pypdf). 글자 y좌표로 위·아래 8 % 띠를 머리말·꼬리말로 분리하고(달리는 머리말의 학습명이 본문 검색에 걸리지 않게), 꼬리말에서 인쇄된 쪽 번호를 읽어 못 읽은 쪽은 다수결 offset으로 '추정'한다. 표·스타일·구역이 없으므로 `Document`가 아니라 `PdfDocument`(쪽별 body/header/footer/folio)다. 스캔본처럼 글자를 못 뽑으면 ValueError.

### 3.2 공통 파서 `ncs_core/manuscript/`
"원고 양식이 어떻게 생겼는가"를 아는 유일한 곳. 판정은 하지 않는다.
- **`patterns.py`** — 차례 줄(`학습 1. 명 3`, `1-1. 명 5`, `• 평가 20`, `참고 자료 92`), 개요 제목, `1-1.` 제목, 내비게이터 `학습 N`, 계획서 `1-1 명`/`1-1. 명` 정규식.
- **`toc.py`** — 차례 면 → `{학습:[{no,text,page}], 내용:[{no,sub,text}], 꼬리:{참고 자료:쪽, 활용 서식:쪽, 부록:쪽}}`. `parse_plan_toc`는 개발계획서의 학습명·내용명(표 우선, 아래 `plan_table`).
- **`overview.py`** — 학습모듈의 개요 → 목표 문장, 선수학습(쉼표 분리, 괄호 안 쉼표 보호), 내용체계 표(학습명·내용명·요소 코드), 핵심 용어. `parse_plan`은 계획서 모듈 블록(정의·목표·학습명·내용명·요소).
- **`plan_table.py`** — 계획서 모듈 표를 **셀 단위**로 읽는다(열 이름 학습명/학습내용명/학습 목표로 열을 찾음). 변경승인 계획서의 '비고' 열이 내용명으로 섞이던 오탐과 줄바꿈으로 잘리던 목표 문장을 해결. 표를 못 찾으면 줄 단위 읽기로 돌아간다.
- **`plan_goals.py`** — 계획서 학습 내용별 학습 목표 문장(수행 준거) `{(N,M): {'text','goals':[…]}}`.
- **`body.py`** — 본문 구조: 내비게이터 묶음(`학습 1 … 학습 N` 연속) → 학습 구간(spans). 묶음의 학습 번호는 강조 항목(큰학습-제목/숫자 스타일) 또는 묶음 뒤 첫 `N-M.` 제목의 N으로 읽는다. `1-1.` 제목(표 밖 우선), 학습별 교수·학습 방법/평가 제목 위치. 메모(aside) 문단은 뺀다.
- **`units.py`** — 학습 내용(N-M) 구간마다 '학습 목표' 문장 묶음과 머리말(필요 지식/수행 내용/수행 순서/평가 …) 위치.
- **`presence.py`** — 참고 자료·활용 서식·부록이 본문에 "있는지"의 근거(제목 줄, 참고문헌 꼴 줄, 배너 그림, 표). "이름 확정 못 함(None)"과 "배너만"을 구분한다.
- **`names.py`** — 학습명·내용명 목록 비교 `diff_list(label, expected, actual, where=, basis=)` → 누락/추가/다름/순서를 difflib로 구분하고 비고를 만든다.
- **`pages.py`** — 출력본 PDF에서 차례가 가리키는 제목('학습 N', 'N-M', '학습 N 교수·학습 방법/평가', '참고 자료/활용 서식/부록')이 처음 시작하는 쪽을 찾는다. 내비게이터 묶음은 글자만으로 어느 학습의 시작인지 모르므로 그 뒤 첫 'N-M.' 제목의 N을 쓴다. 차례 ⑦이 비교에 쓴다.
- **`config.py`** — 파서의 조정 가능한 상수(제목 최대 길이 등).

### 3.3 비교·판정 도우미
- **`text.py`** — `O X △ -`, `적합/부적합/판단불가`, `make_normalizer(prefix)`(머리 번호 제거·PUA 기호→가운뎃점·NFC), `verdict(checks)`(X 있으면 부적합, △ 있으면 판단불가), `flatten`(행 → 지적사항), `visible`(기호 글꼴 문자를 읽을 수 있게).
- **`goals.py`** — 문장 목록 비교. `normalize`, `compare_lists`(순서 무시, 가장 비슷한 문장을 짝지어 어절 차이만 보여 줌), `difference`, **`explain_pair`**(두 이름을 문서 이름 붙여 나란히 + 띄어쓰기만/기호만/글자 다름).
- **`notes.py`** — 비고 문구 틀 함수(대조·누락·꼴·개수·판단불가 등). 규칙은 이 틀로 비고를 만든다.
- **`sentences.py`** — 행동 문장 종결 판정(`~한다`: '다' 앞 음절 받침 ㄴ이면 O, 이다/있다/없다 △).
- **`lexicon.py`** — 행동명사 사전(`data/action_nouns.txt`) + 표준국어대사전 API(`W하다` 동사 표제어). 조회 결과를 파일에 바로 덧붙인다. 키 없으면 △.
- **`ncs_catalog.py`** — `data/ncs_units.tsv`(세분류별 분류 명칭·능력단위) + `data/ncs_levels.tsv`(전 능력단위 수준). `NCS_CATALOG_FILE`로 교체·비활성화(합성 원고 테스트).
- **`ncs_api.py`** — 공공데이터포털 B490007/ncsInfo 호출. 운용 전 표 갱신용. 검수 서버는 호출하지 않는다.
- **`llm.py`** — 생성형 AI 호출(수행 ②). 응답은 `.llm_cache/`(git 제외)에 캐시한다.
- **`field_terms.py`** — 모듈 코드 → 분야(NCS 분류 이름)와 `data/field_terms.tsv`의 공용 명칭. 수행 ② 프롬프트가 분야별 '상표로 보지 않을 것'을 담는 데 쓴다.
- **`f02_items.py`** — F02 확인서 54항목 원문 문구(확인서 표의 '체크 항목' 열).

### 3.4 실행·결과
- **`rules.py`** — `Rule(name, item_prefix, fn)`과 `run_rules(context, rules)`: 규칙을 순서대로 돌려 행을 모은다.
- **`models.py`** — `ReviewResult(module_code, checklist, findings, diagnostics, context, sheet)`, `SavedReport`.
- **`sheet.py`** — `SheetItem(no, text, item_ids, check_prefix)`로 "확인서 항목 ①에 속하는 행"을 모아 적합/부적합/판단불가/미검사를 정하고, `summarize_remarks`가 체크 이름당 머리 줄 + 사례 줄 + `→ 수정 제안` 줄로 비고를 접는다.
- **`reporting.py`** — 항목별 JSON·확인서·지적사항을 `<코드>_<시각>_<이름>_xxxx/` 폴더와 zip으로 저장. 파일 이름 규칙은 엔진의 `ITEM_FILES`.

---

## 4. 엔진 — 공통 뼈대와 각자의 로직

모든 엔진은 같은 뼈대다: `config.py`(양식 가정) · `models.py`(ReviewContext) · `pipeline.py`(prepare/evaluate/run) · `registry.py`(DEFAULT_RULES) · `rules/*.py`(항목별 판정) · `sheet.py`(ITEMS) · `reporting.py`(ITEM_FILES) · `__main__.py`(`run_cli` 한 줄). 아래는 각 엔진이 **무엇을 읽어 무엇과 비교하는지**.

### `ncs_position` 위치 ①~⑤ — "앞표지의 분류 표가 NCS와 같은가"
- `parsers.py`: 앞부분 문단에서 대/중/소분류 라벨 다음 줄, 표에서 세분류·능력단위·학습모듈명 열, 서식 있는 표(⑤용).
- `pipeline.py`: 기준 = NCS 목록(모듈 코드의 세분류가 목록에 있으면). 세분류 목록(②)만 계획서 우선. 목록이 없으면 개발계획서. 계획서가 목록과 다르면 △로 알림.
- `rules/classification.py` ①: 대·중·소 명칭 + 기호 글꼴 문자. `rules/position.py` ②③④: 목록 비교 — 누락/원고에만/다름/순서, 능력단위-학습모듈명 행 대응. `rules/emphasis.py` ⑤: hwpx 글꼴(KoPub 돋움 Bold)·셀 음영 속성.

### `ncs_toc` 차례 ①~⑦ — "차례 면이 계획서·본문과 맞는가"
- `rules/names.py` ①: 학습명 '~하기', 계획서 학습명·요소명 준용. `rules/action_nouns.py` ②: 학습 내용명 머리어가 행동명사인가(사전→API→△). `rules/consistency.py` ③: 계획서를 기준으로 다섯 자리(차례·내용체계 표·내비게이터 묶음·본문 N-M 제목·평가 표)의 학습명·내용명 비교. `rules/placement.py` ④: 각 학습 끝에 필요 지식 → 교수·학습 방법 → 평가 순서. `rules/tail.py` ⑤⑥: 참고 자료 존재, 활용 서식·부록의 차례↔본문 일치. `evaluation.py`: 평가 표에서 '학습 내용' 열 읽기. `rules/pages.py` ⑦: 차례 쪽수 = 출력본(PDF, 역할 print)에서 그 제목이 시작하는 쪽(`ncs_core.manuscript.pages.locate_headings`). 출력본이 없으면 △ 한 행, 다른 원고의 출력본이면 △, 쪽 번호를 추정한 쪽은 △.

### `ncs_overview` 개요 ①~⑧ — "학습모듈의 개요 면"
- `rules/goal.py` ①: 목표 문장 '~할 수 있다.' 종결, 계획서 능력단위 정의와 대응. `prerequisites.py` ②: 선수학습 5개 이내. `prerequisite_codes.py` ③④: `이름(LM코드)` 분해 → 코드 꼴·NCS 목록 존재·버전·명칭·자기 모듈(③), 수준 표로 선수학습 수준 > 이 모듈 수준이면 X(④). `structure.py` ⑤⑥⑦: 내용체계 표의 학습명·내용명·요소 코드/명칭 = 계획서, 통합 요소는 코드·명칭 모두. `terms.py` ⑧: 핵심 용어 10개 이내 명사형.

### `ncs_knowledge` 필요 지식 ①~⑧ — "본문 학습 내용 단위의 구조·번호·그림"
- `rules/navigator.py` ①②③: 내비게이터 학습명에 코드 없음, '~하기', 차례·내용체계와 일치, 묶음 간 일치. `contents.py` ④: 본문 `N-M.` 제목 = 차례 = 내용체계. `goals.py` ⑤: 학습 목표 = 계획서(순서 무시, 어절 차이 표시). `numbering.py` ⑥: 번호 체계 󰊱〉1.〉(1)〉(가)〉1)〉가)〉①. `figtab.py`(추출)·`rules/figures.py` ⑦: 그림·표 번호 연속, 괄호, 기호 글꼴. `sources.py` ⑧: 그림·표 출처 줄과 F14 14종 골격.

### `ncs_perform` 수행 내용 ①②④
`blocks.py`가 본문을 '수행 내용' 블록(제목·재료·안전·수행 순서)으로 자르고, `rules/title.py` ①: 제목 '~하기', `rules/sentences.py` ④: 수행 순서 '~한다.' 종결. ②는 `rules/brands.py`가 재료·기기 줄만 LLM에 보내 상표·상품·제조사명 후보(△)를 받는다. 시스템 프롬프트는 `system_prompt(module_code)`가 원고 분야와 그 분야의 공용 명칭으로 만든다. ③은 미구현.

### `ncs_teaching` 교수·학습 방법 ①~④
`blocks.py`가 학습마다 교수 방법/학습 방법 글머리 목록을 자르고, `rules/counts.py` ①③: 각 3개 이상, `rules/sentences.py` ②④: 행동동사(-ㄴ다) 종결.

### `ncs_evaluation` 평가 ①②③⑤
`region.py`가 학습별 평가 구역에서 평가 준거 표, 평가 방법 목록, 피드백 블록을 읽는다. `rules/names.py` ①: 표의 학습 내용명 = 계획서. `goals.py` ②: 평가 준거 학습 목표 = 계획서. `methods.py` ③: 평가 방법 2개 이상. `feedback.py` ⑤: 방법별 피드백 개수·이름 일치 + 심화·보충 낱말(없으면 △). ④는 AI 후보.

### `ncs_references` 참고 자료 ①②③
`entries.py`가 참고 자료 항목과 본문 출처 줄을 모으고, `templates.py`가 F14 국내 17·국외 5종 골격. `rules/coverage.py` ①: 본문 인용이 모두 목록에. `format.py` ②: 골격 일치·기관명. `order.py` ③: 국문→번역→영문→중문→일문, 가나다·알파벳, 동일 저자 연대·a/b/c.

### `ncs_colophon` 판권 ①
`tables.py`가 개발 이력 표와 판권 표를 읽고, `rules/colophon.py`가 신규/개선 양식, 세분류 8자리, 학습모듈명(LM코드), 자리표시 잔존, 개발기관(협회만 적는 것이 정상 → 빈 칸·구 명칭만 X), 집필진·검토진, 판권 값, ISBN 행을 본다.

### `ncs_misc` 기타 ①②⑥⑦
`rules/page_starts.py` ①: 개요·내비게이터·교수학습·평가·참고 자료·활용 서식·부록이 새 쪽에서 시작(hwp △). `pictures.py` ②: 캡션↔그림 짝짓기, BinData 존재·0바이트. `ratio.py` ⑥: 필요 지식:수행 내용 글자 수 비율(5:5 넘으면 X). `references.py` ⑦: 활용 서식·부록 참조 문구.

---

## 5. 서비스·웹·화면

- **`ncs_service/registry.py`** — `ENGINES = {position: Engine("ncs_position", required=("manuscript","plan")), toc: …}` 확인서 순서. 엔진 목록의 유일한 원본. `describe_engines()`가 화면 셀렉트 라벨을 만든다.
- **`service.py`** — `execute_review(ReviewRequest)`: 문서 선택 → `prepare_review` → `evaluate_review`. `persist_review`: 파일 저장.
- **`cli.py`** — 엔진 공용 CLI `run_cli(check, 설명)`. 개발계획서 필수 여부는 `Engine.required`, `--body-section`은 엔진 `CheckConfig`에서 읽는다.
- **`store.py` / `postgres.py` / `migrations.py` / `postgres_cli.py`** — 결과 zip 파일 저장소와 PostgreSQL 이력(`review_runs`·`review_results`·`review_inputs`·`review_files`). `postgres_cli import 결과`로 과거 결과 폴더를 이력으로 이관. DSN·비밀번호는 `.env`.
- **`ncs_web/server.py`** — `POST /api/review`, `GET /api/health`, `GET/DELETE /api/reviews/{id}`, zip·확인서 내보내기. 정적 `--dist`로 프런트 제공.
- **`frontend/src/`** — `App.jsx`(화면 조립), `components/`(표·셀렉트·모달), `lib/checks.js`(`CHECKS`·`FILE_HINTS` — 서버 엔진 목록과 테스트가 일치를 검사), `lib/api.js`.

---

## 6. 데이터·도구·테스트

- 데이터(`src/ncs_core/data/`, git 관리): `ncs_units.tsv`(→ `scripts/data/build_ncs_catalog.py`), `ncs_levels.tsv`(→ `scripts/data/build_ncs_levels.py`), `action_nouns*.txt`(→ `scripts/data/build_action_nouns.py`), `F02_검수확인서_양식.hwpx`(확인서 내보내기 틀).
- `scripts/batch/batch_review.py`: 폴더의 원고 전부 × 10엔진 → 체크포인트(json) → xlsx. 출력은 `_batch/<날짜>_<이름>/`(git 제외). `batch_compare.py`가 기대 판정 표와 대조.
- 테스트(`python -m unittest discover tests`): `core/`(파서·도우미), `engines/`(규칙), `service/`(실행·저장·웹·내보내기), `contract/`(엔진 계약·계층·설치·골든·환경 고정), `integration/`(PostgreSQL, `NCS_TEST_DATABASE_URL` 있을 때). 골든은 `tests/fixtures` 합성 원고 6종 × 10엔진 × 계획서 유무 = 114 스냅샷, NCS 목록은 끄고 실행. 외부 API 키는 `tests/_env.py`가 비운다.

---

## 7. 고칠 때 어디를 보나 (치트시트)

| 하고 싶은 것 | 보는 곳 |
|---|---|
| 원고가 안 읽힘 / 구역 오류 | `ncs_core/documents.py` (`normalize_sections`), `hwpx.py`·`hwp.py` |
| 차례·개요·본문 구조를 잘못 잡음 | `ncs_core/manuscript/` (`toc.py`, `overview.py`, `body.py`, `units.py`, `presence.py`) |
| 개발계획서를 잘못 읽음 | `ncs_core/manuscript/plan_table.py`(표) → `overview.parse_plan`, `toc.parse_plan_toc`, `plan_goals` |
| 어떤 항목의 판정 기준 | 해당 엔진 `rules/<항목>.py` (정책은 여기에만) |
| 비고 문구 | `ncs_core/notes.py`, `goals.py explain_pair/difference/compare_lists`, `manuscript/names.py diff_list`, 확인서 요약은 `ncs_core/sheet.py` |
| 새 항목 구현 | 엔진 `rules/` 추가 → `registry.py` Rule → `sheet.py` item_ids → `reporting.py` ITEM_FILES → `tests/engines/` → 골든 |
| 새 엔진 추가 | `ncs_service/registry.py ENGINES` → `ncs_web/server.py CheckName` → `frontend/src/lib/checks.js` → `pyproject.toml` 스크립트 |
| CLI 인자 | `ncs_service/cli.py` (엔진 `__main__`은 고치지 않음) |
| NCS·사전 데이터 갱신 | `scripts/data/build_ncs_catalog.py`, `build_ncs_levels.py`, `build_action_nouns.py` |
| 화면 라벨·표 | `frontend/src/` (`components/Tables.jsx`, `lib/format.jsx`, `app.css`) |
| 이력 DB | `ncs_service/postgres.py`, `migrations.py`, `db/init/` |
