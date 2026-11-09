---
name: f02-verdict-verify
description: "F02 검수 엔진 변경이 의도한 판정만 바꿨는지 검증하는 절차. 기준선 대비 테스트, 골든 diff 판독, 수정 전·후 코드로 같은 원고 묶음을 돌린 판정 변화 표(PR 템플릿 '판정 변화' 표), 기대 표 대조, 규칙 출력과 확인서·메모 원고의 경계면 확인을 다룬다. '판정 변화 표 만들어줘', '이 변경 검증해줘', '골든 diff 봐줘', '회귀 없는지 확인', 'PR 올리기 전에 확인', '배치 다시 돌려서 비교'처럼 src/ncs_core·src/ncs_* 변경의 판정 영향을 확인하는 요청이면 반드시 이 스킬을 사용할 것. 코드를 직접 고친 뒤 검증만 원할 때도 쓴다. 화면(frontend) 변경 확인에는 쓰지 않는다."
---

# F02 판정 검증

"테스트가 통과했다"와 "의도한 판정만 바뀌었다"는 다른 주장이다. 골든은 합성 원고 6종뿐이라 실제 원고의 양식 변형을 대부분 모른다.
그래서 검증은 네 겹으로 한다: 테스트 → 골든 diff → 실제 원고 묶음의 수정 전·후 대조 → 경계면 확인.

환경: `.venv`를 켜고 **`.env`는 올리지 않는다.** 사전 키가 있으면 검수 중에 git 관리 파일(`src/ncs_core/data/action_nouns*.txt`)이 바뀌고, LLM 반출 스위치가 있으면 원고 문장이 외부로 나간다. 무엇보다 수정 전·후를 같은 조건에서 돌려야 차이가 코드 때문이라고 말할 수 있다.

## 1. 테스트 — 기준선과 비교한다

```bash
source .venv/bin/activate
pip install -e . -q && python -m unittest discover tests 2>&1 | tail -40
```

`_workspace/00_input/baseline_tests.txt`(수정 전 결과)와 실패 목록을 비교한다. 기준선이 없으면 §3에서 만드는 수정 전 작업 트리(`_workspace/base`)에서 같은 명령을 돌려 만든다.

- 새 실패 0건이어야 한다. 수정 전부터 실패하던 것은 반려 사유가 아니고 보고서에 '기존 실패'로 적는다.
- `test_layering`(엔진끼리 import), `test_engines`(엔진 계약)가 새로 깨졌으면 구조 위반이다. 판정 검증보다 먼저 반려한다.
- 구현자가 추가했다고 한 테스트가 실제로 있고 돌았는지 이름으로 확인한다.

## 2. 골든 diff — 읽는다

```bash
git diff --stat -- tests/golden
git diff -- tests/golden | grep -E '^[+-]\s+"(판정|검수결과)"' | sort | uniq -c     # 판정 줄만
```

| 관찰 | 판단 |
|---|---|
| diff 없음 | 합성 원고에서는 변화 없음. 사양이 '골든 영향 있음'을 예고했다면 수정이 안 먹은 것일 수 있다 |
| 판정·검수결과 줄이 바뀜 | 바뀐 사례 이름(`<엔진>_원고_<종류>_…_plan/noplan`)과 방향을 사양의 예고와 맞춘다. 예고에 없으면 반려 |
| 비고 문구만 바뀜 | 판정 변화 0. 다만 문구 꼴이 바뀌었으면 §5의 메모 원고 경계면을 본다 |
| 수정한 엔진이 아닌 엔진의 골든이 바뀜 | 코어 변경이 번진 것. 사양의 '영향받는 다른 엔진'에 있었는지 확인 |

사양이 예고하지 않았는데 골든이 재생성돼 있으면, 구현자가 회귀를 스냅샷으로 덮었을 가능성부터 의심한다.

## 3. 실제 원고 묶음 — 수정 전·후를 나란히 돌린다

원고 폴더(`--root`)는 저장소 밖이나 `samples/` 아래에 있다. 오케스트레이터가 알려 준 경로를 쓰고, 없으면 사례 원고가 든 폴더(예: `samples/aiot`)라도 쓴다. 그것도 없으면 이 절은 '미검증'으로 적고 넘어간다.

수정 전 코드는 작업 트리를 건드리지 않고 별도 작업 트리로 꺼낸다. `git stash`는 쓰지 않는다 — 구현자의 변경을 잃을 수 있다.

```bash
BASE=$(git rev-parse HEAD)                      # 변경이 아직 커밋 전일 때. 브랜치에 커밋돼 있으면 git merge-base HEAD main
git worktree add --detach _workspace/base "$BASE"

python _workspace/base/scripts/batch/batch_review.py run --root "<원고폴더>" --work _workspace/batch_before --budget 600
python scripts/batch/batch_review.py              run --root "<원고폴더>" --work _workspace/batch_after  --budget 600
```

`batch_review.py`는 자기 옆의 `src/`를 먼저 import하므로, 어느 작업 트리의 스크립트를 부르느냐가 어느 코드로 검수하느냐를 정한다. 끝에 '모든 단위 완료'가 나올 때까지 같은 명령을 반복한다(예산이 다 되면 이어서 한다). 테스트 원고 묶음처럼 파일명에 모듈 코드가 없으면 양쪽에 같은 `--module-code`·`--plan`을 준다. `--plan`을 줄 때는 `--root`와 `--plan`을 **둘 다 절대 경로**로 준다(상대 `--root`에 절대 `--plan`을 섞으면 ValueError).

원고 묶음이 둘 이상이면(사례 묶음 + 회귀 확인용 묶음) 작업 폴더 이름 뒤에 꼬리를 붙여 나눈다(`batch_before_aiot`, `batch_before_yh` …).

이미 끝난 단위는 건너뛰므로, 재검증할 때는 `_workspace/batch_after`를 지우고 다시 돌린다. `batch_before`는 기준 커밋이 같으면 다시 쓴다.

판정 변화 표:

```bash
python .claude/skills/f02-verdict-verify/scripts/verdict_diff.py \
    --before _workspace/batch_before --after _workspace/batch_after --remarks --out _workspace/03_qa_diff_internal.md
python .claude/skills/f02-verdict-verify/scripts/verdict_diff.py \
    --before _workspace/batch_before --after _workspace/batch_after --out _workspace/03_qa_verdict_changes.md
```

`--remarks`는 수정 후 비고를 함께 적는다. 비고에는 원고 문구가 있으므로 내부 확인용이고, PR에 붙일 표는 `--remarks` 없이 만든 두 번째 파일이다.

### 체크 행까지 대조한다

배치 결과에는 확인서 항목의 판정과 비고만 있고 체크리스트 행이 없다. 확인서 한 항목은 여러 행·여러 체크를 접은 것이라, 부적합 3건이 1건으로 줄거나 다른 체크가 O→X로 바뀌어도 항목 판정이 그대로면 위 표에는 나오지 않는다. 사양의 '기대 판정 변화'는 대개 체크 단위로 적혀 있으므로, **사례 원고는 엔진 CLI로 수정 전·후를 따로 돌려 행을 대조한다.**

```bash
for c in position toc overview knowledge perform teaching evaluation references colophon misc; do
  PYTHONPATH=_workspace/base/src python -m ncs_$c "<원고>" "<개발계획서>" --out _workspace/rows_before/$c   # 수정 전
  python -m ncs_$c "<원고>" "<개발계획서>" --out _workspace/rows_after/$c                                     # 수정 후
done
python .claude/skills/f02-verdict-verify/scripts/rows_diff.py --before _workspace/rows_before --after _workspace/rows_after --remarks
```

`PYTHONPATH`로 수정 전 `src/`를 앞에 두면 설치된 패키지 대신 그 코드가 실행된다. 처음 한 번 `python -c "import ncs_core; print(ncs_core.__file__)"`를 같은 방식으로 찍어 정말 `_workspace/base/src`인지 확인한다. 개발계획서가 필요 없는 엔진은 원고만 줘도 된다(`position`만 필수).

끝나면 `git worktree remove _workspace/base`로 정리한다.

### 사양과 대조한다

사양의 '기대 판정 변화' 표와 실제 변화 표를 한 줄씩 맞춘다.

| 실제 변화가 | 판단 |
|---|---|
| 사양에 있고 방향도 같다 | 예고된 변화 |
| 사양에 있는데 일어나지 않았다 | 수정이 그 원고에서 안 먹음 → 반려 |
| 사양에 없다 | 예고되지 않은 변화. 내부용 표의 비고를 읽고 원인을 설명할 수 있어야 한다. 같은 변형을 가진 다른 원고라서 생긴 변화면 '같은 원인'으로 적고 통과, 설명이 안 되면 반려 |

예고되지 않은 변화는 **원고로 확인한다.** 비고가 말하는 것(차례에 그 줄이 있다, 본문에 그 영역이 없다)이 원고 사실인지 `python .claude/skills/f02-case-triage/scripts/para_xml.py "<원고.hwpx>" "<문구>"`로 해당 문단의 원본 XML을 보고, 없다는 주장은 본문 전체에서 그 글자를 세어 확인한다. 보이는 글자인지(변경 추적의 삽입 구간인지 삭제 구간인지)도 여기서 갈린다. 원고 사실과 맞으면 사양의 예고가 빠진 것이므로 '같은 원인'으로 적고, 보고서에 사양의 어느 분석이 틀렸는지 남긴다.

방향별로 무게가 다르다. **적합→부적합**(새 오탐 위험)과 **부적합→적합**(새 미탐 위험)은 한 건씩 비고를 읽는다. 판단불가로 가거나 판단불가에서 나오는 변화는 근거가 생겼는지 사라졌는지를 본다. 실행 오류가 새로 생겼으면 판정 변화와 별개로 반려한다.

같은 원고의 hwp·hwpx 짝이 다르게 움직였으면 읽기 층의 차이다. 의도된 차이(hwp에는 서식·자동 번호가 없음)인지 확인한다.

### 기대 표가 있는 묶음이면

드라이브 테스트 원고 묶음(폴더 = 망가뜨린 항목)처럼 기대 표가 있으면 수정 후 결과를 대조한다.

```bash
python scripts/batch/batch_compare.py --work _workspace/batch_after --expected scripts/batch/batch_expected_테스트데이터.tsv \
    --baseline "<원본 문서ID 또는 글로브>" --engines <담당 엔진…> --out _workspace/03_qa_compare.md
```

미탐·오탐 후보 건수를 수정 전(`--work _workspace/batch_before`로 한 번 더)과 비교한다. 사례가 미탐이었다면 그 줄이 '일치'로 바뀌었는지, 다른 줄이 새로 미탐·오탐이 되지 않았는지 본다.

## 4. 변경 요약과 diff를 대조한다

`git diff --stat`과 `_workspace/02_dev_changes.md`의 '바꾼 파일'을 맞춘다. 요약에 없는 파일이 바뀌었으면 '설명 없는 변경'이다. 그리고 다음을 본다.

- `samples/`·원고 문구가 테스트나 문서에 들어가지 않았는가(`git diff`에서 사양에 인용된 원고 문구를 검색).
- `src/ncs_core/data/`가 바뀌었다면 사양의 분류가 C(기준 데이터)였는가. 아니라면 검수 중 사전 조회가 파일을 고친 부작용이다.
- 정책·동작 변경인데 `docs/CONSISTENCY_REVIEW.md`에 절이 없는가.

## 5. 경계면 — 양쪽을 함께 연다

규칙이 내는 행을 읽는 쪽이 셋 있다. 규칙만 보면 다 맞아 보여도 읽는 쪽에서 빠질 수 있으므로, 바뀐 규칙 파일과 아래 파일을 같이 열어 비교한다.

| 규칙이 내는 것 | 읽는 쪽 | 어긋나면 |
|---|---|---|
| `item_id`, 체크 이름의 접두(①②…) | `src/ncs_<엔진>/sheet.py`의 `SheetItem(item_ids, check_prefix)` | 행은 있는데 확인서 항목에 안 잡혀 '미검사'나 엉뚱한 번호로 간다 |
| `비고`(체크 이름 → 문장, 사례는 줄바꿈) | `src/ncs_core/sheet.py`가 줄 단위로 쌓고 자름 | 사례가 한 줄로 뭉치거나 머리 줄이 사례로 세어짐 |
| 비고의 `원고 「…」`, `region_path`, `위치` | `src/ncs_service/annotate.py`가 메모 달 문단을 찾음 | 메모가 문단을 못 찾아 총괄 메모로 밀린다 |

확인 방법은 돌려 보는 것이다. 수정 후 배치 결과(`_workspace/batch_after/<문서>/<엔진>.json`의 `sheet`)에서 바뀐 항목의 `검수결과`와 `비고`가 체크리스트 행의 판정과 맞는지 본다. 비고 꼴을 바꾼 변경이면 `tests/service/test_annotate.py`·`tests/core/test_sheet.py`가 그 꼴을 다루는지 확인하고, 다루지 않으면 '미검증 경계면'으로 보고한다.

메모 원고는 비고만 봐서는 알 수 없다. 원고 문구가 바뀌면 메모가 다른 문단에 붙을 수 있으므로, 사례 원고가 hwpx이면 `ncs_service.annotate`의 `Annotator`를 수정 전 행(`rows_before`)과 수정 후 행(`rows_after`)으로 각각 돌려 **붙은 문단과 못 붙인 행**을 비교한다(호출 방법은 `tests/service/test_annotate.py` 참고). 메모가 옮겨 붙었으면 이번 변경이 만든 것인지, 기존 약점이 드러난 것인지 갈라 적는다.

파서가 새 키를 내거나 값의 꼴을 바꿨으면(숫자였던 값이 None이 되는 등) 그 값을 읽는 곳을 `grep -rn "키 이름" src --include='*.py'`로 모두 찾아 한 곳씩 연다.

참고: 테스트 모듈 하나만 고를 때는 `tests/` 안에서 묶음 이름을 붙여 돌린다(`cd tests && python -m unittest core.test_manuscript`). 묶음은 core·engines·service·contract·integration이다.

## 6. 검증 보고서

`_workspace/03_qa_report.md`:

```markdown
# 검증 보고서 — 합격 | 반려 | 합격(배치 미검증)
기준 커밋 <sha>, 원고 묶음 <root 경로와 문서 수>

## 요약
- 테스트: 전체 N, 새 실패 K (기존 실패 M)
- 골든: 변화 없음 | 바뀐 사례 N건(판정 n, 문구만 m)
- 판정 변화: 총 N건 = 예고됨 a + 같은 원인 b + 설명 안 됨 c
- 예고됐는데 일어나지 않은 변화: N건
- 경계면: 확인서 ✓ / 메모 원고 ✓ | 미검증(사유)

## 반려 사유            ← 반려일 때만. 구현자가 바로 고칠 수 있게
1. `파일:줄` — 무엇이 어떻게 틀렸고, 무엇을 기대하는가

## 사양 대조
| 원고 | 체크 항목 | 사양(이전→이후) | 실제 | 판단 |

## 예고되지 않은 변화
| 원고 | 체크 항목 | 이전 | 이후 | 원인 |

## 미검증
(돌리지 못한 검증과 이유)
```

합격 기준: 새 테스트 실패 0, 예고된 변화가 모두 일어남, 설명 안 되는 변화 0, 새 실행 오류 0, 설명 없는 변경 0.
배치를 돌리지 못했으면 나머지가 다 맞아도 `합격(배치 미검증)`으로 구분한다 — 실제 원고에서 확인하지 않았다는 사실이 사용자에게 전달돼야 한다.
