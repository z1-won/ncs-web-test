"""원고(hwp·hwpx)에서 도표·표·그래프 생성(REQ-02-006 ①)을 재어 볼 문단을 뽑는다 — diagram_probe.py에 넣을 문단 파일을 만든다.

  PYTHONPATH=src python scripts/probe/manuscript_paragraphs.py 원고폴더_또는_파일… --out _workspace_probe/문단.txt [--count 30] [--seed 20261125]
뽑는 법: 본문 문단 가운데 길이가 --min~--max 글자이고 문장으로 끝나는 것만 남긴다(표 안의 글, 제목, 캡션, 출처 줄, 목록 한 줄은 뺀다).
절반은 '그릴 거리가 있을 법한' 문단(순서·종류·비교를 가리키는 말이나 수치가 둘 이상), 절반은 그렇지 않은 문단에서 고른다 —
그릴 것이 없는 문단에 억지로 그리지 않는지도 보려는 것이다. 같은 --seed면 같은 문단이 나온다.
쓰는 파일: 문단 파일(빈 줄로 나눈 문단)과 같은 이름의 .tsv(번호, 원고 파일, 구역, 문단 순번, 갈래). 외부로 보내는 것은 없다.
원고의 글이 그대로 들어가므로 결과는 저장소에 올리지 않는 곳(_workspace*/)에 둔다.
"""

import argparse
import random
import re
from pathlib import Path

from ncs_core.documents import load_document

CUE = re.compile(r"먼저|다음으로|이어서|마지막으로|단계|순서|절차|과정|종류|유형|구분|분류|나뉜다|나눈다|구성|반면|비교|각각|첫째|둘째")
NUMBER = re.compile(r"\d[\d,.]*\s*(?:%|건|명|개|원|회|시간|일|년|kg|g|m|㎡|℃)")
SKIP = re.compile(r"^(?:출처\s*:|\[그림|<표|[•·\-◦▪▶○●□■※]|\d+[.)]\s|\(\d+\)|[가-하][.)]\s)")
SENTENCE_END = re.compile(r"[다요음함됨임][.]\s*$")


def likely(text: str) -> bool:
    return len(CUE.findall(text)) >= 2 or len(NUMBER.findall(text)) >= 2


def paragraphs(path: Path, low: int, high: int):
    document = load_document(path)
    for section_no, section in enumerate(document.sections):
        for index, text in enumerate(section):
            text = " ".join(str(text).split())
            if low <= len(text) <= high and SENTENCE_END.search(text) and not SKIP.match(text):
                yield section_no, index, text


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("sources", type=Path, nargs="+", help="원고 파일이나 폴더(폴더는 아래의 hwp·hwpx를 모두 읽는다)")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--count", type=int, default=30)
    parser.add_argument("--min", type=int, default=120, dest="low")
    parser.add_argument("--max", type=int, default=700, dest="high")
    parser.add_argument("--seed", type=int, default=20261125)
    args = parser.parse_args()
    files = sorted({file for source in args.sources
                    for file in ([source] if source.is_file() else [*source.rglob("*.hwp"), *source.rglob("*.hwpx")])})
    if not files:
        parser.error("원고(hwp·hwpx)를 찾지 못했습니다")
    pool: dict[bool, list[tuple]] = {True: [], False: []}
    seen: set[str] = set()
    for file in files:
        try:
            found = list(paragraphs(file, args.low, args.high))
        except Exception as error:      # noqa: BLE001 — 못 읽는 원고는 건너뛰고 알린다
            print(f"건너뜀: {file.name} ({type(error).__name__}: {error})")
            continue
        for section_no, index, text in found:
            if text not in seen:
                seen.add(text)
                pool[likely(text)].append((file.name, section_no, index, text))
        print(f"{file.name}: 문단 {len(found)}개")
    rng = random.Random(args.seed)
    half = min(len(pool[True]), (args.count + 1) // 2)
    rest = min(len(pool[False]), args.count - half)
    picked = [("그릴 거리 있을 법함", row) for row in rng.sample(pool[True], half)] + [("그 밖", row) for row in rng.sample(pool[False], rest)]
    rng.shuffle(picked)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n\n".join(row[3] for _, row in picked) + "\n", encoding="utf-8")
    index_file = args.out.with_suffix(".tsv")
    index_file.write_text("번호\t원고\t구역\t문단 순번\t갈래\n" + "".join(
        f"{number}\t{row[0]}\t{row[1]}\t{row[2]}\t{group}\n" for number, (group, row) in enumerate(picked, 1)), encoding="utf-8")
    print(f"\n후보 문단 {len(pool[True]) + len(pool[False])}개(그릴 거리 있을 법함 {len(pool[True])}) 가운데 {len(picked)}개를 뽑았습니다 → {args.out}, {index_file}")


if __name__ == "__main__":
    main()
