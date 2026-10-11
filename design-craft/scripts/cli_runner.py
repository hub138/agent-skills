import json
import os
import pathlib
import re
import shlex
import shutil
import subprocess
import time

from markdown_it import MarkdownIt

# 公开 CLI 运行器：按环境变量 CLI_REVIEW_COMMAND 提供的命令模板调模型评审。
# 模板里 {model} 与 {prompt} 会被替换，例如：
#   export CLI_REVIEW_COMMAND="claude -p --model {model}"
#   export CLI_REVIEW_COMMAND="codex exec -m {model}"
# 未设置时依次探测 claude / codex / codebuddy。
DEFAULT_PROMPT_RUNNERS = (
    ('claude', ['claude', '-p', '--model', '{model}']),
    ('codex', ['codex', 'exec', '-m', '{model}']),
    ('codebuddy', ['codebuddy', 'chat', '-p']),
)
DEFAULT_MODELS = ('claude-sonnet', 'codex')


def executable():
    name = os.environ.get('CLI_REVIEW_COMMAND')
    if name:
        return shlex.split(name)
    for probe, template in DEFAULT_PROMPT_RUNNERS:
        if shutil.which(probe):
            return template
    raise FileNotFoundError('需要 claude/codex/codebuddy 之一，或设置 CLI_REVIEW_COMMAND')


def parse_output(text, exit_code):
    if exit_code:
        return 'error', '进程退出码 %s' % exit_code, ''
    content = text.strip()
    if not content:
        return 'error', '命令没有输出', ''
    lowered = content.lower()
    if any(s in lowered for s in ('rate limit', 'rate_limit', 'too many requests', '429')):
        return 'limited', content[:200], ''
    return 'finished', '', content


def parse_result(content):
    body = content.strip()
    if not body.startswith('{'):
        blocks = [t.content for t in MarkdownIt().parse(body)
                  if t.type == 'fence' and t.info.strip().lower() == 'json']
        if len(blocks) != 1:
            raise ValueError('最终回答需要一个 JSON 对象或唯一的 JSON 代码块')
        body = blocks[0]
    try:
        result = json.loads(body)
    except json.JSONDecodeError:
        result = repair_json(body)
    if not isinstance(result, dict):
        raise ValueError('评审输出必须为 JSON 对象')
    return result


def repair_json(body):
    """模型输出偶尔混入未转义引号或控制字符，能救则救，救不了返回空结果由调用方降级。

    直接抛出会让整篇评审前功尽弃：一次格式抖动比一条缺失意见代价大得多。
    """
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", body)
    dec = json.JSONDecoder()
    for start in range(len(cleaned)):
        if cleaned[start] != "{":
            continue
        try:
            obj, _ = dec.raw_decode(cleaned[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            obj["_repaired"] = True
            return obj
    raise ValueError('无法从输出里恢复 JSON 对象')


def run_json(prompt, files, workspace, models=DEFAULT_MODELS, exclude=(), timeout=180):
    workspace = pathlib.Path(workspace).resolve(strict=True)
    attachments = []
    for source in files:
        source = pathlib.Path(source).resolve(strict=True)
        target = workspace / source.name
        if target.exists():
            raise FileExistsError('评审附件重名: %s' % target.name)
        target.write_bytes(source.read_bytes())
        attachments.append(target)
    expected = {p: p.read_bytes() for p in attachments}
    chain = list(dict.fromkeys(m for m in models if m not in exclude))
    if any(not m or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._' for c in m)
           for m in chain):
        raise ValueError('模型名称含非法字符')
    if not chain:
        raise ValueError('没有独立可用的评审模型')
    deadline = time.monotonic() + timeout
    attempts = []
    for index, model in enumerate(chain):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('评审总时间预算已用尽')
        template = executable()
        command = [part.replace('{model}', model) for part in template]
        command += ['-p', prompt] if template[0] != 'codex' else [prompt]
        process = subprocess.run(command, cwd=workspace, text=True, capture_output=True,
                                 timeout=remaining, stdin=subprocess.DEVNULL)
        raw_path = workspace / ('attempt-%d-%s.jsonl' % (index, model))
        raw_path.write_text(process.stdout, encoding='utf-8')
        if any(p.read_bytes() != data for p, data in expected.items()):
            raise ValueError('评审输入被修改，拒绝采用结果')
        verdict, detail, content = parse_output(process.stdout, process.returncode)
        attempts.append({'model': model, 'verdict': verdict, 'detail': detail})
        if verdict == 'limited':
            continue
        if verdict != 'finished':
            raise RuntimeError('评审失败: %s' % detail)
        return parse_result(content), model, attempts
    raise RuntimeError('批准的模型均被限流: %s' % json.dumps(attempts, ensure_ascii=False))
