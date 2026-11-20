"""research_loop.report 渲染回归(方案 9.4/10、13.1)。"""
import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL / "scripts"))

from research_loop import report, store  # noqa: E402

PROJECT = {
    "identity": {"project_id": "demo-project", "objective_version": "obj-1",
                 "goal": "提升缺陷引入风险点召回"},
    "metrics": {
        "primary_metric": {"metric_id": "risk_recall", "direction": "maximize",
                           "threshold": 0.98, "comparison": "gt",
                           "unit": "ratio"},
        "guard_metrics": [{"metric_id": "alert_precision",
                           "direction": "maximize"}],
    },
    "data": {"manifest": "labels/v3", "version": "data-v3"},
    "evaluator": {"adapter_id": "static-judge"},
    "isolation": {"mode": "limited"},
    "completion": {"final_gate": "R>0.98 且 precision_lower_bound>0.30"},
}


@pytest.fixture()
def seeded_db(tmp_path):
    db = tmp_path / "state" / "research.db"
    conn = store.open_db(str(db))
    with store.tx_ctx(conn):
        conn.execute(
            "INSERT INTO experiments(experiment_id, created_ts, stage,"
            " objective_version, data_version, evaluator_digest)"
            " VALUES(?,?,?,?,?,?)",
            ("exp-1", 1000.0, "trial", "obj-1", "data-v3", "judge-digest-1"))
        for aid, exec_st, ev_st, trial, started, finished in (
                ("att-succ", "succeeded", "valid", "beneficial",
                 1001.0, 1002.0),
                ("att-queued", "queued", "pending", "untested", 1003.0, None),
                ("att-fail", "failed", "invalid", "inconclusive",
                 1004.0, 1005.0)):
            conn.execute(
                "INSERT INTO attempts(attempt_id, experiment_id, stage,"
                " exec_status, evidence_status, trial_status, started_ts,"
                " finished_ts) VALUES(?,?,?,?,?,?,?,?)",
                (aid, "exp-1", "trial", exec_st, ev_st, trial, started,
                 finished))
        conn.execute(
            "INSERT INTO metrics(attempt_id, metric_id, value, numerator,"
            " denominator, unknown_count, lower_bound, stat_method)"
            " VALUES(?,?,?,?,?,?,?,?)",
            ("att-succ", "risk_recall", 0.4, 40, 100, 0, None,
             "wilson_two_sided"))
        conn.execute(
            "INSERT INTO decisions(decision_id, attempt_id, decision, reason,"
            " ts) VALUES(?,?,?,?,?)",
            ("dec-1", "att-succ", "promote_to_screening",
             "净收益成立(guard 未退化)", 1003.0))
        conn.execute(
            "INSERT INTO ideas(idea_id, title, kind, direction, status,"
            " created_ts, updated_ts) VALUES(?,?,?,?,?,?,?)",
            ("idea-1", "祖先历史补证", "knowledge_context", "召回", "queued",
             1000.0, 1000.0))
        conn.execute(
            "INSERT INTO ideas(idea_id, title, kind, direction, status,"
            " created_ts, updated_ts) VALUES(?,?,?,?,?,?,?)",
            ("idea-2", "<script>alert(1)</script>", "prompt_engineering",
             "精确率", "queued", 1001.0, 1001.0))
        store.append_event(conn, "round.started", {
            "round_id": "exp-1", "mechanism": "祖先历史补证",
            "hypothesis": "祖先线可达则可归因", "parent_candidate": "c0",
            "idea_id": "idea-1", "direction": "ancestry"})
        store.append_event(conn, "metrics_imported", {
            "attempt_id": "att-succ",
            "per_metric": {"risk_recall": {"tp": 40, "fn": 60, "fp": 0,
                                           "unknown": 0}}})
        store.append_event(conn, "data_quality",
                           {"split": "dev", "grade": "precise", "n": 10})
    conn.close()
    return db


@pytest.fixture()
def rendered(seeded_db, tmp_path):
    out_dir = tmp_path / "reports"
    result = report.render_report(str(seeded_db), PROJECT, str(out_dir))
    result["_out"] = out_dir
    return result


def _read(rendered, name):
    return (rendered["_out"] / name).read_text(encoding="utf-8")


def test_render_report_writes_four_files(rendered):
    files = rendered["files"]
    assert set(files) == {"STATUS.md", "CHANGELOG.md", "REPORT.md",
                          "report.html"}
    for path in files.values():
        p = Path(path)
        assert p.exists() and p.stat().st_size > 0
    assert rendered["project_id"] == "demo-project"
    assert rendered["experiments"] == 1
    assert rendered["attempts"] == 3


def test_status_goal_and_run_zones(rendered):
    text = _read(rendered, "STATUS.md")
    assert "## 目标区" in text
    assert "risk_recall" in text and "data-v3" in text
    assert "0.3094" in text            # 当前最佳: db 行 40/100 经 aggregate 重算
    assert "### 进行中" in text and "### 已结束" in text
    active = text.split("### 进行中", 1)[1].split("### 已结束", 1)[0]
    finished = text.split("### 已结束", 1)[1]
    assert "att-queued" in active      # queued 只出现在进行中
    assert "att-queued" not in finished
    assert "att-succ" in finished and "att-fail" in finished


def test_changelog_round_contents(rendered):
    text = _read(rendered, "CHANGELOG.md")
    assert "祖先历史补证" in text                       # 机制(来自事件)
    assert "TP=40" in text and "FP=0" in text
    assert "FN=60" in text and "unknown=0" in text
    assert "lower=0.3094" in text                      # 指标下界
    assert "wilson_two_sided" in text
    assert "判定" in text and "beneficial" in text


def test_report_md_three_sections(rendered):
    text = _read(rendered, "REPORT.md")
    for head in ("## 一、整体规划与进展", "## 二、问题波折与解决证据",
                 "## 三、后续目标、待验证假设与资源计划"):
        assert head in text
    assert "att-fail" in text      # 失败尝试进"问题波折"段,不冒充成功
    assert "idea-1" in text        # 待验证假设进第三段


def test_html_five_zones_nav_and_inline_css(rendered):
    page = _read(rendered, "report.html")
    for anchor in ('id="goal"', 'id="explore"', 'id="rounds"',
                   'id="data-quality"', 'id="runs"'):
        assert anchor in page
    assert 'id="nav-toggle"' in page       # 导航可收起(纯 CSS,无脚本)
    assert "<style>" in page
    assert "<script" not in page.lower()   # 单文件内联 CSS,无外部依赖
    assert "0.3094" in page                # 数字来自 db 经 aggregate
    assert 'id="exp-exp-1"' in page        # 内部链接锚点跳具体实验
    assert "<script>alert(1)</script>" not in page   # 动态内容已转义
    assert "&lt;script&gt;" in page
