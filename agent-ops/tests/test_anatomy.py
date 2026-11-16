"""ANATOMY 对账器的回归测试：它必须真的能拦住文档漂移。

用临时目录构造最小仓库，逐项验证：缺章节、引用不存在的路径、
脚本未覆盖、门禁未接、缺审阅任务书都会被判为问题。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import anatomy_check  # noqa: E402


def _minimal_repo(tmp_path: Path) -> Path:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "ok.py").write_text("", encoding="utf-8")
    (tmp_path / "templates" / "tasks").mkdir(parents=True)
    (tmp_path / "templates" / "tasks" / "generic.md").write_text("", encoding="utf-8")
    (tmp_path / "radar" / "prompts").mkdir(parents=True)
    (tmp_path / "radar" / "prompts" / "session.md").write_text("", encoding="utf-8")
    (tmp_path / "radar" / "prompts" / "anatomy-review.md").write_text(
        "", encoding="utf-8")
    (tmp_path / "GOVERNANCE.md").write_text("anatomy_check.py", encoding="utf-8")
    (tmp_path / "SKILL.md").write_text("anatomy_check.py", encoding="utf-8")
    text = "\n".join([
        "# ANATOMY", "",
        "## 1. a", "`scripts/ok.py`",
        "## 2. b", "## 3. c", "`generic.md`", "`session.md`",
        "`anatomy-review.md`", "`radar/prompts/session.md`",
        "## 4. d", "## 5. e",
        "## 6. f", "`taskctl.py`", "`radar_store.py`", "`radar_cli.py`",
        "`_done-contract.md`",
        "## 7. g", "## 8. h", "## 9. i", "## 10. j",
    ])
    (tmp_path / "ANATOMY.md").write_text(text, encoding="utf-8")
    return tmp_path


def test_minimal_repo_is_clean(tmp_path):
    assert anatomy_check.check(_minimal_repo(tmp_path)) == []


def test_missing_section_is_reported(tmp_path):
    root = _minimal_repo(tmp_path)
    p = root / "ANATOMY.md"
    p.write_text(p.read_text(encoding="utf-8").replace("## 10. j", ""),
                 encoding="utf-8")
    issues = anatomy_check.check(root)
    assert any("第 10 节" in x for x in issues)


def test_missing_path_is_reported(tmp_path):
    root = _minimal_repo(tmp_path)
    with (root / "ANATOMY.md").open("a", encoding="utf-8") as fh:
        fh.write("\n`scripts/ghost.py`\n")
    issues = anatomy_check.check(root)
    assert any("ghost.py" in x for x in issues)


def test_uncovered_script_is_reported(tmp_path):
    root = _minimal_repo(tmp_path)
    (root / "scripts" / "newmod.py").write_text("", encoding="utf-8")
    issues = anatomy_check.check(root)
    assert any("newmod.py" in x for x in issues)


def test_gate_not_wired_is_reported(tmp_path):
    root = _minimal_repo(tmp_path)
    (root / "GOVERNANCE.md").write_text("no gate here", encoding="utf-8")
    issues = anatomy_check.check(root)
    assert any("GOVERNANCE.md" in x for x in issues)


def test_missing_review_prompt_is_reported(tmp_path):
    root = _minimal_repo(tmp_path)
    (root / "radar" / "prompts" / "anatomy-review.md").unlink()
    issues = anatomy_check.check(root)
    assert any("anatomy-review.md" in x for x in issues)
