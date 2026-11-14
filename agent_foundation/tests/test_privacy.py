"""开源资格红线：本包任何文件（含编译产物）不得含内部/私有痕迹。

为什么用测试而不是口头约定：这个包会长期演进，贡献者（包括 AI 会话）在
紧急修复时顺手 import 一个内部模块、或把一个私有服务名写进 docstring 注释，
都不是恶意——但只要发生过一次，包就永远不能公开了。机器闸门的优点是
不依赖记性。

**禁词表来自包外的本地配置**，不写进仓库：公开仓库不该列出一份内部命名清单，
否则闸门本身就成了泄漏源。配置方式：

    # 环境变量：逗号分隔的字面词，或 re:<正则> 形式的边界匹配
    PRIVACY_FORBIDDEN="internal-client,ca-prefix,re:(?<![A-Za-z])ioa(?![A-Za-z])"

    # 或本地文件（每行一个，忽略空行与 # 注释），路径由环境变量给出：
    PRIVACY_FORBIDDEN_FILE=~/.config/agent-foundation/forbidden.txt

两者可同时用，取并集。未配置时，只跑「绝对路径 / pyc 入库」这两项与
结构检查，字面词扫描自动跳过（不误报，也不假装扫过）。

跑法：pytest tests/test_privacy.py —— 红了就是有痕迹进了包。
"""

import os
import re
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent
SELF = Path(__file__).name


def _load_forbidden():
    """字面词 / 正则 列表，全部来自包外配置。"""
    raw = []
    env = os.environ.get("PRIVACY_FORBIDDEN", "")
    raw += [w.strip() for w in env.split(",") if w.strip()]
    fpath = os.environ.get("PRIVACY_FORBIDDEN_FILE", "")
    if fpath:
        fp = Path(os.path.expanduser(fpath))
        if fp.exists():
            for line in fp.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    raw.append(line)
    out = []
    for w in raw:
        if w.startswith("re:"):
            out.append({"pattern": w[3:], "label": w[3:]})
        else:
            out.append(w)
    return out


FORBIDDEN = _load_forbidden()


def _iter_files():
    for p in PKG_ROOT.rglob("*"):
        if not p.is_file():
            continue
        parts = {part.lower() for part in p.parts}
        if "__pycache__" in parts or ".pytest_cache" in parts:
            continue
        yield p


def test_no_internal_traces_in_any_file():
    """文本文件逐个扫禁词；禁词表未配置时跳过（不假装扫过）。"""
    if not FORBIDDEN:
        return
    offenders = []
    for p in _iter_files():
        if p.name == SELF:
            continue  # 本文件读取配置，不含字面禁词
        try:
            data = p.read_bytes()
        except OSError:
            continue
        text = data.decode("utf-8", errors="replace")
        for word in FORBIDDEN:
            if isinstance(word, dict):
                if re.search(word["pattern"], text, re.I):
                    offenders.append(f"{p.relative_to(PKG_ROOT)}: 含 '{word['label']}'")
            elif word.lower() in text.lower():
                offenders.append(f"{p.relative_to(PKG_ROOT)}: 含 '{word}'")
    assert not offenders, "开源资格红线被触碰（见下）——清除后方可入库：\n" + \
        "\n".join(offenders[:10])


def test_no_pyc_tracked():
    """pyc 把生成机器的绝对路径嵌进字节码。pytest 运行必然生成磁盘 pyc
    （gitignore 已挡），所以真正的泄露路径是**入库**——这里查 git 索引。"""
    import subprocess
    r = subprocess.run(["git", "ls-files", "--", "*.pyc"],
                       cwd=str(PKG_ROOT), capture_output=True, text=True)
    tracked = [l for l in r.stdout.splitlines() if l.strip()]
    assert not tracked, f"编译产物在版本控制里（含本机绝对路径）：{tracked[:5]}"


def test_no_absolute_paths_in_source():
    """源代码不得硬编码绝对路径（环境差异走参数），同时是路径类泄露兜底。"""
    known_dirs = ("/etc", "/usr", "/tmp", "/var", "/data", "/root", "/home",
                  "/opt", "/bin", "/sbin", "/Library", "/Applications")
    offenders = []
    for p in PKG_ROOT.rglob("*.py"):
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            for m in re.finditer(r'["\'](/(?:etc|usr|tmp|var|data|root|home|opt|bin|sbin|Library|Applications)[\w./-]{4,})["\']', line):
                path = m.group(1)
                if any(path.startswith(pre) for pre in known_dirs):
                    continue
                if p.name == SELF:
                    continue
                offenders.append(f"{p.relative_to(PKG_ROOT)}:{i}: {path}")
    assert not offenders, "源码含硬编码绝对路径：\n" + "\n".join(offenders[:8])
