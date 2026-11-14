#!/usr/bin/env node
'use strict';
// state-core 回归测试：纯合成数据（sh900001 / sz900002），零用户私有信息
const fs = require('fs');
const path = require('path');
const os = require('os');
const { execFileSync } = require('child_process');

const CORE = path.join(__dirname, '..', 'scripts', 'state-core.js');
let pass = 0, fail = 0;
function ok(name, cond, extra) { if (cond) { pass++; console.log(`  PASS ${name}`); } else { fail++; console.log(`  FAIL ${name}${extra ? ' :: ' + extra : ''}`); } }
function run(args, env) {
  try {
    const out = execFileSync('node', [CORE, ...args], { encoding: 'utf8', env: { ...process.env, ...env } });
    return { code: 0, out };
  } catch (e) {
    return { code: e.status ?? 1, out: (e.stdout || '') + (e.stderr || '') };
  }
}
function jrun(args, env) {
  const r = run(args, env);
  try { return { ...r, json: JSON.parse(r.out) }; } catch (e) { return { ...r, json: null }; }

}
function tmpHome() {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'sg-core-'));
  return d;
}

console.log('state-core tests (synthetic)');
const H = tmpHome();

// 1 init + validate
let r = jrun(['init', '--sg-home', H]);
ok('init ok', r.code === 0 && r.json && r.json.ok, r.out.slice(0, 120));
r = jrun(['validate', '--sg-home', H]);
ok('validate after init', r.code === 0 && r.json.ok, r.out.slice(0, 160));

// 2 set-account CAS
r = jrun(['set-account', '--cash', '30000', '--cash-status', 'estimated', '--total-assets', '40000', '--data-status', 'estimated', '--expect-revision', '0', '--sg-home', H]);
ok('set-account accepted', r.code === 0 && r.json.ok, r.out.slice(0, 160));
r = jrun(['set-account', '--cash', '30000', '--expect-revision', '0', '--sg-home', H]);
ok('stale revision rejected', r.code !== 0 && /revision mismatch/.test(r.out), r.out.slice(0, 120));

// 3 unknown cash cannot be confirmed
r = jrun(['set-account', '--cash', 'unknown', '--cash-status', 'confirmed', '--expect-revision', '1', '--sg-home', H]);
ok('unknown cash cannot be confirmed', r.code !== 0, r.out.slice(0, 120));

// 4 set-position
r = jrun(['set-position', 'sh900001', '5000', '5000', 'unknown', 'user_report', '2026-10-27', '--expect-revision', '1', '--sg-home', H]);
ok('set-position ok', r.code === 0 && r.json.position && r.json.position.quantity === 5000, r.out.slice(0, 160));

// 5 record-execution SELL exceeding sellable rejected
r = jrun(['record-execution', '--id', 'e1', '--code', 'sh900001', '--side', 'SELL', '--qty', '6000', '--price', '0.7', '--expect-revision', '2', '--sg-home', H]);
ok('sell exceeds sellable rejected', r.code !== 0 && /sellable/.test(r.out), r.out.slice(0, 160));

// 6 historical execution does not change position
r = jrun(['record-execution', '--id', 'hist1', '--code', 'sh900001', '--side', 'SELL', '--qty', '3000', '--price', 'unknown', '--historical', '--expect-revision', '2', '--sg-home', H]);
ok('historical exec ok', r.code === 0 && r.json.ok, r.out.slice(0, 160));
r = jrun(['show', '--sg-home', H]);
const p1 = r.json.records.find(x => x.type === 'POSITION' && x.code === 'sh900001');
ok('historical exec leaves quantity', p1 && p1.quantity === 5000, JSON.stringify(p1));

// 7 unknown price -> estimated cash status
const acc = r.json.records.find(x => x.type === 'ACCOUNT');
ok('unknown price marks estimated', acc && acc.data_status === 'estimated', JSON.stringify(acc));

// 8 live SELL reduces position; BUY adds quantity but not sellable (T+1)
r = jrun(['record-execution', '--id', 'e2', '--code', 'sh900001', '--side', 'SELL', '--qty', '1000', '--price', '0.7', '--expect-revision', '3', '--sg-home', H]);
ok('live sell ok', r.code === 0 && r.json.position.quantity === 4000, r.out.slice(0, 200));
r = jrun(['record-execution', '--id', 'e3', '--code', 'sh900001', '--side', 'BUY', '--qty', '500', '--price', '0.7', '--expect-revision', '4', '--sg-home', H]);
// 卖出1000后 sellable=4000；T+1买入不增加当日可卖额度，故仍为4000
ok('buy adds quantity, sellable T+1 locked', r.code === 0 && r.json.position.quantity === 4500 && r.json.position.sellable === 4000, JSON.stringify(r.json.position));
r = jrun(['record-execution', '--id', 'e3', '--code', 'sh900001', '--side', 'BUY', '--qty', '500', '--price', '0.7', '--expect-revision', '5', '--sg-home', H]);
ok('execution idempotent', r.json.idempotent === true, r.out.slice(0, 160));

// 9 settle-t1 unlocks sellable
r = jrun(['settle-t1', '--expect-revision', '5', '--sg-home', H]);
ok('settle-t1 unlocks', r.code === 0 && r.json.settled >= 1, r.out.slice(0, 160));

// 10 import-pool merges dual entries into one candidate
const poolFile = path.join(H, 'pool.md');
fs.writeFileSync(poolFile, [
  '# pool',
  'POOL|p1|2026-10-01|sh900002|合成A|低吸防御|9.50|9.00|2026-11-01|active|0|计划一',
  'POOL|p2|2026-10-02|sh900002|合成A|突破追涨|10.50|9.80|2026-11-02|active|0|计划二',
  'POOL|p3|2026-10-03|sz900003|合成B|突破追涨|5.00|4.50|2026-11-03|active|0|计划三'
].join('\n'));
const beforeRev = jrun(['validate', '--sg-home', H]).json.revision;
r = jrun(['import-pool', '--source', poolFile, '--expect-revision', String(beforeRev), '--sg-home', H]);
ok('import-pool merges by code', r.code === 0 && r.json.imported === 2, r.out.slice(0, 160));
r = jrun(['show', '--sg-home', H]);
const cand = r.json.records.find(x => x.type === 'CANDIDATE' && x.code === 'sh900002');
ok('candidate has 2 entry plans', cand && cand.entry_plans.length === 2, JSON.stringify(cand));

// 11 render-views generated, no legacy copy
r = jrun(['render-views', '--sg-home', H]);
ok('render-views ok', r.code === 0 && fs.existsSync(path.join(H, 'views', 'portfolio.current.md')), r.out.slice(0, 160));
const pf = fs.readFileSync(path.join(H, 'views', 'portfolio.current.md'), 'utf8');
ok('view has positions from master', /sh900001/.test(pf) && /5000|4500/.test(pf), pf.slice(0, 200));

// 12 write without --expect-revision rejected
r = jrun(['set-position', 'sz900002', '100', '100', 'unknown', 'user_report', '2026-10-28', '--sg-home', H]);
ok('write requires expect-revision', r.code !== 0 && /expect-revision/.test(r.out), r.out.slice(0, 160));

// 13 invalid code rejected
r = jrun(['set-position', 'badcode', '100', '100', 'unknown', 'user_report', '2026-10-28', '--expect-revision', '0', '--sg-home', H]);
ok('invalid code rejected', r.code !== 0, r.out.slice(0, 140));

// 14 path whitelist: outside allowed prefixes rejected
r = jrun(['init', '--sg-home', '/etc/sg-evil']);
ok('path outside whitelist rejected', r.code !== 0 && /not allowed/.test(r.out), r.out.slice(0, 160));

// 15 privacy: 实现与测试不得含账户私有字面量；模式用字符码构造，避免扫描器自匹配
const PRIV_BACK = [[53, 56, 56, 49, 55, 48], [50, 53, 57, 48, 48], [50, 48, 57, 48, 48], [50, 54, 46, 53, 57], [108, 101, 111, 113, 113, 105, 97, 110], [119, 111, 97, 46, 99, 111, 109]];
const PRIV_RE = new RegExp(PRIV_BACK.map((a) => a.map((c) => String.fromCharCode(c)).join('').replace(/\./g, '\\.')).join('|'));
const src = fs.readFileSync(CORE, 'utf8') + fs.readFileSync(__filename, 'utf8');
ok('no private literals in code+tests', !PRIV_RE.test(src));

// 16 historical known-price exec must not double-count cash
const revNow = jrun(['validate', '--sg-home', H]).json.revision;
const cashBefore = jrun(['show', '--sg-home', H]).json.records.find(x => x.type === 'ACCOUNT').cash.amount;
r = jrun(['record-execution', '--id', 'hist2', '--code', 'sh900001', '--side', 'BUY', '--qty', '100', '--price', '0.5', '--historical', '--expect-revision', String(revNow), '--sg-home', H]);
const cashAfter = jrun(['show', '--sg-home', H]).json.records.find(x => x.type === 'ACCOUNT').cash.amount;
ok('historical known-price exec does not touch cash', r.code === 0 && cashBefore === cashAfter, `${cashBefore}->${cashAfter}`);

console.log(`\n通过 ${pass} / 失败 ${fail}`);
process.exit(fail > 0 ? 1 : 0);
