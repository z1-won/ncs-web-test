"""행동명사 목록(src/ncs_core/data/action_nouns.txt)을 국립국어원 표준국어대사전 API로 키운다.

검수 실행은 이 스크립트와 무관하다(네트워크를 쓰지 않고 목록 파일만 읽는다). 개발자가 가끔 돌린다.

판정 방법: 단어 W를 search.do로 찾아 명사 항목들의 target_code를 얻고, 각각을 view.do로 열어
파생어·관련어 가운데 'W하다'(또는 'W-하다') 동사가 있으면 행동명사로 본다. 없으면 'W하다'를 직접 검색해
동사 표제어가 있는지 한 번 더 본다. 둘 다 없으면 '미확정'으로 남겨 사람이 결정한다(사전에 없음 ≠ 틀림).

사용 (저장소 루트, .env의 STDICT_API_KEY 필요):
  set -a; source .env; set +a
  python scripts/build_action_nouns.py 분석 설계 구현            # 단어 직접
  python scripts/build_action_nouns.py --from-file 후보.txt      # 한 줄 한 단어
  python scripts/build_action_nouns.py --from-results webapp/결과 # 차례② 결과 JSON에서 △ 단어 수집
  python scripts/build_action_nouns.py --debug 분석              # 첫 단어의 원응답을 scripts/.stdict_debug.json에 저장
응답은 scripts/.stdict_cache.json에 캐시되어 같은 단어를 다시 묻지 않는다.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEXICON = ROOT / "src" / "ncs_core" / "data" / "action_nouns.txt"
CACHE = Path(__file__).resolve().parent / ".stdict_cache.json"
DEBUG = Path(__file__).resolve().parent / ".stdict_debug.json"
SEARCH_URL = "https://stdict.korean.go.kr/api/search.do"
VIEW_URL = "https://stdict.korean.go.kr/api/view.do"
PAUSE = 0.2  # 초. 연속 호출 간격


class Api:
    def __init__(self, key: str, cache_path: Path, debug: bool = False):
        self.key, self.cache_path, self.debug = key, cache_path, debug
        self.cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
        self.calls = 0

    def _get(self, url: str, params: dict) -> dict:
        key = url + "?" + urllib.parse.urlencode(sorted(params.items()))
        if key in self.cache:
            return self.cache[key]
        query = urllib.parse.urlencode({**params, "key": self.key, "req_type": "json"})
        with urllib.request.urlopen(f"{url}?{query}", timeout=20) as response:
            raw = response.read().decode("utf-8")
        self.calls += 1
        time.sleep(PAUSE)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            raise SystemExit(f"JSON이 아닌 응답(키 오류·한도 초과일 수 있음):\n{raw[:500]}")
        if self.debug and not DEBUG.exists():
            DEBUG.write_text(json.dumps({"request": key, "response": data}, ensure_ascii=False, indent=1), encoding="utf-8")
        self.cache[key] = data
        return data

    def search(self, word: str) -> list[dict]:
        data = self._get(SEARCH_URL, {"q": word, "advanced": "y", "method": "exact", "type_search": "search", "num": 50})
        items = (data.get("channel") or {}).get("item") or []
        return items if isinstance(items, list) else [items]

    def view(self, target_code: str) -> dict:
        data = self._get(VIEW_URL, {"q": str(target_code), "method": "target_code"})
        return (data.get("channel") or {}).get("item") or {}

    def save(self) -> None:
        self.cache_path.write_text(json.dumps(self.cache, ensure_ascii=False, indent=1), encoding="utf-8")


def _walk(value):
    """중첩 dict/list를 모두 돌며 dict만 낸다."""
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _plain(word: str) -> str:
    return word.replace("-", "").replace("^", "").replace(" ", "")


def has_hada_derivative(entry: dict, word: str) -> bool:
    """view.do 항목 안의 파생어·관련어에 'W하다'가 있는가."""
    target = word + "하다"
    for node in _walk(entry):
        text = node.get("word")
        kind = str(node.get("type", "")) + str(node.get("relation_type", "")) + str(node.get("link_type", ""))
        if isinstance(text, str) and _plain(text) == target and ("파생" in kind or "관련" in kind or kind == ""):
            return True
    return False


def is_action_noun(api: Api, word: str) -> tuple[bool | None, str]:
    """→ (True 행동명사 / False 사전상 근거 없음 / None 사전에 단어 없음, 근거)."""
    items = api.search(word)
    nouns = [it for it in items if _plain(str(it.get("word", ""))) == word and "명사" in str(it.get("pos", ""))]
    if not items:
        return None, "표제어 없음"
    for it in nouns:
        code = it.get("target_code")
        if code and has_hada_derivative(api.view(code), word):
            return True, f"'{word}' 명사 항목(target_code {code})의 파생어 '{word}하다'"
    verbs = [it for it in api.search(word + "하다") if "동사" in str(it.get("pos", ""))]
    if verbs:
        return True, f"'{word}하다' 동사 표제어(target_code {verbs[0].get('target_code')})"
    return False, "명사 항목은 있으나 '-하다' 파생어·동사 표제어 없음" if nouns else "명사 표제어 없음"


def read_lexicon() -> dict[str, tuple[str, str]]:
    out = {}
    for line in LEXICON.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            parts = (line.split("\t") + ["", ""])[:3]
            out[parts[0].strip()] = (parts[1].strip(), parts[2].strip())
    return out


def write_lexicon(entries: dict[str, tuple[str, str]]) -> None:
    header = [l for l in LEXICON.read_text(encoding="utf-8").splitlines() if l.startswith("#")]
    body = [f"{w}\t{src}\t{d}" for w, (src, d) in sorted(entries.items())]
    LEXICON.write_text("\n".join(header + body) + "\n", encoding="utf-8")


def words_from_results(folder: Path) -> set[str]:
    """차례② 결과 JSON에서 △(목록에 없음)로 나온 마지막 어절을 모은다."""
    words = set()
    for path in folder.rglob("*차례②*.json"):
        for row in json.loads(path.read_text(encoding="utf-8")):
            if row.get("체크", {}).get("행동명사 종결") == "△" and row.get("마지막 어절"):
                words.add(row["마지막 어절"])
    return words


def main() -> None:
    parser = argparse.ArgumentParser(description="행동명사 목록을 표준국어대사전 API로 갱신")
    parser.add_argument("words", nargs="*")
    parser.add_argument("--from-file", type=Path)
    parser.add_argument("--from-results", type=Path, help="검수 결과 폴더(차례② JSON의 △ 단어 수집)")
    parser.add_argument("--debug", action="store_true", help="첫 API 원응답을 scripts/.stdict_debug.json에 저장")
    parser.add_argument("--dry-run", action="store_true", help="목록 파일을 쓰지 않고 결과만 출력")
    args = parser.parse_args()

    key = os.getenv("STDICT_API_KEY")
    if not key:
        parser.exit(2, "STDICT_API_KEY 환경 변수가 필요합니다 (.env에 넣고 set -a; source .env; set +a)\n")
    candidates = set(args.words)
    if args.from_file:
        candidates |= {l.strip() for l in args.from_file.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")}
    if args.from_results:
        candidates |= words_from_results(args.from_results)
    lexicon = read_lexicon()
    todo = sorted(w for w in candidates if w and w not in lexicon)
    if not todo:
        parser.exit(0, "새로 조회할 단어가 없습니다\n")

    api = Api(key, CACHE, debug=args.debug)
    added, rejected, unknown = [], [], []
    try:
        for word in todo:
            try:
                verdict, why = is_action_noun(api, word)
            except urllib.error.URLError as error:
                print(f"  {word}: 네트워크 오류 {error}", file=sys.stderr)
                continue
            if verdict is True:
                lexicon[word] = ("stdict", date.today().isoformat())
                added.append((word, why))
            elif verdict is False:
                rejected.append((word, why))
            else:
                unknown.append((word, why))
    finally:
        api.save()

    print(f"조회 {len(todo)}단어, API 호출 {api.calls}회 (캐시 적중은 제외)")
    if added:
        print(f"\n행동명사로 확인 → 목록에 추가 {len(added)}:")
        for w, why in added:
            print(f"  {w}\t{why}")
    if rejected:
        print(f"\n사전에 '-하다' 근거 없음 {len(rejected)} — 사람이 확인. 전문용어라 누락일 수 있음:")
        for w, why in rejected:
            print(f"  {w}\t{why}")
        print("  → 행동명사가 맞으면 action_nouns.txt에 '단어<TAB>manual<TAB>날짜', 아니면 non_action_nouns.txt에 추가")
    if unknown:
        print(f"\n표제어 자체가 없음 {len(unknown)} — 복합어·전문용어. 사람이 확인:")
        for w, why in unknown:
            print(f"  {w}\t{why}")
    if added and not args.dry_run:
        write_lexicon(lexicon)
        print(f"\n{LEXICON.relative_to(ROOT)} 갱신. git diff로 확인 후 커밋하세요.")


if __name__ == "__main__":
    main()
