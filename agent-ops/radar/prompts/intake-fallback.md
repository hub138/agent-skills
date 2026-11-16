# 任务书：简报解析兜底（radar/intake-fallback）

> 何时用：`radar_cli.py intake --dry-run` 解析出的条目数明显不对，
> 或简报是混合格式（通知卡片、聊天记录、多期拼接）。
> 原则：**只抽取原文里明确存在的内容，不补全、不猜测、不编 URL。**

## 1. 流程

```bash
python3 scripts/radar_cli.py intake --file <brief.md> --dry-run   # 先看脚本解析结果
```

对照原文，若条目数/标题/URL 明显缺失，手工（或让模型）产出 JSON，再：

```bash
python3 scripts/radar_cli.py intake --json-file /tmp/items.json --date 2026-11-16 --slot 11:00
```

## 2. JSON 结构（严格照此）

```json
{
  "title": "技术情报简报 2026-11-16",
  "date": "2026-11-16",
  "slot": "11:00",
  "raw": "可选：原始全文；不填则脚本用本 JSON 的文本做 sha",
  "items": [
    {
      "seq": 1,
      "title": "GitHub - Tencent/LoopForge: ...",
      "url": "https://github.com/Tencent/LoopForge",
      "core": "自托管 Agent 交付工作流……",
      "innovation": "Agent、Script、Human-gate、子 SOP 四类节点……",
      "audience": ""
    }
  ]
}
```

规则：

- `seq` 从 1 连续递增，与原文顺序一致。
- `title` 用原文标题，不改写、不翻译、不加书名号。
- `url` 只填原文中出现过的链接；**原文没有就留空字符串**，绝不根据标题猜 URL。
- `core` / `innovation` 用原文措辞，可去掉「核心　」「创新　」前缀。
- 同一天多期用 `slot` 区分（如 `11:00`、`15:00`）；只有一期可留空。
- 原文页脚（「查看完整简报」「主题串联」等）不是条目。

## 3. 校验

```bash
python3 scripts/radar_cli.py intake --json-file /tmp/items.json --dry-run
python3 scripts/radar_cli.py list --brief 2026-11-16
```

- 条目数与原文标题数一致；
- 每个 GitHub 链接的 host 是 `github.com`，kind 为 `repo`；
- 没有 `file://`、`javascript:`、相对路径。

## 4. 完成判据

- [ ] 条目数、顺序、标题与原文一致；
- [ ] 所有 URL 可在原文中逐字找到；
- [ ] 同一天多期已用 `slot` 区分；
- [ ] 入账后 `list` 能看到全部条目，且原文已落盘到 `radar/intake/`。
