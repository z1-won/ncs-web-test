"""F02 수행 내용 ④: 수행 순서 문장은 번호 체계마다 ‘~한다.’로 종결하였는가? — 최소한 네모 번호([1])에서만이라도.

확정 범위(설계 Q5·Q6·Q7, 2026-10-28): 네모 번호(수준 1) 제목 줄만 검사한다. 하위 번호·내용 문단은 보지 않는다.
  O  '(한|된|킨|는)다' + (괄호·따옴표) + '.'          예: ~숙지한다.  ~제공된다.  ~한다).
     '~할 수 있다.' — 수행 목표를 적는 꼴은 '~한다.'로 바꿀 다른 표현이 마땅치 않고, 사람 검수를 통과한
     최종본(SW제품기획 0401·0407)에도 있어 적합으로 본다(결정 2026-11-15).
  X  그 외 — '~이다/~없다/~가 있다.', 마침표 없음, 쉼표 종결, 명사형, 질문형 …
판단불가(△)는 내지 않는다(안내서 A-04는 자동 판정). 구역을 못 찾았거나 hwp라 번호 수준을 추정한 경우만 △.
표 안(수행 tip·스크립트 상자)·메모 문단은 blocks.py에서 이미 제외됐다.
"""

from ncs_core import O, PASS, TRI, X, verdict, visible
from ncs_core.sentences import judge_action_sentence

ITEM_ID = "F02-수행-④"


def judge_sentence(text: str) -> tuple[str, str | None]:
    """공통 판정(ncs_core.sentences)에 '~할 수 있다.'만 적합으로 더한다."""
    return judge_action_sentence(text, allow_can=True)


def check_perform_sentences(blocks: list[dict], *, has_styles: bool = True) -> list[dict]:
    rows = []
    if not blocks:
        return [{
            "item_id": ITEM_ID, "region_path": "section1", "원고": None, "개발계획서": None,
            "체크": {"④ 수행 순서 네모 번호 '~한다.' 종결": TRI}, "판정": verdict({"④ 수행 순서 네모 번호 '~한다.' 종결": TRI}),
            "비고": {"④ 수행 순서 네모 번호 '~한다.' 종결": "본문에서 '수행 내용' 머리를 찾지 못해 판단할 수 없음"}, "수정 제안": None,
        }]
    for block in blocks:
        level1 = [s for s in block["수행순서"] if s.get("level1")]
        checks: dict[str, str] = {}
        notes: dict[str, str] = {}
        violations = []
        if "수행순서" in block["소제목 누락"]:
            checks["④ 수행 순서 네모 번호 '~한다.' 종결"] = X
            notes["④ 수행 순서 네모 번호 '~한다.' 종결"] = "'수행 순서' 소제목을 찾지 못함(필수 작성)"
        elif not level1:
            checks["④ 수행 순서 네모 번호 '~한다.' 종결"] = TRI if not has_styles else X
            notes["④ 수행 순서 네모 번호 '~한다.' 종결"] = (
                "네모 번호([1]) 제목 줄을 찾지 못함" + ("" if has_styles else " — hwp는 스타일 정보가 없어 첫 글자로 추정")
            )
        else:
            values = []
            for s in level1:
                value, why = judge_sentence(s["text"])
                values.append(value)
                if value != O or why:
                    violations.append({"idx": s["idx"], "체크": value, "문장": visible(s["text"]), "사유": why})
            key = "④ 수행 순서 네모 번호 '~한다.' 종결"
            checks[key] = X if X in values else O
            bad = [v for v in violations if v["체크"] != O]
            if bad:
                notes[key] = f"네모 번호 {len(level1)}줄 중 {len(bad)}줄 위반: " + " / ".join(
                    f"p{v['idx']} \"{v['문장'][:30]}\" ({v['사유']})" for v in bad[:5]
                ) + (" …" if len(bad) > 5 else "")
            if not has_styles:
                checks["번호 수준 추정"] = TRI
                notes["번호 수준 추정"] = "hwp: 스타일 정보 없이 첫 글자로 네모 번호를 추정"
        result = verdict(checks)
        rows.append(
            {
                "item_id": ITEM_ID,
                "region_path": f"section1 > {block['block_id']} > 수행 순서",
                "원고": {"네모 번호 줄 수": len(level1), "제목": visible(block["title"]) if block["title"] else None},
                "개발계획서": None,
                "체크": checks,
                "판정": result,
                "비고": notes,
                "위반 문단": [v for v in violations if v["체크"] != O],
                "수정 제안": None if result == PASS else "수행 순서의 네모 번호 문장을 '~한다.'로 종결",
            }
        )
    return rows
