"""원본 패키지와 리팩토링 패키지를 같은 입력으로 실행해 체크리스트를 비교한다.

사용: python3 -I tests/compare_with_original.py <원본 패키지 폴더> <새 src 폴더> <fixtures 폴더>
"""

import importlib
import json
import sys
import types
from pathlib import Path


def fresh_import(root, *names):
    for name in list(sys.modules):
        if name.split(".")[0] in {"ncs_toc", "ncs_position", "ncs_core"}:
            del sys.modules[name]
    sys.path.insert(0, str(root))
    importlib.invalidate_caches()
    modules = [importlib.import_module(n) for n in names]
    sys.path.remove(str(root))
    return modules


def run_original(original, fixtures):
    sys.modules.setdefault("olefile", types.SimpleNamespace(OleFileIO=None))  # hwpx만 쓰므로 스텁
    (toc,) = fresh_import(original, "ncs_toc")
    out = {}
    plan = fixtures / "개발계획서_LM1203020201_24v3.hwpx"
    for manuscript in sorted(fixtures.glob("원고_*.hwpx")):
        for with_plan in (True, False):
            paths = [str(manuscript)] + ([str(plan)] if with_plan else [])
            result = toc.inspect_files(paths)
            out[f"toc/{manuscript.stem}/{'plan' if with_plan else 'noplan'}"] = result.checklist
    (position,) = fresh_import(original, "ncs_position")
    for manuscript in sorted(fixtures.glob("원고_*.hwpx")):
        result = position.run_review(str(plan), str(manuscript))
        out[f"position/{manuscript.stem}"] = result.checklist
    return out


def run_refactored(src, fixtures):
    toc, position = fresh_import(src, "ncs_toc", "ncs_position")
    out = {}
    plan = fixtures / "개발계획서_LM1203020201_24v3.hwpx"
    for manuscript in sorted(fixtures.glob("원고_*.hwpx")):
        for with_plan in (True, False):
            paths = [str(manuscript)] + ([str(plan)] if with_plan else [])
            result = toc.run_review(paths)
            out[f"toc/{manuscript.stem}/{'plan' if with_plan else 'noplan'}"] = result.checklist
        result = position.run_review([str(plan), str(manuscript)])
        out[f"position/{manuscript.stem}"] = result.checklist
    return out


def main():
    original, src, fixtures = (Path(a) for a in sys.argv[1:4])
    before = run_original(original, fixtures)
    # 원본의 판정 표현(반영/미반영)을 현재 표현(적합/부적합)으로 맞춘 뒤 비교한다.
    before = json.loads(json.dumps(before, ensure_ascii=False).replace('"미반영"', '"부적합"').replace('"반영"', '"적합"'))
    after = run_refactored(src, fixtures)
    # 원본에 없는 항목(차례 ④ 등 이후 추가된 규칙)은 비교에서 뺀다.
    for key, rows in after.items():
        known = {r["item_id"] for r in before[key]}
        after[key] = [r for r in rows if r["item_id"] in known]
    differences = 0
    for key in sorted(before):
        a, b = json.dumps(before[key], ensure_ascii=False, sort_keys=True), json.dumps(after[key], ensure_ascii=False, sort_keys=True)
        if a != b:
            differences += 1
            print("DIFF", key)
            for x, y in zip(before[key], after[key]):
                if x != y:
                    print("  before:", json.dumps(x, ensure_ascii=False)[:600])
                    print("  after :", json.dumps(y, ensure_ascii=False)[:600])
            if len(before[key]) != len(after[key]):
                print("  row count", len(before[key]), "->", len(after[key]))
    verdicts = {k: [r["판정"] for r in v] for k, v in after.items()}
    print(json.dumps(verdicts, ensure_ascii=False, indent=1))
    print("cases:", len(before), "differences:", differences)
    sys.exit(1 if differences else 0)


if __name__ == "__main__":
    main()
