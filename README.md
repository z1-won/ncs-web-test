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
## Computer Vision Assignment

`computer_vision_assignment/` 폴더에 컴퓨터 비전 과제 노트북 두 개가 있습니다. 검수 엔진과는 관계없는 별도 과제입니다.

### 1. `conputervisionass3.ipynb` — 모폴로지 연산으로 글자 이미지의 잡음 제거

**실험 설계**

- **입력**: 잡음이 섞인 글자 이미지 3장(Google Drive에서 불러옴, 저장소에는 없음)을 흑백으로 읽음
  - `nt1`: 검은 바탕에 흰 한글(가~하), 흰 대각선 긁힘과 작은 점 잡음
  - `nt2`: 흰 바탕에 검은 영문 문서, 검은 곡선 낙서 잡음
  - `nt3`: 흰 바탕에 테두리만 있는 한글 손글씨(「은댕이의 달달한 블로그」)
- **이진화**: 세 이미지 모두 임계값 150으로 `cv2.threshold`(THRESH_BINARY)
- **구조 요소(3×3)** 4종: 십자(Cross), 정사각형(Square), 세로선(1×3), 가로선(3×1)
- **연산**: 구조 요소마다
  - 팽창(dilation) → `nt2`
  - 침식(erosion) → `nt1`, `nt3`
  - 열림(opening)·닫힘(closing) → `nt1`, `nt2`
- 결과는 이미지로 출력해 눈으로 비교

**결과**

- **잡음과 글자의 색에 따라 맞는 연산이 다르다.** OpenCV 연산은 흰색(255)을 기준으로 동작하므로,
  - 흰 잡음(`nt1`)은 침식·열림이 지우고, 닫힘은 아무 효과가 없었습니다.
  - 검은 잡음(`nt2`)은 팽창·닫힘이 지우고, 열림은 아무 효과가 없었습니다(오히려 검은 선이 그대로 남음).
- **구조 요소 모양이 글자 손상을 좌우한다.**
  - `nt1` 열림: 십자·정사각형·세로선은 긁힘을 지웠지만 한글의 짧은 가로획까지 지워 「라→리」「타→티」「하→히」처럼 글자가 바뀌었습니다. **가로선(3×1)** 은 긁힘을 지우면서 글자 모양을 가장 잘 지켰습니다(작은 점 몇 개만 남음).
  - `nt2` 팽창·닫힘: 정사각형은 본문 작은 글자를 크게 깨뜨렸고, 가로선은 곡선 잡음이 일부 남았습니다. **세로선(1×3)** 이 낙서를 지우면서 본문 글자를 가장 온전하게 남겼습니다.
- **`nt3`**: 임계값 150 이진화에서 얇은 테두리가 점선처럼 끊겼습니다. 침식(검은 획이 두꺼워짐)을 하면 끊긴 테두리가 다시 이어졌고, 정사각형이 가장 굵고 잘 이어졌으며 십자는 그보다 약했습니다. 세로선·가로선은 각각 그 방향의 끊김만 메웠습니다.
- 한계: 임계값을 150으로 고정해 `nt3`의 테두리가 끊기고 `nt2`의 컬러 이모지가 깨졌습니다. 이미지마다 임계값(또는 Otsu)을 따로 정했으면 이진화 손실이 줄었을 것입니다.

### 2. `Assignment_knn.ipynb` — CIFAR-10 k-NN 분류와 하이퍼파라미터 탐색

**실험 설계**

- **데이터**: CIFAR-10(학습 50,000장, 테스트 10,000장, 10클래스). 32×32×3 이미지를 3,072차원 벡터로 펼쳐 원시 픽셀값 그대로 사용
- **탐색 범위**: k ∈ {1, 3, 5, …, 17}(홀수 9개) × 거리 {유클리드, 맨해튼} = 18조합
- **검증**: 5-fold 교차검증(`KFold(shuffle=True, random_state=42)`), fold 평균으로 비교
  - 실행 시간이 너무 길어 교차검증은 학습 데이터 앞 **10,000장**만 사용
- **평가 지표**: accuracy와 macro precision·recall·F1을 모두 기록해, 지표에 따라 최적 조합이 달라지는지 확인
- **최종 평가**: 최적 조합으로 **학습 50,000장 전체**를 학습하고 테스트 10,000장에서 평가

**결과**

교차검증(10,000장, 5-fold 평균) 주요 결과:

| 거리 | k | accuracy | precision | recall | F1 |
|---|---|---|---|---|---|
| 유클리드 | 1 | 0.2851 | 0.3420 | 0.2835 | 0.2766 |
| 유클리드 | 9 (유클리드 최고) | 0.2876 | 0.3883 | 0.2853 | 0.2635 |
| 맨해튼 | 1 | 0.3080 | 0.3584 | 0.3067 | 0.3051 |
| **맨해튼** | **13 (전체 최고)** | **0.3218** | **0.4075** | **0.3194** | **0.3055** |

- 네 지표 모두 최적 조합이 **k = 13, 맨해튼 거리**로 같았습니다.
- 모든 k에서 **맨해튼이 유클리드보다 2~4%p 높았습니다.** 큰 차이 하나에 덜 민감한 L1 거리가 원시 픽셀 비교에 더 유리했습니다.
- k가 커질수록 precision은 꾸준히 올랐지만(0.34→0.40) recall·accuracy는 거의 그대로였고, 유클리드에서는 F1이 k = 1일 때 가장 높았습니다. k만 키워서는 분류가 크게 나아지지 않았습니다.

테스트 결과(k = 13, 맨해튼, 학습 50,000장 전체):

| accuracy | precision | recall | F1 |
|---|---|---|---|
| 0.3722 | 0.4627 | 0.3722 | 0.3652 |

- 테스트 정확도(37.2%)가 교차검증(32.2%)보다 높은 것은, 교차검증은 10,000장 중 8,000장으로 학습했고 최종 모델은 50,000장 전체로 학습해 이웃 후보가 많았기 때문입니다.
- 무작위 추측(10%)보다는 훨씬 낫지만, 원시 픽셀 거리만으로는 CIFAR-10의 물체를 구분하는 데 한계가 뚜렷합니다.
