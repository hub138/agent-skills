"""技术雷达子功能的回归测试：解析、入账、领取、渲染、清理边界。

这些测试保护的是「可追溯」这条链路：只要简报能解析、结论能入账、台账能渲染、
清理不越界，雷达就不会变成一堆散落的 md。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import radar_store as store  # noqa: E402
import radar_workspace as ws  # noqa: E402

BRIEF_TECH = """# 技术情报简报 2026-11-16

## 值得看

### GitHub - Tencent/LoopForge: Self-hosted workflows
- 核心：自托管交付工作流，Docker 沙箱 + 人工门禁
- 创新点：Agent、Script、Human-gate、子 SOP 四类节点
- 谁该看：做 Agent 运行时的后端工程师
- 链接：https://github.com/Tencent/LoopForge

### 长任务续跑
- 核心：检查点、确定性重放与幂等三件套
- 创新点：最小快照四问
- 链接：https://example.com/a

## 略过
- 某产品通稿
"""

BRIEF_PASTE = """技术情报简报 2026-11-16

1. GitHub - Tencent/LoopForge: Self-hosted workflows for coding-agent delivery.
核心　自托管Agent交付工作流，Docker沙箱+角色子代理+人工门禁
创新　Agent、Script、Human-gate、子SOP四类节点编排；提供MIRROR registry避墙方案
[原文](https://github.com/Tencent/LoopForge)

2. SuperAgent 实战：让 Router 看见全局
核心　多Agent调度共享同一份事实，GlobalContextPacket一次装配按角色投影
创新　SaResultEnvelope单一结果信封、大对象走坐标传引用
[原文](https://cloud.tencent.com/developer/article/2784348)

[查看完整简报](http://radar.example/brief/2026-11-16)
"""


@pytest.fixture()
def conn(tmp_path, monkeypatch):
    monkeypatch.setenv("RADAR_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("RADAR_DB", str(tmp_path / "state" / "radar.db"))
    monkeypatch.setenv("RADAR_CACHE", str(tmp_path / "cache"))
    c = store.connect()
    store.init_db(c)
    yield c
    c.close()


def test_parse_tech_radar_format():
    items = store.parse_brief(BRIEF_TECH)
    assert len(items) == 2
    assert items[0]["title"].startswith("GitHub - Tencent/LoopForge")
    assert items[0]["kind"] == "repo"
    assert items[0]["host"] == "github.com"
    assert "Docker" in items[0]["core"]
    assert items[1]["kind"] == "article"


def test_parse_pasted_format_ignores_footer_link():
    items = store.parse_brief(BRIEF_PASTE)
    assert len(items) == 2
    assert items[0]["url"] == "https://github.com/Tencent/LoopForge"
    assert "人工门禁" in items[0]["core"]
    assert items[1]["kind"] == "article"
    assert all("查看完整简报" not in i["title"] for i in items)


def test_ingest_is_idempotent(conn):
    first = store.ingest_brief(conn, BRIEF_TECH, brief_date="2026-11-16",
                               source="test")
    assert first["inserted"] == 2
    again = store.ingest_brief(conn, BRIEF_TECH, brief_date="2026-11-16")
    assert again["duplicate"] is True
    assert store.stats(conn)["candidates"] == 2


def test_take_next_is_exclusive(conn):
    store.ingest_brief(conn, BRIEF_PASTE, brief_date="2026-11-15")
    a = store.take_next(conn)
    b = store.take_next(conn)
    assert a and b and a["id"] != b["id"]
    assert store.take_next(conn) is None
    assert store.stats(conn)["new"] == 0
    claims = conn.execute(
        "SELECT COUNT(*) FROM events WHERE kind='claim'").fetchone()[0]
    assert claims == 2


def test_record_analysis_and_ledger(conn):
    store.ingest_brief(conn, BRIEF_PASTE, brief_date="2026-11-15")
    cand = store.take_next(conn)
    report = Path(store.state_root()) / "r.md"
    report.write_text("# 分析\n", encoding="utf-8")
    store.record_analysis(conn, cand["id"], report_path=store.rel(report),
                          verdict="adapt", mechanisms=["结果信封"],
                          evidence=["src/x.py:12"], cost="2h", risk="低",
                          relevance=4, reason="现有 result.json 可加校验")
    out = Path(store.state_root()) / "LEDGER.md"
    text = store.render_ledger(conn, out=out)
    assert "改造" in text
    assert "结果信封" not in text  # 台账只放结论，细节留在分析报告
    assert cand["title"][:10] in text


def test_workspace_path_rejects_non_repo():
    assert ws.repo_slug("file:///etc/passwd") is None
    assert ws.repo_slug("/data/local/repo") is None
    assert ws.repo_slug("https://github.com/Tencent/LoopForge") == (
        "github.com", "Tencent", "LoopForge")
    assert ws.repo_slug("git@git.example.com:org/tech-radar.git") == (
        "git.example.com", "org", "tech-radar")


def test_clean_never_touches_outside_cache(tmp_path):
    cache = tmp_path / "cache"
    inside = cache / "github.com" / "org" / "repo"
    inside.mkdir(parents=True)
    (inside / "a.txt").write_text("x" * 100, encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("keep", encoding="utf-8")

    res = ws.clean(cache, [{"path": str(outside), "bytes": 4},
                           {"path": str(inside), "bytes": 100}])
    assert not inside.exists()
    assert (outside / "keep.txt").exists()
    assert any("越出缓存根" in s["why"] for s in res["skipped"])
    assert res["freed_bytes"] == 100


def test_workspace_ensure_rejects_unknown_url(tmp_path):
    res = ws.ensure_workspace("not-a-url", tmp_path)
    assert res["ok"] is False


def test_triage_routes_by_signal():
    """无关条目必须被拦在深读之外；机制条目必须进 deep。"""
    assert store.triage_text("腾讯混元发布 Hy4 flash 模型")["route"] == "skip"
    assert store.triage_text("某公司完成新一轮融资，估值翻倍")["route"] == "skip"
    deep = store.triage_text(
        "Agent 干到一半崩了：长任务续跑的工程学",
        "检查点、确定性重放与幂等三件套")
    assert deep["route"] == "deep"
    brief = store.triage_text("Agent 可观测实践", "Trace 分层与评估")
    assert brief["route"] == "brief"


def test_take_next_skips_skip_route(conn):
    items = [
        {"seq": 1, "title": "某模型正式发布", "url": "https://example.com/a",
         "kind": "article", "core": "", "innovation": ""},
        {"seq": 2, "title": "检查点与续跑", "url": "https://example.com/b",
         "kind": "article", "core": "检查点 幂等", "innovation": ""},
    ]
    store.ingest_brief(conn, "raw", brief_date="2026-11-16", items=items)
    store.triage_pending(conn)
    first = store.take_next(conn)
    assert first["seq"] == 2, "默认必须跳过 skip 条目"
    forced = store.take_next(conn, include_skip=True)
    assert forced["seq"] == 1


def test_triage_columns_migrated(tmp_path, monkeypatch):
    """旧台账没有 triage_* 列，init_db 只加列、不重建。"""
    import sqlite3
    monkeypatch.setenv("RADAR_HOME", str(tmp_path))
    conn = sqlite3.connect(str(tmp_path / "old.db"))
    conn.execute("CREATE TABLE briefs (id INTEGER PRIMARY KEY, brief_date TEXT,"
                 " title TEXT, source TEXT, source_path TEXT, raw_sha256 TEXT,"
                 " item_count INTEGER, ingested_at TEXT)")
    conn.execute("CREATE TABLE candidates (id INTEGER PRIMARY KEY, brief_id INTEGER,"
                 " seq INTEGER, title TEXT, url TEXT, host TEXT, kind TEXT,"
                 " core TEXT, innovation TEXT, audience TEXT, status TEXT,"
                 " relevance INTEGER, verdict TEXT, reason TEXT,"
                 " created_at TEXT, updated_at TEXT)")
    conn.commit()
    store.init_db(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(candidates)")}
    assert {"triage_score", "triage_route", "triage_reason", "triage_at"} <= cols
    assert "slot" in {r[1] for r in conn.execute("PRAGMA table_info(briefs)")}


def test_same_day_two_slots(conn):
    store.ingest_brief(conn, BRIEF_TECH, brief_date="2026-11-16", slot="11:00")
    store.ingest_brief(conn, BRIEF_PASTE, brief_date="2026-11-16", slot="15:00")
    rows = [dict(r) for r in conn.execute("SELECT slot FROM briefs ORDER BY id")]
    assert [r["slot"] for r in rows] == ["11:00", "15:00"]
    assert store.stats(conn)["briefs"] == 2


def test_record_analysis_rolls_back_with_audit(conn, monkeypatch):
    """变更与审计必须同事务：审计写不进去，分析结论也不许落库。"""
    store.ingest_brief(conn, BRIEF_PASTE, brief_date="2026-11-16")
    cand = store.take_next(conn)
    report = Path(store.state_root()) / "r.md"
    report.write_text("# 分析\n", encoding="utf-8")

    def boom(*_a, **_k):
        raise RuntimeError("audit store down")

    monkeypatch.setattr(store, "_event_row", boom)
    with pytest.raises(RuntimeError):
        store.record_analysis(conn, cand["id"], report_path=store.rel(report),
                              verdict="skip", mechanisms=[], evidence=[],
                              relevance=2, reason="test")
    row = conn.execute("SELECT status FROM candidates WHERE id=?",
                       (cand["id"],)).fetchone()
    assert row["status"] == "screened"
    assert conn.execute("SELECT COUNT(*) FROM analyses").fetchone()[0] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM events WHERE kind='analysis'").fetchone()[0] == 0


def test_render_prompt_includes_done_contract(tmp_path):
    """落地验证：断点快照四问必须真的进入任务提示词，而不只是写在契约里。"""
    import taskctl
    text = taskctl.render_prompt("generic", {"topic": "检查构建"}, tmp_path, "t")
    assert "断点快照四问" in text
    assert "未知副作用" in text


def test_cli_intake_dry_run(tmp_path, monkeypatch, capsys):
    import radar_cli
    brief = tmp_path / "b.md"
    brief.write_text(BRIEF_TECH, encoding="utf-8")
    monkeypatch.setenv("RADAR_HOME", str(tmp_path / "state"))
    assert radar_cli.main(["intake", "--file", str(brief),
                           "--dry-run", "--json"]) == 0
    import json
    data = json.loads(capsys.readouterr().out)
    assert data["count"] == 2
