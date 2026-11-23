"""참고 문장 묶음 — 기존 학습모듈·공공저작물(F12 집필 우수사례집 등)에서 규정 꼴을 지킨 문장을 모아 둔 표. 정정 후보의 근거 문장으로 쓴다.

요구사항(REQ-02-004 수행예시 1-3): '근거 있는 문장(기존 학습모듈·공공저작물) 기반 정정 후보'. 후보 자체는 LLM이 원문을 고쳐 쓰고,
이 묶음은 (1) LLM에 표현 참고로 함께 보내고 (2) 검증을 통과한 후보마다 가장 비슷한 문장을 '근거 문장'(출처·자리·유사도)으로 붙이는 데 쓴다.
직무 내용을 가져오는 용도가 아니다 — 후보는 여전히 원문 유사도 하한·새 수치·영문·상호 금지 검증을 통과해야 한다.

파일  <기준정보 폴더>/suggest_refs.tsv (ncs_core.refdata — ncs-web --data 또는 NCS_DATA_DIR, git 제외). NCS_SUGGEST_REFS로 파일을 직접 정할 수 있다.
      열: 종류 \t 문장 \t 출처(문서 이름) \t 자리.  '#'으로 시작하는 줄은 주석. 파일이 없으면 빈 묶음(근거 문장 없이 동작).
만들기 python -m ncs_suggest.corpus 기존원고1.hwpx 기존원고2.hwp … [--out 파일] [--loose] [--replace]
      원고마다 extract.collect로 종류별 문장을 모아 규정 꼴을 지킨 것(kinds.check가 True)만 싣는다. 이미 있는 파일에는 보태고 같은 문장은 한 번만 둔다.
      --loose: 학습모듈 양식이 아닌 문서(F12 우수사례집 등)는 구조를 읽지 못하므로 모든 문단에서 끝말만 보고 싣는다 —
               '~할 수 있다.'는 학습 목표로, '~한다.'는 종류를 알 수 없어 ACTION_COMMON(수행 순서·교수 방법·학습 방법이 함께 씀)으로.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from ncs_core import visible
from ncs_core.documents import load_document
from ncs_core.refdata import overlay_path, replace_file

from .config import DEFAULT_CONFIG, KINDS, SuggestConfig
from .extract import collect, split_prefix, verbs_in
from .kinds import check

REFS_FILE = "suggest_refs.tsv"
ACTION_COMMON = "~한다. 문장"                                   # --loose로 모은, 종류를 모르는 '~한다.' 문장
ACTION_KINDS = ("수행 순서", "교수 방법", "학습 방법", "안전·유의 사항")
LOOSE_LENGTH = (8, 120)                                         # --loose에서 문장으로 보는 글자 수 범위
PREFILTER = 30                                                  # 글자 쌍 겹침으로 먼저 추리는 수(그 뒤에만 difflib)
HEADER = "# 문장 추천(REQ-02-004) 참고 문장 묶음 — python -m ncs_suggest.corpus 로 만든다. 열: 종류\t문장\t출처\t자리\n"


@dataclass(frozen=True)
class Reference:
    kind: str
    text: str
    source: str
    where: str


def _compact(text: str) -> str:
    return re.sub(r"[\s.,·()]", "", text or "")


def _pairs(text: str) -> frozenset[str]:
    compact = _compact(text)
    return frozenset(compact[i:i + 2] for i in range(len(compact) - 1))


class Corpus:
    """종류별 참고 문장. find()가 비슷한 문장을 유사도 순으로 돌려준다."""

    def __init__(self, references: list[Reference] | tuple[Reference, ...] = (), name: str = ""):
        self.name = name
        self.by_kind: dict[str, list[tuple[Reference, frozenset[str]]]] = {}
        seen = set()
        for ref in references:
            key = (ref.kind, _compact(ref.text))
            if key in seen or not key[1]:
                continue
            seen.add(key)
            self.by_kind.setdefault(ref.kind, []).append((ref, _pairs(ref.text)))

    def __len__(self) -> int:
        return sum(len(pool) for pool in self.by_kind.values())

    def counts(self) -> dict[str, int]:
        return {kind: len(pool) for kind, pool in self.by_kind.items()}

    def find(self, kind: str, body: str, *, limit: int, minimum: float) -> list[dict]:
        """같은 종류의 참고 문장 가운데 body와 비슷한 것 → [{'문장','출처','자리','유사도'}] 유사도 순, 최대 limit개(유사도 minimum 이상)."""
        pool = list(self.by_kind.get(kind, []))
        if kind in ACTION_KINDS:
            pool += self.by_kind.get(ACTION_COMMON, [])
        target, target_pairs = _compact(body), _pairs(body)
        if not pool or not target or limit <= 0:
            return []
        rough = sorted(((len(target_pairs & pairs) / (len(target_pairs | pairs) or 1), n) for n, (_, pairs) in enumerate(pool)), reverse=True)
        scored = []
        for _, n in rough[:PREFILTER]:
            ref = pool[n][0]
            if _compact(ref.text) == target:
                ratio = 1.0
            else:
                ratio = SequenceMatcher(None, target, _compact(ref.text), autojunk=False).ratio()
            if ratio >= minimum:
                scored.append((ratio, n, ref))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [{"문장": ref.text, "출처": ref.source, "자리": ref.where, "유사도": round(ratio, 2)} for ratio, _, ref in scored[:limit]]


EMPTY = Corpus()


def refs_path() -> Path | None:
    """참고 문장 파일 경로(없는 파일일 수 있다). NCS_SUGGEST_REFS가 먼저, 없으면 기준정보 폴더. 둘 다 없으면 None."""
    custom = os.getenv("NCS_SUGGEST_REFS")
    return Path(custom).expanduser() if custom else overlay_path(REFS_FILE)


def read(path: Path) -> list[Reference]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        cells = (line.split("\t") + ["", "", ""])[:4]
        kind, text = cells[0].strip(), cells[1].strip()
        if text and (kind in KINDS or kind == ACTION_COMMON):
            out.append(Reference(kind, text, cells[2].strip(), cells[3].strip()))
    return out


_cache: dict[tuple[str, float], Corpus] = {}


def load(path: Path | str | None = None) -> Corpus:
    """참고 문장 묶음을 읽는다(파일이 바뀌면 다시 읽음). 파일이 정해지지 않았거나 없으면 빈 묶음."""
    target = Path(path) if path else refs_path()
    if target is None or not target.is_file():
        return EMPTY
    key = (str(target), target.stat().st_mtime)
    if key not in _cache:
        _cache.clear()
        _cache[key] = Corpus(read(target), name=target.name)
    return _cache[key]


def state(corpus: Corpus) -> str:
    """화면·요약에 적는 상태 문구."""
    if len(corpus):
        return f"참고 문장 {len(corpus)}개({corpus.name or '주입된 묶음'})"
    return f"참고 문장 묶음 없음 — 기존 학습모듈로 만들어 두면 후보에 근거 문장을 붙입니다(python -m ncs_suggest.corpus 원고…, 파일 {REFS_FILE})"


def harvest(path: Path | str, *, loose: bool = False) -> list[Reference]:
    """문서 하나에서 규정 꼴을 지킨 문장을 모은다. 출처는 파일 이름."""
    document = load_document(path)
    source = Path(path).name
    extra = verbs_in(document)
    out = [Reference(s.kind, s.body, source, s.where) for s in collect(document) if check(s.kind, s.body, extra)[0] is True]
    if loose:
        low, high = LOOSE_LENGTH
        for number, section in enumerate(document.sections, 1):
            for line in section:
                body = split_prefix(visible(line or ""))[1]
                if not low <= len(body) <= high:
                    continue
                if check("학습 목표", body)[0] is True:
                    out.append(Reference("학습 목표", body, source, f"구역 {number}"))
                elif check("교수 방법", body)[0] is True:
                    out.append(Reference(ACTION_COMMON, body, source, f"구역 {number}"))
    return out


def _clean(value: str) -> str:
    return re.sub(r"[\t\r\n]+", " ", value or "").strip()


def write(path: Path, references: list[Reference]) -> int:
    """중복을 빼고 종류·출처 순으로 쓴다 → 쓴 문장 수."""
    rows, seen = [], set()
    for ref in references:
        key = (ref.kind, _compact(ref.text))
        if key in seen or not key[1]:
            continue
        seen.add(key)
        rows.append(ref)
    order = {kind: n for n, kind in enumerate([*KINDS, ACTION_COMMON])}
    rows.sort(key=lambda ref: (order.get(ref.kind, 99), ref.source, ref.where))
    replace_file(path, HEADER + "".join(f"{ref.kind}\t{_clean(ref.text)}\t{_clean(ref.source)}\t{_clean(ref.where)}\n" for ref in rows))
    return len(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ncs_suggest.corpus",
                                     description="기존 학습모듈·공공저작물에서 규정 꼴을 지킨 문장을 모아 참고 문장 묶음을 만든다(REQ-02-004).")
    parser.add_argument("documents", nargs="+", type=Path, help="기존 학습모듈 원고·우수사례집(hwp/hwpx)")
    parser.add_argument("--out", type=Path, help=f"쓸 파일(기본: NCS_SUGGEST_REFS 또는 기준정보 폴더의 {REFS_FILE})")
    parser.add_argument("--loose", action="store_true", help="학습모듈 양식이 아닌 문서에서 끝말만 보고 싣는다(F12 우수사례집 등)")
    parser.add_argument("--replace", action="store_true", help="이미 있는 파일에 보태지 않고 새로 쓴다")
    args = parser.parse_args(argv)
    target = args.out or refs_path()
    if target is None:
        print("오류: 쓸 곳이 없습니다. --out 파일을 주거나 NCS_DATA_DIR(기준정보 폴더) 또는 NCS_SUGGEST_REFS를 정하세요.", file=sys.stderr)
        return 1
    references = [] if args.replace or not target.is_file() else read(target)
    before = len(Corpus(references))
    for path in args.documents:
        try:
            found = harvest(path, loose=args.loose)
        except (ValueError, OSError) as error:
            print(f"건너뜀: {path} — {error}", file=sys.stderr)
            continue
        print(f"{Path(path).name}: 규정 꼴을 지킨 문장 {len(found)}개")
        references += found
    total = write(target, references)
    counts = Corpus(read(target)).counts()
    print(f"저장: {target} — {total}개(새로 {total - before}개) · " + ", ".join(f"{kind} {n}" for kind, n in counts.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
