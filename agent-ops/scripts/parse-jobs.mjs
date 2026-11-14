import fs from 'fs';
import path from 'path';

// 把 jobs.json 翻译成 bash 好读的形态：
//   state/gen/<任务>.meta        一行一个 JOB_XXX='值'，可直接 source
//   state/gen/<任务>.prompts/N.txt   每个提示词单独一个文件（中文、引号、换行都不用转义）
//   state/gen/names.txt          任务名清单

const root = path.resolve(process.argv[2]);
const jobsFile = path.join(root, 'jobs.json');
const genDir = path.join(root, 'state', 'gen');

if (!fs.existsSync(jobsFile)) {
  console.error('找不到配置文件：' + jobsFile);
  process.exit(1);
}

const cfg = JSON.parse(fs.readFileSync(jobsFile, 'utf8'));
const def = cfg.defaults || {};

fs.rmSync(genDir, { recursive: true, force: true });
fs.mkdirSync(genDir, { recursive: true });

const q = s => "'" + String(s).replace(/'/g, "'\\''") + "'";
const num = (v, d) => (typeof v === 'number' ? v : d);
const pick = (...xs) => { const v = xs.find(x => x !== undefined && x !== null && x !== ''); return v === undefined ? '' : v; };

const names = [];
for (const w of cfg.watchers || []) {
  if (w.enabled === false) continue;
  if (!w.name || !w.session_id) continue;
  const name = w.name;

  const pdir = path.join(genDir, name + '.prompts');
  fs.mkdirSync(pdir, { recursive: true });
  const prompts = Array.isArray(w.prompts) ? w.prompts : [];
  prompts.forEach((p, i) => {
    let text = '';
    if (p && typeof p === 'object') {
      // text 直接写；file 从 md 文件读（长提示词放外面更好维护）
      if (p.file) text = fs.readFileSync(path.resolve(root, p.file), 'utf8');
      else text = p.text || '';
    } else {
      text = String(p || '');
    }
    fs.writeFileSync(path.join(pdir, i + '.txt'), text);
  });

  const extra = w.extra_args || def.extra_args || ['-y'];
  const meta = {
    name,
    session_id: w.session_id,
    workdir: pick(w.workdir, def.workdir, process.env.HOME || '/root'),
    // 默认模型：免费档 free-model。想换就改这里的 DEFAULT_MODEL 或在 jobs.json 里配 model 字段
    model: String(pick(w.model, def.model, 'free-model-preview-ioa')),
    extra_args: extra.join(' '),
    check_interval_minutes: num(w.check_interval_minutes, num(def.check_interval_minutes, 5)),
    stale_minutes: num(w.stale_minutes, num(def.stale_minutes, 0)),
    max_restarts: num(w.max_restarts, num(def.max_restarts, 20)),
    restart_cooldown_seconds: num(w.restart_cooldown_seconds, num(def.restart_cooldown_seconds, 60)),
    prompt_mode: pick(w.prompt_mode, def.prompt_mode, 'step'),
    // 会话轮换:每 N 次拉起换一个新会话,防主会话上下文膨胀(每轮全量重发历史是大头消耗)。0 = 关闭
    session_rollover: num(w.session_rollover, num(def.session_rollover, 6)),
    sandbox: (w.sandbox === undefined ? (def.sandbox === undefined ? true : def.sandbox) : w.sandbox) ? '1' : '0',
    done_file: String(pick(w.done_file, '')),
    prompt_count: prompts.length,
    prompts_dir: pdir,
  };
  fs.writeFileSync(
    path.join(genDir, name + '.meta'),
    Object.entries(meta).map(([k, v]) => 'JOB_' + k.toUpperCase() + '=' + q(v)).join('\n') + '\n'
  );
  names.push(name);
}

fs.writeFileSync(path.join(genDir, 'names.txt'), names.join('\n') + (names.length ? '\n' : ''));
process.stdout.write(names.join(' '));
