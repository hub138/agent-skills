#!/usr/bin/env python3
"""死士检查通用件：对健康检查的健康检查（配置驱动，任何项目一份 JSON 即可用）。

设计原则（来自 2026-11-13 业务项目 实战）：
- 只信客观事实：进程表 / DB 时间戳与计数 / 日志 mtime，不信任被监控对象自己的状态输出；
- 「没输入」不等于「停摆」：可判定队列必须与业务口径一致（如排除无 diff 条目），
  否则会像 业务项目 06:00/08:00 那样每 2h 发一次假告警；
- 正常不发通知只写日志（防刷屏），异常才发；阈值全置 0 = 自检演练模式；
- 通知通道可插拔：notify_cmd 里用 {msg} 占位符接任何发送命令，不绑企微。

用法：
    python3 deadman.py --config deadman.json            # 巡检一轮
    python3 deadman.py --config deadman.json --dry-run  # 只打印，不发送不写日志

check 类型：
    process_alive  进程表里有匹配 cmdline 的进程
    db_freshness   SQL 取 MAX(时间戳)，超龄判停摆；可配 gate_sql（队列空则视为正常空闲）
    db_output      SQL 计数，窗口内新增=0 判停摆；可配 require_process（进程死了单独报）
    queue_stall    可判定数>0 且窗口内判定=0 判停摆（口径必须与业务 pending() 一致）
    log_freshness  日志 glob 最新 mtime 超龄且进程仍存活判空转
    notify_silence 通知日志/发送标记超龄无记录则提醒（通知链路自己死了也能感知）

DB 支持 mysql（延迟导入 pymysql）与 sqlite（内置），配置见 templates/deadman.example.json。
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

TS_RE = re.compile(r"(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})")
SEND_MARKERS_DEFAULT = ("Notification sent successfully", "通知发送成功")


# ── 基础工具 ──────────────────────────────────────────────────────────

def parse_ts(text):
    m = TS_RE.search(text or "")
    if not m:
        return None
    return datetime.strptime(m.group(1) + " " + m.group(2), "%Y-%m-%d %H:%M:%S")


def fmt_duration(hours):
    if hours is None:
        return "无法计算"
    if hours < 1:
        return f"{int(hours * 60)} 分钟"
    return f"{hours:.1f} 小时"


def process_alive(pattern: str) -> bool:
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                cmd = f.read().decode("utf-8", "replace").replace("\x00", " ")
        except OSError:
            continue
        if pattern in cmd and "grep" not in cmd and "deadman" not in cmd:
            return True
    return False


def newest_mtime(pattern: str):
    newest = None
    for f in glob.glob(pattern):
        try:
            m = os.path.getmtime(f)
        except OSError:
            continue
        if newest is None or m > newest:
            newest = m
    return newest


class DB:
    """延迟连接：mysql 用 pymysql（可选依赖），sqlite 用内置。"""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.kind = cfg.get("kind", "mysql")
        self._conn = None

    def query(self, sql: str, params=()):
        # 占位符移植：配置统一写 ?（sqlite 风格），mysql 内部转 %s。
        # 这样同一份 SQL 配置在两种库上都能跑。
        if self.kind == "mysql" and "?" in sql:
            sql = sql.replace("?", "%s")
        if self.kind == "sqlite":
            import sqlite3
            if self._conn is None:
                self._conn = sqlite3.connect(self.cfg["path"])
                self._conn.row_factory = sqlite3.Row
            rows = self._conn.execute(sql, params).fetchall()
            return [tuple(r) for r in rows]
        import pymysql  # 延迟导入：只有真用 MySQL 检查才需要
        if self._conn is None:
            self._conn = pymysql.connect(
                host=self.cfg["host"], user=self.cfg["user"],
                password=self.cfg["password"], database=self.cfg["database"],
                port=int(self.cfg.get("port", 3306)), charset="utf8mb4")
        with self._conn.cursor() as cur:
            cur.execute(sql, params or ())
            return list(cur.fetchall())

    def scalar(self, sql: str, params=()):
        rows = self.query(sql, params)
        return rows[0][0] if rows else None

    def close(self):
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None


def render_ts(v):
    if v is None:
        return "无记录"
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    return str(v)


# ── check 类型实现：每个返回 {ok, name, evidence, duration, note} ────

def check_process_alive(c, now, dbs, th):
    ok = process_alive(c["pattern"])
    return [{"ok": ok, "name": c["name"],
            "evidence": (f"进程表中未找到 {c['pattern']}" if not ok
                         else f"进程存活：{c['pattern']}"),
            "duration": "无法计算" if not ok else "-"}]


def check_db_freshness(c, now, dbs, th):
    db = dbs[c["db"]]
    max_ts = db.scalar(c["freshness_sql"])
    if not isinstance(max_ts, datetime):
        max_ts = parse_ts(max_ts)
    age = (now - max_ts).total_seconds() / 3600 if max_ts else None
    max_h = float(c.get("max_age_hours", 6))
    # gate：可判定队列（如排除无 diff 的口径）；空则视为正常空闲
    gate = None
    if c.get("gate_sql"):
        gate = db.scalar(c["gate_sql"]) or 0
    gate_min = int(c.get("gate_min", 1))
    bypass = max_h <= 0  # 阈值 0 = 自检演练
    stale = (age is None) or (age > max_h)
    if stale and (gate is None or gate >= gate_min or bypass):
        return [{"ok": False, "name": c["name"],
                 "evidence": f"最新 {render_ts(max_ts)}，gate={gate}，阈值 {max_h}h",
                 "duration": fmt_duration(age)}]
    return [{"ok": True, "name": c["name"],
             "evidence": f"最新 {render_ts(max_ts)}（{fmt_duration(age)}前，阈值 {max_h}h），gate={gate}",
             "duration": "-"}]


def check_db_output(c, now, dbs, th):
    db = dbs[c["db"]]
    win = float(c.get("window_hours", 12))
    start = (now - timedelta(hours=win)).strftime("%Y-%m-%d %H:%M:%S")
    n = db.scalar(c["count_sql"], (start,)) or 0
    proc = c.get("require_process")
    out = [{"ok": True, "name": c["name"] + "-进程", "evidence": f"进程存活：{proc}",
            "duration": "-"}]
    if proc and not process_alive(proc):
        out[0] = {"ok": False, "name": c["name"] + "-进程未存活",
                  "evidence": f"进程表中未找到 {proc}", "duration": "无法计算"}
        return out
    if n == 0 and win > 0:
        last = db.scalar(c.get("last_sql", "")) if c.get("last_sql") else None
        # gate：候选队列为空时「无产出」是正常空闲，不是停摆（2026-11-14 实测：
        # MRS/NDB 等不适用组件被反复捡起跑、失败、隔离，12h 零产出全是假告警）
        gate = None
        gsql = c.get("gate_sql")
        if gsql:
            try:
                gate = int(db.scalar(gsql) or 0)
            except Exception:
                gate = None  # 查询失败按「有活」保守处理，宁可告警
        if gate == 0:
            out[0]["evidence"] = (f"近 {win}h 新增 0 条，但候选队列为空"
                                  f"（{c.get('gate_desc') or '正常空闲'}），最近一条 {render_ts(last)}")
        else:
            out[0] = {"ok": False, "name": c["name"] + "-产出停摆",
                      "evidence": f"近 {win}h 新增 0 条，最近一条 {render_ts(last)}"
                                  + (f"，候选 {gate} 条待处理" if gate else ""),
                      "duration": "-"}
    else:
        out[0]["evidence"] = f"近 {win}h 新增 {n} 条"
    return out


def check_queue_stall(c, now, dbs, th):
    db = dbs[c["db"]]
    win = float(c.get("window_hours", 12))
    start = (now - timedelta(hours=win)).strftime("%Y-%m-%d %H:%M:%S")
    pending = db.scalar(c["pending_sql"]) or 0
    judged = db.scalar(c["judged_sql"], (start,)) or 0
    if pending > 0 and judged == 0 and win > 0:
        return [{"ok": False, "name": c["name"],
                 "evidence": f"可判定 {pending} 条，近 {win}h 判定 0 条（口径须与业务 pending 一致）",
                 "duration": "-"}]
    return [{"ok": True, "name": c["name"],
             "evidence": f"可判定 {pending} 条，近 {win}h 判定 {judged} 条", "duration": "-"}]


def check_log_freshness(c, now, dbs, th):
    mt = newest_mtime(c["glob"])
    max_h = float(c.get("max_age_hours", 2))
    proc = c.get("require_process")
    alive = process_alive(proc) if proc else False
    if mt is None:
        return [{"ok": not c.get("require_match", True), "name": c["name"],
                 "evidence": f"未找到匹配日志 {c['glob']}", "duration": "无法计算"}]
    age = (now.timestamp() - mt) / 3600
    if age > max_h and (alive or not proc):
        return [{"ok": False, "name": c["name"] + "-空转",
                 "evidence": f"最新日志 {datetime.fromtimestamp(mt):%Y-%m-%d %H:%M:%S}，"
                             f"阈值 {max_h}h" + ("，进程仍存活" if alive else ""),
                 "duration": fmt_duration(age)}]
    return [{"ok": True, "name": c["name"],
             "evidence": f"最新日志 {fmt_duration(age)}前（阈值 {max_h}h）", "duration": "-"}]


def check_notify_silence(c, now, dbs, th):
    markers = tuple(c.get("markers", SEND_MARKERS_DEFAULT))
    log_path = Path(c["notify_log"]) if c.get("notify_log") else None
    latest = None
    if log_path and log_path.is_file():
        for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
            t = parse_ts(line)
            if t and (latest is None or t > latest):
                latest = t
    week_ago = (now - timedelta(days=7)).timestamp()
    for pat in c.get("scan_globs", []):
        for f in glob.glob(pat):
            try:
                if not os.path.isfile(f) or os.path.getmtime(f) < week_ago:
                    continue
                with open(f, encoding="utf-8", errors="replace") as fh:
                    for line in fh:
                        if any(mk in line for mk in markers):
                            t = parse_ts(line)
                            if t and (latest is None or t > latest):
                                latest = t
            except OSError:
                continue
    max_h = float(c.get("max_age_hours", 48))
    if latest is None:
        return [{"ok": False, "name": c["name"] + "-无发送记录",
                 "evidence": "近 7 天日志中未找到任何通知发送记录", "duration": "无法计算"}]
    age = (now - latest).total_seconds() / 3600
    if age > max_h:
        return [{"ok": False, "name": c["name"] + "-长时间无通知",
                 "evidence": f"最近一次发送 {latest:%Y-%m-%d %H:%M:%S}，阈值 {max_h}h",
                 "duration": fmt_duration(age)}]
    return [{"ok": True, "name": c["name"],
             "evidence": f"最近发送 {latest:%Y-%m-%d %H:%M:%S}（{fmt_duration(age)}前）",
             "duration": "-"}]


CHECKS = {
    "process_alive": check_process_alive,
    "db_freshness": check_db_freshness,
    "db_output": check_db_output,
    "queue_stall": check_queue_stall,
    "log_freshness": check_log_freshness,
    "notify_silence": check_notify_silence,
}


# ── 主流程 ────────────────────────────────────────────────────────────

def run_checks(cfg: dict):
    now = datetime.now()
    dbs = {k: DB(v) for k, v in (cfg.get("databases") or {}).items()}
    results = []
    try:
        for c in cfg.get("checks", []):
            fn = CHECKS.get(c["type"])
            if fn is None:
                results.extend([{"ok": False, "name": c.get("name", c["type"]),
                                 "evidence": f"未知 check 类型 {c['type']}",
                                 "duration": "-"}])
                continue
            try:
                results.extend(fn(c, now, dbs, cfg.get("thresholds", {})))
            except Exception as e:  # 单项失败不拖垮整轮巡检
                results.extend([{"ok": False, "name": c.get("name", c["type"]) + "-检查器异常",
                                 "evidence": f"{type(e).__name__}: {e}", "duration": "-"}])
    finally:
        for db in dbs.values():
            db.close()
    anomalies = [r for r in results if not r["ok"]]
    normals = [f"{r['name']}：{r['evidence']}" for r in results if r["ok"]]
    return {"now": now, "anomalies": anomalies, "normals": normals}


def render(result):
    lines = []
    if result["anomalies"]:
        lines.append(f"🔴 存活巡检：发现 {len(result['anomalies'])} 项异常")
        lines.append("【异常清单】")
        for a in result["anomalies"]:
            lines.append(f"- {a['name']}｜证据：{a['evidence']}｜持续：{a['duration']}")
    else:
        lines.append("✅ 存活巡检：全部正常")
    if result["normals"]:
        lines.append("【正常项】" + " ; ".join(result["normals"]))
    return "\n".join(lines)


def notify(cfg: dict, content: str) -> str:
    """可插拔通知：内容走 stdin，命令自己读。

    不用 {msg} 占位符的原因：占位符替换要处理 shell 引号转义，
    中文会被 uXXXX 转义、嵌套引号会 RC=127（2026-11-13 实测）。
    stdin 是零转义管道：echo 也好、企微脚本也好，读到的就是原文。
    """
    cmd = (cfg.get("notify_cmd") or "").strip()
    if not cmd:
        return "(未配置 notify_cmd，跳过发送)"
    r = subprocess.run(cmd, shell=True, input=content,
                       capture_output=True, text=True, timeout=60)
    tail = (r.stdout or r.stderr or "").strip().splitlines()
    return f"notify_cmd RC={r.returncode} {tail[-1][:80] if tail else ''}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="死士检查（配置驱动通用件）")
    ap.add_argument("--config", required=True)
    ap.add_argument("--dry-run", action="store_true", help="只打印，不发送不写日志")
    args = ap.parse_args(argv)

    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    result = run_checks(cfg)
    text = render(result)
    print(text)

    if args.dry_run:
        print("（dry-run：不写日志、不发送）")
        return 0

    log_file = cfg.get("log_file")
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        brief = ",".join(a["name"] for a in result["anomalies"]) if result["anomalies"] else "全部正常"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"{result['now']:%Y-%m-%d %H:%M:%S} | 异常 {len(result['anomalies'])} 项 | "
                    f"正常 {len(result['normals'])} 项 | {brief}\n")

    if result["anomalies"]:
        head = f"【存活巡检告警】{result['now']:%Y-%m-%d %H:%M:%S}"
        th0 = all(float(c.get("max_age_hours", c.get("window_hours", 1))) <= 0
                  for c in cfg.get("checks", [])
                  if c["type"] in ("db_freshness", "log_freshness", "notify_silence"))
        if th0:
            head += "（本次为自检演练：阈值已置 0）"
        how = notify(cfg, head + "\n" + text)
        print(f"异常通知：{how}")
    else:
        print("无异常，未发送通知")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
