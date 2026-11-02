# F02 검수 웹앱·Python 패키지

- NCS 학습모듈 원고(HWP/HWPX)와 개발계획서를 읽어 「2026년 NCS학습모듈 검수 확인서(F02)」 검수
- 10개 구성요소 중 47/54 체크항목 검수 완료 (약 87%)


 - 검수 엔진: Python 3.10 이상과 표준 라이브러리만 사용
 - 웹:
 FastAPI·Uvicorn(Python 3.11 이상, 3.14에서 검증)
 React·Vite·KRDS
 웹 서버·CLI·배치는 모두 `ncs_service`를 거쳐 같은 검수·저장 경로를 탑니다.

자세한 흐름과 파일별 로직은 프로젝트 문서 `PoC2_설계_아키텍처_소개및분석_v1-3`, 항목별 구현 현황은 `PoC2_현황_F02_체크항목_구현여부_v1-1`, 개발 규칙은 `PoC2_운영_개발규칙_3인분업_v1-0`을 봅니다.

### `src/` 패키지별 역할

호출 흐름은 `webapp(React) → ncs_web → ncs_service → 엔진 10개 → ncs_core`입니다.

| 패키지 | 역할 | F02 항목 |
|---|---|---|
| `ncs_core` | 공통 코어: hwp/hwpx 읽기, 구역 정규화, 원고·개발계획서 파서(`manuscript/`), 비교 도우미(`goals`), NCS 목록·수준 표(`ncs_catalog`), 행동명사 사전(`lexicon`), 규칙 실행(`rules`), 확인서 접기(`sheet`), LLM 호출(`llm`) | — |
| `ncs_service` | 검수 종류↔엔진 연결(`registry`), 실행(`service`), 저장(파일·PostgreSQL), F02 확인서 xlsx/hwpx 내보내기(`export`), 수정 메모 원고(`annotate`) | — |
| `ncs_web` | FastAPI 서버: 업로드·검수·이력·내보내기 API, 빌드된 화면 제공 | — |
| `ncs_position` | 위치: 분류 대조, NCS 목록 기준 위치, 강조 서식 | 위치 ①~⑤ (전부 구현) |
| `ncs_toc` | 차례: 계획서 대조, 행동명사, 본문·내비게이터 일관성, 그림 배치, 참고자료·부록 | 차례 ①~⑥ (⑦ 쪽수 미구현) |
| `ncs_overview` | 개요: 학습 목표, 선수학습 개수·코드·수준, 내용체계 구조, 용어 | 개요 ①~⑧ (전부) |
| `ncs_knowledge` | 필요 지식: 내비게이터 ①②③, 내용체계 대조, 목표, 자동 번호, 그림·표, 출처 | 필요 지식 ①~⑧ (전부) |
| `ncs_perform` | 수행 내용: 제목, 상품명(LLM △), 문장형 | 수행 ①②④ (③ 안전사항 미구현) |
| `ncs_teaching` | 교수·학습 방법: 개수, 문장형 | 교수학습 ①~④ (전부) |
| `ncs_evaluation` | 평가: 학습 내용명, 준거↔목표, 방법 수, 피드백 | 평가 ①②③⑤ (④ 구체성 미구현) |
| `ncs_references` | 참고 자료: 인용 누락, 표기 형식, 정렬 | 참고자료 ①②③ (④ 미구현) |
| `ncs_colophon` | 판권: 개발 이력·개발기관 | 판권 ① |
| `ncs_misc` | 기타: 쪽 시작, 그림, 비율, 참고 표기 | 기타 ①②⑥⑦ (③④⑤⑧ 이미지 분석 미구현) |

엔진은 서로 import하지 않고 `ncs_core` 위에 평행하게 선다. (`tests/test_layering.py`). 모든 엔진은 "구역 0 = 앞부분(위치·차례·개요), 구역 1 = 본문"을 가정하고, 원고의 실제 구역 나눔은 `ncs_core.documents.normalize_sections`가 그 모양으로 맞춥니다.

## 설치와 환경 변수

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[web]"            # 엔진만 쓰면 pip install -e .
pip install -e ".[test]"           # 테스트 의존성
pip install openpyxl               # scripts/batch_review.py xlsx 출력용
```

`.env`(git 제외)에 두는 값. 서버·CLI를 띄우는 셸에서 `set -a; source .env; set +a`로 올립니다.

| 변수 | 용도 |
|---|---|
| `STDICT_API_KEY` | 표준국어대사전 — 차례 ② 행동명사 조회(없으면 목록에 없는 단어는 △) |
| `NCS_API_KEY` | 공공데이터포털 B490007/ncsInfo — 수준 표 갱신 스크립트만 사용(검수 서버는 호출하지 않음) |
| `LLM_API_KEY`(또는 `OPENAI_API_KEY`), `LLM_MODEL`(기본 gpt-5.4-mini), `LLM_ALLOW_UPLOAD=1` | 수행 ② LLM 후보. 키와 반출 승인 스위치가 **둘 다** 있어야 원고 문장을 전송. `LLM_ALLOWED_TASKS`로 더 좁힐 수 있음 |
| `NCS_DB_*` / DSN | PostgreSQL 검수 이력(선택). 없으면 파일 저장만 |

키 값은 저장소·문서·채팅에 적지 않습니다.

## 웹 실행

```bash
set -a; source .env; set +a
ncs-web --dist webapp/frontend/dist          # API + 빌드된 화면, http://127.0.0.1:8765
```

화면을 고칠 때는 `cd webapp/frontend && npm install && npm run dev`(개발 서버 5173) 또는 `npm run build` 후 위 명령. `--out 폴더`로 결과 저장 위치를 바꿉니다(기본 `결과/`). API 문서는 `/docs`. 포트가 잡혀 있으면 `lsof -ti :8765 | xargs kill`.

검수 항목 목록의 마지막 **전체**를 고르면 구성요소 10개를 확인서 순서대로 한 번에 검사합니다(개발계획서가 없으면 '위치'만 건너뜀). 결과는 구성요소별 아코디언으로 열어 보고, 이력에는 한 묶음이 한 줄로 남습니다.

| API | 쓰는 곳 |
|---|---|
| `POST /api/review` (`files[]`, `check`, `module_code`) | 검수 1건. 응답은 요약·검수확인서·진단·지적사항·전체 |
| `POST /api/uploads` → `{upload, group, roles, expires_in}` / `DELETE /api/uploads/{token}` | 전체 실행: 파일을 한 번 올려 토큰을 받고, `POST /api/review`에 `upload=토큰&group=묶음id`로 엔진마다 부른다. 토큰은 10분 뒤 자동 삭제 |
| `GET /api/reviews[?standalone=true]`, `GET/DELETE /api/reviews/{id}`, `GET /api/reviews/{id}/zip` | 단독 실행 이력(`DATABASE_URL` 설정 시) |
| `GET /api/groups`, `GET/DELETE /api/groups/{group_id}` | 전체 실행 묶음 이력 — 한 묶음의 모든 검수를 한 번에 열고 지운다 |
| `POST /api/export/sheet?format=xlsx\|hwpx` (`{module_code, rows, created_at}`) | **F02 검수 확인서 파일**. hwpx는 원본 양식(`src/ncs_core/data/F02_검수확인서_양식.hwpx`)에 ✓·비고를 채운 제출본, xlsx는 열람·편집용. 실행하지 않은 구성요소는 '미검사'로 54개 항목을 모두 채운다 |
| `POST /api/export/annotated` (`upload` 토큰, `rows` JSON) | **수정 메모 원고**: 원고 hwpx의 해당 문단에 지적사항을 한글 메모로 단 파일(본문 불변). 문단을 못 찾은 지적은 첫 문단의 총괄 메모에 목록으로. hwp 원고는 불가 |

## CLI 실행

```bash
ncs-position 원고.hwpx 개발계획서.hwp --out 결과      # 개발계획서 필수
ncs-toc 원고.hwpx [개발계획서.hwp] --out 결과          # 나머지는 선택(있으면 대조 항목이 확정 판정)
ncs-overview / ncs-knowledge / ncs-perform / ncs-teaching / ncs-evaluation / ncs-references / ncs-colophon / ncs-misc
```

모듈 코드는 파일명(`LM##########_NNvN`)에서 읽고, 없으면 `--module-code`로 지정합니다. `python -m ncs_toc …` 꼴도 같습니다.

## 검수 범위 (47/54)

| 구성요소 | 구현 | 미구현 | 메모 |
|---|---|---|---|
| 위치 | ①~⑤ | — | 기준은 NCS 목록(없는 세분류는 개발계획서). 계획서가 목록과 다르면 △로 알림. ⑤는 hwpx 서식 |
| 차례 | ①~⑥ | ⑦(쪽수, PDF 필요) | ②는 행동명사 목록 + 사전 API |
| 개요 | ①~⑧ | — | ③④는 NCS 목록·수준 표로 선수학습 코드·수준 검사 |
| 필요 지식 | ①~⑧ | — | ⑥ 자동 번호 복원(hwpx), ⑧ F14 출처 골격 |
| 수행 내용 | ①②④ | ③(안전사항 추상성, LLM 예정) | ②는 LLM 후보(항상 △ + 근거) |
| 교수·학습 방법 | ①~④ | — | |
| 평가 | ①②③⑤ | ④(구체성, LLM 예정) | |
| 참고 자료 | ①②③ | ④(이전 판본 자료 필요) | |
| 개발 이력 및 판권 | ① | — | 개발기관은 F14대로 협회만 적어도 적합 |
| 기타 | ①②⑥⑦ | ③④⑤⑧(이미지 분석) | |

판정: 적합 / 부적합 / 판단불가(사람 확인) / 미검사(규칙 없음). 비고는 `{자리} 「원고 문구」 / {기준 문서} 「기준 문구」 — 띄어쓰기만 다름 …` 꼴로 두 문서의 문구를 함께 적습니다.
**hwp(바이너리)** 는 문단·표 텍스트만 읽히고 스타일·자동 번호·쪽 나눔·그림은 없어서 위치 ⑤, 필요 지식 ⑥, 기타 ①②⑥ 등이 △가 됩니다. 가능하면 hwpx로 변환해 넣습니다.

## 외부 데이터 갱신 (`src/ncs_core/data/`, git 관리)

```bash
python scripts/build_ncs_catalog.py 분류보기폴더          # NCS 포털 '학습모듈 분류보기' 내려받기(.xls 24개) → ncs_units.tsv
python scripts/build_ncs_levels.py --from-csv 능력단위목록.csv   # NCS 포털 능력단위 목록 CSV → ncs_levels.tsv (또는 --refresh 세분류코드… 로 API)
set -a; source .env; set +a
python scripts/build_action_nouns.py --from-manuscripts 원고.hwpx …   # 차례 ② 행동명사 — 운용 전에 채워 둔다
```

## 생성형 AI (수행 ②)

`ncs_core.llm`이 OpenAI 호환 API를 표준 라이브러리로 호출합니다. 블록의 재료·기기 줄만 보내고, 결과는 항상 △(사람 확인) + 줄 번호·근거·일반 명칭 제안이며 자동 X는 없습니다. (모델, 프롬프트) 해시로 `.llm_cache/`(git 제외)에 캐시해 재검수는 과금되지 않고, `usage.jsonl`에 토큰이 기록됩니다. LLM을 부를 수 있는 작업은 `ncs_core.llm.ALLOWED_TASKS`에 명시된 것뿐입니다(지금은 수행 ② 하나).

```bash
python scripts/llm_probe.py           # 합성 문장으로 키·모델·캐시 점검(실제 원고 전송 없음)
python scripts/llm_probe.py --usage   # 토큰 합계·비용 추정
```

## 다문서 배치 테스트

```bash
python scripts/batch_review.py scan --root 원고폴더 --work samples/batch_x
python scripts/batch_review.py run  --root 원고폴더 --work samples/batch_x --budget 3600
python scripts/batch_review.py xlsx --root 원고폴더 --work samples/batch_x --out 결과.xlsx
```

폴더의 원고 전부(hwp·hwpx, 초고본/수정본/에디팅완료 자동 분류, 세분류 계획서 자동 매칭) × 10엔진을 문서×엔진 단위로 체크포인트하며 돌리고, xlsx 9시트(문서목록·실행요약·판정매트릭스·항목별집계·상세비고(사람 판정 열)·버전변화·형식비교·실행오류·설정)로 모읍니다. `samples/`는 git 제외입니다.

## 변경 검증

```bash
pip install -e . -q && python -m unittest discover tests      # 단위 + 골든 + 계약
```

골든은 `tests/golden/`의 합성 원고 6종 × 10엔진 × 개발계획서 유/무 결과 스냅샷입니다. 판정 정책을 **의도적으로** 바꿨을 때만 `PYTHONPATH=src python tests/make_golden.py`로 다시 만들고, `git diff tests/golden`에서 판정 변동이 의도한 것인지 확인한 뒤 함께 커밋합니다(문구만 바뀐 경우 메시지에 적습니다). 골든은 NCS 목록을 끄고(개발계획서 기준), 외부 API 키를 비운 채(`tests/test_0_environment.py`) 실행됩니다.