import argparse
import json
import re
import sys
from pathlib import Path

import frontmatter

RULES = []


def rule(rule_id, layer, name, pattern, hint, flags=0):
    RULES.append(
        {
            "id": rule_id,
            "layer": layer,
            "name": name,
            "pattern": re.compile(pattern, flags),
            "hint": hint,
        }
    )


rule("0.2", "L0", "虚假精确", r"\d+\s*倍|提升\s*\d+\s*%|提升\d+%|\d+\s*成以上|节省\s*\d+\s*%", "去掉无来源的数值，或补上测量方式")
rule("0.3", "L0", "模糊归因", r"专家认为|专家表示|行业报告显示|观察者指出|有观点认为|多个来源表示|业内人士指出|的实录——[^。；\n]*\d|案例回流：[^。；\n]*\d", "换成具体来源或改为作者判断；\"实录\"带数字而无链接的，改成有条件推演")
rule("0.4", "L0", "重要性拔高", r"标志着|见证了|里程碑|关键时刻|深远影响|奠定基础|留下.{0,4}印记|作为.{0,12}的证明", "删掉拔高句，直接写发生了什么")
rule("0.5", "L0", "知名度强调", r"被.{0,10}媒体引用|拥有超过.{0,6}粉丝|广受.{0,6}关注|活跃的社交媒体", "换成实质性内容")
rule("0.6", "L0", "时效声明残留", r"截至我|根据我最后(的)?训练|基于可用信息|目前资料(有限|稀缺)|就我(所)?知", "删掉声明，换成可查信息")

rule("1.1", "L1", "正确废话", r"在当今(社会|时代)|随着(时代|社会)的发展|随着.{0,10}的(不断)?(发展|推进)|综上所述|由此可见|总而言之|值得(我们)?深思|这提醒我们|让我们共同|我们应当携手", "整句删除")
rule("1.2", "L1", "公式化收尾", r"一句话(总结|概括)|简单(来说|点说)|总结一下(，|,)?(核心|关键)|说白了就是|归纳起来", "删掉，或改成具体判断")
rule("1.3", "L1", "列举套路", r"首先.{0,40}?其次.{0,40}?最后|其一.{0,30}?其二|一方面.{0,40}?另一方面", "用内容衔接替代序号", flags=re.S)
rule("1.5", "L1", "预设反驳", r"有人可能会说|这并不意味着|当然(，|,)?(我们)?也要承认", "删掉，或保留真实矛盾")
rule("1.6", "L1", "挑战展望段", r"面临(着)?(若干|诸多)?挑战|尽管存在这些挑战|未来(的)?展望|挑战与(遗产|机遇)", "换成具体事实或删除")
rule("1.7", "L1", "通用积极结论", r"未来可期|迈出(了)?重要(的)?一步|继续(追求|书写).{0,8}(卓越|辉煌|旅程)|前景(光明|广阔)", "换成具体下一步")
rule("1.8", "L1", "过度限定", r"可以潜在地|可能被认为|或许会(对.{0,10})?产生(一定|一些)影响", "保留一层限定")

rule("2.1", "L2", "二分对照", r"不是[^。！？；\n]{1,30}而是|不是[^。！？；\n]{1,30}，是|并非[^。！？；\n]{1,30}而是|不在于[^。！？；\n]{1,30}而在于|要[^。！？；\n]{1,20}不要[^。！？；\n]{1,20}|不要[^。！？；\n]{1,20}要[^。！？；\n]{1,20}", "改成正面陈述或把否定并进从句；只删\"不是\"会把句意反过来")
rule("2.2", "L2", "否定式排比", r"不仅[^。\n]{1,30}(而且|更是|还)|(这)?不仅仅是[^。\n]{1,40}", "合并为一句直接陈述")
rule("2.3", "L2", "抽象名词做主语", r"(这一)?(现象|问题|设计|做法|趋势|现实|逻辑)的?(本质|意义|逻辑|价值)在于|的本质是|的逻辑在于", "换成具体主语")
rule("2.4", "L2", "条件句堆叠", r"一旦[^。\n]{1,25}就|只有[^。\n]{1,25}才|无论[^。\n]{1,25}都|正是因为[^。\n]{1,25}所以|通过[^。\n]{1,20}来", "拆成独立陈述句")
rule("2.6", "L2", "句尾虚假深度", r"，(彰显|反映了?|体现了?|象征着?|确保了?|凸显了?|展示了?)[^。\n]{0,30}。", "删掉补语或改为独立句")
rule("2.7", "L2", "三段式法则", r"[^，。；\n]{2,10}、[^，。；\n]{2,10}和[^，。；\n]{2,10}(，|,)[^。\n]{0,10}(机会|体验|价值|未来)$", "按实际数量写", flags=re.M)
rule("2.10", "L2", "极值判断", r"最[^。\n]{1,12}的地方(在于|是)|真正[^。\n]{1,10}的是|更[^。\n]{1,10}的是|值得注意的?是|这里的关键是", "改为普通陈述")
rule("2.11", "L2", "戏剧化揭露", r"遮羞布|揭开.{0,6}真面目|戳穿.{0,6}真相|撕下.{0,6}面具|剥开.{0,6}外衣", "删掉揭示动作")
rule("2.12", "L2", "温和让步壳", r"当然(，|,)?(有|也).{0,10}的?(来处|道理)|原不该被|更麻烦的地方", "只保留必要的让步")
rule("2.13", "L2", "指示性定位", r"卡在.{0,10}(裂缝|中间|这里)|难处正在这里|正卡在", "直接说清困难")
rule("2.14", "L2", "无生命对象拟人", r"(数据|血管|市场|系统|时间|现实)(并不?|不)(在乎|关心|认)|(数据|市场)不认", "改为对机制的陈述")
rule("2.17", "L2", "想象中稻草人", r"没有(某些人|很多人)想象中|并不像(传言|想象)", "直接给出真实状态")
rule("2.20", "L2", "破折号加点评", r"——[^。\n]{0,20}(吧|吗|呢|啊|太|能不能)", "去掉点评或融入前句")

rule("3.1", "L3", "AI 高频分析词", r"拆解|梳理|剖析|解构|聚焦|洞察|深耕|拉通", "只清理出现最多的几个，换具体动词")
rule("3.2", "L3", "商业套话", r"赋能|助力|践行|抓手|闭环|赛道|颗粒度|对齐(一下)?|拉齐|打法|组合拳", "换成具体动作与对象")
rule("3.3", "L3", "概念包装", r"底层逻辑|认知升级|范式转移|思维模型|认知飞轮|三件套|方法论体系", "用朴素语言直说")
rule("3.4", "L3", "伪学术腔", r"舆论场|宏大叙事|权柄|话语体系|定调|话术|通稿|结构性困境", "删除或改成具体所指")
rule("3.5", "L3", "物理动词悬空", r"接住[^。\n]{0,8}(论点|情绪|观点|场)|击穿[^。\n]{0,8}(认知|防线|底线)|折射[^。\n]{0,10}(时代|现象|变化)|沉淀[^。\n]{0,6}(经验|能力)|扎根|生根|站住脚|破圈", "换成字面动作或直接陈述")
rule("3.6", "L3", "华丽比喻", r"亮起(了)?红灯|(变成|成了)[^。\n]{0,8}的?刀|信息(的)?海洋|(心中的)?灯塔|像(一)?颗?种子|沙漏", "去掉比喻改直说")
rule("3.7", "L3", "英文词混入", r"\b(prompt|context|feedback|vibe|mindset|highlight|insight|pain point|awareness)\b", "换成中文，约定俗成缩写除外")
rule("3.8", "L3", "协作口吻", r"作为(一?个)?AI|截至我|接下来我们|我们先来看|下面我们|希望这能帮助|如果你需要.{0,6}我可以", "整句删除")
rule("3.9", "L3", "讲义动作", r"拆一拆|盘一盘|捋一捋|聊一聊|唠一唠|划重点|敲黑板", "删掉动作词，直接进入内容")
rule("3.10", "L3", "路标词", r"更关键|更要命|换句话说|事实上|值得注意|值得记住|值得看清|值得一提|要强调的是|需要注意的是|与此同时|不难发现", "全文合计两处以内")
rule("3.11", "L3", "谄媚客服腔", r"好问题|您说得(完全)?正确|很乐意(帮|为)您|当然可以", "改为中性陈述")
rule("3.12", "L3", "填充短语", r"为了实现这(一目标|个目标)|在这个时间点|在(您|你)需要帮助的情况下|具有.{0,6}的能力", "压成直接说法")
rule("3.14", "L3", "标题党标记", r"（(必看|建议收藏|强烈推荐|深度好文|干货|收藏)）|\((必看|建议收藏|强烈推荐)\)", "删掉括号部分")
rule("3.15", "L3", "伪口语化模板", r"^(说实话|其实|聊聊|说句(公道话|心里话))", "口语词不重复出现在同一位置", flags=re.M)
rule("3.16", "L3", "比喻模板起句", r"^(先用一个比喻建立形状|我们?先用一个比喻|打个比方[，：])", "跨文章同一开场超过 3 篇就是模板复发，起句直接从映射关系讲起", flags=re.M)
rule("3.17", "L3", "括号塞话", r"（(跳过|各自?的[^）]{0,8}|两个核|少数键[^）]{0,10}|热点稳定时[^）]{0,14}|99% 走一边)）", "十个字内读者顺着句子读得出的碎括注直接删", )

rule("4.4", "L4", "绝对确定感", r"毫无疑问|必然是|一定会|所有人都会|肯定不会", "降级为有条件判断")
rule("4.6", "L4", "细节模糊", r"很多人|近年来|大幅(提升|改善)|显著(提升|改善|提高)", "换成可查的具体值")
rule("4.7", "L4", "emoji 滥用", r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", "技术文档与报告一律不用")

# 粗体与内联标题列表属于格式手法，规范文档与清单里天然大量出现。
# 它们不按出现次数判定，改由 scan_text 在文件级按比例评估。
BOLD_RATIO_LIMIT = 0.15
INLINE_TITLE_RATIO_LIMIT = 0.12

CODE_FENCE = re.compile(r"^\s*(?:```|~~~)")
INLINE_CODE = re.compile(r"`[^`\n]*`")
URL = re.compile(r"https?://\S+")
WIKILINK = re.compile(r"\[\[[^]]+\]\]")


def strip_non_prose(text):
    """压掉代码块与非正文片段，但用空行占位。

    直接丢弃会让后面的行号整体前移：带代码块的 md，报告里每一条行号都偏。
    占位空行不改变命中判定（空行会被跳过），只保住 L 编号对得上原文。
    """
    lines = []
    in_fence = False
    for line in text.splitlines():
        if CODE_FENCE.match(line):
            in_fence = not in_fence
            lines.append("")
            continue
        if in_fence:
            lines.append("")
            continue
        line = URL.sub("", line)
        line = WIKILINK.sub("", line)
        line = INLINE_CODE.sub("", line)
        lines.append(line)
    return lines


def scan_text(text, threshold):
    lines = strip_non_prose(text)
    hits = []
    per_rule = {}
    for index, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            continue
        for item in RULES:
            found = item["pattern"].findall(stripped)
            if not found:
                continue
            per_rule.setdefault(item["id"], []).append(index)
            hits.append(
                {
                    "line": index,
                    "id": item["id"],
                    "layer": item["layer"],
                    "name": item["name"],
                    "hint": item["hint"],
                    "text": stripped[:120],
                }
            )
    dense = []
    for rule_id, line_numbers in per_rule.items():
        if len(line_numbers) >= threshold:
            dense.append({"id": rule_id, "count": len(line_numbers), "lines": line_numbers})
    dense.sort(key=lambda x: -x["count"])
    return hits, dense


def assess_format_density(lines):
    """按比例评估粗体与内联标题列表，格式手法不按次数判定。"""
    prose = [line for line in lines if line.strip()]
    if not prose:
        return []
    total = len(prose)
    bold_lines = sum(1 for line in prose if re.search(r"\*\*[^*\n]{1,40}\*\*", line))
    title_lines = sum(1 for line in prose if re.match(r"^\s*[-*]\s*\*\*[^*\n]{1,24}\*\*\s*[:：]", line))
    notes = []
    bold_ratio = bold_lines / total
    if bold_ratio > BOLD_RATIO_LIMIT:
        notes.append(
            {
                "id": "4.8",
                "name": "粗体滥用",
                "ratio": round(bold_ratio, 3),
                "hint": f"含粗体的行占 {bold_ratio:.0%}，对照表与清单可放宽，叙述文按扫读锚点削减",
            }
        )
    title_ratio = title_lines / total
    if title_ratio > INLINE_TITLE_RATIO_LIMIT:
        notes.append(
            {
                "id": "4.9",
                "name": "内联标题列表",
                "ratio": round(title_ratio, 3),
                "hint": f"内联标题列表占 {title_ratio:.0%}，叙述文改成完整句子，规范文档可保留",
            }
        )
    return notes


def scan_file(path, threshold):
    raw = Path(path).read_text(encoding="utf-8")
    text = raw
    if Path(path).suffix == ".md":
        # frontmatter 的 title/tags/来源不参与文风判定，否则来源条目里的
        # 「权威指南」这类词会被算成模板腔。清空为等量空行以保住行号。
        try:
            post = frontmatter.loads(raw)
        except Exception:
            post = None
        if post is not None and post.content:
            head = raw[: raw.index(post.content)]
            text = re.sub(r"[^\n]", " ", head) + post.content
    lines = strip_non_prose(text)
    hits, dense = scan_text(text, threshold)
    return {
        "path": str(path),
        "hits": hits,
        "dense": dense,
        "format_notes": assess_format_density(lines),
        "hit_count": len(hits),
        "rule_count": len({h["id"] for h in hits}),
        "line_count": len(text.splitlines()),
    }


def render(result, verbose):
    lines = []
    lines.append(f"{result['path']}  ({result['line_count']} 行)")
    if not result["hits"] and not result["format_notes"]:
        lines.append("  未命中机器可判特征")
        return "\n".join(lines)
    if result["hits"]:
        lines.append(f"  命中 {result['hit_count']} 处，涉及 {result['rule_count']} 类")
    if result["dense"]:
        summary = "、".join(f"{d['id']}({d['count']}次)" for d in result["dense"][:8])
        lines.append(f"  高密度类目：{summary}")
    for note in result["format_notes"]:
        lines.append(f"  格式比例：{note['id']} {note['name']}（{note['ratio']:.0%}）{note['hint']}")
    if verbose:
        for hit in result["hits"]:
            lines.append(f"    L{hit['line']}  [{hit['id']} {hit['name']}] {hit['text']}")
            lines.append(f"        {hit['hint']}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="扫描中文文本中机器可判的 AI 写作特征")
    parser.add_argument("paths", nargs="+", help="待扫描的文件或目录")
    parser.add_argument("--threshold", type=int, default=3, help="同一规则出现多少次算高密度，默认 3")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("-v", "--verbose", action="store_true", help="逐条列出命中位置")
    args = parser.parse_args()

    targets = []
    for raw in args.paths:
        path = Path(raw)
        if path.is_dir():
            targets.extend(sorted(path.rglob("*.md")))
        elif path.is_file():
            targets.append(path)
        else:
            # 路径写错却返回 0，会让调用方以为"扫过了、没命中"
            print("路径不存在: %s" % path, file=sys.stderr)
            return 2

    if not targets:
        print("没有可扫描的文件")
        return 0

    results = [scan_file(path, args.threshold) for path in targets]
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0

    total_hits = 0
    for result in results:
        total_hits += result["hit_count"]
        print(render(result, args.verbose))
    print(f"合计：{len(results)} 个文件，{total_hits} 处命中")
    print("命中不等于缺陷。单个特征出现一两次属于正常波动，先看高密度类目。")
    return 0


if __name__ == "__main__":
    sys.exit(main())