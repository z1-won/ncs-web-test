"""python -m ncs_toc 원고.hwpx [개발계획서.hwpx] --module-code LM..."""
import argparse
import json
from . import CheckConfig, inspect_files, save_results


def main():
    parser = argparse.ArgumentParser(description='F02 차례 ①·③·⑤·⑥ 검수')
    parser.add_argument('paths', nargs='+')
    parser.add_argument('--module-code')
    parser.add_argument('--manuscript', help='자동 역할 분류 대신 원고로 지정할 입력 경로')
    parser.add_argument('--plan', help='자동 역할 분류 대신 개발계획서로 지정할 입력 경로')
    parser.add_argument('--front-section', type=int, default=0)
    parser.add_argument('--body-section', type=int, default=1)
    parser.add_argument('--out-dir', default='결과')
    args = parser.parse_args()
    roles = {}
    if args.manuscript:
        roles[args.manuscript] = 'manuscript'
    if args.plan:
        roles[args.plan] = 'plan'
    try:
        result = inspect_files(args.paths, roles=roles, module_code=args.module_code,
                               config=CheckConfig(front_section=args.front_section, body_section=args.body_section))
        summary, archive = save_results(result.checklist, result.findings, result.module_code,
                                        args.out_dir, diagnostics=result.diagnostics)
    except (OSError, ValueError) as error:
        parser.exit(2, f'검수 실행 실패: {error}\n')
    print(json.dumps({'요약': summary, '진단': result.diagnostics, 'ZIP': archive}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
