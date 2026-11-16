#!/usr/bin/env python3
"""技术雷达子功能的唯一命令行入口。

设计：确定性的事（解析、入账、clone、清理、渲染）由脚本做；判断的事
（相关性、借鉴价值、落地方式）由 AI 按 radar/prompts/ 的提示词做。脚本从不
调用模型，因此可以安全地在 cron / 子 agent / 人工三种场景下重复执行。

常用：
  radar_cli.py intake --file brief.md --date 2026-11-16
  radar_cli.py intake --from-dir ~/tech-radar --latest
  radar_cli.py next
  radar_cli.py workspace --candidate 3
  radar_cli.py record --candidate 3 --report radar/analyses/2026-11-16/x.md \
      --verdict adapt --relevance 4 --reason "..."
  radar_cli.py applied --candidate 3 --files scripts/x.py --summary "..." \
      --rationale "..." --tests '{"pytest":"68 passed"}'
  radar_cli.py ledger
  radar_cli.py clean --days 3 --max-mb 500
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import radar_store as store  # noqa: E402
import radar_workspace as ws  # noqa: E402


def _out(obj, as_json: bool) -> None:
    if as_json:
        print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (list, dict)):
                print("%s: %s" % (k, json.dumps(v, ensure_ascii=False)))
            else:
                print("%s: %s" % (k, v))
    else:
        print(obj)


def _date_from_name(path: Path) -> str:
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", path.name)
    if m:
        return "%s-%s-%s" % m.groups()
    return datetime.now().strftime("%Y-%m-%d")


def _brief_files(repo: Path, latest: bool = False) -> list[Path]:
    """列出雷达仓库里的简报。默认收全部（同一天多期都能进），--latest 只收最新一份。"""
    for sub in ("data/briefs", "briefs", "data"):
        d = repo / sub
        if not d.is_dir():
            continue
        dated = sorted(f for f in d.glob("*.md")
                       if re.search(r"\d{4}-\d{2}-\d{2}", f.name))
        if dated:
            return dated[-1:] if latest else dated
    return []


def _read_text(src: str | None) -> str:
    if src in (None, "-"):
        return sys.stdin.read()
    return Path(src).read_text(encoding="utf-8")


def cmd_init(args) -> int:
    conn = store.connect()
    store.init_db(conn)
    out = {"db": str(store.db_path()), "cache": str(store.cache_root()),
           "ledger": str(store.LEDGER_PATH)}
    _out(out, args.json)
    return 0


def cmd_intake(args) -> int:
    conn = store.connect()
    store.init_db(conn)
    today = datetime.now().strftime("%Y-%m-%d")
    batches: list[dict] = []

    if args.json_file:
        payload = json.loads(Path(args.json_file).read_text(encoding="utf-8"))
        batches.append({
            "text": payload.get("raw") or json.dumps(payload, ensure_ascii=False),
            "date": args.date or payload.get("date") or today,
            "title": args.title or payload.get("title", ""),
            "source": "json", "src_path": args.json_file,
            "items": payload.get("items"),
            "slot": args.slot or payload.get("slot", ""),
        })
    elif args.from_dir:
        files = _brief_files(Path(args.from_dir).expanduser(), args.latest)
        if not files:
            raise SystemExit("没找到带日期的简报 md（找 data/briefs/*.md）")
        by_date: dict[str, list[Path]] = {}
        for f in files:
            by_date.setdefault(_date_from_name(f), []).append(f)
        for date, group in sorted(by_date.items()):
            for idx, f in enumerate(sorted(group), 1):
                auto_slot = "%02d" % idx if len(group) > 1 else ""
                batches.append({
                    "text": f.read_text(encoding="utf-8"),
                    "date": args.date or date,
                    "title": args.title or "",
                    "source": "tech-radar", "src_path": str(f),
                    "items": None, "slot": args.slot or auto_slot,
                })
    else:
        batches.append({
            "text": _read_text(args.file), "date": args.date or today,
            "title": args.title or "", "source": args.source,
            "src_path": args.file or "stdin", "items": None, "slot": args.slot,
        })

    if args.dry_run:
        all_items = []
        for b in batches:
            items = b["items"] if b["items"] is not None else store.parse_brief(b["text"])
            all_items.extend(items)
        _out({"count": len(all_items), "batches": len(batches),
              "items": all_items}, args.json)
        return 0

    results = []
    out_dir = store.RADAR_DIR / "intake"
    out_dir.mkdir(parents=True, exist_ok=True)
    for b in batches:
        try:
            res = store.ingest_brief(
                conn, b["text"], brief_date=b["date"], slot=b["slot"],
                title=b["title"], source=b["source"],
                source_path=b["src_path"], items=b["items"])
        except ValueError as exc:
            print("intake 失败：%s（%s）" % (exc, b["src_path"]), file=sys.stderr)
            return 2
        raw_out = out_dir / ("%s-%s.md" % (b["date"], res["brief_id"]))
        if not res["duplicate"]:
            raw_out.write_text(
                b["text"] if b["text"].endswith("\n") else b["text"] + "\n",
                encoding="utf-8")
            # 台账来源必须是仓库内路径；/tmp 会被清理，不能作为追溯依据。
            conn.execute("UPDATE briefs SET source_path=? WHERE id=?",
                         (store.rel(raw_out), res["brief_id"]))
            conn.commit()
        res["raw_path"] = store.rel(raw_out)
        res["slot"] = b["slot"]
        results.append(res)
    _out({"batches": len(results), "results": results}
         if len(results) != 1 else results[0], args.json)
    return 0


def cmd_triage(args) -> int:
    conn = store.connect()
    store.init_db(conn)
    if args.candidate:
        infos = [store.triage_candidate(conn, args.candidate)]
    else:
        infos = store.triage_pending(conn, force=args.force)
    if args.json:
        _out({"count": len(infos), "items": infos}, True)
    else:
        for i in infos:
            print("#%-3d %-6s score=%-3d %s" % (
                i["candidate_id"], i["route"], i["score"], i["reason"]))
        if not infos:
            print("没有待分诊的候选（用 --force 重新打分）")
    return 0


def cmd_list(args) -> int:
    conn = store.connect()
    store.init_db(conn)
    rows = store.list_candidates(conn, status=args.status, brief=args.brief,
                                 route=args.route)
    if not args.json:
        print("%-4s %-11s %-6s %-6s %-3s %-7s %s" %
              ("#", "日期", "状态", "路由", "相", "结论", "条目"))
    for r in rows:
        if args.json:
            print(json.dumps(r, ensure_ascii=False))
        else:
            print("%-4d %-11s %-6s %-6s %-3s %-7s %s" % (
                r["id"], r["brief_date"], r["status"],
                r.get("triage_route") or "-",
                r["relevance"] if r["relevance"] is not None else "-",
                r["verdict"] or "-", r["title"][:60]))
    return 0


def cmd_next(args) -> int:
    conn = store.connect()
    store.init_db(conn)
    row = store.take_next(conn, include_skip=args.force)
    if not row:
        _out({"remaining": 0,
              "note": "没有可领取的候选（skip 条目需 --force）"}, args.json)
        return 0
    row["remaining"] = len(store.list_candidates(conn, status="new"))
    _out(row, args.json)
    return 0


def _candidate(conn, cid: int) -> dict:
    row = conn.execute("SELECT * FROM candidates WHERE id=?", (cid,)).fetchone()
    if not row:
        raise SystemExit("候选 %s 不存在" % cid)
    return dict(row)


def cmd_workspace(args) -> int:
    conn = store.connect()
    store.init_db(conn)
    cand = _candidate(conn, args.candidate)
    if not cand["url"]:
        raise SystemExit("候选 %s 没有 URL，无法 clone" % args.candidate)
    if cand.get("triage_route") == "skip" and not args.force:
        raise SystemExit(
            "候选 %s 分诊为 skip（%s）。确认要读请加 --force。" % (
                args.candidate, cand.get("triage_reason") or "无理由"))
    res = ws.ensure_workspace(cand["url"], store.cache_root(),
                              max_mb=args.max_mb)
    if res.get("ok"):
        store.record_workspace(conn, args.candidate, path=res["path"],
                               commit_sha=res["commit_sha"], nbytes=res["bytes"])
        # 只为「还没分析」的候选推进状态；已 analyzed/applied 的重新 clone 不能把
        # 结论退回去（补读代码时很常见）。
        if cand["status"] in ("new", "screened"):
            store.set_status(conn, args.candidate, "workspace")
        res["path_rel"] = store.rel(Path(res["path"]))
    _out(res, args.json)
    return 0 if res.get("ok") else 1


def cmd_record(args) -> int:
    conn = store.connect()
    store.init_db(conn)
    report = Path(args.report)
    if not report.exists():
        raise SystemExit("分析报告不存在：%s（先写报告再入账）" % report)
    cand = _candidate(conn, args.candidate)
    override = ""
    if (cand.get("triage_route") == "skip"
            and args.verdict in ("adopt", "adapt")):
        override = args.reason or "深读后推翻 skip 分诊"
    store.record_analysis(
        conn, args.candidate, report_path=store.rel(report),
        verdict=args.verdict,
        mechanisms=args.mechanism or [], evidence=args.evidence or [],
        cost=args.cost, risk=args.risk, relevance=args.relevance,
        reason=args.reason, override_reason=override)
    _out({"candidate": args.candidate, "verdict": args.verdict,
          "report": store.rel(report)}, args.json)
    return 0


def cmd_applied(args) -> int:
    conn = store.connect()
    store.init_db(conn)
    store.record_change(
        conn, args.candidate, files=args.files or [],
        summary=args.summary, rationale=args.rationale,
        diffstat=args.diffstat, gate=json.loads(args.tests) if args.tests else {},
        commit_sha=args.commit)
    _out({"candidate": args.candidate, "files": args.files,
          "commit": args.commit}, args.json)
    return 0


def cmd_events(args) -> int:
    conn = store.connect()
    store.init_db(conn)
    rows = store.events_by_kind(conn, args.kind, args.limit)
    if args.json:
        _out({"count": len(rows), "events": rows}, True)
    else:
        for r in rows:
            print("%s %-18s %s" % (r["ts"], r["kind"], r["detail"][:140]))
    return 0


def cmd_ledger(args) -> int:
    conn = store.connect()
    store.init_db(conn)
    text = store.render_ledger(conn)
    if args.json:
        _out(store.stats(conn), True)
    else:
        print("台账已渲染：%s（%d 字符）" % (store.LEDGER_PATH, len(text)))
    return 0


def cmd_status(args) -> int:
    conn = store.connect()
    store.init_db(conn)
    data = store.stats(conn)
    data["disk"] = ws.disk_report(store.cache_root())
    data["recent"] = store.recent_events(conn, 10)
    data["db"] = str(store.db_path())
    _out(data, args.json)
    return 0


def cmd_clean(args) -> int:
    conn = store.connect()
    store.init_db(conn)
    targets = store.clean_candidates(conn, args.days)
    ttl_count = len(targets)
    if args.max_mb is not None:
        # TTL 之外再按容量兜底：把仍在使用但最旧的工作区排到后面
        extra = [dict(r) for r in conn.execute(
            "SELECT path, bytes FROM workspaces WHERE cleaned_at IS NULL "
            "ORDER BY last_seen_at")]
        seen = {t["path"] for t in targets}
        targets += [e for e in extra if e["path"] not in seen]
    res = ws.clean(store.cache_root(), targets, max_mb=args.max_mb,
                   ttl_count=ttl_count, dry_run=args.dry_run)
    if res["removed"] and not args.dry_run:
        store.mark_cleaned(conn, res["removed"])
    _out(res, args.json)
    return 0


def build_parser() -> argparse.ArgumentParser:
    # allow_abbrev=False 是必需的：argparse 默认允许前缀匹配，
    # `--json` 会被当成 `--json-file` 的缩写而报 "expected one argument"（实测踩过）。
    # --json 挂在每个子命令上（`status --json`），主命令不设，避免两处默认值互相覆盖。
    ap = argparse.ArgumentParser(description="agent-ops 技术雷达子功能",
                                 allow_abbrev=False)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def new(name: str, help_text: str) -> argparse.ArgumentParser:
        p = sub.add_parser(name, help=help_text, allow_abbrev=False)
        p.add_argument("--json", action="store_true", help="机器可读输出")
        return p

    p = new("init", "建库")
    p.set_defaults(func=cmd_init)

    p = new("intake", "收一期简报")
    p.add_argument("--file", help="简报 md 路径，- 表示 stdin")
    p.add_argument("--from-dir", help="tech-radar 仓库根，配合 --latest")
    p.add_argument("--latest", action="store_true", help="取该仓库最新一期")
    p.add_argument("--json-file", help="格式识别失败时显式给条目 JSON")
    p.add_argument("--date", help="YYYY-MM-DD，默认今天或文件名日期")
    p.add_argument("--slot", default="",
                   help="同一天多期时区分批次，如 11:00 / 15:00")
    p.add_argument("--title", default="", help="简报标题")
    p.add_argument("--source", default="paste", help="来源标记")
    p.add_argument("--dry-run", action="store_true", help="只解析不入库")
    p.set_defaults(func=cmd_intake)

    p = new("triage", "确定性分诊：deep / brief / skip")
    p.add_argument("--candidate", type=int, help="只分诊这一条")
    p.add_argument("--force", action="store_true", help="重新打分（含已分诊）")
    p.set_defaults(func=cmd_triage)

    p = new("list", "看候选")
    p.add_argument("--status", choices=["new", "screened", "workspace",
                                        "analyzed", "applied", "skipped"])
    p.add_argument("--brief", help="按日期过滤，YYYY-MM-DD")
    p.add_argument("--route", choices=["deep", "brief", "skip"])
    p.set_defaults(func=cmd_list)

    p = new("next", "原子领取一条待分析（默认跳过 skip）")
    p.add_argument("--force", action="store_true", help="允许领取 skip 条目复核")
    p.set_defaults(func=cmd_next)

    p = new("workspace", "clone/刷新候选仓库")
    p.add_argument("--candidate", type=int, required=True)
    p.add_argument("--max-mb", type=int, default=ws.MAX_MB_DEFAULT)
    p.add_argument("--force", action="store_true", help="允许 clone skip 条目")
    p.set_defaults(func=cmd_workspace)

    p = new("record", "登记一条分析结论")
    p.add_argument("--candidate", type=int, required=True)
    p.add_argument("--report", required=True, help="分析 md 路径")
    p.add_argument("--verdict", required=True, choices=list(store.VERDICT_WORDS))
    p.add_argument("--relevance", type=int, choices=[1, 2, 3, 4, 5])
    p.add_argument("--reason", default="")
    p.add_argument("--mechanism", action="append", help="可重复")
    p.add_argument("--evidence", action="append", help="path:line 或 URL，可重复")
    p.add_argument("--cost", default="")
    p.add_argument("--risk", default="")
    p.set_defaults(func=cmd_record)

    p = new("applied", "登记一次已落地变更")
    p.add_argument("--candidate", type=int, required=True)
    p.add_argument("--files", nargs="+", required=True)
    p.add_argument("--summary", required=True)
    p.add_argument("--rationale", required=True)
    p.add_argument("--diffstat", default="")
    p.add_argument("--tests", help='JSON，如 {"pytest":"68 passed"}')
    p.add_argument("--commit", default="")
    p.set_defaults(func=cmd_applied)

    p = new("ledger", "渲染 radar/LEDGER.md")
    p.set_defaults(func=cmd_ledger)

    p = new("events", "按类型查审计事件（claim / triage_override / ...）")
    p.add_argument("--kind", help="事件类型")
    p.add_argument("--limit", type=int, default=50)
    p.set_defaults(func=cmd_events)

    p = new("status", "汇总 + 磁盘")
    p.set_defaults(func=cmd_status)

    p = new("clean", "清理工作区")
    p.add_argument("--days", type=int, default=3, help="超过 N 天未用则删")
    p.add_argument("--max-mb", type=int, default=None,
                   help="缓存总容量上限，超出按最旧删")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_clean)
    return ap


def main(argv=None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
