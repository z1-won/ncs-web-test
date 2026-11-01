"""행동명사 목록(src/ncs_core/data/action_nouns.txt)을 국립국어원 표준국어대사전 API로 키운다.

검수 실행은 이 스크립트와 무관하다(네트워크를 쓰지 않고 목록 파일만 읽는다). 개발자가 가끔 돌린다.

판정 방법: 'W하다'를 search.do로 정확 검색해 동사 표제어('설계-하다' 「동사」)가 있으면 행동명사로 본다.
없으면 W 자체를 검색해 명사 표제어가 있는지 보고, 있으면 "사전상 '-하다' 근거 없음", 없으면 "표제어 없음"으로
남겨 사람이 결정한다(사전에 없음 ≠ 틀림). view.do는 쓰지 않는다 — 명사 항목의 lexical_info에는 반대말·비슷한말만
있고 파생어('W하다')는 실려 있지 않음을 확인했다(2026-11-01, '설계' target_code 174276).

사용 (저장소 루트, .env의 STDICT_API_KEY 필요):
  set -a; source .env; set +a
  python scripts/build_action_nouns.py 분석 설계 구현            # 단어 직접
  python scripts/build_action_nouns.py --from-file 후보.txt      # 한 줄 한 단어
  python scripts/build_action_nouns.py --from-results webapp/결과 # 차례 진단 JSON의 '행동명사 미확인' 단어 수집
  python scripts/build_action_nouns.py --debug 분석              # 첫 단어의 원응답을 scripts/.stdict_debug.json에 저장
응답(XML)은 scripts/.stdict_cache.json에 캐시되어 같은 단어를 다시 묻지 않는다. --debug는 첫 원응답을 scripts/.stdict_debug.xml에 둔다.
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
from xml.etree import ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEXICON = ROOT / "src" / "ncs_core" / "data" / "action_nouns.txt"
CACHE = Path(__file__).resolve().parent / ".stdict_cache.json"
DEBUG = Path(__file__).resolve().parent / ".stdict_debug.xml"
SEARCH_URL = "https://stdict.korean.go.kr/api/search.do"
PAUSE = 0.2  # 초. 연속 호출 간격


class Api:
    def __init__(self, key: str, cache_path: Path, debug: bool = False):
        self.key, self.cache_path, self.debug = key, cache_path, debug
        self.cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
        self.calls = 0

    def _get(self, url: str, params: dict) -> ET.Element:
        """XML(기본 형식)로 요청해 루트 요소를 돌려준다. 캐시에는 XML 문자열을 둔다(키는 포함하지 않음)."""
        key = url + "?" + urllib.parse.urlencode(sorted(params.items()))
        cached = self.cache.get(key)
        if isinstance(cached, str) and cached.strip():  # 옛 형식(dict)·빈 항목은 다시 조회
            return ET.fromstring(cached)
        query = urllib.parse.urlencode({**params, "key": self.key})
        request = urllib.request.Request(f"{url}?{query}", headers={"User-Agent": "ncs-f02-review/0.1"})
        with urllib.request.urlopen(request, timeout=20) as response:
            status, headers = response.status, dict(response.headers)
            raw = response.read().decode("utf-8", errors="replace")
        self.calls += 1
        time.sleep(PAUSE)
        if self.debug and not DEBUG.exists():
            DEBUG.write_text(f"<!-- {key}\n HTTP {status} {headers} -->\n{raw}", encoding="utf-8")
        if not raw.strip():
            raise SystemExit(
                f"빈 응답 (HTTP {status}, Content-Type {headers.get('Content-Type')}). "
                "인증키가 틀렸거나 승인 전이거나 일일 한도를 넘었을 수 있습니다. "
                "브라우저에서 같은 주소를 열어 메시지를 확인하세요:\n"
                f"  {url}?{urllib.parse.urlencode({**params, 'key': '<키>'})}"
            )
        try:
            root = ET.fromstring(raw)
        except ET.ParseError:
            raise SystemExit(f"XML이 아닌 응답(HTTP {status}):\n{raw[:800]}")
        error = root.find(".//error_code")
        if error is not None:
            message = root.findtext(".//message") or ""
            raise SystemExit(f"API 오류 {error.text}: {message}  ({key})")
        self.cache[key] = raw
        return root

    def search(self, word: str) -> list[dict]:
        """→ [{'word','pos','target_code'}]. 띄어쓰기·'-'·'^' 표기는 word에 그대로 둔다."""
        root = self._get(SEARCH_URL, {"q": word, "advanced": "y", "method": "exact", "type_search": "search", "num": 50})
        items = []
        for item in root.iter("item"):
            items.append({
                "word": item.findtext("word", default=""),
                "pos": item.findtext("pos", default="") or item.findtext(".//pos", default=""),
                "target_code": item.findtext("target_code", default=""),
            })
        return items

    def save(self) -> None:
        self.cache_path.write_text(json.dumps(self.cache, ensure_ascii=False), encoding="utf-8")


def _plain(word: str) -> str:
    return word.replace("-", "").replace("^", "").replace(" ", "")


def is_action_noun(api: Api, word: str) -> tuple[bool | None, str]:
    """→ (True 행동명사 / False 사전상 근거 없음 / None 사전에 단어 없음, 근거)."""
    target = word + "하다"
    verbs = [it for it in api.search(target) if _plain(it["word"]) == target and "동사" in it["pos"]]
    if verbs:
        return True, f"'{verbs[0]['word']}' 동사 표제어(target_code {verbs[0]['target_code']})"
    nouns = [it for it in api.search(word) if _plain(it["word"]) == word]
    if nouns:
        kinds = sorted({it["pos"] for it in nouns})
        return False, f"'{word}' 표제어({', '.join(kinds)})는 있으나 '{target}' 동사 표제어 없음"
    return None, f"'{word}' 표제어 없음"


def read_lexicon() -> dict[str, tuple[str, str, str]]:
    """단어 → (출처, 날짜, 근거)."""
    out = {}
    for line in LEXICON.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            parts = (line.split("\t") + ["", "", ""])[:4]
            out[parts[0].strip()] = (parts[1].strip(), parts[2].strip(), parts[3].strip())
    return out


def write_lexicon(entries: dict[str, tuple[str, str, str]]) -> None:
    header = [l for l in LEXICON.read_text(encoding="utf-8").splitlines() if l.startswith("#")]
    body = [f"{w}\t{src}\t{d}\t{why}".rstrip("\t") for w, (src, d, why) in sorted(entries.items())]
    LEXICON.write_text("\n".join(header + body) + "\n", encoding="utf-8")


def words_from_results(folder: Path) -> set[str]:
    """차례 검수 진단 JSON의 '행동명사 미확인' 목록을 모은다(파일 모드 결과 폴더)."""
    words = set()
    for path in folder.rglob("*_차례_진단.json"):
        words |= set(json.loads(path.read_text(encoding="utf-8")).get("행동명사 미확인", []))
    return words


def main() -> None:
    parser = argparse.ArgumentParser(description="행동명사 목록을 표준국어대사전 API로 갱신")
    parser.add_argument("words", nargs="*")
    parser.add_argument("--from-file", type=Path)
    parser.add_argument("--from-results", type=Path, help="검수 결과 폴더(차례 진단 JSON의 '행동명사 미확인' 수집)")
    parser.add_argument("--debug", action="store_true", help="첫 API 원응답을 scripts/.stdict_debug.xml에 저장")
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
                lexicon[word] = ("stdict", date.today().isoformat(), why)
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
        print("  → 행동명사가 맞으면 action_nouns.txt에 '단어<TAB>manual<TAB>날짜<TAB>근거' 로 추가. 아니면 그대로 둔다(검수에서 △로 남아 사람이 본다)")
    if unknown:
        print(f"\n표제어 자체가 없음 {len(unknown)} — 복합어·전문용어. 사람이 확인:")
        for w, why in unknown:
            print(f"  {w}\t{why}")
    if added and not args.dry_run:
        write_lexicon(lexicon)
        print(f"\n{LEXICON.relative_to(ROOT)} 갱신. git diff로 확인 후 커밋하세요.")


if __name__ == "__main__":
    main()
