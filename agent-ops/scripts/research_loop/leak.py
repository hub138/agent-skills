"""工作区泄漏扫描、反向读取探测与隔离门禁(方案 8.1、9.2、13.1 隔离项)。

口径(方案 1.2#6/8.1):文件哈希、禁读提示词或访问监视本身不等于隔离;
本层提供的是审计与门禁判定:
- scan_workspace:静态扫描 reviewer 可见工作区,三类 violation;
- probe_reverse_read:从 reviewer 侧身份实际尝试读取禁止路径,
  能读出即隔离失败(反向读取测试,方案 8.1"开跑前验证");
- isolation_gate:full 需扫描与反向探测双过;limited 只看扫描;
  终验(final)只接受 full 的 pass,没有阻断能力的环境不得虚报盲测。
"""
from __future__ import annotations

import os

from .core_types import sha256_file

DEFAULT_MAX_FILE_BYTES = 5 * 1024 * 1024
SCAN_PASS = "pass"
SCAN_FAIL = "fail"
GATE_PASS = "pass"
GATE_FAIL = "fail"
GATE_BLOCKED = "blocked"


def _deny_index(deny_paths) -> tuple:
    """返回 (精确命中集合, 目录前缀列表, sha256→来源路径)。

    全部先 realpath 解析, symlink 指向禁止文件即命中(方案 8.1 符号链接通道)。
    """
    exact = set()
    prefixes = []
    hashes = {}
    for p in deny_paths or []:
        raw = str(p)
        real = os.path.realpath(os.path.abspath(raw))
        exact.add(real)
        exact.add(os.path.abspath(raw))
        if os.path.isdir(real):
            prefixes.append(real.rstrip(os.sep) + os.sep)
        elif os.path.isfile(real):
            try:
                hashes.setdefault(sha256_file(real), raw)
            except OSError:
                pass
    return exact, prefixes, hashes


def scan_workspace(workspace_root, deny_paths, canaries,
                   max_file_bytes: int = DEFAULT_MAX_FILE_BYTES) -> dict:
    """扫描工作区,返回 {violations, verdict}。

    violation 三类(方案 8.1):
    - path-in-deny: 文件路径或其 symlink 解析命中禁止清单(含禁目录前缀);
    - hash-match:   sha256 与禁止文件相同(改路径改名不改内容也拦);
    - canary-found: 内容含 canary 标记(蜜罐词,覆盖摘抄泄漏)。
    超过 max_file_bytes 的文件跳过内容比对(超大文件不烧资源)。
    """
    exact, prefixes, hashes = _deny_index(deny_paths)
    canary_bytes = []
    seen_canaries = set()
    for c in canaries or []:
        text = str(c)
        if text and text not in seen_canaries:
            seen_canaries.add(text)
            canary_bytes.append(text.encode("utf-8"))
    violations = []
    for dirpath, _dirnames, filenames in os.walk(
            str(workspace_root), followlinks=False):
        # 审计问题 4：目录符号链接解析命中 deny → violation（不递归）
        for dname in list(_dirnames):
            dpath = os.path.join(dirpath, dname)
            if os.path.islink(dpath):
                real_d = os.path.realpath(dpath)
                for dp in prefixes:
                    if real_d.startswith(dp):
                        violations.append({
                            "type": "path-in-deny", "path": dpath,
                            "detail": "目录 symlink 解析到禁止路径: %s" % real_d})
                        _dirnames.remove(dname)
                        break
        for name in filenames:
            path = os.path.join(dirpath, name)
            try:
                real = os.path.realpath(path)
                st = os.stat(real)
            except OSError:
                continue
            if not os.path.isfile(real):
                continue
            hit = real in exact or os.path.abspath(path) in exact
            if not hit:
                norm = real.rstrip(os.sep) + os.sep
                hit = any(norm.startswith(p) for p in prefixes)
            if hit:
                violations.append({
                    "type": "path-in-deny", "path": path,
                    "detail": "路径或 symlink 解析命中禁止清单: %s" % real,
                })
                continue
            if st.st_size > max_file_bytes:
                continue
            try:
                digest = sha256_file(real)
            except OSError:
                continue
            if digest in hashes:
                violations.append({
                    "type": "hash-match", "path": path,
                    "detail": "sha256 与禁止文件 %s 相同" % hashes[digest],
                })
                continue
            if canary_bytes:
                try:
                    with open(real, "rb") as f:
                        blob = f.read()
                except OSError:
                    continue
                for cb in canary_bytes:
                    if cb in blob:
                        violations.append({
                            "type": "canary-found", "path": path,
                            "detail": "内容含 canary %r"
                                      % cb.decode("utf-8", "replace"),
                        })
                        break
    verdict = SCAN_FAIL if violations else SCAN_PASS
    return {"violations": violations, "verdict": verdict}


def probe_reverse_read(deny_paths) -> dict:
    """反向读取探测:以当前(模拟 reviewer)身份逐个尝试 open().read()。

    能读出即隔离失败——文件监视挡不住实际读取(方案 8.1 反向读取测试)。
    返回 {attempts: [{path, readable, bytes}], readable_count, verdict}。
    """
    attempts = []
    for p in deny_paths or []:
        path = str(p)
        readable = False
        n = 0
        err = None
        try:
            with open(path, "rb") as f:
                blob = f.read()
            readable = True
            n = len(blob)
        except OSError as e:
            err = "%s: %s" % (type(e).__name__, e)
        rec = {"path": path, "readable": readable, "bytes": n}
        if err is not None:
            rec["error"] = err
        attempts.append(rec)
    leaked = [a for a in attempts if a["readable"]]
    return {
        "attempts": attempts,
        "readable_count": len(leaked),
        "verdict": SCAN_FAIL if leaked else SCAN_PASS,
    }


def isolation_gate(mode: str, scan: dict, probe: dict) -> dict:
    """隔离门禁判定(方案 8.1)。

    - mode=full:  需 scan pass 且反向探测无任何可读路径,否则 fail;
    - mode=limited: 只需 scan pass(无阻断能力,不得标最终盲测);
    - 其他(含 blocked/非法值): blocked。
    返回 {mode, verdict, scan_ok, probe_clean, reasons}。
    """
    scan_ok = isinstance(scan, dict) and scan.get("verdict") == SCAN_PASS
    probe_clean = (isinstance(probe, dict)
                   and not any(a.get("readable")
                               for a in probe.get("attempts") or []))
    reasons = []
    if not scan_ok:
        n = len(scan.get("violations") or []) if isinstance(scan, dict) else "?"
        reasons.append("工作区扫描未通过(violations=%s)" % n)
    if mode == "full" and not probe_clean:
        n = probe.get("readable_count") if isinstance(probe, dict) else "?"
        reasons.append("反向读取探测发现可读禁止路径(readable=%s)" % n)
    if mode == "full":
        verdict = GATE_PASS if (scan_ok and probe_clean) else GATE_FAIL
    elif mode == "limited":
        verdict = GATE_PASS if scan_ok else GATE_FAIL
        if not scan_ok:
            pass
        else:
            reasons.append("limited 隔离:仅静态扫描通过,无阻断能力,"
                           "不得用于最终盲测(方案 8.1)")
    else:
        verdict = GATE_BLOCKED
        reasons.append("隔离模式 %r 无门禁能力,阻断(方案 8.1)" % (mode,))
    if verdict == GATE_PASS and not reasons:
        reasons.append("扫描通过且反向探测无可读禁止路径" if mode == "full"
                       else "扫描通过")
    return {"mode": mode, "verdict": verdict, "scan_ok": scan_ok,
            "probe_clean": probe_clean, "reasons": reasons}


def accepts_final(gate: dict) -> bool:
    """终验(final)只接受 full 隔离的 pass(方案 8.1/13.3#3)。"""
    return bool(isinstance(gate, dict) and gate.get("mode") == "full"
                and gate.get("verdict") == GATE_PASS)
