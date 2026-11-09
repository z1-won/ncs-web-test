# scripts

저장소 루트에서 `.venv`를 켠 뒤 `python scripts/<묶음>/<이름>.py`로 실행합니다. 묶음은 `batch/`(배치 검증), `data/`(기준 데이터 생성), `probe/`(연결 점검) 셋입니다. 각 파일 첫머리의 설명에 사용법이 있습니다.

## batch/ — 규칙을 여러 원고에 돌려 보기

| 파일 | 하는 일 |
|---|---|
| `batch_review.py` | 폴더의 원고 전부 × 엔진 10개를 돌려 체크포인트(JSON)로 남기고 xlsx로 모읍니다. 끝난 단위는 다시 돌리지 않으므로, 코드를 고친 뒤 다시 보려면 `--work`를 새 폴더로 줍니다 |
| `batch_compare.py` | 배치 결과를 기대 판정 표와 대조해 미탐·오탐 후보를 뽑습니다 |
| `batch_expected_테스트데이터.tsv` | 테스트 원고 묶음의 기대 판정 표(`batch_compare.py`의 입력) |

## data/ — 기준 데이터(`src/ncs_core/data/`) 갱신

| 파일 | 하는 일 | 필요한 것 |
|---|---|---|
| `build_action_nouns.py` | 행동명사 목록(차례 ②)을 미리 채웁니다 | `STDICT_API_KEY` |
| `action_noun_candidates.txt` | 위 스크립트에 `--from-file`로 주는 후보 단어 목록 | — |
| `build_ncs_catalog.py` | NCS 포털 '학습모듈 분류보기' 파일로 분류·능력단위 목록(`ncs_units.tsv`)을 만듭니다 | 내려받은 .xls |
| `build_ncs_levels.py` | 능력단위 수준 표(`ncs_levels.tsv`)를 만듭니다 | CSV 또는 `NCS_API_KEY` |

## probe/ — 외부 API가 동작하는지 확인

| 파일 | 하는 일 |
|---|---|
| `llm_probe.py` | LLM 키·모델·캐시를 합성 문장으로 점검하고 토큰 사용량을 봅니다(실제 원고는 보내지 않음) |
| `ncs_api_probe.py` | 공공데이터포털 NCS API의 호출 경로와 응답 모양을 알아봅니다 |

실제 원고·개발계획서(입력)는 `samples/`, 배치 체크포인트·xlsx(출력)는 `_workspace/batch/<날짜>_<이름>/`에 둡니다. 둘 다 git 제외입니다.
