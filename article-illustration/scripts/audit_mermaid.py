import json
import os
import re
import statistics
import sys

from playwright.sync_api import sync_playwright

# mermaid 图的自动化审查
# 用法: python3 audit_mermaid.py <文章.md | 目录> [--json 输出路径] [--shots 截图目录] [--quiet]
# 目标必填，目录写绝对路径；另可用 --mermaid-js 指定 mermaid.min.js 路径
#
# 判据分三档:
#   FAIL 渲染失败、节点文字显示不全、最窄手机端字号不可读
#   WARN 图宽超出正文栏宽、图高需要滚动、节点过多、连线缺少语义标签、写法与模板不一致
#   INFO 尺寸与数量统计
#
# 宽度规律由实测校准得到（记录在 references/benchmarks.md）:
#   纵向链路宽度只由最宽的那个节点决定，与节点数无关
#   横向链路宽度随节点数线性增长，4 个节点即超出手机可读范围
#   分叉宽度随分支数线性增长，3 支即可能超出
#   图宽可以用公式提前算出来，见 predict_width

# 正文栏宽与最窄容器宽度，按目标站点的实际排版量出后修改这两个值
DESKTOP_BODY = 706
PHONE_INNER = 296

# 基准字号，mermaid 渲染节点文字默认 16px
BASE_FONT = 16.0
# 最窄手机端字号不可读的下限
FAIL_PHONE_FONT = 8.0
# 最窄手机端舒适阅读的下限
WARN_PHONE_FONT = 10.0
# 节点数量上限
MAX_NODES = 12
# 图高提醒线，超出后手机端需要滚动多屏
WARN_HEIGHT = 1200

RUNNER_TEMPLATE = '''<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
html,body{margin:0;padding:0;background:#fefdfb}
#stage{padding:14px 16px;box-sizing:border-box;background:#fbf9f5}
</style></head><body>
<div id="stage"></div>
<script src="file://%s"></script>
<script>mermaid.initialize({startOnLoad:false,securityLevel:'strict',theme:'neutral'});</script>
</body></html>'''

MEASURE = '''() => {
    const stage = document.getElementById('stage');
    const svg = stage.querySelector('svg');
    if (!svg) return { error: 'no svg' };
    const vb = svg.getAttribute('viewBox');
    let natural;
    if (vb) {
        natural = vb.split(/[\\s,]+/).map(Number)[2];
    } else {
        natural = svg.getBBox().width;
    }
    const nodes = [...svg.querySelectorAll('g.node')];
    const labels = nodes.map(n => (n.textContent || '').trim().replace(/\\s+/g, ' '));
    const edgeLabels = [...svg.querySelectorAll('g.edgeLabel')]
        .map(e => (e.textContent || '').trim()).filter(Boolean);
    let edges = [...svg.querySelectorAll('g.edgePaths path, path.flowchart-link')].length;
    const messages = [...svg.querySelectorAll('g.messageText')]
        .map(e => (e.textContent || '').trim()).filter(Boolean);
    if (messages.length) {
        edges = messages.length;
    }
    const overflow = [];
    nodes.forEach(n => {
        const fo = n.querySelector('foreignObject');
        if (fo) {
            const div = fo.querySelector('div');
            if (div && div.scrollWidth > div.clientWidth + 1) {
                overflow.push((n.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 40));
            }
        }
    });
    return {
        natural_w: Math.round(natural),
        natural_h: Math.round(svg.getBBox().height),
        node_count: nodes.length,
        node_labels: labels,
        edge_count: edges,
        edge_labels: edgeLabels,
        messages: messages,
        overflow_nodes: overflow
    };
}'''

TEMPLATE_CHECKS = {}


def _check_sequence(src, m):
    issues = []
    parts = re.findall(r'participant\s+\w+\s+as\s+([^\n]+)', src)
    # 实测时序图宽度 = 200 × 参与者数 + 50，3 个即 650px 不可读
    if len(parts) > 2:
        issues.append(
            'WARN 参与者 %d 个，按公式宽约 %dpx，超过 2 个即不可读，改画流程图' % (
                len(parts), 200 * len(parts) + 50))
    if '-->>' not in src and '->>' not in src:
        issues.append('WARN 没有返回或异步消息，全部为同步调用')
    msgs = m.get('messages', [])
    if len(msgs) > 12:
        issues.append('WARN 消息 %d 条，超过 12 条' % len(msgs))
    return issues


def _check_state(src, m):
    issues = []
    if '[*]' not in src:
        issues.append('WARN 没有初始态或终止态标记')
    if re.search(r'-->', src) and not re.search(r'-->[^:\n]*:', src):
        issues.append('WARN 状态迁移缺少条件标注')
    return issues


def _check_quadrant(src, m):
    issues = []
    if 'x-axis' not in src or 'y-axis' not in src:
        issues.append('WARN 象限图缺少坐标轴定义')
    points = re.findall(r'[^:\n]+:\s*\[[^\]]+\]', src)
    if len(points) > 6:
        issues.append('WARN 候选点 %d 个，超过 6 个' % len(points))
    if len(points) < 2:
        issues.append('WARN 候选点少于 2 个，无法表达比较')
    return issues


def _check_xychart(src, m):
    issues = []
    series = re.findall(r'^\s*(line|bar)\s', src, re.M)
    if len(series) > 3:
        issues.append('WARN 数据系列 %d 条，超过 3 条' % len(series))
    if 'x-axis' not in src or 'y-axis' not in src:
        issues.append('WARN 缺少坐标轴定义')
    return issues


def _check_graph(src, m):
    issues = []
    head = first_code_line(src)
    labels = m.get('node_labels', [])
    unnamed = [x for x in labels if re.fullmatch(r'[A-Za-z]\d*', x)]
    if unnamed:
        issues.append('WARN 节点标签过短，可能未写含义: %s' % unnamed[:5])
    edges = m.get('edge_count', 0)
    elabels = m.get('edge_labels', [])
    # 简单链路的关系由节点名自明，只在连线数量足够多时检查标签覆盖
    if edges >= 4 and len(elabels) / max(edges, 1) < 0.5:
        issues.append('WARN 连线语义标签覆盖不足: %d/%d' % (len(elabels), edges))
    # LR 方向的线性链路宽度随节点数线性增长，实测 4 个节点即达 816px
    if re.match(r'(?:flowchart|graph)\s+LR', head):
        chain = re.findall(r'\[[^\]]+\]\s*→?\s*--?>', src)
        if len(chain) >= 4:
            issues.append(
                'WARN 横向链路 %d 个节点，实测 4 个即达 816px 超出图区，改用纵向排列（TD）' % len(chain))
    # 分叉宽度随分支数线性增长，实测 3 支即可能超出
    out_edges = {}
    for mm in EDGE_RE.finditer(strip_init(src)):
        out_edges[mm.group(1)] = out_edges.get(mm.group(1), 0) + 1
    k = max(out_edges.values(), default=0)
    if k >= 2:
        labels = re.findall(r'\[([^\]]*)\]', src)
        longest = max((len(re.findall(r'[\u4e00-\u9fff]', x.split('<br/>')[0])) for x in labels),
                      default=0)
        w = k * (min(76 + 16 * longest, 276) + 34) - 34
        if w > 473:
            issues.append(
                'WARN 分叉 %d 支、最长标签 %d 字，按公式宽约 %dpx，超过合格线 473px，'
                '改为不超过 2 支或缩短标签' % (k, longest, w))
    return issues


TEMPLATE_CHECKS.update({
    'sequenceDiagram': _check_sequence,
    'stateDiagram': _check_state,
    'quadrantChart': _check_quadrant,
    'xychart': _check_xychart,
    'flowchart': _check_graph,
})


INIT_RE = re.compile(r'^\s*%%\{.*\}%%\s*$')

# 连线识别：节点可以只写标识符，也可以带方括号、圆括号或花括号形状
EDGE_RE = re.compile(r'([A-Za-z_]\w*)(?:\[[^\]]*\]|\([^)]*\)|\{[^}]*\})?\s*--?>')


def strip_init(src):
    """去掉开头的 init 指令行，露出真正的图型声明行。"""
    lines = [l for l in src.strip().split('\n') if not INIT_RE.match(l)]
    return '\n'.join(lines) if lines else src.strip()


def first_code_line(src):
    """第一行非 init 指令的内容。"""
    for line in src.strip().split('\n'):
        if not INIT_RE.match(line):
            return line.strip()
    return ''


def has_init_width(src, key):
    """判断是否用 init 指令设定了宽度，返回设定的数值或 None。"""
    for line in src.split('\n'):
        if INIT_RE.match(line) and key in line:
            m = re.search(r'"%s"\s*:\s*(\d+)' % key, line)
            if m:
                return int(m.group(1))
    return None


def text_width(label):
    """单个标签的像素宽度：中文 16px，西文数字 10px，与实测吻合。"""
    cjk = len(re.findall(r'[\u4e00-\u9fff]', label))
    latin = len(re.findall(r'[A-Za-z0-9]', label))
    return 76 + 16 * cjk + 10 * latin


def parse_nodes(src):
    """解析节点标识符与标签，后出现的声明覆盖先前的。"""
    labels = {}
    order = []
    for m in re.finditer(r'([A-Za-z_]\w*)\s*\[([^\]]*)\]', src):
        node_id, label = m.group(1), m.group(2).split('<br/>')[0]
        if node_id not in labels:
            order.append(node_id)
        labels[node_id] = label
    return order, labels


def predict_width(src, kind):
    """按实测公式预测图宽。

    单个节点宽 = 76 + 16 × 汉字数 + 10 × 西文数字数，上限 276px（13 汉字起换行封顶）
    分叉（一个节点连出 k 条） k × (最长节点宽 + 34) − 34
    横向链路 n 个节点 n × (节点宽 + 34) − 34
    纵向链路 取最长节点宽，与节点数无关
    时序图 200 × 参与者数 + 50
    象限图 500（默认），chartWidth 可改
    数据图 700（默认），width 可改
    """
    if kind in ('quadrantChart', 'xychart'):
        return None

    order, labels = parse_nodes(src)
    widths = {k: min(text_width(v), 276) for k, v in labels.items()}
    longest = max(widths.values(), default=76)

    if kind == 'sequenceDiagram':
        parts = re.findall(r'participant\s+\w+\s+as\s+([^\n]+)', src)
        return 200 * len(parts) + 50
    if kind == 'flowchart':
        # 分组 subgraph 与连线标签会显著改变排布，公式不适用
        if 'subgraph' in src or re.search(r'--?>[^-\n|]*\|', src):
            return None
        body = strip_init(src)
        out_edges = {}
        for m in EDGE_RE.finditer(body):
            out_edges[m.group(1)] = out_edges.get(m.group(1), 0) + 1
        k = max(out_edges.values(), default=1)
        if k >= 2:
            return k * (longest + 34) - 34
        head = first_code_line(src)
        if re.match(r'(?:flowchart|graph)\s+LR', head):
            return len(order) * (longest + 34) - 34
        return longest
    return None


def detect_kind(src):
    head = first_code_line(src)
    if head.startswith('sequenceDiagram'):
        return 'sequenceDiagram'
    if head.startswith('stateDiagram'):
        return 'stateDiagram'
    if head.startswith('quadrantChart'):
        return 'quadrantChart'
    if head.startswith('xychart'):
        return 'xychart'
    if head.startswith('flowchart') or head.startswith('graph'):
        return 'flowchart'
    return 'unknown'


def collect(target):
    if os.path.isfile(target):
        files = [target]
    else:
        files = []
        for dirpath, dirs, names in os.walk(target):
            for name in names:
                if name.endswith('.md'):
                    files.append(os.path.join(dirpath, name))
    items = []
    # 两种围栏写法都要收集：反引号与波浪号
    fence = re.compile(r'(?:```|~~~)mermaid[^\n]*\n(.*?)\n(?:```|~~~)', re.S)
    for path in sorted(files):
        text = open(path, encoding='utf-8').read()
        for i, src in enumerate(fence.findall(text)):
            items.append({'path': path, 'index': i, 'src': src, 'doc_chars': len(text)})
    return items


def parse_args(argv):
    opts = {
        'json': None,
        'shots': None,
        'quiet': False,
        'target': None,
        'mermaid_js': None,
    }
    i = 1
    while i < len(argv):
        a = argv[i]
        if a == '--json' and i + 1 < len(argv):
            opts['json'] = argv[i + 1]
            i += 2
            continue
        if a == '--shots' and i + 1 < len(argv):
            opts['shots'] = argv[i + 1]
            i += 2
            continue
        if a == '--mermaid-js' and i + 1 < len(argv):
            opts['mermaid_js'] = argv[i + 1]
            i += 2
            continue
        if a == '--quiet':
            opts['quiet'] = True
            i += 1
            continue
        if not a.startswith('--'):
            opts['target'] = a
        i += 1
    return opts


def grade_width(natural_w):
    font = BASE_FONT * min(PHONE_INNER / max(natural_w, 1), 1.0)
    if font >= WARN_PHONE_FONT:
        return '优', font
    if font >= FAIL_PHONE_FONT:
        return '可接受', font
    return '不合格', font


def render_all(items, shots_dir, mermaid_js):
    results = []
    if not os.path.isfile(mermaid_js):
        sys.exit('mermaid.min.js 不存在: %s（用 --mermaid-js 指定路径）' % mermaid_js)
    first_dir = os.path.dirname(os.path.abspath(items[0]['path'])) or os.getcwd()
    runner_dir = os.path.join(first_dir, '.audit-mmd-tmp')
    os.makedirs(runner_dir, exist_ok=True)
    runner_path = os.path.join(runner_dir, 'audit_runner.html')
    open(runner_path, 'w', encoding='utf-8').write(RUNNER_TEMPLATE % mermaid_js)
    if shots_dir:
        os.makedirs(shots_dir, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 800, 'height': 900}, device_scale_factor=2)
        page.goto('file://' + runner_path)
        for item in items:
            src = item['src']
            kind = detect_kind(src)
            entry = {
                'path': item['path'],
                'abs_path': item['path'],
                'index': item['index'],
                'kind': kind,
                'head': first_code_line(src),
                'doc_chars': item['doc_chars'],
                'issues': []
            }
            try:
                page.evaluate('''async (src) => {
                    const stage = document.getElementById('stage');
                    stage.innerHTML = '';
                    const { svg } = await mermaid.render('a' + Date.now() + Math.random().toString(36).slice(2), src);
                    stage.innerHTML = svg;
                }''', src)
                m = page.evaluate(MEASURE)
            except Exception as exc:
                entry['ok'] = False
                entry['issues'].append('FAIL 渲染失败: %s' % str(exc).split('\n')[0][:200])
                results.append(entry)
                continue

            if m.get('error'):
                entry['ok'] = False
                entry['issues'].append('FAIL 渲染结果异常: %s' % m['error'])
                results.append(entry)
                continue

            entry['ok'] = True
            entry['metrics'] = m
            natural_w = m['natural_w']
            natural_h = m['natural_h']
            grade, phone_font = grade_width(natural_w)
            entry['width_grade'] = grade
            entry['phone_font_px'] = round(phone_font, 2)

            if natural_w > DESKTOP_BODY:
                entry['issues'].append(
                    'WARN 图宽 %dpx 超出正文栏宽 %dpx（%s：最窄手机端字号 %.1fpx）' % (
                        natural_w, DESKTOP_BODY, grade, phone_font))
            if grade == '不合格':
                entry['issues'].append(
                    'FAIL 最窄手机端字号仅 %.1fpx，不可读（下限 %dpx）' % (phone_font, FAIL_PHONE_FONT))
            elif grade == '可接受' and natural_w > DESKTOP_BODY:
                entry['issues'].append(
                    'WARN 最窄手机端字号 %.1fpx，低于舒适下限 %dpx' % (phone_font, WARN_PHONE_FONT))
            if natural_h > WARN_HEIGHT:
                entry['issues'].append('WARN 图高 %dpx，手机端需要滚动查看' % natural_h)
            if m['node_count'] > MAX_NODES:
                entry['issues'].append('WARN 节点 %d 个，超过上限 %d 个' % (m['node_count'], MAX_NODES))
            if m['overflow_nodes']:
                entry['issues'].append('FAIL 节点文字显示不全: %s' % m['overflow_nodes'])
            if m['node_count'] == 0 and kind == 'flowchart':
                entry['issues'].append('FAIL 流程图没有解析出任何节点，图可能写错')
            # 按实测公式预测的宽度，与实测值比对，差异明显时提示
            predicted = predict_width(src, kind)
            if predicted:
                entry['predicted_w'] = predicted
            if predicted and predicted < natural_w - 60 and natural_w > 473:
                entry['issues'].append(
                    'WARN 公式预测 %dpx，实测 %dpx，实测已超合格线 473px' % (
                        predicted, natural_w))
            if kind in ('xychart', 'quadrantChart'):
                key = 'width' if kind == 'xychart' else 'chartWidth'
                set_w = has_init_width(src, key)
                entry['init_width'] = set_w
                if set_w is None:
                    default_w = 700 if kind == 'xychart' else 500
                    hint = ('数据图默认宽 700px，手机端 6.8px，加 init 指令指定宽度后可用，'
                            '例如 %%{init: {"xyChart": {"width": 460, "height": 300}}}%%'
                            if kind == 'xychart' else
                            '象限图默认宽 500px，手机端 9.5px，加 init 指令指定宽度后可用，'
                            '例如 %%{init: {"quadrantChart": {"chartWidth": 360, "chartHeight": 360}}}%%')
                    entry['issues'].append('WARN 未指定宽度，按默认 %dpx 渲染（%s）' % (default_w, hint))
                elif set_w > 473:
                    entry['issues'].append(
                        'WARN 指定的宽度 %dpx 超过合格线 473px' % set_w)
                if kind == 'xychart' and set_w is not None and not has_init_width(src, 'height'):
                    entry['issues'].append(
                        'FAIL 数据图只写了 width，mermaid 会报无法识别图型，必须同时写 height')
            if kind in TEMPLATE_CHECKS:
                entry['issues'].extend(TEMPLATE_CHECKS[kind](src, m))
            else:
                entry['issues'].append('WARN 无法识别的图型，检查第一行写法: %s' % entry['head'])

            if shots_dir:
                shot = os.path.join(
                    shots_dir,
                    '%s-%d.png' % (
                        re.sub(r'[^\w]+', '-', os.path.splitext(os.path.basename(item['path']))[0])[:40],
                        item['index']))
                page.locator('#stage svg').screenshot(path=shot)
                entry['shot'] = shot
            results.append(entry)
        browser.close()
    os.remove(runner_path)
    try:
        os.rmdir(runner_dir)
    except OSError:
        pass
    return results


def print_report(results):
    for r in results:
        if not r['issues']:
            continue
        print('%s 块%d [%s]' % (r['path'], r['index'], r['kind']))
        for x in r['issues']:
            print('    ' + x)
    widths = [r['metrics']['natural_w'] for r in results if r.get('metrics')]
    if widths:
        grades = {}
        for r in results:
            g = r.get('width_grade')
            if g:
                grades[g] = grades.get(g, 0) + 1
        print()
        print('图宽: 最小 %d 中位 %d 最大 %d' % (
            min(widths), int(statistics.median(widths)), max(widths)))
        print('分级: ' + ' '.join('%s %d' % kv for kv in grades.items()))


def main():
    opts = parse_args(sys.argv)
    if not opts['target']:
        sys.exit('用法: python3 audit_mermaid.py <文章.md | 目录> '
                 '[--mermaid-js mermaid.min.js 路径] [--json 输出路径] [--shots 截图目录] [--quiet]')
    target = os.path.abspath(opts['target'])
    mermaid_js = os.path.abspath(opts['mermaid_js'] or os.path.join(os.path.dirname(target), 'mermaid.min.js'))
    items = collect(target)
    if not items:
        print('没有找到 mermaid 图块: %s' % target)
        return

    results = render_all(items, opts['shots'], mermaid_js)
    fails = [r for r in results if any(x.startswith('FAIL') for x in r['issues'])]
    warns = [r for r in results if any(x.startswith('WARN') for x in r['issues'])]
    passed = [r for r in results if not r['issues']]

    if not opts['quiet']:
        print_report(results)

    print('图块 %d | FAIL %d | WARN %d | 通过 %d' % (len(results), len(fails), len(warns), len(passed)))
    if opts['json']:
        with open(opts['json'], 'w', encoding='utf-8') as fh:
            json.dump(results, fh, ensure_ascii=False, indent=2)
        print('报告: %s' % opts['json'])


main()