# 작업 절차·3인 분업·운영 체크리스트

코드 규약은 `CONVENTIONS.md`, 구조와 모듈별 로직은 `ARCHITECTURE.md`를 본다.
(2026-11-09 프로젝트 문서 `PoC2_운영_개발규칙_3인분업_v1-0`에서 옮김. 이후 변경은 이 파일에서 한다.)

## 1. 비고(검수자가 읽는 문장) 규칙

- 부적합·판단불가 비고는 **어느 문서의 어떤 문구인지 양쪽을 다 적는다**: `{자리} 「원고 문구」, {기준 문서} 「기준 문구」 (띄어쓰기만 다름 | 기호·띄어쓰기만 다름 | 글자가 다름 | 다른 곳: …)`. 틀은 `ncs_core.notes`, 대조 도우미는 `ncs_core.goals.explain_pair / difference / compare_lists`, `ncs_core.manuscript.names.diff_list(where=, basis=)`.
- "기준"이라는 말 대신 실제 이름: 개발계획서, NCS 목록, 차례, 내용체계 표, 내비게이터 N번째 묶음, 본문 제목, 평가 준거 표 …
- 1층(규칙) 비고는 항상 한 줄, 여러 사례는 `\n`, 여러 제안은 ` / `. 확인서(`ncs_core.sheet.summarize_remarks`)가 머리 줄 + 사례 줄 + `→ 수정 제안` 줄로 펼친다.
- 띄어쓰기·윤문 차이도 X(결정 2026-11-01). 순서만 다른 것은 같은 것(필요 지식 ⑤·평가 ②).

## 2. 데이터 파일과 갱신 (`src/ncs_core/data/`, git 관리)

| 파일 | 갱신 명령 | 주기 |
|---|---|---|
| `ncs_units.tsv` | NCS 포털 학습모듈 분류보기 24개 내려받기 → `python scripts/data/build_ncs_catalog.py 폴더` | 사업 시작 시, NCS 개정 공지 시 |
| `ncs_levels.tsv` | `python scripts/data/build_ncs_levels.py --from-csv 능력단위목록.csv` 또는 세분류 코드(API) | 〃 |
| `field_terms.tsv` | 손으로 추가(분야 코드 앞자리 + 용어). 수행 ② LLM이 그 분야의 일반 명칭을 상표로 잡을 때 | 새 세분류 원고 받을 때, 오탐이 나올 때 |
| `action_nouns.txt` / `_rejected.txt` | `set -a; source .env; set +a; python scripts/data/build_action_nouns.py --from-manuscripts 원고…` | 새 세분류 원고 받을 때 |

환경 변수(`.env`, git 제외, 값은 채팅·문서에 적지 않음): `STDICT_API_KEY`, `NCS_API_KEY`, `LLM_*`, DB 변수. 검수 서버는 외부 API를 호출하지 않는다 — 조회 결과는 모두 위 파일로 들어와야 한다(LLM은 예외, 캐시 사용).

## 3. 작업 절차 (한 요청 = 한 커밋)

1. 재현 — 실제 원고로 현상 확인. 원고는 `samples/`(git 제외)에 두고 저장소에 넣지 않는다.
2. 규칙·파서 수정 → 단위 테스트 추가(규칙은 `tests/engines/`, 파서·도우미는 `tests/core/`, 서비스·웹은 `tests/service/`).
3. `pip install -e ".[test]" -q && python -m unittest discover tests`. 묶음 하나는 `python -m unittest discover tests/engines -t tests`, 한 파일은 `python -m unittest tests.engines.test_colophon`(루트에서). 골든이 바뀌면 `PYTHONPATH=src python tests/make_golden.py` 후 `git diff tests/golden`에서 **판정 변동이 의도한 것인지** 확인하고 같이 커밋. 문구만 바뀐 골든 갱신은 커밋 메시지에 "문구만"이라고 적는다.
4. 다문서 배치로 회귀 확인(필요할 때): `python scripts/batch/batch_review.py run --root 원고폴더 --work _batch/<날짜>_<이름> --budget 150` → `xlsx --out …`. 오판정 수정은 `f02-fix-loop` 스킬(`.claude/CLAUDE.md`)이 이 절차를 자동으로 돈다.
5. 커밋 메시지는 `.gitmessage` 형식(TYPE: 무엇을 / 왜). 다른 사람이 수정 중인 파일은 건드리지 않거나 자기 hunk만 스테이징한다.
6. feature 브랜치(`이름/주제`)에서 작업하고 PR로 main에 올린다. CI(`.github/workflows/test.yml`)가 테스트와 화면 빌드를 돌린다.

## 4. 3인 분업

| 역할 | 담당 | 파일 영역 | 테스트 |
|---|---|---|---|
| 총괄 | 코어·서비스·웹, 데이터 파일, 배치, 통합 | `ncs_core`, `ncs_service`, `ncs_web`, `frontend/`, `scripts/`, `tests/golden` | `tests/core`, `tests/service`, `tests/contract` |
| A | 위치·차례·개요·필요 지식·판권 (문서 앞부분·구조) | `ncs_position`, `ncs_toc`, `ncs_overview`, `ncs_knowledge`, `ncs_colophon` | `tests/engines`의 해당 파일 |
| B | 수행 내용·교수학습·평가·참고 자료·기타 (본문 뒷부분·AI 후보) | `ncs_perform`, `ncs_teaching`, `ncs_evaluation`, `ncs_references`, `ncs_misc` | 〃 |

- 코어를 고쳐야 하는 변경은 총괄에게 넘기거나 PR로 분리한다(파서 변경은 모든 엔진에 영향).
- 충돌 지점은 `ncs_core/manuscript/*`(파서), `tests/golden`(결과 스냅샷), `frontend/src/App.jsx`. 한 사람이 한 번에 하나씩.
- 결정이 필요한 규칙(무엇을 X로 볼지)은 코드보다 먼저 문서에 적고 합의한다.

## 5. 운영 체크리스트 (새 세분류 원고를 받았을 때)

1. 폴더 구조 확인: `00.개발계획서 / 01.초고본 / 02.수정본`, 파일명에 모듈 코드 `LM##########_NNvN`(버전 없으면 웹에서 module_code 입력).
2. hwp는 hwpx로 변환(한글 → 다른 이름으로 저장). hwp는 자동 번호·쪽 나눔·그림·서식을 못 읽어 여러 항목이 △가 된다.
3. 변환 결과 크기 확인(비정상적으로 작으면 재변환).
4. 행동명사 목록 채우기(2장), NCS 목록에 세분류가 있는지 확인(없으면 분류보기 다시 내려받기).
5. 배치 실행 → xlsx '실행오류' 시트가 비어 있는지, '항목별집계'에서 전 문서 부적합/판단불가 항목이 있으면 규칙 의심.
6. 사람 확인: '상세비고' 시트의 사람 판정 열(정확/오탐/미탐)을 채워 돌려준다 → 오탐은 이슈로.

## 6. 로컬 폴더 (git 제외)

| 폴더 | 내용 | 정리 |
|---|---|---|
| `samples/` | 실제 원고·개발계획서 **입력만** | 사업 종료 시 |
| `_batch/<날짜>_<이름>/` | 배치 체크포인트·xlsx | 비교 기준으로 쓰는 것만 남긴다 |
| `결과/` | DB 없이 돌린 웹·CLI 결과(`<코드>_<시각>_<이름>_xxxx/`) | `python -m ncs_service.postgres_cli import 결과`로 DB 이력에 옮긴 뒤 지워도 된다 |
| `_workspace*/` | 오판정 수정 하네스 산출물. 새 사례마다 `_workspace_<시각>/`로 밀려남 | 사례 종료 후 |
| `.llm_cache/` | LLM 응답 캐시(원고 문장 포함) | 필요 시 |

## 7. 알려진 한계

- hwp: 스타일·자동 번호·쪽 나눔·그림·서식이 없음 → 필요 지식 ⑥, 기타 ①②⑥, 수행 ④, 위치 ⑤ 일부 △.
- 위치 ②의 세분류 목록: '분류보기'에는 학습모듈 미개발 세분류가 없어 개발계획서를 우선.
- 차례 ⑦(쪽수)은 PDF 입력 필요. 평가 ⑤ 심화·보충은 낱말 탐지(의미 판단은 AI 후보).
- 폴더명이 NFD(자소 분리)인 경우 셸 경로 입력 주의(스크립트는 NFC 정규화). Mac에서는 `git config core.precomposeunicode true`.
