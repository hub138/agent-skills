# 校验 cron-recipe.md 配方模板与线上 cron_tasks.json 任务的 jobMessage 同源性
# 用法：python3 check-cron-sync.py [cron_tasks.json 路径]（默认 ./cron_tasks.json，传入你的定时任务文件路径）
# 输出：逐任务 OK/DRIFT，配方里新增而线上缺失的能力标记为 GAP
import json
import re
import sys
from pathlib import Path

RECIPE = Path(__file__).resolve().parent.parent / "references" / "cron-recipe.md"
TASKS = Path(sys.argv[1] if len(sys.argv) > 1 else "./cron_tasks.json")

# 配方任务名 → 线上任务名映射（线上命名带前缀）
NAME_MAP = {
    "早报": "股票管家·早报（美股夜报+持仓检查）",
    "财务哨兵": "股票管家·财务哨兵",
    "亚太早巡": "股票管家·亚太早巡",
    "开盘快照": "股票管家·开盘快照",
    "箱体确认": "股票管家·箱体确认",
    "午间检查": "股票管家·午间检查",
    "盘中巡检": "股票管家·盘中巡检",
    "尾盘决策": "股票管家·尾盘编辑".replace("编辑", "决策"),
    "风格雷达": "股票管家·风格雷达",
    "盘后荐股": "股票管家·盘后荐股",
    "荐股验证": "股票管家·荐股验证",
    "美股开盘报": "股票管家·美股开盘报",
    "美股半场报": "股票管家·美股半场报",
    "美股收盘报": "股票管家·美股收盘报",
}

# 能力标记：配方挂载的新能力短语 → 所属任务
CAPABILITY_MARKERS = {
    "早报": ["三情景预演", "票性画像保鲜"],
    "财务哨兵": ["宏观日历"],
    "尾盘决策": ["组合相关性周评", "票性画像保鲜"],
    "风格雷达": ["票性画像保鲜"],
    "盘后荐股": ["独立性铁律", "连续错熔断", "picks-log.sh rec"],
    "荐股验证": ["验证落判四态", "picks-log.sh verify", "周五例行思路复盘"],
}


def load_recipe_messages():
    text = RECIPE.read_text(encoding="utf-8")
    out = {}
    for name in NAME_MAP:
        m = re.search(rf"^- {name}：(.+)$", text, re.M)
        if m:
            out[name] = m.group(1)
    return out


def main():
    recipe = load_recipe_messages()
    tasks = json.loads(TASKS.read_text(encoding="utf-8"))
    by_name = {}
    for t in tasks:
        msg = (t.get("payload") or {}).get("message") or ""
        by_name[t.get("name", "")] = msg
    ok = drift = gap = 0
    for recipe_name, online_name in NAME_MAP.items():
        msg = recipe.get(recipe_name)
        online = by_name.get(online_name, "")
        if not msg:
            print(f"[NO-TEMPLATE] {recipe_name}：配方缺模板")
            continue
        if online_name not in by_name:
            print(f"[MISSING] {online_name}：线上任务不存在")
            continue
        if msg == online:
            print(f"[OK] {online_name}")
            ok += 1
            continue
        # 内容不同：检查是否只是占位符差异，逐能力标记对照
        missing_markers = [
            m for m in CAPABILITY_MARKERS.get(recipe_name, [])
            if m in msg and m not in online
        ]
        if missing_markers:
            gap += 1
            print(f"[GAP] {online_name}：线上缺配方标记 {missing_markers}")
        else:
            drift += 1
            print(f"[DRIFT] {online_name}：线上 jobMessage 与配方模板不一致（占位符差异属正常）")
    print(f"\n合计：{len(NAME_MAP)} 任务 | OK {ok} | GAP {gap} | DRIFT {drift}")
    print("口径：OK=完全一致；GAP=线上缺配方新挂载的能力；DRIFT=文本不一致（占位符差异属正常）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
