#!/usr/bin/env node
/**
 * test-runtime-utils.js — 运行时工具回归测试（零网络、零 fixtures、纯合成数据）
 *
 * 覆盖：
 *  T4  timing-update.sh：只写 paper marker 区块，不新增/不删除现役 watch 行，幂等，--dry-run 不落盘
 *  T5  install-runtime-cron.sh：node 绝对路径、两条标记行、幂等、保留无关 cron、--dry-run 不写
 *
 * 运行：node tests/test-runtime-utils.js
 * 退出码：0=全部通过；1=有失败。
 */
'use strict';

const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const ROOT = path.resolve(__dirname, '..');
const SCRIPTS = path.join(ROOT, 'scripts');
const WORK = path.join(ROOT, 'tests', '.tmp-work-runtime');
// 断言中途失败也不留临时目录（此前异常退出会残留 tests/.tmp-work-runtime）
process.on('exit', () => { try { fs.rmSync(WORK, { recursive: true, force: true }); } catch {} });

let pass = 0;
let fail = 0;
const ok = (n, m) => { pass++; console.log(`  PASS ${n} — ${m}`); };
const bad = (n, m) => { fail++; console.log(`  FAIL ${n} — ${m}`); };
const run = (cmd, args, opts = {}) => {
  const r = spawnSync(cmd, args, { encoding: 'utf8', ...opts });
  return { code: r.status, stdout: r.stdout || '', stderr: r.stderr || '', out: (r.stdout || '') + (r.stderr || '') };
};

// ---------- T4：timing writer（离线 fake node/curl，合成代码 sh900001）----------
function testTiming() {
  console.log('\n== T4: timing-update paper-only ==');
  const binDir = path.join(WORK, '.fakebin');
  fs.mkdirSync(binDir, { recursive: true });

  // fake node：拦截 node -e '<脚本>' "$CODE" "$KJSON"，输出固定 paper 区块（模拟真实计算输出）
  const fakeNode = `#!/usr/bin/env bash
if [ "$1" = "-e" ]; then
  CODE="$2"; KJSON="$3"
  cat <<EOF
# === market-timing paper BEGIN（Phase 0：paper-only，不构成交易指令）===
# 本区块由 timing-update.sh 生成：只做 paper 观察记录，不写 watch.conf 主动买卖线，不触发任何交易指令
PAPER_TIMING|sh900001|2026-07-15|close=0.930|MA20=0.920|MA60=0.910|state=双上=paper观察仓口径
# === market-timing paper END ===
EOF
  exit 0
fi
exec "$(command -v -p node 2>/dev/null || echo /usr/bin/node)" "$@"
`;
  fs.writeFileSync(path.join(binDir, 'node'), fakeNode, { mode: 0o755 });

  // fake curl：输出合法 JSON K 线（70 根足够 MA60）
  const days = [];
  for (let i = 0; i < 70; i++) days.push(`"2026-07-${String((i % 28) + 1).padStart(2, '0')}",0.905,0.930,0.910,0.920`);
  const fakeCurl = `#!/usr/bin/env bash
echo '{"data":{"sh900001":{"qfqday":[${days.join(',')}]}}}'
`;
  fs.writeFileSync(path.join(binDir, 'curl'), fakeCurl, { mode: 0o755 });

  const sg = path.join(WORK, 'timing-sg');
  fs.rmSync(sg, { recursive: true, force: true });
  fs.mkdirSync(sg, { recursive: true });
  const wc = path.join(sg, 'watch.conf');
  const pre = [
    '# 用户重要注释A（不可删）',
    'watch|sz900002|below|10.50|合成止损线|说明文字',
    '# === 市场择时线 ===',
    'watch|sh900001|above|0.930|旧MA线1|说明',
    'watch|sh900001|below|0.900|旧MA线2|说明',
    '# 用户重要注释B（不可删）',
    'watch|sz900003|below|0.860|合成线|说明',
  ];
  fs.writeFileSync(wc, pre.join('\n') + '\n');
  const beforeLines = pre.join('\n').split('\n').length;

  const r = run('bash', [path.join(SCRIPTS, 'timing-update.sh'), 'sh900001', '--sg-home', sg],
    { env: { ...process.env, PATH: `${binDir}:${process.env.PATH}` } });

  if (/^PAPER_TIMING\|/m.test(r.stdout)) ok('T4a-paper-timing-line', '输出 PAPER_TIMING 机器行');
  else bad('T4a-paper-timing-line', `stdout 无 PAPER_TIMING 行：${r.stdout.slice(0, 200)} ${r.stderr.slice(0, 200)}`);

  const after = fs.readFileSync(wc, 'utf8');
  const watchBefore = pre.filter((l) => l.trim().startsWith('watch|')).length;
  const activeWatch = after.split('\n').filter((l) => l.trim().startsWith('watch|'));
  if (activeWatch.length === watchBefore) ok('T4b-no-watch-written', `现役 watch 行数 ${watchBefore}→${activeWatch.length}（无新增主动线）`);
  else bad('T4b-no-watch-written', `现役 watch 行数异常：${watchBefore}→${activeWatch.length}（${activeWatch.join(' ; ').slice(0, 200)}）`);

  const afterLines = after.split('\n');
  let bi = 0; let preserved = true; const lost = [];
  for (const l of pre) {
    let found = -1;
    for (let j = bi; j < afterLines.length; j++) if (afterLines[j] === l) { found = j; break; }
    if (found < 0) { preserved = false; lost.push(l); } else bi = found + 1;
  }
  if (preserved) ok('T4c-marker-outside-intact', `marker 外 ${beforeLines} 行全部保留且顺序不变`);
  else bad('T4c-marker-outside-intact', `marker 外行被删/乱序：${lost.slice(0, 3).join(' | ')}`);

  const snap1 = fs.readFileSync(wc, 'utf8');
  run('bash', [path.join(SCRIPTS, 'timing-update.sh'), 'sh900001', '--sg-home', sg], { env: { ...process.env, PATH: `${binDir}:${process.env.PATH}` } });
  const snap2 = fs.readFileSync(wc, 'utf8');
  if (snap1 === snap2) ok('T4d-idempotent', '连续两次运行文件内容一致（幂等）');
  else bad('T4d-idempotent', '连续两次运行产生不同内容');

  const sg2 = path.join(WORK, 'timing-sg2');
  fs.rmSync(sg2, { recursive: true, force: true });
  fs.mkdirSync(sg2, { recursive: true });
  const raw = 'watch|sz900002|below|10.50|x|y\n';
  fs.writeFileSync(path.join(sg2, 'watch.conf'), raw);
  run('bash', [path.join(SCRIPTS, 'timing-update.sh'), 'sh900001', '--sg-home', sg2, '--dry-run'], { env: { ...process.env, PATH: `${binDir}:${process.env.PATH}` } });
  if (fs.readFileSync(path.join(sg2, 'watch.conf'), 'utf8') === raw) ok('T4e-dryrun-nowrite', '--dry-run 不落盘');
  else bad('T4e-dryrun-nowrite', '--dry-run 修改了文件');
}

// ---------- T5：cron 幂等 ----------
function testCron() {
  console.log('\n== T5: install-runtime-cron 幂等 ==');
  const out1 = path.join(WORK, 'crontab.t1.txt');
  const g1 = run('bash', [path.join(SCRIPTS, 'install-runtime-cron.sh'), '--sg-home', WORK, '--out', out1]);
  if (g1.code !== 0) { bad('T5-generate', `生成失败：${g1.out.slice(0, 200)}`); return; }
  const c1 = fs.readFileSync(out1, 'utf8');
  if (!/^[^#\s]\S*\s+\S+\s+\S+\s+\S+\s+\S+\s+.*\/node /m.test(c1) && !/(\*|\d)\s+(\*|\d)\s+\S+\s+\S+\s+\S+\s+\S*\/node\s/.test(c1)) {
    bad('T5a-abs-node', 'cron 行未使用 node 绝对路径'); return;
  }
  ok('T5a-abs-node', 'cron 使用 node 绝对路径');
  // 四条：watchdog + doctor + 池线同步(每10分钟) + 开盘前 09:25 覆盖体检（2026-10-29 加，治理"开盘只有 1 条线"）
  if ((c1.match(/# phase0:runtime$/gm) || []).length === 4 && c1.includes('pool-watch-sync.js') &&
      c1.includes('coverage-audit.js --notify') && !c1.includes('timing-update.sh')) {
    ok('T5b-four-lines', '四条 cron（watchdog+doctor+池线同步+盘前覆盖体检）带标记，且无 timing paper cron（不自动装）');
  } else {
    bad('T5b-two-lines', `标记行数=${(c1.match(/# phase0:runtime$/gm) || []).length}，盘前体检存在=${c1.includes('coverage-audit.js --notify')}，timing cron 存在=${c1.includes('timing-update.sh')}`);
  }

  const g2 = run('bash', [path.join(SCRIPTS, 'install-runtime-cron.sh'), '--sg-home', WORK, '--out', out1]);
  const c2 = fs.readFileSync(out1, 'utf8');
  if (g2.code === 0 && c1 === c2) ok('T5c-idempotent', '重复运行输出一致（幂等）');
  else bad('T5c-idempotent', '重复运行输出不一致');

  fs.writeFileSync(out1, '# 我的无关任务\n0 9 * * * echo hello\n');
  run('bash', [path.join(SCRIPTS, 'install-runtime-cron.sh'), '--sg-home', WORK, '--out', out1]);
  const c3 = fs.readFileSync(out1, 'utf8');
  if (c3.includes('echo hello') && c3.includes('# 我的无关任务')) ok('T5d-keep-unrelated', '无关 cron 行保留');
  else bad('T5d-keep-unrelated', '无关 cron 行丢失');

  const before = fs.readFileSync(out1, 'utf8');
  run('bash', [path.join(SCRIPTS, 'install-runtime-cron.sh'), '--sg-home', WORK, '--out', out1, '--dry-run']);
  if (fs.readFileSync(out1, 'utf8') === before) ok('T5e-dryrun', '--dry-run 不写文件');
  else bad('T5e-dryrun', '--dry-run 写了文件');
}

fs.rmSync(WORK, { recursive: true, force: true });
fs.mkdirSync(WORK, { recursive: true });
testTiming();
testCron();

console.log(`\n通过 ${pass} / 失败 ${fail}`);
process.exit(fail > 0 ? 1 : 0);
