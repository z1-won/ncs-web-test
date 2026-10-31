"""기존 JSON 계약을 유지하는 결과 저장."""
import json
import zipfile
from pathlib import Path
from .common import X, TRI

ITEM_FILES = [('F02-차례-①', '차례①_학습명'), ('F02-차례-③', '차례③_학습명내용명_5곳일치'), ('F02-차례-⑤', '차례⑤_참고자료'), ('F02-차례-⑥', '차례⑥_활용서식부록')]

def flatten(checklist):
    F = []
    for c in checklist:
        for name, val in c['체크'].items():
            if val in (X, TRI):
                notes = c['비고']
                reason = notes.get(name, '') if isinstance(notes, dict) else '; '.join(notes)
                F.append({'item_id': c['item_id'], 'check': name, 'region_path': c['region_path'],
                          'verdict': '미반영' if val == X else '판단불가', 'evidence_quote': c['원고'],
                          'reason': reason, 'suggestion': c['수정 제안']})
    return F


def save_results(checklist, findings, module_code, out_dir='결과', *, diagnostics=None):
    """항목별 JSON과 ZIP을 out_dir에 저장한다. 동일 코드 재실행은 덮어쓴다."""
    import re
    if not re.fullmatch(r'LM\d{10}_\d+v\d+', module_code):
        raise ValueError('올바른 모듈코드를 지정하세요')
    output = Path(out_dir)
    output.mkdir(parents=True, exist_ok=True)
    buckets = {tail: [] for _, tail in ITEM_FILES}
    names = dict(ITEM_FILES)
    for row in checklist:
        tail = names.get(row['item_id'], '차례_기타')
        buckets.setdefault(tail, []).append(row)
    paths, summary = [], {}

    def write(name, value):
        path = output / f'{module_code}_{name}.json'
        with path.open('w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=1)
        paths.append(path)
        return path

    for tail, rows in buckets.items():
        path = write(tail, rows)
        verdicts = [row['판정'] for row in rows]
        summary[tail] = {v: verdicts.count(v) for v in ('반영', '미반영', '판단불가')}
        summary[tail]['파일'] = path.name
    for name, value in (('차례_00_요약', summary), ('차례_지적사항', findings), ('차례_전체', checklist)):
        write(name, value)
    if diagnostics is not None:
        write('차례_진단', diagnostics)
    archive_path = output / f'{module_code}_차례_검수결과.zip'
    with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            archive.write(path, path.name)
    return summary, str(archive_path)

