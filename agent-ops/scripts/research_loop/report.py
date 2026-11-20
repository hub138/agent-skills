"""报告渲染:STATUS/CHANGELOG/REPORT/HTML(方案 9.4 三份 changelog 不混用、第 10 节五区)。

约定:
- 只读 research.db;所有数字一律经 metrics.aggregate 重算(逐用例明细来自
  kind=metrics_imported 事件,缺事件时退回 metrics 表行),不另行维护口径;
- 执行失败/未完成的尝试不参与计分聚合(方案 13.1:执行失败不冒充无收益);
- queued/running/retry_wait 一律显示为"进行中",不显示为已完成;
- HTML 为单文件内联 CSS、五区结构、导航可收起(纯 CSS)、无脚本无前端依赖;
- 页面/正文动态内容统一 html.escape,状态时间取 db 真实事件时间。
"""
from __future__ import annotations

import html
import json
import time
from pathlib import Path

from . import metrics
from .core_types import (
    EXEC_BLOCKED, EXEC_CANCELED, EXEC_FAILED, EXEC_QUEUED, EXEC_RETRY_WAIT,
    EXEC_RUNNING, EXEC_SUCCEEDED, atomic_write_text, now_ts,
)
from .store import open_db

ACTIVE_STATUSES = (EXEC_QUEUED, EXEC_RUNNING, EXEC_RETRY_WAIT)
FINISHED_STATUSES = (EXEC_SUCCEEDED, EXEC_FAILED, EXEC_BLOCKED, EXEC_CANCELED)
DQ_EVENT_PREFIXES = ("data_", "label_", "leakage_", "grade_")
OPS_EVENT_PREFIXES = ("rate_", "retry_", "blocked_", "recovery_", "resume_")
REPORT_FILES = ("STATUS.md", "CHANGELOG.md", "REPORT.md", "report.html")

_HTML_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>research-loop report — %s</title>
<style>
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { font-family: system-ui, -apple-system, "Segoe UI", sans-serif; margin: 0 auto; max-width: 62rem; padding: 0 1rem 3rem; line-height: 1.55; }
h1 { font-size: 1.35rem; margin: 1rem 0 .4rem; }
h2 { font-size: 1.12rem; border-bottom: 1px solid currentColor; padding-bottom: .25rem; }
h3 { font-size: 1rem; margin: .9rem 0 .3rem; }
table { border-collapse: collapse; width: 100%%; margin: .5rem 0; font-size: .92rem; }
th, td { border: 1px solid #949494; padding: .28rem .55rem; text-align: left; vertical-align: top; }
th { background: rgba(127, 127, 127, .14); }
.scroll { overflow-x: auto; }
.nav-toggle { position: absolute; opacity: 0; width: 1px; height: 1px; }
.nav-toggle:checked ~ nav { display: none; }
.nav-toggle:focus-visible + .nav-label { outline: 2px solid #4c9ffe; }
.nav-label { display: inline-block; cursor: pointer; border: 1px solid #949494; border-radius: 4px; padding: .22rem .7rem; margin: .4rem 0; user-select: none; }
nav a { display: inline-block; margin: 0 .9rem .4rem 0; }
.muted { opacity: .78; font-size: .9rem; }
section { margin-top: 1.7rem; scroll-margin-top: 1rem; }
@media (prefers-color-scheme: dark) { th, td, .nav-label { border-color: #6f6f6f; } }
</style>
</head>
<body>
<h1>%s — 研究迭代报告</h1>
<p class="muted">生成时间 %s;所有状态时间取自 research.db 真实事件时间(不用当前请求时间冒充最近进展);自包含单文件,无前端依赖。</p>
<input type="checkbox" id="nav-toggle" class="nav-toggle" checked>
<label class="nav-label" for="nav-toggle">研究目录(点击收起 / 展开)</label>
<nav aria-label="研究目录">
<a href="#goal">1 目标区</a>
<a href="#explore">2 探索区</a>
<a href="#rounds">3 轮次区</a>
<a href="#data-quality">4 数据质量区</a>
<a href="#runs">5 运行区</a>
</nav>
<main>
%s
%s
%s
%s
%s
</main>
</body>
</html>
"""


def _s(v) -> str:
    return "未登记" if v is None else str(v)


def _fmt_num(x, nd=4) -> str:
    return "—" if x is None else "%.*f" % (nd, x)


def _fmt_ts(ts) -> str:
    if not ts:
        return "—"
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(ts)))
    except (TypeError, ValueError):
        return str(ts)


def _md_cell(value) -> str:
    text = "—" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def _brief(text, limit=160) -> str:
    text = str(text)
    return text if len(text) <= limit else text[:limit] + "…"


def _project_id(project) -> str:
    if isinstance(project, str):
        return project
    if isinstance(project, dict):
        ident = project.get("identity")
        if isinstance(ident, dict) and ident.get("project_id"):
            return str(ident["project_id"])
        if project.get("project_id"):
            return str(project["project_id"])
    return "unknown-project"


def _goal_fields(project) -> dict:
    p = project if isinstance(project, dict) else {}
    ident = p.get("identity") if isinstance(p.get("identity"), dict) else {}
    m = p.get("metrics") if isinstance(p.get("metrics"), dict) else {}
    data = p.get("data") if isinstance(p.get("data"), dict) else {}
    ev = p.get("evaluator") if isinstance(p.get("evaluator"), dict) else {}
    iso = p.get("isolation") if isinstance(p.get("isolation"), dict) else {}
    comp = p.get("completion")
    return {
        "project_id": ident.get("project_id") or p.get("project_id")
        or "unknown-project",
        "goal": ident.get("goal"),
        "primary_metric": m.get("primary_metric"),
        "guard_metrics": m.get("guard_metrics") or [],
        "data_version": data.get("version"),
        "manifest": data.get("manifest"),
        "evaluator": ev.get("adapter_id"),
        "isolation_mode": iso.get("mode"),
        "final_gate": comp.get("final_gate") if isinstance(comp, dict) else None,
    }


def _pm_desc(pm) -> str:
    if not isinstance(pm, dict) or not pm.get("metric_id"):
        return "未登记"
    return "%s(direction=%s, threshold=%s, comparison=%s, unit=%s)" % (
        pm.get("metric_id"), pm.get("direction"), pm.get("threshold"),
        pm.get("comparison"), pm.get("unit"))


def _guard_desc(g) -> str:
    if isinstance(g, dict) and g.get("metric_id"):
        return "%s(%s, 容差 %s)" % (g["metric_id"],
                                   g.get("direction", "maximize"),
                                   g.get("non_inferiority_tolerance", 0))
    if isinstance(g, str):
        return g
    return "未登记"


def _experiments(conn):
    return conn.execute(
        "SELECT * FROM experiments ORDER BY created_ts, experiment_id").fetchall()


def _attempts(conn, experiment_id=None):
    if experiment_id is None:
        return conn.execute(
            "SELECT * FROM attempts ORDER BY started_ts, attempt_id").fetchall()
    return conn.execute(
        "SELECT * FROM attempts WHERE experiment_id = ?"
        " ORDER BY started_ts, attempt_id", (experiment_id,)).fetchall()


def _active_attempts(rows):
    return [a for a in rows if a["exec_status"] in ACTIVE_STATUSES]


def _finished_attempts(rows):
    return [a for a in rows if a["exec_status"] in FINISHED_STATUSES]


def _ideas(conn):
    return conn.execute(
        "SELECT * FROM ideas ORDER BY created_ts, idea_id").fetchall()


def _planned_events(conn) -> dict:
    """round.started 事件投影（mechanism/hypothesis/idea/父候选，方案 9.4）。"""
    out = {}
    for row in conn.execute(
            "SELECT data FROM events WHERE kind = 'round.started'"
            " ORDER BY id"):
        try:
            d = json.loads(row["data"])
        except Exception:
            continue
        rid = d.get("round_id")
        if rid:
            out[rid] = {
                "mechanism": d.get("mechanism"),
                "hypothesis": d.get("hypothesis"),
                "idea_id": d.get("idea_id"),
                "parent_candidate": d.get("parent_candidate"),
                "direction": d.get("direction"),
            }
    return out



def _metrics_imported_events(conn) -> dict:
    out = {}
    for row in conn.execute(
            "SELECT data FROM events WHERE kind = 'metrics_imported'"
            " ORDER BY id"):
        try:
            data = json.loads(row["data"])
        except (ValueError, TypeError):
            continue
        aid = data.get("attempt_id") if isinstance(data, dict) else None
        per = data.get("per_metric") if isinstance(data, dict) else None
        if isinstance(aid, str) and isinstance(per, dict):
            out[aid] = per
    return out


def _events_by_prefix(conn, prefixes):
    out = []
    for row in conn.execute("SELECT ts, kind, data FROM events ORDER BY id"):
        if str(row["kind"]).startswith(prefixes):
            out.append({"ts": row["ts"], "kind": row["kind"],
                        "data": row["data"]})
    return out


def _round_counts(conn, experiment_id):
    """一轮实验的计分 counts:metrics_imported 事件明细优先;缺事件时
    退回 db metrics 行(numerator/denominator/unknown_count 形态)。
    两种形态都交给 metrics.aggregate 重算,保证数字全部来自 db。"""
    counts = []
    imported = _metrics_imported_events(conn)
    for a in _attempts(conn, experiment_id):
        if a["exec_status"] != EXEC_SUCCEEDED:
            continue  # 执行失败/未完成的尝试不计分(方案 13.1)
        aid = a["attempt_id"]
        per = imported.get(aid)
        if isinstance(per, dict):
            for mid, c in per.items():
                if not (isinstance(mid, str) and isinstance(c, dict)):
                    continue
                counts.append({
                    "case_id": "%s/%s" % (aid, mid), "metric_id": mid,
                    "tp": c.get("tp") or 0, "fn": c.get("fn") or 0,
                    "fp": c.get("fp") or 0, "unknown": c.get("unknown") or 0,
                })
        else:
            for r in conn.execute(
                    "SELECT metric_id, numerator, denominator, unknown_count"
                    " FROM metrics WHERE attempt_id = ?", (aid,)):
                counts.append({
                    "case_id": aid, "metric_id": r["metric_id"],
                    "numerator": r["numerator"],
                    "denominator": r["denominator"],
                    "unknown_count": r["unknown_count"] or 0,
                })
    return counts


def _detail_sums(counts, mid):
    """该 metric 的 TP/FP/FN/unknown 明细和(仅事件形态可提供)。"""
    items = [c for c in counts if c["metric_id"] == mid and "fn" in c]
    if not items:
        return None
    return (sum(c.get("tp") or 0 for c in items),
            sum(c.get("fp") or 0 for c in items),
            sum(c.get("fn") or 0 for c in items),
            sum(c.get("unknown") or 0 for c in items))


def _current_best(conn, pm) -> str:
    """当前最佳:仅采纳(beneficial/expand)尝试,经 aggregate 重算;
    direction 感知(minimize 取最小,方案 9.1 双源同步修正)。"""
    pm_id = pm.get("metric_id") if isinstance(pm, dict) else None
    if not pm_id:
        return "未配置主指标,无法评估"
    direction = pm.get("direction", "maximize")
    best = None
    for a in _attempts(conn):
        if a["exec_status"] != EXEC_SUCCEEDED:
            continue
        if a["trial_status"] not in ("beneficial", "untested"):
            continue  # 未采纳/退化尝试不冒充最佳（方案 9.1）
        rows = conn.execute(
            "SELECT metric_id, numerator, denominator, unknown_count"
            " FROM metrics WHERE attempt_id = ?", (a["attempt_id"],)).fetchall()
        counts = [{"case_id": a["attempt_id"], "metric_id": r["metric_id"],
                   "numerator": r["numerator"],
                   "denominator": r["denominator"],
                   "unknown_count": r["unknown_count"] or 0} for r in rows]
        rec = metrics.aggregate(counts).get(pm_id)
        if rec and rec["value"] is not None:
            better = (best is None or
                      (rec["value"] > best[0] if direction == "maximize"
                       else rec["value"] < best[0]))
            if better:
                best = (rec["value"], rec["lower_bound"], a["attempt_id"])
    if best is None:
        return "暂无已完成并计分的尝试"
    return "%s value=%s lower_bound=%s(均来自 db 经 aggregate 重算)" % (
        best[2], _fmt_num(best[0]), _fmt_num(best[1]))


def _attempt_line(conn, experiment_id) -> str:
    rows = _attempts(conn, experiment_id)
    if not rows:
        return "无 attempt"
    return ", ".join("%s(%s)" % (a["attempt_id"], a["exec_status"])
                     for a in rows)


def _verdict_lines(conn, experiment_id):
    out = []
    for a in _attempts(conn, experiment_id):
        out.append("%s: trial=%s/exec=%s" % (
            a["attempt_id"], a["trial_status"], a["exec_status"]))
    for d in conn.execute(
            "SELECT d.decision AS decision, d.reason AS reason,"
            " a.attempt_id AS attempt_id FROM decisions d"
            " LEFT JOIN attempts a ON a.attempt_id = d.attempt_id"
            " WHERE a.experiment_id = ? ORDER BY d.ts", (experiment_id,)):
        out.append("%s → %s(%s)" % (
            d["attempt_id"], d["decision"], d["reason"] or "无理由"))
    return out


def _runs_section(conn):
    """STATUS.md 运行区:queued/running/retry_wait 一律列进行中(方案 10)。"""
    rows = _attempts(conn)
    lines = ["## 运行区", "",
             "### 进行中(queued/running/retry_wait,未完成,不算已分析)", ""]
    active = _active_attempts(rows)
    if active:
        lines.append("| attempt | experiment | stage | 执行状态 | 证据状态 | 开始时间 |")
        lines.append("|---|---|---|---|---|---|")
        for a in active:
            lines.append("| %s | %s | %s | %s | %s | %s |" % (
                _md_cell(a["attempt_id"]), _md_cell(a["experiment_id"]),
                _md_cell(a["stage"]), _md_cell(a["exec_status"]),
                _md_cell(a["evidence_status"]), _md_cell(_fmt_ts(a["started_ts"]))))
    else:
        lines.append("暂无进行中尝试。")
    lines += ["", "### 已结束(succeeded/failed/blocked/canceled)", ""]
    finished = _finished_attempts(rows)
    if finished:
        lines.append("| attempt | experiment | stage | 执行状态 | 实验状态 | 结束时间 |")
        lines.append("|---|---|---|---|---|---|")
        for a in finished:
            lines.append("| %s | %s | %s | %s | %s | %s |" % (
                _md_cell(a["attempt_id"]), _md_cell(a["experiment_id"]),
                _md_cell(a["stage"]), _md_cell(a["exec_status"]),
                _md_cell(a["trial_status"]), _md_cell(_fmt_ts(a["finished_ts"]))))
    else:
        lines.append("暂无已结束尝试。")
    return lines


def _render_status_conn(conn, project) -> str:
    g = _goal_fields(project)
    lines = ["# STATUS — %s" % g["project_id"], "", "## 目标区", ""]
    lines.append("- 研究目标: %s" % (g["goal"] or "未登记"))
    lines.append("- 主指标: %s" % _pm_desc(g["primary_metric"]))
    lines.append("- guard 门槛: %s" % (
        ", ".join(_guard_desc(x) for x in g["guard_metrics"]) or "未登记"))
    lines.append("- 数据版本: %s;manifest: %s" % (
        g["data_version"] or "未登记", g["manifest"] or "未登记"))
    lines.append("- Judge/评估器: %s" % (g["evaluator"] or "未登记"))
    lines.append("- 隔离模式: %s;最终验收: %s" % (
        g["isolation_mode"] or "未登记", g["final_gate"] or "未登记"))
    lines.append("- 当前最佳: %s" % _current_best(conn, g["primary_metric"]))
    lines.append("")
    lines.extend(_runs_section(conn))
    return "\n".join(lines).rstrip() + "\n"


def render_status(db_path, project) -> str:
    """STATUS.md:目标区 + 运行区;queued 不显示为已完成(方案 10)。

    project 接受 load_project 的契约 dict 或 project_id 字符串。
    """
    conn = open_db(db_path)
    try:
        return _render_status_conn(conn, project)
    finally:
        conn.close()


def _render_changelog_conn(conn, project) -> str:
    g = _goal_fields(project)
    planned = _planned_events(conn)
    lines = ["# CHANGELOG — %s" % g["project_id"], "",
             "逐轮实验台账,自动从 research.db 生成(方案 9.4),不能手改制造结果。",
             ""]
    exps = _experiments(conn)
    if not exps:
        lines.append("暂无实验轮次。")
        return "\n".join(lines).rstrip() + "\n"
    for exp in exps:
        eid = exp["experiment_id"]
        info = planned.get(eid) or {}
        counts = _round_counts(conn, eid)
        agg = metrics.aggregate(counts) if counts else {}
        lines.append("## %s(stage=%s,创建 %s)" % (
            eid, exp["stage"], _fmt_ts(exp["created_ts"])))
        lines.append("")
        lines.append("- 探索目标/机制: %s" % (info.get("mechanism") or "未登记"))
        lines.append("- 机制假设: %s" % (info.get("hypothesis") or "未登记"))
        lines.append("- 来源技术点/idea: %s" % (info.get("idea_id") or "未登记"))
        lines.append("- 父候选版本: %s" % (info.get("parent_candidate") or "未登记"))
        lines.append("- 数据版本: %s;Judge 摘要: %s" % (
            exp["data_version"], exp["evaluator_digest"]))
        lines.append("- 对照批: %s" % _attempt_line(conn, eid))
        if agg:
            lines.append("- 逐指标计数与统计(共 %s 个计分来源,均经 aggregate 重算):"
                         % len(counts))
            for mid in sorted(agg):
                rec = agg[mid]
                detail = _detail_sums(counts, mid)
                if detail is not None:
                    tp_s, fp_s, fn_s, un_s = detail
                else:
                    tp_s, fp_s, fn_s = rec["numerator"], "—", "—"
                    un_s = rec["unknown_count"]
                lines.append("  - %s: TP=%s FP=%s FN=%s unknown=%s;"
                             "value=%s lower=%s(%s)" % (
                                 _md_cell(mid), tp_s, fp_s, fn_s, un_s,
                                 _fmt_num(rec["value"]),
                                 _fmt_num(rec["lower_bound"]),
                                 rec["stat_method"]))
        else:
            lines.append("- 指标: 无计分数据(执行失败/未导入的尝试不计分,方案 13.1)")
        verdicts = _verdict_lines(conn, eid)
        lines.append("- 判定: %s" % (
            "; ".join(_md_cell(v) for v in verdicts) if verdicts else "未判定"))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _render_report_md_conn(conn, project) -> str:
    """REPORT.md 三段式(方案 10):规划进展 / 问题波折与解决证据 / 后续计划。"""
    g = _goal_fields(project)
    lines = ["# REPORT — %s" % g["project_id"], ""]

    lines.append("## 一、整体规划与进展")
    lines.append("")
    lines.append("- 研究目标: %s" % (g["goal"] or "未登记"))
    lines.append("- 主指标: %s" % _pm_desc(g["primary_metric"]))
    lines.append("- guard 门槛: %s" % (
        ", ".join(_guard_desc(x) for x in g["guard_metrics"]) or "未登记"))
    lines.append("- 数据版本: %s;Judge: %s;隔离: %s;最终验收: %s" % (
        g["data_version"] or "未登记", g["evaluator"] or "未登记",
        g["isolation_mode"] or "未登记", g["final_gate"] or "未登记"))
    lines.append("- 当前最佳: %s" % _current_best(conn, g["primary_metric"]))
    lines.append("")
    lines.append("轮次概览(全部数字来自 research.db,经 metrics.aggregate 重算):")
    lines.append("")
    lines.append("| experiment | stage | attempts | 实验状态 |")
    lines.append("|---|---|---|---|")
    exps = _experiments(conn)
    if exps:
        for exp in exps:
            atts = _attempts(conn, exp["experiment_id"])
            trials = sorted({a["trial_status"] for a in atts}) or ["-"]
            lines.append("| %s | %s | %s | %s |" % (
                _md_cell(exp["experiment_id"]), _md_cell(exp["stage"]),
                len(atts), _md_cell(",".join(trials))))
    else:
        lines.append("| — | 暂无实验轮次 | 0 | — |")
    lines.append("")

    lines.append("## 二、问题波折与解决证据")
    lines.append("")
    failed = [a for a in _attempts(conn)
              if a["exec_status"] in (EXEC_FAILED, EXEC_BLOCKED, EXEC_CANCELED)]
    if failed:
        lines.append("失败/阻塞尝试(执行失败不计分,不冒充无收益,方案 13.1):")
        lines.append("")
        lines.append("| attempt | experiment | 执行状态 | 证据状态 | 结束时间 |")
        lines.append("|---|---|---|---|---|")
        for a in failed:
            lines.append("| %s | %s | %s | %s | %s |" % (
                _md_cell(a["attempt_id"]), _md_cell(a["experiment_id"]),
                _md_cell(a["exec_status"]), _md_cell(a["evidence_status"]),
                _md_cell(_fmt_ts(a["finished_ts"]))))
    else:
        lines.append("暂无失败/阻塞尝试。")
    lines.append("")
    decs = conn.execute(
        "SELECT d.decision AS decision, d.reason AS reason, d.ts AS ts,"
        " a.attempt_id AS attempt_id FROM decisions d"
        " LEFT JOIN attempts a ON a.attempt_id = d.attempt_id"
        " ORDER BY d.ts").fetchall()
    if decs:
        lines.append("机器门禁决定(保留完整失败史,不删):")
        lines.append("")
        for d in decs:
            lines.append("- %s → %s(%s)" % (
                _md_cell(d["attempt_id"]) if d["attempt_id"] else "—",
                _md_cell(d["decision"]), _md_cell(d["reason"] or "无理由")))
    else:
        lines.append("暂无机器门禁决定。")
    lines.append("")

    lines.append("## 三、后续目标、待验证假设与资源计划")
    lines.append("")
    active = _active_attempts(_attempts(conn))
    if active:
        lines.append("进行中(未完成,不显示为已完成):")
        lines.append("")
        for a in active:
            lines.append("- %s(%s,证据 %s)" % (
                _md_cell(a["attempt_id"]), _md_cell(a["exec_status"]),
                _md_cell(a["evidence_status"])))
    else:
        lines.append("暂无进行中任务。")
    lines.append("")
    ideas = [i for i in _ideas(conn)
             if i["status"] not in ("accepted", "rejected", "rolled_back")]
    if ideas:
        lines.append("待验证假设(ideas 台账):")
        lines.append("")
        for i in ideas:
            lines.append("- %s[%s] %s — %s(尝试 %s/收益 %s)" % (
                _md_cell(i["idea_id"]), _md_cell(i["kind"]),
                _md_cell(i["title"]), _md_cell(i["status"]),
                i["tries"], i["wins"]))
    else:
        lines.append("暂无排队中的待验证假设。")
    lines.append("")
    lines.append("资源计划:重试预算、扩展批与终测须满足方案 12 阶段 D/E 门禁;"
                 "费用未知不得报零(方案 9.3)。")
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _metric_rows_html(counts) -> str:
    agg = metrics.aggregate(counts) if counts else {}
    if not agg:
        return "<p>无计分数据(执行失败或未导入的尝试不计分)。</p>"
    rows = "".join(
        "<tr><td>%s</td><td>%s</td><td>%s</td><td>%s/%s</td><td>%s</td>"
        "<td>%s</td></tr>" % (
            html.escape(str(mid)), _fmt_num(agg[mid]["value"]),
            _fmt_num(agg[mid]["lower_bound"]), agg[mid]["numerator"],
            agg[mid]["denominator"], agg[mid]["unknown_count"],
            html.escape(str(agg[mid]["stat_method"])))
        for mid in sorted(agg))
    return ('<div class="scroll"><table><thead><tr><th>metric</th><th>value</th>'
            '<th>Wilson 下界</th><th>numerator/denominator</th><th>unknown</th>'
            '<th>stat_method</th></tr></thead><tbody>%s</tbody></table></div>'
            % rows)


def _tfpu_html(counts) -> str:
    agg = metrics.aggregate(counts) if counts else {}
    parts = []
    for mid in sorted(agg):
        detail = _detail_sums(counts, mid)
        if detail is not None:
            parts.append("%s: TP=%s FP=%s FN=%s unknown=%s" % (
                mid, detail[0], detail[1], detail[2], detail[3]))
        else:
            parts.append("%s: TP=%s FP/FN=— unknown=%s" % (
                mid, agg[mid]["numerator"], agg[mid]["unknown_count"]))
    if not parts:
        return ""
    return '<p class="muted">%s</p>' % html.escape("; ".join(parts))


def _run_rows_html(rows, finished) -> str:
    if not rows:
        return "<p>暂无。</p>"
    if finished:
        head = ("<th>attempt</th><th>experiment</th><th>stage</th>"
                "<th>执行状态</th><th>实验状态</th><th>结束时间</th>")
        body = "".join(
            "<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td>"
            "<td>%s</td></tr>" % (
                html.escape(str(a["attempt_id"])),
                html.escape(str(a["experiment_id"])),
                html.escape(str(a["stage"])),
                html.escape(str(a["exec_status"])),
                html.escape(str(a["trial_status"])),
                html.escape(_fmt_ts(a["finished_ts"])))
            for a in rows)
    else:
        head = ("<th>attempt</th><th>experiment</th><th>stage</th>"
                "<th>执行状态</th><th>证据状态</th><th>开始时间</th>")
        body = "".join(
            "<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td>"
            "<td>%s</td></tr>" % (
                html.escape(str(a["attempt_id"])),
                html.escape(str(a["experiment_id"])),
                html.escape(str(a["stage"])),
                html.escape(str(a["exec_status"])),
                html.escape(str(a["evidence_status"])),
                html.escape(_fmt_ts(a["started_ts"])))
            for a in rows)
    return ('<div class="scroll"><table><thead><tr>%s</tr></thead><tbody>%s'
            '</tbody></table></div>' % (head, body))


def _render_html_conn(conn, project) -> str:
    """五区单文件 HTML(方案 10):目标/探索/轮次/数据质量/运行;导航可收起。"""
    g = _goal_fields(project)

    goal_items = [
        ("研究目标", g["goal"]),
        ("主指标", _pm_desc(g["primary_metric"])),
        ("guard 门槛", ", ".join(_guard_desc(x) for x in g["guard_metrics"])),
        ("数据版本", g["data_version"]),
        ("manifest", g["manifest"]),
        ("Judge/评估器", g["evaluator"]),
        ("隔离模式", g["isolation_mode"]),
        ("最终验收", g["final_gate"]),
        ("当前最佳", _current_best(conn, g["primary_metric"])),
    ]
    goal_rows = "".join(
        "<tr><th>%s</th><td>%s</td></tr>" % (html.escape(str(k)), html.escape(_s(v)))
        for k, v in goal_items)
    goal_html = ('<section id="goal">'
                 '<h2>1 目标区(指标、阈值、数据/Judge 版本、基线、当前最佳)</h2>'
                 '<table><tbody>%s</tbody></table></section>' % goal_rows)

    ideas = _ideas(conn)
    if ideas:
        idea_rows = "".join(
            "<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td>"
            "<td>%s/%s</td></tr>" % (
                html.escape(str(r["idea_id"])), html.escape(str(r["kind"])),
                html.escape(str(r["title"])), html.escape(_s(r["direction"])),
                html.escape(str(r["status"])), r["tries"], r["wins"])
            for r in ideas)
        explore_html = ('<section id="explore">'
                        '<h2>2 探索区(知识上下文 / 提示词工程 / 用例正确性)</h2>'
                        '<div class="scroll"><table><thead><tr><th>idea_id</th>'
                        '<th>类别</th><th>标题</th><th>方向</th><th>状态</th>'
                        '<th>尝试/收益</th></tr></thead><tbody>%s</tbody>'
                        '</table></div></section>' % idea_rows)
    else:
        explore_html = ('<section id="explore">'
                        '<h2>2 探索区(知识上下文 / 提示词工程 / 用例正确性)</h2>'
                        '<p>暂无技术点台账(ideas)。</p></section>')

    planned = _planned_events(conn)
    blocks = []
    for exp in _experiments(conn):
        eid = exp["experiment_id"]
        info = planned.get(eid) or {}
        counts = _round_counts(conn, eid)
        verdicts = _verdict_lines(conn, eid)
        blocks.append(
            '<div class="round" id="exp-%s">'
            '<h3>%s(stage=%s,创建 %s)</h3>'
            '<p>机制: %s;假设: %s;来源: %s;父候选: %s;'
            '数据版本: %s;Judge 摘要: %s;对照批: %s</p>'
            '%s%s%s'
            '<p class="muted">判定: %s</p>'
            '</div>' % (
                html.escape(eid, quote=True),
                html.escape(eid), html.escape(str(exp["stage"])),
                html.escape(_fmt_ts(exp["created_ts"])),
                html.escape(_s(info.get("mechanism"))),
                html.escape(_s(info.get("hypothesis"))),
                html.escape(_s(info.get("idea_id"))),
                html.escape(_s(info.get("parent_candidate"))),
                html.escape(str(exp["data_version"])),
                html.escape(str(exp["evaluator_digest"])),
                html.escape(_attempt_line(conn, eid)),
                _tfpu_html(counts),
                _metric_rows_html(counts),
                html.escape("; ".join(verdicts) or "未判定"),
                html.escape(eid, quote=True)))
    rounds_html = ('<section id="rounds">'
                   '<h2>3 轮次区(基线→对照→复验→扩展→终测,点开查看证据)</h2>%s'
                   '</section>' % ("".join(blocks) or "<p>暂无实验轮次。</p>"))

    dq_events = _events_by_prefix(conn, DQ_EVENT_PREFIXES)
    dq_head = ('<h2>4 数据质量区(精标/粗标/争议、split、泄漏检查、覆盖率)</h2>')
    if dq_events:
        items = "".join("<li>%s · %s:%s</li>" % (
            html.escape(_fmt_ts(e["ts"])), html.escape(e["kind"]),
            html.escape(_brief(e["data"]))) for e in dq_events)
        dq_html = ('<section id="data-quality">%s<ul>%s</ul></section>'
                   % (dq_head, items))
    else:
        dq_html = ('<section id="data-quality">%s'
                   '<p>暂无数据质量事件(等待数据审计登记;精标/粗标/争议与'
                   '泄漏检查结果在此显示)。</p></section>' % dq_head)

    rows = _attempts(conn)
    ops_events = _events_by_prefix(conn, OPS_EVENT_PREFIXES)
    ops_items = "".join("<li>%s · %s:%s</li>" % (
        html.escape(_fmt_ts(e["ts"])), html.escape(e["kind"]),
        html.escape(_brief(e["data"]))) for e in ops_events) \
        or "<li>暂有限流/阻塞/重试/恢复事件。</li>"
    runs_html = ('<section id="runs">'
                 '<h2>5 运行区(进行中任务、限流、阻塞、重试与恢复)</h2>'
                 '<h3>进行中(queued/running/retry_wait 不显示为已完成)</h3>%s'
                 '<h3>已结束</h3>%s'
                 '<h3>运维事件(限流/阻塞/重试/恢复)</h3><ul>%s</ul></section>'
                 % (_run_rows_html(_active_attempts(rows), finished=False),
                    _run_rows_html(_finished_attempts(rows), finished=True),
                    ops_items))

    pid = html.escape(str(g["project_id"]))
    return _HTML_PAGE % (pid, pid, html.escape(_fmt_ts(now_ts())),
                         goal_html, explore_html, rounds_html,
                         dq_html, runs_html)


def render_report(db_path, project, out_dir) -> dict:
    """生成 STATUS.md/CHANGELOG.md/REPORT.md/report.html(方案 9.4/10)。

    四份文件均经 core_types.atomic_write_text 原子写入 out_dir;
    返回 {"files": {文件名: 落盘路径}, "project_id", "experiments",
    "attempts", "generated_ts"}。
    """
    conn = open_db(db_path)
    try:
        g = _goal_fields(project)
        texts = {
            "STATUS.md": _render_status_conn(conn, project),
            "CHANGELOG.md": _render_changelog_conn(conn, project),
            "REPORT.md": _render_report_md_conn(conn, project),
            "report.html": _render_html_conn(conn, project),
        }
        out = Path(out_dir)
        files = {}
        for name in REPORT_FILES:
            path = out / name
            atomic_write_text(str(path), texts[name])
            files[name] = str(path)
        return {
            "files": files,
            "project_id": g["project_id"],
            "experiments": len(_experiments(conn)),
            "attempts": len(_attempts(conn)),
            "generated_ts": now_ts(),
        }
    finally:
        conn.close()
