"""模型评审入口：调外部 CLI 对技能改动做独立评审。

被测与裁判必须是不同模型；评审结构、校验规则见 skill-craft/SKILL.md 第四节。
流程与 skill_check.py 对齐：先静态检查，再逐项校验评审引用，最后落 review.json。
"""
import argparse
import json
import pathlib
import sys

import cli_runner

PROMPT = (
    '你是独立评审者。附件是技能文件的检查结果与改前改后对照。请判断：'
    '1) 能力是否丢失；2) 已有规则能否覆盖本次改动；3) 改动的适用边界与反例。'
    '只输出一个 JSON 对象：{"approved": true/false, "blocking": ["阻断问题"], '
    '"evidence": [{"file": "相对路径", "quote": "改后文本中连续的原文"}], '
    '"generalization": "适用与不适用的边界", "coverage": "已有规则能否覆盖新增要求"}。'
    'quote 必须逐字来自原文；三项内容缺任一项视为无效评审。'
)


def main():
    ap = argparse.ArgumentParser(description='技能改动的独立模型评审')
    ap.add_argument('--root', required=True, help='被评审的技能目录')
    ap.add_argument('--baseline', required=True, help='基线摘要 JSON（snapshot 产出）')
    ap.add_argument('--author', default='', help='作者模型名，评审模型须与之不同')
    ap.add_argument('--models', default='claude-sonnet,codex', help='评审模型链，逗号分隔')
    ap.add_argument('--timeout', type=int, default=180)
    ap.add_argument('--out', required=True, help='评审结果输出目录')
    args = ap.parse_args()

    root = pathlib.Path(args.root).resolve()
    baseline = json.loads(pathlib.Path(args.baseline).read_text(encoding='utf-8'))
    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=False)

    files = sorted(p for p in root.rglob('*') if p.is_file() and p.suffix in ('.md', '.py'))
    sections = []
    for path in files:
        rel = path.relative_to(root).as_posix()
        sections.extend([f'FILE {rel}', path.read_text(encoding='utf-8')])
    source = out_dir / 'input.txt'
    source.write_text('\n\n'.join(sections), encoding='utf-8')

    reviews, excluded = [], [args.author] if args.author else []
    for number in range(2):
        workspace = out_dir / ('reviewer-%d' % (number + 1))
        workspace.mkdir()
        review, model, attempts = cli_runner.run_json(
            PROMPT, [source], workspace,
            models=args.models.split(','), exclude=excluded, timeout=args.timeout)
        if not isinstance(review.get('evidence'), list) or not review['evidence']:
            raise ValueError('缺少评审引用')
        if not review.get('generalization') or not review.get('coverage'):
            raise ValueError('评审缺少适用边界或已有规则覆盖分析')
        for ev in review['evidence']:
            quote = ev.get('quote')
            target = root / str(ev.get('file') or '')
            if not quote or not (target.is_file() and quote in target.read_text(encoding='utf-8')):
                raise ValueError('评审引用不在当前文件中: %s' % ev.get('file'))
        reviews.append(dict(review, reviewer=model))
        (workspace / 'result.json').write_text(
            json.dumps(reviews[-1], ensure_ascii=False, indent=2), encoding='utf-8')
        excluded.append(model)

    receipt = {'digest': baseline.get('digest', ''), 'reviews': reviews}
    (out_dir / 'review.json').write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'reviewers': [r['reviewer'] for r in reviews]}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
