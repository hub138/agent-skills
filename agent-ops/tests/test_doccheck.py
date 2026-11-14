"""doccheck 自身的反例自测：门禁坏了比没有门禁更危险。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import doccheck  # noqa: E402


def _run(tmp_path, readme: str, skill: str) -> list[str]:
    """把 ROOT 指到临时目录，不改真实仓库。"""
    import shutil
    (tmp_path / "scripts").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "templates/tasks").mkdir(parents=True)
    shutil.copy(ROOT / "scripts/doccheck.py", tmp_path / "scripts/doccheck.py")
    for f in (ROOT / "scripts").glob("*.py"):
        if f.name != "doccheck.py":
            (tmp_path / "scripts" / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
    for f in (ROOT / "tests").glob("test_*.py"):
        (tmp_path / "tests" / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
    for f in (ROOT / "templates/tasks").glob("*.md"):
        (tmp_path / "templates/tasks" / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "README.md").write_text(readme, encoding="utf-8")
    (tmp_path / "SKILL.md").write_text(skill, encoding="utf-8")
    (tmp_path / "FIELD-NOTES.md").write_text("## 1. a\n## 2. b\n", encoding="utf-8")

    orig = doccheck.ROOT
    doccheck.ROOT = tmp_path
    try:
        return doccheck.check()
    finally:
        doccheck.ROOT = orig


def test_catches_wrong_test_count(tmp_path):
    issues = _run(tmp_path, "36 项回归测试", "当前 36 项")
    assert any("回归测试" in x for x in issues)


def test_catches_wrong_fieldnotes_count(tmp_path):
    issues = _run(tmp_path, "99 条实战坑", "")
    assert any("实战坑" in x for x in issues)


def test_single_source_of_model_policy_is_kept():
    """真实仓库里不许再出现第二份白名单 / 写死 BIN 路径。"""
    real = doccheck.check()
    assert not any("ALLOWED_MODELS" in x for x in real)
    assert not any("resolve_bin" in x for x in real)


def test_real_repo_is_consistent():
    assert doccheck.check() == []
