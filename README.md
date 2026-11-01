# F02 검수 웹앱·Python 패키지

HWP/HWPX 원고와 개발계획서를 읽어 위치·차례·개요·필요 지식을 검수합니다.
검수 엔진은 Python 3.10 이상과 표준 라이브러리만 사용합니다. 고정된 웹 의존성은 Python 3.11 이상이 필요하며 Python 3.14.5에서 검증했습니다. 웹 백엔드는 FastAPI·Uvicorn, 화면은 React·Vite 기반입니다.
개발·수정 기준은 `src/`의 Python 소스입니다. 웹 서버와 CLI는 `ncs_service`를 통해 같은 검수·저장 경로를 사용합니다.

## 폴더 구조

- `src/ncs_core/`: 공통 문서 읽기·입력 검증·규칙 실행·결과 저장
- `src/ncs_core/manuscript/`: 차례·개요·본문·개발계획서 구조 파서와 명칭 비교 도우미. 네 검수 패키지가 공유합니다.
- `src/ncs_position/`, `src/ncs_toc/`, `src/ncs_overview/`, `src/ncs_knowledge/`: 검수 패키지. 서로를 import하지 않고 `ncs_core` 위에 평행하게 섭니다(`tests/test_layering.py`가 검사).
- `src/ncs_service/`: HTTP와 독립적인 검수 실행·저장 조정
- `src/ncs_web/`: 설치형 FastAPI 서버와 웹 실행 명령
- `pyproject.toml`: Python 패키지·선택 의존성·실행 명령 정의
- `webapp/`: 호환 실행 파일과 React 화면. [실행 안내](webapp/README.md)
- `webapp/frontend/dist/`: 웹 화면 빌드 결과
- `tests/`: 합성 입력 생성, 기존 구현 비교, 서비스·웹 API 검증, 패키지 계층(`test_layering.py`)과 엔진 계약(`test_engines.py`) 검사
- `tests/golden/`: 네 엔진 × 합성 원고의 기준 검수 결과(JSON). 리팩토링 전후 동일성 비교의 정답지
- `docs/CONVENTIONS.md`: 공통 개발 규약
- `docs/CONSISTENCY_REVIEW.md`: 통합 리팩토링 기록

## 웹 실행

저장소 루트에서 API 서버를 실행합니다.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[web]"
.venv/bin/ncs-web --out webapp/결과
```

별도 터미널에서 화면을 실행합니다.

```bash
cd webapp/frontend
npm install
npm run dev
```

화면은 기본 `http://localhost:5173`, API는 `http://127.0.0.1:8765`입니다.
프런트엔드 폴더에서 `npm run build`를 실행한 뒤, 서버에 `--dist webapp/frontend/dist`를 지정하면 빌드된 화면도 제공합니다(저장소 루트에서 실행).
API 문서는 `http://127.0.0.1:8765/docs`에서 확인합니다.
위 명령은 검수 결과 JSON·ZIP을 기존 `webapp/결과/`에 저장합니다. `--out` 생략 시 실행 위치의 `결과/`를 사용하며, `--dist` 생략 시 API만 제공합니다. 두 경로는 서버 코드 위치와 독립적입니다.

## CLI 실행

엔진만 필요하면 `python -m pip install -e .`로 설치합니다(웹 의존성 제외).
설치 후에는 `PYTHONPATH` 없이 어느 폴더에서든 가상환경의 명령을 실행할 수 있습니다.
다음은 저장소 루트에서 실행하는 예시이며, 입력 파일 경로는 실제 위치로 바꿉니다.

```bash
.venv/bin/ncs-toc 원고.hwpx 개발계획서.hwpx --out 결과
.venv/bin/ncs-position 원고.hwpx 개발계획서.hwpx --out 결과
.venv/bin/ncs-overview 원고.hwpx 개발계획서.hwpx --out 결과
.venv/bin/ncs-knowledge 원고.hwpx 개발계획서.hwpx --out 결과
```

기존 `python -m ncs_toc` 등 모듈 실행도 설치 후 사용할 수 있습니다.
`-e`는 수정한 Python 소스를 다음 실행에 반영하는 개발용 설치이며, 실행 중인 서버는 재시작해야 합니다.
`--src`는 제거했습니다. 다른 소스를 사용할 때는 해당 가상환경에서 `pip install -e /프로젝트/경로`로 등록합니다.
배포용 복사 설치는 `pip install ".[web]"` 또는 wheel 설치를 사용합니다.
프런트엔드 빌드 파일은 Python 배포본에 포함하지 않으며 `--dist`로 별도 지정합니다.

## 검수 범위

| 검수 | 구현 항목 | 개발계획서 |
|---|---|---|
| 위치 | ①~⑤ | 필수 |
| 차례 | ①~⑥ (②는 행동명사 목록 기반, 목록에 없는 단어는 판단불가) | 선택 |
| 개요 | ①·②·⑤·⑥·⑧ | 선택 |
| 필요 지식 | ①~⑧ | ⑤ 대조에 필요 |

종합 판정은 실행된 규칙의 결과입니다. 미구현 항목은 확인서의 미검사 및 진단 정보로 확인합니다.
HWP는 글꼴·음영을 읽지 않아 위치 ⑤가 판단불가입니다.
차례·필요지식의 기본 양식은 section0=차례·개요, section1=본문이며 Python API와 CLI 설정으로 조정할 수 있습니다.

## 행동명사 목록 갱신 (차례 ②)

차례 ②는 `src/ncs_core/data/action_nouns.txt`의 단어로 판정하며 목록에 없는 단어는 판단불가(△)로 두고 비고에 단어를 적습니다. 목록은 국립국어원 표준국어대사전 API로 확인해 키웁니다(`.env`에 `STDICT_API_KEY`).

```bash
set -a; source .env; set +a
.venv/bin/python scripts/build_action_nouns.py --from-file scripts/action_noun_candidates.txt   # 후보 일괄
.venv/bin/python scripts/build_action_nouns.py --from-results webapp/결과                        # 검수에서 △로 나온 단어
.venv/bin/python scripts/build_action_nouns.py 구성 산출                                          # 단어 직접
```

API가 확인한 단어만 목록에 들어갑니다(출처 `stdict`, 근거에 target_code). "사전에 근거 없음"으로 나온 외래어·전문용어는 사람이 판단해 행동명사면 `action_nouns.txt`에 출처 `manual`과 근거를 적어 추가하고, 아니면 그대로 둡니다(검수에서 △로 남아 사람이 봅니다). ②는 O와 △만 내고 X는 내지 않습니다. 갱신 후 골든이 바뀌면 `tests/make_golden.py`로 재생성하고 함께 커밋합니다.

## 변경 검증

실행 조정 계층·CLI·웹 API 검증:

```bash
.venv/bin/python -m pip install -e ".[test]"
.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
```

수정 전후 검수 결과가 같은지는 골든 테스트가 확인합니다. `tests/golden/`에 네 엔진 × 합성 원고 6종 × 개발계획서 유/무 = 42건의 체크리스트·지적사항·확인서·진단 JSON이 저장되어 있고, `tests/test_golden.py`가 현재 결과와 비교합니다(위 `unittest discover`에 포함).

판정 정책을 **의도적으로** 바꿨을 때만 정답지를 다시 만듭니다. 생기는 diff가 바뀐 내용의 기록이므로 `docs/CONSISTENCY_REVIEW.md`의 '의도적으로 바꾼 동작' 표와 함께 커밋합니다.

```bash
.venv/bin/python tests/make_fixtures.py tests/fixtures   # 합성 원고를 바꿨을 때
.venv/bin/python tests/make_golden.py                    # 정책을 바꿨을 때
```

## 평가 ① 학습 내용명 일치

웹 검수 종류에서 **평가 ① 학습 내용명 일치**를 선택하거나 다음 명령으로 실행합니다.

```bash
.venv/bin/ncs-evaluation 원고.hwpx 개발계획서.hwpx --out 결과
```

개발계획서를 기준으로 차례·개요·필요 지식·평가 준거·평가 방법의 학습 내용명을 검사합니다.
번호가 있으면 학습/내용 번호로 연결하고, 평가표의 번호 없는 이름은 해당 학습 구간 안에서 정확한 명칭 목록으로 비교합니다.
연속 공백·줄바꿈은 축약하지만 단어 사이 공백, 어휘, 문장부호는 바꾸지 않습니다. 유사도나 AI 판정은 사용하지 않습니다.
평가 ②~⑤는 미검사입니다. 계획서가 없으면 차례로 대체하지 않고 판단불가로 표시합니다.

초기 지원 범위는 차례·개요 섹션과 본문 섹션, 반복 내비게이터로 구분된 학습,
평가 영역의 `학습 내용` + `학습 목표`(준거) 또는 `평가 항목`(방법) 머리글을 가진 표입니다.
같은 학습에서 완전한 명칭 목록을 가진 평가표가 여러 개이면 각각 검사합니다. 동일 명칭의 반복과 번호 유무 혼용도 기준 번호에 유일하게 연결되면 검사합니다. 일부 목록만 있는 분할 표, 기준 번호 연결이 모호한 명칭, 분리된 본문 제목, 인식 불가 표는 판단불가로 남깁니다.
HWP는 표 내부 문단을 구별하지 못하므로 본문 명칭의 완전한 적합 판정에는 HWPX가 필요합니다.
섹션 위치는 `--front-section`, `--body-section`으로 지정합니다. 두 섹션 밖에 내용이 있으면 전체 검사 범위 확인이 필요합니다.
실제 원고 양식에 대한 정확도는 추가 검증이 필요하며, 현재 자동 검증은 합성 원고와 오류 변형 사례를 대상으로 합니다.
