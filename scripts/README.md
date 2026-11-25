# scripts

저장소 루트에서 `.venv`를 켠 뒤 `python scripts/<묶음>/<이름>.py`로 실행합니다. 묶음은 `batch/`(배치 검증), `data/`(기준 데이터 생성), `probe/`(연결 점검) 셋입니다. 각 파일 첫머리의 설명에 사용법이 있습니다.

## batch/ — 규칙을 여러 원고에 돌려 보기

| 파일 | 하는 일 |
|---|---|
| `batch_review.py` | 폴더의 원고 전부 × 엔진 10개를 돌려 체크포인트(JSON)로 남기고 xlsx로 모읍니다. 끝난 단위는 다시 돌리지 않으므로, 코드를 고친 뒤 다시 보려면 `--work`를 새 폴더로 줍니다 |
| `batch_compare.py` | 배치 결과를 기대 판정 표와 대조해 미탐·오탐 후보를 뽑고, 구성요소별 오차율과 미탐율(REQ-02-002 검증 기준과 견줄 값)을 냅니다. 조작하지 않은 항목까지 세려면 `--baseline`으로 원본을 지정합니다 |
| `batch_expected_테스트데이터.tsv` | 테스트 원고 묶음의 기대 판정 표(`batch_compare.py`의 입력) |

## data/ — 기준 데이터(`src/ncs_core/data/`) 갱신

| 파일 | 하는 일 | 필요한 것 |
|---|---|---|
| `build_action_nouns.py` | 행동명사 목록(차례 ②)을 미리 채웁니다 | `STDICT_API_KEY` |
| `action_noun_candidates.txt` | 위 스크립트에 `--from-file`로 주는 후보 단어 목록 | — |
| `build_ncs_catalog.py` | NCS 포털 '학습모듈 분류보기' 파일로 분류·능력단위 목록(`ncs_units.tsv`)을 만듭니다 | 내려받은 .xls |
| `fetch_all_ncs.py` | 요소·수행준거를 세분류 전체에 대해 미리 받아 기준정보 폴더(`기준정보/ncs_elements.tsv`)에 둡니다. 이미 있는 세분류는 건너뛰고 하루 한도에서 멈추므로 며칠에 나눠 다시 돌립니다(전체 약 27,000번 호출, 하루 한도 10,000번). `--only 20 1203`으로 분야를 골라 먼저, `--dry-run`으로 남은 양만 | `NCS_API_KEY` |
| `build_ncs_levels.py` | 능력단위 수준 표(`ncs_levels.tsv`)를 만듭니다 | CSV 또는 `NCS_API_KEY` |

## probe/ — 외부 API가 동작하는지 확인

| 파일 | 하는 일 |
|---|---|
| `llm_probe.py` | LLM 키·모델·캐시를 합성 문장으로 점검하고 토큰 사용량을 봅니다(실제 원고는 보내지 않음) |
| `embed_probe.py` | 그림 임베딩 모델이 이 컴퓨터에서 올라오는지, 한국어 문장과 그림이 맞게 짝지어지는지 봅니다(외부 전송 없음) |
| `ncs_api_probe.py` | 공공데이터포털 NCS API의 호출 경로와 응답 모양을 알아봅니다 |
| `diagram_probe.py` | 도표·표·그래프 생성을 실제 생성형 AI로 돌려 후보와 검사 결과를 찍습니다. `--report`로 사람이 채울 판정표를 쓰고 `--tally`로 셉니다(문단이 외부로 전송됨) |
| `manuscript_paragraphs.py` | 원고(hwp·hwpx)에서 `diagram_probe.py`에 넣을 문단을 뽑습니다(외부 전송 없음, 결과는 `_workspace*/`에) |
| `imagegen_probe.py` | 사진·삽화 생성 엔진(서버에 올리는 공개 모델)이 이 컴퓨터에서 도는지, 한 장에 얼마나 걸리는지 봅니다(외부 전송 없음, 모델 내려받기만) |
| `similar_recall.py` | 닮은 그림 대조의 Recall@k를 잽니다: DB의 그림을 조금 바꿔 넣었을 때 원래 그림이 상위 k에 나오는가(외부 전송 없음) |

## measure/ — 요구사항정의서 검증 기준(P열) 실측

| 파일 | 하는 일 |
|---|---|
| `measure_req.py` | REQ-02-001(초안과 최종결과 T03 대조, 일부러 틀리게 한 계획서의 탐지)과 REQ-02-008(출처 줄 추출, AI 표기 판정)을 잽니다. `samples/`의 표본이 필요하고 결과는 `docs/measure/`에 둡니다. 합성 입력의 정답은 스크립트가 정한 것입니다 |

## demo/ — 시연 준비

| 파일 | 하는 일 |
|---|---|
| `seed_demo.py` | 시연 계정과 세분류 건 하나를 만듭니다(`DATABASE_URL` 필요, `docs/WEB.md`의 세분류 건) |

실제 원고·개발계획서(입력)는 `samples/`, 배치 체크포인트·xlsx(출력)는 `_batch/<날짜>_<이름>/`에 둡니다. 둘 다 git 제외입니다.
