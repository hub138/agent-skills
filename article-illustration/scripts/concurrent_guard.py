# -*- coding: utf-8 -*-
"""多智能体并发写同一批文件时的写入互斥与内容校验。

lock   拿独占锁，拿不到说明有人在改
unlock 释放锁
fp     打印内容指纹
check  写入前校验内容是否被改动过
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import sys
import time

LOCK_DIR_NAME = ".concurrent-guard"
DEFAULT_TTL_MIN = 30


def repo_root_of(path: pathlib.Path):
    cur = path if path.is_dir() else path.parent
    for base in [cur] + list(cur.parents):
        if (base / ".git").exists():
            return base
    return None


def ensure_ignored(root: pathlib.Path) -> None:
    gi = root / ".gitignore"
    line = LOCK_DIR_NAME + "/"
    if gi.exists():
        text = gi.read_text(encoding="utf-8")
        if line in text.split("\n"):
            return
        sep = "" if (text == "" or text.endswith("\n")) else "\n"
        gi.write_text(text + sep + line + "\n", encoding="utf-8")
    else:
        gi.write_text(line + "\n", encoding="utf-8")


def state_dir(path: pathlib.Path) -> pathlib.Path:
    root = repo_root_of(path)
    if root is not None:
        d = root / LOCK_DIR_NAME
    else:
        d = pathlib.Path.home() / ".concurrent-guard"
    d.mkdir(parents=True, exist_ok=True)
    if root is not None:
        ensure_ignored(root)
    return d


def lock_path(path: pathlib.Path, state: pathlib.Path) -> pathlib.Path:
    key = hashlib.sha1(str(path.resolve()).encode("utf-8")).hexdigest()[:16]
    return state / (key + ".lock")


def fm_bounds(text: str):
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end < 0:
        return None
    return 4, end


def content_fp(path: pathlib.Path) -> str:
    """有 frontmatter 时只算正文，没有时算全文。

    本脚本同时服务两类文件：文章（有 frontmatter）与 css/js/py（没有）。
    只算正文是因为 editorial_pass 写 editorial_* / updated 会改 frontmatter，
    全文指纹会让持有者自己写标记后立刻误判成冲突；
    退化到全文是因为没有 frontmatter 的文件谈不上元数据改动，全文即内容。
    """
    text = path.read_text(encoding="utf-8")
    bounds = fm_bounds(text)
    body = text[bounds[1] + 5:] if bounds else text
    return hashlib.sha1(body.encode("utf-8")).hexdigest()[:12]


def open_exclusive(lp: pathlib.Path) -> int:
    return os.open(str(lp), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)


def cmd_lock(args) -> int:
    p = pathlib.Path(args.path)
    if not p.is_file():
        print("不是文件: %s" % p, file=sys.stderr)
        return 2
    sd = state_dir(p)
    lp = lock_path(p, sd)
    fp = content_fp(p)
    payload = json.dumps({
        "path": str(p.resolve()),
        "agent": args.agent,
        "pid": os.getpid(),
        "ts": time.time(),
        "fp": fp,
    }, ensure_ascii=False)
    try:
        fd = open_exclusive(lp)
    except FileExistsError:
        info = json.loads(lp.read_text(encoding="utf-8"))
        age = (time.time() - float(info.get("ts", 0))) / 60.0
        if age <= args.ttl_min:
            print("文件已被占用，禁止并行写入。\n"
                  "  持有者 %s（pid %s），已持有 %.1f 分钟。\n"
                  "  锁文件 %s\n"
                  "  换一个目标，或确认对方已中断后加 --ttl-min 0 抢占。"
                  % (info.get("agent"), info.get("pid"), age, lp), file=sys.stderr)
            return 3
        print("抢占过期锁（原持有者 %s，持有 %.1f 分钟，超过 %d 分钟）"
              % (info.get("agent"), age, args.ttl_min))
        os.unlink(lp)
        fd = open_exclusive(lp)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(payload)
    print("LOCKED fp=%s" % fp)
    return 0


def cmd_unlock(args) -> int:
    p = pathlib.Path(args.path)
    lp = lock_path(p, state_dir(p))
    if not lp.exists():
        print("没有锁记录: %s" % p, file=sys.stderr)
        return 1
    os.unlink(lp)
    print("UNLOCKED")
    return 0


def cmd_fp(args) -> int:
    p = pathlib.Path(args.path)
    if not p.is_file():
        print("不是文件: %s" % p, file=sys.stderr)
        return 2
    print(content_fp(p))
    return 0


def cmd_check(args) -> int:
    p = pathlib.Path(args.path)
    if not p.is_file():
        print("不是文件: %s" % p, file=sys.stderr)
        return 2
    cur = content_fp(p)
    if cur != args.fp:
        print("内容已被改动，禁止覆盖。\n"
              "  基线 %s，当前 %s。\n"
              "  重读全文，把外部改动并进本轮再写入。"
              % (args.fp, cur), file=sys.stderr)
        return 4
    print("OK 内容未变，可以写入")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="多智能体并发写文件的互斥锁与内容校验",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    lk = sub.add_parser("lock", help="拿独占锁")
    lk.add_argument("path")
    lk.add_argument("--agent", default="agent-unknown")
    lk.add_argument("--ttl-min", type=int, default=DEFAULT_TTL_MIN,
                    help="锁超过多少分钟视为过期可抢占")
    lk.set_defaults(func=cmd_lock)

    ul = sub.add_parser("unlock", help="释放锁")
    ul.add_argument("path")
    ul.set_defaults(func=cmd_unlock)

    fp = sub.add_parser("fp", help="打印内容指纹")
    fp.add_argument("path")
    fp.set_defaults(func=cmd_fp)

    ck = sub.add_parser("check", help="写入前校验内容是否被改动")
    ck.add_argument("path")
    ck.add_argument("--fp", required=True)
    ck.set_defaults(func=cmd_check)
    return ap


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
