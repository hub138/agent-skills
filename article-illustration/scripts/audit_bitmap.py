import json
import os
import re
import sys

from lxml import etree
from PIL import Image

# 位图与矢量图的自动化审查
# 用法: python3 audit_bitmap.py <文章.md | 目录> [--json 输出路径] [--quiet]
#
# 判据分三档:
#   FAIL 引用的图片文件不存在、文件损坏、外链为明文协议、位图宽度不足以清晰显示
#   WARN 文件过大、缺少替代文字、每篇数量超过限制、地址特征像页面装饰、外链图没有来源页面
#   INFO 尺寸与格式统计
#
# 位图可外链或本地引用，本地适合放自绘矢量图。详见 references/patterns.md 与 references/sources.md。

# 线条示意图的宽度下限，等于正文栏宽 706px
DIAGRAM_MIN_WIDTH = 706
# 含密集文字的截图的宽度下限，两倍栏宽以覆盖高密度屏幕
DETAIL_MIN_WIDTH = 1480
# 默认走含密集文字的严格标准，正文栏宽两倍
MIN_WIDTH = DETAIL_MIN_WIDTH
# 单张图文件大小上限
MAX_BYTES = 1_500_000
# 每篇允许的位图数量上限
MAX_PER_ARTICLE = 4

IMG_REF = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')
ALLOWED_EXT = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg'}
# 页面装饰类图片的地址特征
NOISE = re.compile(
    r'(logo|icon|favicon|avatar|sprite|badge|placeholder|spacer|bullet|qrcode)', re.I)
# Markdown 链接与裸地址，用于核对图注是否给出可点击的来源页面
MD_LINK = re.compile(r'\[[^\]]+\]\((https?://[^)]+)\)')
BARE_URL = re.compile(r'https?://[^\s)]+')


def svg_size(path):
    root = etree.parse(path).getroot()
    view_box = root.get('viewBox')
    if view_box:
        nums = [float(x) for x in re.split(r'[\s,]+', view_box.strip())]
        if len(nums) == 4:
            return int(nums[2]), int(nums[3])
    w = re.sub(r'[^\d.]', '', root.get('width') or '')
    h = re.sub(r'[^\d.]', '', root.get('height') or '')
    if w and h:
        return int(float(w)), int(float(h))
    return None, None


def collect(target):
    if os.path.isfile(target):
        return [target]
    files = []
    for dirpath, dirs, names in os.walk(target):
        for name in names:
            if name.endswith('.md'):
                files.append(os.path.join(dirpath, name))
    return sorted(files)


def main():
    json_out = None
    quiet = '--quiet' in sys.argv
    positional = []
    i = 1
    while i < len(sys.argv):
        a = sys.argv[i]
        if a == '--json' and i + 1 < len(sys.argv):
            json_out = sys.argv[i + 1]
            i += 2
            continue
        if not a.startswith('--'):
            positional.append(a)
        i += 1
    if not positional:
        sys.exit('用法: python3 audit_bitmap.py <文章.md | 目录> [--json 输出路径] [--quiet]')
    target = positional[0]

    results = []
    for path in collect(target):
        text = open(path, encoding='utf-8').read()
        refs = IMG_REF.findall(text)
        remote = [r for r in refs if r[1].startswith(('http://', 'https://', 'data:'))]
        local = [r for r in refs if r not in remote]
        entry = {
            'path': path,
            'abs_path': path,
            'doc_chars': len(text),
            'ref_total': len(refs),
            'ref_remote': len(remote),
            'images': [],
            'issues': []
        }
        if not refs:
            continue

        if len(local) > MAX_PER_ARTICLE:
            entry['issues'].append(
                'WARN 本地位图 %d 张，超过每篇 %d 张的限制' % (len(local), MAX_PER_ARTICLE))

        for alt, src in remote:
            item = {'alt': alt, 'src': src}
            if not alt.strip():
                entry['issues'].append('WARN 缺少替代文字: %s' % src)
            if src.startswith('http://'):
                entry['issues'].append(
                    'FAIL 明文 http 外链会被内容安全策略拦截，页面上显示为破图: %s' % src)
            if NOISE.search(src):
                entry['issues'].append('WARN 地址特征像页面装饰，确认是否为内容图: %s' % src)
            ext = os.path.splitext(src.split('?')[0])[1].lower()
            item['ext'] = ext
            if ext and ext not in ALLOWED_EXT:
                entry['issues'].append('WARN 图片格式 %s 未在允许列表内: %s' % (ext, src))
            entry['images'].append(item)
        if remote:
            others = set(MD_LINK.findall(text)) | set(BARE_URL.findall(text))
            others = {link for link in others if link not in {s for _, s in remote}}
            if not others:
                entry['issues'].append(
                    'WARN 外链图 %d 张但正文没有来源页面地址，图注需写明来源' % len(remote))

        for alt, src in local:
            item = {'alt': alt, 'src': src}
            if not alt.strip():
                entry['issues'].append('WARN 缺少替代文字: %s' % src)
            resolved = os.path.normpath(os.path.join(os.path.dirname(path), src))
            item['resolved'] = resolved
            if not os.path.isfile(resolved):
                entry['issues'].append('FAIL 图片文件不存在: %s' % src)
                entry['images'].append(item)
                continue
            ext = os.path.splitext(resolved)[1].lower()
            item['ext'] = ext
            size = os.path.getsize(resolved)
            item['bytes'] = size
            if ext not in ALLOWED_EXT:
                entry['issues'].append('WARN 图片格式 %s 未在允许列表内: %s' % (ext, src))
            if size > MAX_BYTES:
                entry['issues'].append(
                    'WARN 文件 %.1fMB 超过上限 %.1fMB: %s' % (size / 1e6, MAX_BYTES / 1e6, src))
            if ext == '.svg':
                try:
                    width, height = svg_size(resolved)
                    item['width'], item['height'] = width, height
                    item['format'] = 'SVG'
                    if width and height:
                        item['ratio'] = round(width / height, 3)
                except Exception as exc:
                    entry['issues'].append('FAIL 矢量图无法解析: %s (%s)' % (src, str(exc)[:70]))
                entry['images'].append(item)
                continue
            try:
                with Image.open(resolved) as im:
                    item['width'] = im.width
                    item['height'] = im.height
                    item['mode'] = im.mode
                    item['format'] = im.format
                    if im.width < MIN_WIDTH:
                        entry['issues'].append(
                            'FAIL 宽度 %dpx 低于清晰显示下限 %dpx: %s' % (
                                im.width, MIN_WIDTH, src))
                    if im.width and im.height:
                        item['ratio'] = round(im.width / im.height, 3)
            except Exception as exc:
                entry['issues'].append('FAIL 图片无法打开: %s (%s)' % (src, str(exc)[:80]))
            entry['images'].append(item)
        results.append(entry)

    fails = [r for r in results if any(x.startswith('FAIL') for x in r['issues'])]
    warns = [r for r in results if any(x.startswith('WARN') for x in r['issues'])]
    ok = [r for r in results if not r['issues']]

    if not quiet:
        for r in results:
            if not r['issues']:
                continue
            print(r['path'])
            for x in r['issues']:
                print('    ' + x)
            for im in r['images']:
                if 'width' in im:
                    print('    %s %dx%d %s %.0fKB' % (
                        im['src'], im['width'], im['height'], im.get('format', '?'),
                        im.get('bytes', 0) / 1024))

    print('含位图文章 %d | FAIL %d | WARN %d | 通过 %d' % (
        len(results), len(fails), len(warns), len(ok)))
    if json_out:
        with open(json_out, 'w', encoding='utf-8') as fh:
            json.dump(results, fh, ensure_ascii=False, indent=2)
        print('报告: %s' % json_out)


main()