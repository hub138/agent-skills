import argparse
import collections
import hashlib
import json
import pathlib
import re

from markdown_it import MarkdownIt

MD = MarkdownIt()


def document_map(root):
    root = pathlib.Path(root).resolve(strict=True)
    files = [root / 'SKILL.md', *sorted((root / 'references').rglob('*.md'))]
    result = {}
    for path in files:
        path.resolve(strict=True).relative_to(root)
        if path.is_symlink():
            raise ValueError('技能文件不允许使用符号链接: %s' % path)
        result[path.relative_to(root).as_posix()] = path.read_text(encoding='utf-8')
    return result


def digest(documents):
    return hashlib.sha256(json.dumps(documents, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def snapshot(root):
    docs = document_map(root)
    return {'root': str(pathlib.Path(root).resolve()), 'digest': digest(docs), 'documents': docs}


def measures(docs):
    return {'lines': sum(len(t.splitlines()) for t in docs.values()),
            'characters': sum(len(t) for t in docs.values())}


def duplicates(docs):
    blocks = collections.Counter()
    for text in docs.values():
        for token in MD.parse(text):
            if token.type == 'inline':
                block = re.sub(r'\s+', '', token.content)
                if len(block) >= 100:
                    blocks[block] += 1
    return {key: count for key, count in blocks.items() if count > 1}


def check(root, baseline, current=None):
    root = pathlib.Path(root).resolve(strict=True)
    current = snapshot(root) if current is None else current
    old = baseline['documents']
    if digest(old) != baseline['digest']:
        raise ValueError('基线摘要不一致')
    errors = []
    before, after = measures(old), measures(current['documents'])
    for key in before:
        if after[key] > before[key]:
            errors.append('%s 净增 %d；请合并已有规则' % (key, after[key] - before[key]))
    entry = current['documents']['SKILL.md']
    if len(entry.splitlines()) > 500 or len(entry) > 24000:
        errors.append('入口超过 500 行或 24000 字符预算')
    previous_duplicates = duplicates(old)
    for block, count in duplicates(current['documents']).items():
        if count > previous_duplicates.get(block, 1):
            errors.append('新增重复规则: ' + block[:80])
    for name, text in current['documents'].items():
        for token in MD.parse(text):
            for child in token.children or []:
                if child.type != 'code_inline':
                    continue
                ref = child.content.split(' ', 1)[0]
                if not ref.startswith(('references/', 'scripts/')) or '<' in ref or '*' in ref:
                    continue
                if ref.endswith(('.md', '.py', '.sh', '.json')) and not (root / ref).exists():
                    errors.append('%s 引用不存在: %s' % (name, ref))
    return {'digest': current['digest'], 'baseline_digest': baseline['digest'],
            'before': before, 'after': after, 'errors': sorted(set(errors))}


def validate_reviews(report, receipt, author):
    errors = []
    if receipt.get('digest') != report['digest'] or receipt.get('baseline_digest') != report['baseline_digest']:
        errors.append('评审所用版本与当前文件不一致')
    rows = receipt.get('reviews', [])
    identities = {r.get('reviewer') for r in rows}
    if len(rows) < 2 or len(identities) != len(rows) or author in identities or None in identities:
        errors.append('需要两位不同于作者的独立评审者')
    for row in rows:
        if row.get('approved') is not True or row.get('blocking'):
            errors.append('评审未通过: %s' % row.get('reviewer'))
        if not row.get('evidence') or not row.get('generalization') or not row.get('coverage'):
            errors.append('评审缺少引用、适用边界或已有规则覆盖分析')
    return errors


def main():
    ap = argparse.ArgumentParser(description='技能文档预算、引用、重复与独立评审检查')
    ap.add_argument('action', choices=['snapshot', 'check'])
    ap.add_argument('--root', required=True, type=pathlib.Path)
    ap.add_argument('--baseline', type=pathlib.Path)
    ap.add_argument('--review', type=pathlib.Path)
    ap.add_argument('--author', default='main')
    ap.add_argument('--out', required=True, type=pathlib.Path)
    args = ap.parse_args()
    if args.action == 'snapshot':
        if args.out.exists():
            ap.error('基线已经存在，禁止覆盖')
        result = snapshot(args.root)
    else:
        if not args.baseline:
            ap.error('check 需要 --baseline')
        result = check(args.root, json.loads(args.baseline.read_text(encoding='utf-8')))
        if args.review:
            receipt = json.loads(args.review.read_text(encoding='utf-8'))
            result['errors'] += validate_reviews(result, receipt, args.author)
        result['publishable'] = bool(args.review) and not result['errors']
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'documents'}, ensure_ascii=False))
    return int(bool(result.get('errors')))


if __name__ == '__main__':
    raise SystemExit(main())
