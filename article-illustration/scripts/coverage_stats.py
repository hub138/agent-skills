import os
import re
import sys

# 统计文章的配图密度：位图、mermaid、svg 均计入
# 用法: python3 coverage_stats.py <文章目录> [--list]
# 文章目录必填，写绝对路径；--list 按路径打印每篇图块数，无图文章排最前

if len(sys.argv) < 2:
    sys.exit('用法: python3 coverage_stats.py <文章目录> [--list]')
root = sys.argv[1]
if not os.path.isdir(root):
    sys.exit(f'目录不存在: {root}')

total = 0
with_figure = 0
figure_count = 0
char_count = 0
per_file = []
by_top = {}

pattern = re.compile(r'!\[[^\]]*\]\(|<img |```mermaid|~~~mermaid|<svg')

for dirpath, dirs, files in os.walk(root):
    for f in files:
        if not f.endswith('.md'):
            continue
        path = os.path.join(dirpath, f)
        text = open(path, encoding='utf-8').read()
        n = len(pattern.findall(text))
        rel = os.path.relpath(path, root)
        per_file.append((rel, n))
        total += 1
        char_count += len(text)
        figure_count += n
        if n > 0:
            with_figure += 1
        top = rel.split('/')[0]
        stat = by_top.setdefault(top, [0, 0, 0])
        stat[0] += 1
        stat[1] += n
        stat[2] += len(text)

if '--list' in sys.argv:
    for rel, n in sorted(per_file, key=lambda x: (x[1], x[0])):
        print(f'{n}  {rel}')
    sys.exit(0)

print(f'目录: {root}')
print(f'文章总数 {total} | 有图文章 {with_figure} ({with_figure * 100 // max(total, 1)}%) | 图总数 {figure_count}')
print(f'全库密度 {figure_count * 1000 / max(char_count, 1):.3f} 图/千字 (目标 0.3 到 0.5)')
print()
print('按领域:')
print(f'{"领域":<26s}{"篇数":>6s}{"图数":>6s}{"图/千字":>10s}')
for top, (cnt, figs, chars) in sorted(by_top.items(), key=lambda x: x[1][1] / max(x[1][2], 1)):
    print(f'{top[:24]:<26s}{cnt:>6d}{figs:>6d}{figs * 1000 / max(chars, 1):>10.3f}')
