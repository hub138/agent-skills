# 从 archify deliver 产出的 HTML 中提取内嵌 SVG，转成可独立显示的 .svg 文件
# archify 的成品 SVG 依赖 HTML 里约 186KB 的 CSS 变量与类规则，不能直接抄；
# 本脚本抽 SVG、解析浅色主题变量、内联 SVG 实际用到的 CSS 规则，产物直接进站点图床。
#
# 用法: python3 export_archify_svg.py <archify.html> <output.svg> [light|dark]
# 前置: 先用 archify deliver 以 --quality showcase 产出 HTML（showcase 全绿才算成功）
# 后置: 产物放进站点图床目录，先请求一次 URL 确认 200，再改文章里的图片链接
import re
import sys

html_path, out_path = sys.argv[1], sys.argv[2]
preset = sys.argv[3] if len(sys.argv) > 3 else "light"

html = open(html_path, encoding="utf-8").read()

# 页面有两个 :root 变量块：dark 在前，light 在后，按 data-theme 归类
root_blocks = re.findall(r"((?::root[^{]*|\[data-theme=\"(?:light|dark)\"\][^{,]*)+(?:\s*,\s*(?::root[^{]*|\[data-theme=\"(?:light|dark)\"\][^{,]*)*)*)\{([^}]*)\}", html)

light_vars, dark_vars = {}, {}
for selectors, body in root_blocks:
    vars_found = dict(re.findall(r"(--[a-zA-Z0-9-]+)\s*:\s*([^;]+);", body))
    if 'data-theme="dark"' in selectors and "light" not in selectors:
        dark_vars.update(vars_found)
    elif 'data-theme="light"' in selectors or selectors.strip().startswith(":root"):
        light_vars.update(vars_found)

chosen = light_vars if preset == "light" else dark_vars
if not chosen:
    sys.exit(f"未找到 {preset} 主题变量")

svg_match = re.search(r"<svg\b[^>]*>.*?</svg>", html, re.S)
if not svg_match:
    sys.exit("HTML 中未找到 SVG")
svg = svg_match.group(0)

# 收集 SVG 用到的 class；选择器含任一目标类的规则都收，排除其他 preset 的规则
css = re.search(r"<style[^>]*>(.*?)</style>", html, re.S).group(1)
css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
svg_classes = set()
for m in re.finditer(r'class="([^"]+)"', svg):
    svg_classes.update(m.group(1).split())

rules = []
for m in re.finditer(r"([^{}]+)\{([^}]*)\}", css):
    sel, body = m.group(1).strip(), m.group(2).strip()
    if not body or "/*" in sel:
        continue
    sel_classes = set(re.findall(r"\.([a-zA-Z0-9-]+)", sel))
    if 'data-preset=' in sel and 'data-preset="classic"' not in sel:
        continue
    if sel_classes & svg_classes:
        rules.append((sel, body))

def resolve(text, depth=0):
    if depth > 4:
        return text
    def sub(m):
        name, fallback = m.group(1), m.group(2)
        val = chosen.get(name)
        if val and "var(" in val:
            return val
        if val:
            return val
        return fallback if fallback else "currentColor"
    return re.sub(r"var\((--[a-zA-Z0-9-]+)(?:,\s*([^)]+))?\)", sub, text)

rules_text = resolve("\n".join(f"{s} {{ {b} }}" for s, b in rules))
svg = resolve(svg)

# data-animation="trace" 依赖页面脚本，独立 SVG 里去掉
svg = svg.replace(' data-animation="trace"', "")

inline_style = f"<style>\n{rules_text}\n</style>\n"
if 'xmlns="http://www.w3.org/2000/svg"' not in svg.split(">")[0]:
    svg = svg.replace("<svg ", '<svg xmlns="http://www.w3.org/2000/svg" ', 1)
svg = svg.replace(">", f">\n{inline_style}", 1)

open(out_path, "w", encoding="utf-8").write(svg)
print(f"导出 {out_path}: {len(svg)} 字节, {len(svg_classes)} 个类, {len(rules)} 条规则 ({preset})")
