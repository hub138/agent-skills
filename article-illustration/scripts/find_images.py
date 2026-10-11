import io
import json
import os
import re
import sys
import urllib.parse
import urllib.request

from bs4 import BeautifulSoup
from lxml import etree
from PIL import Image

# 从给定页面提取候选配图并校验
# 用法:
#   python3 find_images.py --page URL [--page URL ...] [--json 输出路径]
#   python3 find_images.py --commons "检索词" [--json 输出路径]
#
# 脚本只做技术校验与上下文取证，不判断图与文章的相关性。
# 相关性由人工或模型依据脚本给出的图注、替代文字、所属小节标题判断。

UA = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/124 Safari/537.36'
}

# 维基媒体要求调用方声明身份与联系方式，用浏览器标识会被限流
COMMONS_UA = {
    'User-Agent': 'article-illustration-find-images/1.0 '
                  '(illustration sourcing for technical articles; contact: user@example.com)'
}

# 页面装饰类图片，按地址特征排除
NOISE = re.compile(
    r'(logo|icon|favicon|avatar|sprite|badge|placeholder|spacer|blank|bullet|flag|qrcode)',
    re.I)

# 正文内容图的最小自然宽度，低于此值判为图标或缩略图
MIN_CANDIDATE_WIDTH = 560
# 正文栏宽
BODY_WIDTH = 706
# 线条示意图的宽度下限，按 1 倍栏宽即可清晰显示
DIAGRAM_MIN_WIDTH = 706
# 含细节文字的截图需要 2 倍栏宽覆盖高密度屏幕
DETAIL_MIN_WIDTH = 1480
# 默认下限，走 1 倍栏宽的示意图标准
MIN_USABLE_WIDTH = DIAGRAM_MIN_WIDTH
# 单张图体积上限
MAX_BYTES = 1_500_000
# 取样读取的字节上限，够读出图片头部
SAMPLE_BYTES = 600_000

COMMONS_API = ('https://commons.wikimedia.org/w/api.php?action=query&format=json'
               '&generator=search&gsrnamespace=6&gsrlimit={limit}&gsrsearch={term}'
               '&prop=imageinfo&iiprop=url|size|extmetadata&iiurlwidth=1920')

# 维基共享检索结果里允许出现的图片文件类型
COMMONS_KINDS = {'png', 'jpg', 'jpeg', 'svg', 'gif', 'webp'}


def fetch(url, timeout=40, limit=None, headers=None):
    req = urllib.request.Request(url, headers=headers or UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        if limit is None:
            return resp.read()
        return resp.read(limit)


def parse_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize(src, base):
    if src.startswith('data:'):
        return None
    if src.startswith('//'):
        return 'https:' + src
    return urllib.parse.urljoin(base, src)


def pick_src(tag, base):
    for attr in ('src', 'data', 'data-src', 'data-original', 'data-lazy-src'):
        value = tag.get(attr)
        if value:
            resolved = normalize(value, base)
            if resolved:
                return resolved
    srcset = tag.get('srcset') or tag.get('data-srcset')
    if srcset:
        best = None
        for part in srcset.split(','):
            piece = part.strip().split()
            if not piece:
                continue
            resolved = normalize(piece[0], base)
            if resolved and (best is None or len(piece) > 1):
                best = resolved
        return best
    return None


def context_of(tag):
    alt = (tag.get('alt') or '').strip()
    caption = ''
    parent = tag.find_parent(['figure', 'picture'])
    if parent:
        cap = parent.find('figcaption')
        if cap:
            caption = cap.get_text(' ', strip=True)
    if not caption:
        holder = tag.find_parent(['p', 'div', 'td'])
        if holder:
            sibling = holder.find_next_sibling(['p', 'div'])
            if sibling:
                text = sibling.get_text(' ', strip=True)
                if len(text) < 240:
                    caption = text
    heading = ''
    node = tag
    while node is not None and not heading:
        node = node.find_previous(['h1', 'h2', 'h3'])
        if node is not None:
            heading = node.get_text(' ', strip=True)
    return {'alt': alt, 'caption': caption, 'section': heading}


def head_size(url, timeout=30):
    req = urllib.request.Request(url, headers=UA, method='HEAD')
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        length = resp.headers.get('Content-Length')
    return int(length) if length and length.isdigit() else None


def measure(url, kind_hint):
    try:
        raw = fetch(url, limit=SAMPLE_BYTES)
    except Exception as exc:
        return {'reachable': False, 'error': str(exc)[:90]}
    m = {'reachable': True, 'sample_bytes': len(raw)}
    looks_svg = kind_hint == 'svg' or b'<svg' in raw[:600]
    if looks_svg:
        try:
            root = etree.fromstring(raw[:SAMPLE_BYTES])
        except Exception as exc:
            return {'reachable': True, 'error': 'SVG 解析失败 %s' % str(exc)[:60]}
        m['format'] = 'SVG'
        view_box = root.get('viewBox')
        if view_box:
            nums = [float(x) for x in re.split(r'[\s,]+', view_box.strip())]
            if len(nums) == 4:
                m['width'], m['height'] = int(nums[2]), int(nums[3])
        if 'width' not in m:
            w = re.sub(r'[^\d.]', '', root.get('width') or '')
            h = re.sub(r'[^\d.]', '', root.get('height') or '')
            if w and h:
                m['width'], m['height'] = int(float(w)), int(float(h))
        try:
            m['size'] = head_size(url)
        except Exception as exc:
            m['size'] = None
        return m
    try:
        with Image.open(io.BytesIO(raw)) as im:
            m['width'], m['height'], m['format'] = im.width, im.height, im.format
            m['ratio'] = round(im.width / im.height, 2) if im.height else None
    except Exception as exc:
        m['error'] = '无法解析图片头 %s' % str(exc)[:60]
        return m
    if len(raw) < SAMPLE_BYTES:
        m['size'] = len(raw)
    else:
        try:
            m['size'] = head_size(url)
        except Exception as exc:
            m['size'] = None
    return m


def judge(item, min_width):
    issues = []
    if not item.get('reachable'):
        return ['FAIL 图片地址不可达: %s' % item.get('error', '')], '不合格'
    if item.get('error') and 'width' not in item:
        return ['FAIL %s' % item['error']], '不合格'
    if not item.get('url', '').startswith('https://'):
        issues.append('FAIL 明文 http 地址会被站点内容安全策略拦截，必须换 https')
    width = item.get('width') or 0
    # 矢量图放大不损失清晰度，像素宽度下限对它不适用，只提示原始尺寸
    if item.get('format') != 'SVG' and width < min_width:
        issues.append('WARN 宽度 %dpx 低于可用下限 %dpx' % (width, min_width))
    if item.get('format') == 'SVG' and width < MIN_CANDIDATE_WIDTH:
        issues.append('WARN 矢量图原始宽度仅 %dpx，放大到正文宽度后线条可能过细' % width)
    if item.get('size') and item['size'] > MAX_BYTES:
        issues.append('WARN 体积 %.1fMB 超过上限 %.1fMB' % (
            item['size'] / 1e6, MAX_BYTES / 1e6))
    if any(x.startswith('FAIL') for x in issues):
        return issues, '不合格'
    if issues:
        return issues, '可接受'
    return issues, '通过'


def scan_page(url, min_width):
    soup = BeautifulSoup(fetch(url).decode('utf-8', 'ignore'), 'lxml')
    found = []
    seen = set()
    for tag in soup.find_all(['img', 'object']):
        src = pick_src(tag, url)
        if not src or src in seen:
            continue
        seen.add(src)
        if NOISE.search(src):
            continue
        ctx = context_of(tag)
        declared = tag.get('width')
        try:
            declared_w = int(re.sub(r'\D', '', declared or '0') or 0)
        except ValueError:
            declared_w = 0
        if tag.name == 'object' and src.lower().endswith('.svg'):
            declared_w = round(declared_w * 4 / 3)
        if declared_w and declared_w < MIN_CANDIDATE_WIDTH and not (tag.name == 'object' and src.lower().endswith('.svg')):
            continue
        kind = 'svg' if src.lower().split('?')[0].endswith('.svg') else 'bitmap'
        item = {'page': url, 'url': src, 'kind': kind}
        item.update(ctx)
        item.update(measure(src, kind))
        if item.get('width') and item['width'] < MIN_CANDIDATE_WIDTH and kind != 'svg':
            continue
        issues, grade = judge(item, min_width)
        item['issues'] = issues
        item['grade'] = grade
        found.append(item)
    return found


def scan_commons(term, limit):
    url = COMMONS_API.format(term=urllib.parse.quote(term), limit=limit)
    data = json.loads(fetch(url, headers=COMMONS_UA).decode('utf-8'))
    pages = (data.get('query') or {}).get('pages') or {}
    found = []
    for pid, entry in pages.items():
        title = str(entry.get('title', ''))
        ext = title.rsplit('.', 1)[-1].lower()
        if ext not in COMMONS_KINDS:
            continue
        info = (entry.get('imageinfo') or [{}])[0]
        meta = info.get('extmetadata') or {}
        license_name = (meta.get('LicenseShortName') or {}).get('value', '未知')
        author = re.sub(r'<[^>]+>', '', (meta.get('Artist') or {}).get('value', ''))[:60]
        item = {
            'page': 'https://commons.wikimedia.org/wiki/' + urllib.parse.quote(
                title.replace(' ', '_')),
            'url': info.get('thumburl') or info.get('url'),
            'original_url': info.get('url'),
            'kind': 'bitmap',
            'title': title,
            'alt': '',
            'caption': '作者 %s，许可 %s' % (author or '未标注', license_name),
            'section': '维基共享资源检索',
            'width': parse_int(info.get('thumbwidth')) or info.get('width'),
            'height': parse_int(info.get('thumbheight')) or info.get('height'),
            'original_width': info.get('width'),
            'original_height': info.get('height'),
            'size': info.get('size'),
            'reachable': True,
            'format': ext.upper(),
        }
        item['license'] = license_name
        if item.get('width') and item['width'] < MIN_CANDIDATE_WIDTH:
            continue
        issues, grade = judge(item, MIN_USABLE_WIDTH)
        item['issues'] = issues
        item['grade'] = grade
        found.append(item)
    return found


def parse_args(argv):
    opts = {'pages': [], 'commons': [], 'json': None, 'min_width': MIN_USABLE_WIDTH}
    i = 1
    while i < len(argv):
        a = argv[i]
        if a == '--page' and i + 1 < len(argv):
            opts['pages'].append(argv[i + 1])
            i += 2
            continue
        if a == '--commons' and i + 1 < len(argv):
            opts['commons'].append(argv[i + 1])
            i += 2
            continue
        if a == '--json' and i + 1 < len(argv):
            opts['json'] = argv[i + 1]
            i += 2
            continue
        if a == '--min-width' and i + 1 < len(argv):
            opts['min_width'] = int(argv[i + 1])
            i += 2
            continue
        i += 1
    return opts


def main():
    opts = parse_args(sys.argv)
    if not opts['pages'] and not opts['commons']:
        print('用法: python3 find_images.py --page URL [--page URL] '
              '[--commons 检索词] [--json 路径]')
        return
    results = []
    for url in opts['pages']:
        try:
            items = scan_page(url, opts['min_width'])
        except Exception as exc:
            print('页面取回失败 %s (%s)' % (url, str(exc)[:70]))
            continue
        print('=== %s 候选 %d 张 ===' % (url, len(items)))
        results.extend(items)
    for term in opts['commons']:
        try:
            items = scan_commons(term, 8)
        except Exception as exc:
            print('维基共享检索失败 %s (%s)' % (term, str(exc)[:70]))
            continue
        print('=== 维基共享「%s」候选 %d 张 ===' % (term, len(items)))
        results.extend(items)

    print()
    for item in results:
        size = item.get('size')
        print('[%s] %sx%s %s %s' % (
            item['grade'], item.get('width'), item.get('height'),
            item.get('format', '?'),
            ('%.0fKB' % (size / 1024)) if size else ''))
        print('    地址 %s' % item['url'])
        if item.get('section'):
            print('    小节 %s' % item['section'][:70])
        if item.get('alt'):
            print('    替代文字 %s' % item['alt'][:80])
        if item.get('caption'):
            print('    图注 %s' % item['caption'][:90])
        if item.get('license'):
            print('    许可 %s' % item['license'])
        for issue in item['issues']:
            print('    ' + issue)

    print()
    grades = {}
    for item in results:
        grades[item['grade']] = grades.get(item['grade'], 0) + 1
    print('候选合计 %d | ' % len(results) + ' '.join('%s %d' % kv for kv in grades.items()))
    if opts['json']:
        with open(opts['json'], 'w', encoding='utf-8') as fh:
            json.dump(results, fh, ensure_ascii=False, indent=2)
        print('报告: %s' % opts['json'])


main()