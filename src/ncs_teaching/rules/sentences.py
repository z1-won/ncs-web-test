"""F02 교수·학습 방법 ②·④: 교수 방법 / 학습 방법 내용은 행동동사로 종결하였는가? (~지도한다. ~학습한다.)

판정은 ncs_core.sentences.judge_action_sentence를 쓰되 △를 X로 올린다: '~한다.' O / 그 외 X.
'~이다·있다·없다.'('~할 수 있다.' 등)는 행동동사 종결이 아니므로 X(체크리스트: "행동동사로 종결").
행동동사인지(설명·지도·유도…)까지는 보지 않는다 — 종결 형태만 본다.
"""

from ncs_core import O, TRI, X, visible
from ncs_core.sentences import judge_action_sentence

from .common import PART_LABEL, no_block_row, row

ITEM_NO = {"교수": "②", "학습": "④"}


def check_sentences(blocks: list[dict], part: str) -> list[dict]:
    no, label = ITEM_NO[part], PART_LABEL[part]
    name = f"{no} {label} '~한다.' 종결"
    if not blocks:
        return [no_block_row(no, name)]
    rows = []
    for block in blocks:
        items = block[part]
        checks, notes, bad = {}, {}, []
        if not items:
            checks[name], notes[name] = X, f"'{label}' 항목이 없음"
        else:
            values = []
            for item in items:
                value, why = judge_action_sentence(item["text"])
                if value == TRI:  # '~이다/있다/없다.' — 행동동사 종결이 아님
                    value, why = X, "'~이다/있다/없다.'로 끝남 — 행동동사('~한다.')로 종결"
                values.append(value)
                if value != O:
                    bad.append({"idx": item["idx"], "체크": value, "문장": visible(item["text"]), "사유": why})
            checks[name] = X if X in values else TRI if TRI in values else O
            if bad:
                notes[name] = f"{len(items)}개 중 {len(bad)}개 위반: " + " / ".join(
                    f'p{b["idx"]} "{b["문장"][-25:]}" ({b["사유"]})' for b in bad[:5]) + (" …" if len(bad) > 5 else "")
        rows.append(row(no, block, {"개수": len(items)}, checks, notes, f"{label} 문장을 '~한다.'로 종결", 위반_문단=bad))
    return rows
