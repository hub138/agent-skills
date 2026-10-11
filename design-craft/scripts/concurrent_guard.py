import argparse
import fcntl
import hashlib
import hmac
import json
import os
import pathlib
import secrets
import time
from contextlib import contextmanager

import frontmatter

LOCK_DIR_NAME = '.concurrent-guard'
DEFAULT_TTL_MIN = 30


def state_dir(path):
    path = path.resolve()
    explicit = os.environ.get('CONCURRENT_GUARD_HOME')
    if explicit:
        root = pathlib.Path(explicit).resolve()
    else:
        parent = next((p for p in path.parents if (p / '.git').exists()), path.parent)
        root = parent / LOCK_DIR_NAME
    root.mkdir(parents=True, exist_ok=True)
    return root


def lock_path(path, state):
    key = hashlib.sha1(str(path.resolve()).encode()).hexdigest()[:16]
    return state / (key + '.lock')


def content_fp(path, whole=False):
    raw = path.read_bytes()
    if not whole and path.suffix == '.md':
        raw = frontmatter.loads(raw.decode('utf-8')).content.encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


@contextmanager
def mutex(path):
    gate = path.with_suffix('.mutex')
    with gate.open('a') as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def main():
    ap = argparse.ArgumentParser(description='文件认领与指纹校验；锁操作互斥，释放需要身份和 token')
    sub = ap.add_subparsers(dest='command', required=True)
    for name in ('lock', 'unlock', 'renew', 'fp', 'check'):
        parser = sub.add_parser(name)
        parser.add_argument('path', type=pathlib.Path)
        if name in ('lock', 'unlock', 'renew'):
            parser.add_argument('--agent', required=True)
        if name in ('unlock', 'renew'):
            parser.add_argument('--token', required=True)
        if name == 'lock':
            parser.add_argument('--ttl-min', type=float, default=DEFAULT_TTL_MIN)
        if name in ('lock', 'fp', 'check'):
            parser.add_argument('--whole', action='store_true', help='包括 frontmatter 的全文指纹')
        if name == 'check':
            parser.add_argument('--fp', required=True)
    args = ap.parse_args()
    path = args.path.resolve()
    if not path.is_file():
        print('不是文件: %s' % path)
        return 2
    if args.command in ('fp', 'check'):
        current = content_fp(path, args.whole)
        if args.command == 'fp':
            print(current)
            return 0
        if current != args.fp:
            print('文件已变化；基线 %s，当前 %s' % (args.fp, current))
            return 4
        print('OK 内容未变')
        return 0
    record = lock_path(path, state_dir(path))
    with mutex(record):
        info = json.loads(record.read_text(encoding='utf-8')) if record.exists() else None
        now = time.time()
        if args.command == 'lock':
            if args.ttl_min < 0:
                ap.error('--ttl-min 必须非负')
            if info and now - info['ts'] <= info.get('ttl_min', DEFAULT_TTL_MIN) * 60:
                print('文件已被 %s 占用' % info['agent'])
                return 3
            payload = {'path': str(path), 'agent': args.agent, 'token': secrets.token_hex(24),
                       'ts': now, 'ttl_min': args.ttl_min, 'fp': content_fp(path, args.whole)}
            with record.open('w', encoding='utf-8') as handle:
                json.dump(payload, handle, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
            print(json.dumps(payload, ensure_ascii=False))
            return 0
        if info is None:
            print('没有锁记录')
            return 1
        # compare_digest 接受 str 时只认 ASCII，中文 agent 名会抛 TypeError 而不是返回 False；
        # 那会让 lock 成功、unlock 必崩，锁永远释放不掉。统一按 UTF-8 字节比。
        if not hmac.compare_digest(info['agent'].encode('utf-8'), args.agent.encode('utf-8')) or \
                not hmac.compare_digest(str(info.get('token', '')).encode('utf-8'),
                                        args.token.encode('utf-8')):
            print('认领身份或 token 不一致，禁止操作')
            return 3
        if args.command == 'unlock':
            record.unlink()
            print('UNLOCKED')
        else:
            info['ts'] = now
            record.write_text(json.dumps(info, ensure_ascii=False), encoding='utf-8')
            print('RENEWED')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
