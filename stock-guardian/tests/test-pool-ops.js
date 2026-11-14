#!/usr/bin/env node
// 观察池运维子命令回归（合成沙箱，不读真实账户数据）
// 覆盖：add 去重、同码两行出池不误核销、update 改字段留痕、update 参数校验、
//       已终态出池不改判、sync-picks 从台账补入池且幂等、满池即停。
'use strict';
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');

const SKILL = path.resolve(__dirname, '..');
const POOL = path.join(SKILL, 'scripts', 'pool.sh');
const PICKS = path.join(SKILL, 'scripts', 'picks-log.sh');
const HOME = fs.mkdtempSync(path.join(os.tmpdir(), 'pool-ops-'));
const env = Object.assign({}, process.env, { SG_HOME: HOME });
const pool = () => fs.readFileSync(path.join(HOME, 'pool.md'), 'utf8');
const ledger = () => fs.readFileSync(path.join(HOME, 'picks.md'), 'utf8');
const rows = () => pool().split('\n').filter((l) => l.startsWith('POOL|'));
const count = (re, text) => (text.match(re) || []).length;

let pass = 0;
const fail = [];
function ck(name, got, want) {
  if (String(got) === String(want)) { pass++; console.log('  ✔ ' + name); }
  else { fail.push(name); console.log('  ✘ ' + name + '：期望[' + want + '] 实际[' + got + ']'); }
}
function run(bin, args, wantFail) {
  try { return execFileSync(bash(bin), args, { env, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }); }
  catch (e) { if (wantFail) return ''; throw new Error(bin + ' ' + args.join(' ') + ' 失败：' + (e.stderr || e.message)); }
}
function bash(f) { return f; }
function exitCode(bin, args) {
  try { execFileSync(bin, args, { env, stdio: 'ignore' }); return 0; } catch (e) { return e.status || 1; }
}
const today = new Date().toISOString().slice(0, 10);

console.log('T1 入池：同码两行 + 台账去重');
run(POOL, ['add', 'sh510300', '测试ETF', '低吸防御', '1.00', '0.97', '2026-12-31', '低吸档']);
run(POOL, ['add', 'sh510300', '测试ETF', '突破追涨', '1.10', '1.06', '2026-12-31', '突破档']);
const id1 = rows()[0].split('|')[1];
const id2 = rows()[1].split('|')[1];
ck('池两行', rows().length, 2);
ck('台账仅一条 PICK', count(/^PICK\|/gm, ledger()), 1);

console.log('T2 同码两行时出池：不得误核销另一行的 PICK');
run(POOL, ['drop', id2, '清出', '测试：突破档撤下']);
ck('池剩一行', rows().length, 1);
ck('台账未出现终态', count(/^VERDICT\|/gm, ledger()), 0);
ck('出池留痕', count(/pool出池/g, fs.readFileSync(path.join(HOME, 'pool-ops.log'), 'utf8')) > 0, true);

console.log('T3 update 改字段');
run(POOL, ['update', id1, '--trig', '0.98', '--void', '0.95', '--exp', '2026-12-28', '回踩档下移']);
const row = rows()[0].split('|');
ck('触发价', row[6], '0.98');
ck('作废价', row[7], '0.95');
ck('有效期', row[8], '2026-12-28');
ck('状态仍 active', row[9], 'active');
ck('理由留痕', row[11].includes('update：回踩档下移'), true);
ck('台账 INSIGHT', count(/^INSIGHT\|/gm, ledger()), 1);
ck('只改一行', rows().length, 1);

console.log('T4 update 参数校验（缺字段/缺理由/行不存在都必须非零退出）');
ck('缺字段', exitCode(POOL, ['update', id1, '只给理由']) !== 0, true);
ck('缺理由', exitCode(POOL, ['update', id1, '--trig', '0.99']) !== 0, true);
ck('行不存在', exitCode(POOL, ['update', 'pool-19700101-9', '--trig', '1.00', 'x']) !== 0, true);
ck('校验失败不改文件', rows()[0].split('|')[6], '0.98');

console.log('T5 已终态出池：不改判');
const pickId = ledger().split('\n').filter((l) => l.startsWith('PICK|'))[0].split('|')[1];
fs.writeFileSync(path.join(HOME, 'picks.md'), ledger().split('\n').map((l) => (l.startsWith('PICK|') ? l.replace('|' + today + '|', '|2026-01-05|') : l)).join('\n'));
run(PICKS, ['verify', pickId, '命中', '测试：已兑现']);
run(POOL, ['drop', id1, '清出', '测试：兑现后撤下']);
ck('池空', rows().length, 0);
ck('VERDICT 仅一条', count(/^VERDICT\|/gm, ledger()), 1);
ck('仍是命中', new RegExp('^VERDICT\\|' + pickId + '\\|.*\\|命中\\|', 'm').test(ledger()), true);

console.log('T6 sync-picks 从台账补入池且幂等');
run(PICKS, ['rec', 'sh600519', '测试酒', '突破追涨', '1.50', '1.44', '2026-12-31', '台账推荐未入池']);
run(POOL, ['sync-picks', today]);
ck('补入 1 只', rows().length, 1);
ck('票号正确', rows()[0].split('|')[3], 'sh600519');
run(POOL, ['sync-picks', today]);
ck('二次运行幂等', rows().length, 1);

console.log('T7 满池即停（容量默认 10，可用 POOL_CAPACITY 覆盖）');
for (let i = 1; i <= 12; i++) run(PICKS, ['rec', 'sh9001' + String(i).padStart(2, '0'), '测试票' + i, '防御逆势', '1.00', '0.96', '2026-12-31', '容量测试']);
const before7 = rows().length;
run(POOL, ['sync-picks', today]);
ck('补至容量上限即停', rows().length, 10);
ck('确有补入（不是一条没进）', rows().length > before7, true);
let capBlocked = false;
try { execFileSync(POOL, ['add', 'sh999999', '测试票超容', '低吸防御', '1.00', '0.96', '2026-12-31', '容量覆盖'], { env: Object.assign({}, env, { POOL_CAPACITY: '2' }), stdio: 'ignore' }); } catch { capBlocked = true; }
ck('POOL_CAPACITY 覆盖生效（上限 2 时拒绝入池）', capBlocked, true);

console.log('T8 池内同链拦截（同一板块风险敞口池内只留一条）');
for (const r of rows()) run(POOL, ['drop', r.split('|')[1], '清出', 'T8 前置清池'], true);
fs.writeFileSync(path.join(HOME, 'chains.json'), JSON.stringify({ sh510300: '测试链A', sh511000: '测试链A', sh512000: '测试链B' }));
run(POOL, ['add', 'sh510300', '测试票甲', '低吸防御', '1.00', '0.96', '2026-12-31', '同链首条']);
ck('首条入池', rows().length, 1);
ck('同链第二条被拦（非零退出）', exitCode(POOL, ['add', 'sh511000', '测试票乙', '低吸防御', '1.00', '0.96', '2026-12-31', '同链第二条']) !== 0, true);
ck('同链未入池', rows().length, 1);
let out = run(POOL, ['add', 'sh511000', '测试票乙', '低吸防御', '1.00', '0.96', '2026-12-31', '同链第二条', '--allow-dup-chain']);
ck('显式放行可入池', rows().length, 2);
ck('放行有告警', /同链并行（已显式放行）/.test(out), true);
run(POOL, ['add', 'sh512000', '测试票丙', '低吸防御', '1.00', '0.96', '2026-12-31', '别链']);
ck('别链可入池', rows().length, 3);
out = run(POOL, ['add', 'sh513000', '测试票丁', '低吸防御', '1.00', '0.96', '2026-12-31', '未登记链条']);
ck('未登记链条给提示不拦', /未登记链条/.test(out), true);

console.log('T9 ls 显示链条（分散度可查）');
out = run(POOL, ['ls']);
ck('已登记显示链条名', /｜链条测试链A/.test(out), true);
ck('未登记显示未登记', /｜链条未登记/.test(out), true);
ck('ls 退出码为 0（池非空时曾因 [ ] && echo 返回 1）', exitCode(POOL, ['ls']), 0);

fs.rmSync(HOME, { recursive: true, force: true });
console.log('\n通过 ' + pass + ' 项' + (fail.length ? '，失败 ' + fail.length + ' 项：' + fail.join('、') : '，全部通过'));
process.exit(fail.length ? 1 : 0);
