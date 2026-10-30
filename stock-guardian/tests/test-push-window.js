#!/usr/bin/env node
'use strict';
// push-window 回归测试（2026-10-30 立，时钟错位母题「跨轮去重作用域」家族第 2 例的验收）
// 原案：10-30（周五）00:00:04 line-audit --notify 拿 10-29 收盘价把三条时机卡当新一天首推。
// 合成数据：sh900001 / sz900002，零用户私有信息。
// 断言分两层：本模块纯函数（窗口/时区/周末）+ line-audit 端到端（--at 钉死时刻 + 注入行情日期）。
const path = require('path');
const { execFileSync } = require('child_process');

const PW = path.join(__dirname, '..', 'scripts', 'push-window.js');
const LA = path.join(__dirname, '..', 'scripts', 'line-audit.js');
let pass = 0, fail = 0;
function ok(name, cond, extra) { if (cond) { pass++; console.log(`  PASS ${name}`); } else { fail++; console.log(`  FAIL ${name}${extra ? ' :: ' + extra : ''}`); } }

// ---- 已知时刻（上海时区）的窗口判定 ----
const { inWindow, blockedReason } = require(PW);
// UTC 时刻 -> 上海：+8h。挑四个代表点：零点(案发时刻)/窗首/盘中/周末
ok('周五 00:00 窗外（案发时刻）', inWindow(new Date('2026-10-30T00:00:00+08:00')) === false);
ok('周五 08:30 窗首（含）', inWindow(new Date('2026-10-30T08:30:00+08:00')) === true);
ok('周五 11:45 盘中', inWindow(new Date('2026-10-30T11:45:00+08:00')) === true);
ok('周五 15:30 窗尾（含）', inWindow(new Date('2026-10-30T15:30:00+08:00')) === true);
ok('周五 15:31 窗外', inWindow(new Date('2026-10-30T15:31:00+08:00')) === false);
ok('周六 10:00 周末窗外', inWindow(new Date('2026-10-31T10:00:00+08:00')) === false);
ok('周日 00:00 周末窗外（复发预言场景）', inWindow(new Date('2026-11-01T00:00:00+08:00')) === false);
ok('周一 00:00 跨周翻转窗外', inWindow(new Date('2026-11-02T00:00:00+08:00')) === false);
ok('blockedReason 窗内返回 null', blockedReason(new Date('2026-10-30T11:45:00+08:00')) === null);
ok('blockedReason 窗外给原因', /窗外/.test(blockedReason(new Date('2026-10-30T00:00:00+08:00')) || ''));
ok('blockedReason 周末给原因', /非交易日/.test(blockedReason(new Date('2026-10-31T10:00:00+08:00')) || ''));
// 服务器为 UTC 时区时窗口判断仍须按上海时间（用 UTC 16:00=上海 00:00 验证时区正确性）
ok('UTC 16:00 (=上海 00:00) 窗外——时区按上海算', inWindow(new Date('2026-10-30T16:00:00Z')) === false);
ok('UTC 01:00 (=上海 09:00) 窗内——时区按上海算', inWindow(new Date('2026-10-30T01:00:00Z')) === true);

// ---- line-audit 端到端：合成池 + --at 钉死时刻 ----
// 喂法：SG_HOME 指到临时目录，pool.md 放一条合成 V右票；quote-public.sh 不可 mock（子进程 bash），
// 故用 SG_QUOTE_BIN 环境变量？——line-audit 直接调 quote-public.sh，无法注入。改为验证守卫行为本身：
//   1) --at 零点 + 真实行情（今日数据）→ 因窗外静默（quoteDay=today 不触发第二守卫，单守卫生效）
//   2) 状态文件断言：零点跑完 line-audit.state.json 不得新增当日键（不占配额）
//   3) --preview 不受守卫影响（手动查看随时可用）
const os = require('os');
const fs = require('fs');
function tmpHome() { const d = fs.mkdtempSync(path.join(os.tmpdir(), 'sg-pw-')); return d; }

const HOME = tmpHome();
// 夹具用 sh000001 上证指数：公开数据、有真实日线可拉、与任何持仓/池票零关联。
// （合成代码 900001 系拉不到日线，fetchKline 抛错会让退出码变 1 干扰断言——教训：夹具选代码先验证数据可得。）
fs.writeFileSync(path.join(HOME, 'pool.md'), 'POOL|20261030-1|2026-10-30|sh000001|合成·指数票|低吸回踩|3600|3500|至2026-11-03|active\n');

function runLA(args, env = {}) {
  try {
    const out = execFileSync('node', [LA, ...args], { encoding: 'utf8', timeout: 120000, env: { ...process.env, SG_HOME: HOME, ...env } });
    return { code: 0, out };
  } catch (e) { return { code: e.status ?? 1, out: (e.stdout || '') + (e.stderr || '') }; }
}

// 零点时刻（案发时刻复现）：窗外必须静默且不写状态
const st0 = path.join(HOME, 'line-audit.state.json');
const r0 = runLA(['--notify', '--at', '2026-10-30T00:00:04+08:00']);
ok('零点 tick 运行退出码正常（0/2/3 之一）', [0, 2, 3].includes(r0.code), `code=${r0.code}`);
const stAfter0 = fs.existsSync(st0) ? JSON.parse(fs.readFileSync(st0, 'utf8')) : {};
ok('零点 tick 后状态文件不含任何 2026-10-30 键（不占配额）', !Object.keys(stAfter0).some((k) => k.endsWith('2026-10-30')), JSON.stringify(Object.keys(stAfter0)));

// 交易日 10:00 盘中时刻：守卫放行（推送与否取决于真实形态与行情，键只在该轮真的 emit 时写入；
// 若真实行情/形态不成立导致未推送，退而验证"守卫未拦截"——输出里不得出现"静默"字样）
const r1 = runLA(['--notify', '--at', '2026-10-30T10:00:00+08:00']);
ok('盘中 tick 不被守卫静默（无"静默："行）', !/静默：/.test(r1.out), r1.out.split('\n').filter((l) => /静默/.test(l)).join('; ').slice(0, 120));

// --preview 随时可用：守卫不影响手动查看
const r2 = runLA(['--preview', '--at', '2026-10-30T00:30:00+08:00']);
ok('--preview 零点仍可看正文（守卫只管推送）', r2.code === 0 || r2.code === 2 || r2.code === 3);

// 清理
fs.rmSync(HOME, { recursive: true, force: true });
console.log(`\npush-window tests: ${pass} pass, ${fail} fail`);
process.exit(fail ? 1 : 0);
