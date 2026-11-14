#!/usr/bin/env node
// 覆盖体检 + 线变更留痕 回归（离线沙箱，2026-10-29 立）
// 锁住的问题（都是当天真实暴露的）：
//   · 开盘那一刻"只有 1 条线在盯"（覆盖空白）必须被机器抓住；
//   · 池里有票但 watch 里没有线（缺线）→ FAIL；
//   · 池块里留着池里已没有的线（僵尸线）→ FAIL；
//   · 主题在队列里、候选载体却没人盯 → FAIL；
//   · 线在盘中凭空增删必须留痕（line-changes.log）。
'use strict';
const fs = require('fs'), path = require('path'), os = require('os');
const { execFileSync } = require('child_process');
const SCRIPTS = path.join(__dirname, '..', 'scripts');
const AUD = path.join(SCRIPTS, 'coverage-audit.js');
const SYNC = path.join(SCRIPTS, 'pool-watch-sync.js');
const LC = path.join(SCRIPTS, 'line-changes.js');
const { BEGIN, END } = require(AUD);

let pass = 0;
const bad = [];
function ck(name, got, want = true) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (ok) { pass++; console.log('  ✔ ' + name); } else { bad.push(name); console.log('  ✘ ' + name + '  got=' + JSON.stringify(got) + ' want=' + JSON.stringify(want)); }
}
const TODAY = '2026-10-29';

function sandbox() { return fs.mkdtempSync(path.join(os.tmpdir(), 'cov-')); }
function poolRow(id, code, dir, trig, voidP, exp = '2026-11-05') {
  return `POOL|${id}|2026-10-29|${code}|测试票${id}|${dir}|${trig}|${voidP}|${exp}|active|0|理由`;
}
function writeWatch(dir, blockLines, manualLines = []) {
  // 池块内 = pool-watch-sync 机器维护；块外 = 人工线（真实系统里两者物理分开，测试必须同样对待）
  const head = manualLines.length ? manualLines.concat(['']) : [];
  fs.writeFileSync(path.join(dir, 'watch.conf'), head.concat([BEGIN, ...blockLines, END, '']).join('\n'));
}
function runAudit(dir, date = TODAY) {
  try {
    const out = execFileSync('node', [AUD, '--sg-home', dir, '--date', date, '--json'], { encoding: 'utf8' });
    return { code: 0, r: JSON.parse(out) };
  } catch (e) { return { code: e.status, r: JSON.parse(e.stdout || '{}') }; }
}
const idsFailed = (r) => (r.items || []).filter((i) => !i.ok).map((i) => i.id);
const msgOf = (r, id) => ((r.items || []).find((i) => i.id === id) || {}).msg || '';

console.log('T1 齐全 → 全 PASS，退出码 0');
{
  const d = sandbox();
  fs.writeFileSync(path.join(d, 'pool.md'), [poolRow(1, 'sh900001', '低吸回踩', '7.62', '7.36'), ''].join('\n'));
  writeWatch(d, ['watch|sh900001|below|7.62|池票 测试票1 低吸观察触发线（低吸回踩）|回落触发价=系统通知+多维复核，非买入指令|至2026-11-03',
    'watch|sh900001|below|7.36|池票 测试票1 作废线（低吸回踩）|触及作废价=该观察计划失效（通知留档，不动手）|至2026-11-03']);
  const { code, r } = runAudit(d);
  ck('退出码 0', code, 0);
  ck('无 FAIL 项', idsFailed(r), []);
  ck('统计：池 1 行 / 监控 1 只', [r.poolActive, r.monitorCodes], [1, 1]);
}

console.log('T2 池里有票、watch 无这条线 → A1 FAIL');
{
  const d = sandbox();
  fs.writeFileSync(path.join(d, 'pool.md'), [poolRow(1, 'sh900001', '低吸回踩', '7.62', '7.36'), ''].join('\n'));
  writeWatch(d, ['watch|sh900001|below|7.62|池票 测试票1 低吸观察触发线（低吸回踩）|x|至2026-11-03']);   // 缺作废线
  const { code, r } = runAudit(d);
  ck('退出码 2', code, 2);
  ck('A1 报缺线', idsFailed(r), ['A1']);
  ck('缺的是作废线', /作废线/.test(msgOf(r, 'A1')), true);
}

console.log('T3 池块里有池里已没有的线（僵尸线）→ A2 FAIL');
{
  const d = sandbox();
  fs.writeFileSync(path.join(d, 'pool.md'), [poolRow(1, 'sh900001', '低吸回踩', '7.62', '7.36'), ''].join('\n'));
  writeWatch(d, ['watch|sh900001|below|7.62|池票 测试票1 低吸观察触发线（低吸回踩）|x|至2026-11-03',
    'watch|sh900001|below|7.36|池票 测试票1 作废线（低吸回踩）|x|至2026-11-03',
    'watch|sh999999|below|1.00|池票 已出池票 低吸观察触发线（低吸回踩）|x|至2026-11-03']);
  const { code, r } = runAudit(d);
  ck('退出码 2', code, 2);
  ck('A2 报僵尸线', idsFailed(r), ['A2']);
  ck('点出具体代码', /sh999999/.test(msgOf(r, 'A2')), true);
}

console.log('T4 过期线仍现役 → A3 FAIL');
{
  const d = sandbox();
  fs.writeFileSync(path.join(d, 'pool.md'), [poolRow(1, 'sh900001', '低吸回踩', '7.62', '7.36'), ''].join('\n'));
  writeWatch(d, ['watch|sh900001|below|7.62|池票 测试票1 低吸观察触发线（低吸回踩）|x|至2026-11-03',
    'watch|sh900001|below|7.36|池票 测试票1 作废线（低吸回踩）|x|至2026-11-03'],
  ['watch|sh900002|below|50.60|人工线 已过期|作废|至2026-10-01']);
  const { code, r } = runAudit(d);
  ck('退出码 2', code, 2);
  ck('A3 报过期线（且不误报 A2：块外人工线不参与漂移判定）', idsFailed(r), ['A3']);
}

console.log('T5 主题在队列、候选载体却没人盯 → A4 FAIL');
{
  const d = sandbox();
  fs.writeFileSync(path.join(d, 'pool.md'), [poolRow(1, 'sh900001', '低吸回踩', '7.62', '7.36'), ''].join('\n'));
  writeWatch(d, ['watch|sh900001|below|7.62|池票 测试票1 低吸观察触发线（低吸回踩）|x|至2026-11-03',
    'watch|sh900001|below|7.36|池票 测试票1 作废线（低吸回踩）|x|至2026-11-03']);
  fs.writeFileSync(path.join(d, 'themes.md'), ['THEME|卫星互联网|商业航天·卫星|2026-10-27|2026-10-29|active|组网提速|sh600118,sh600879', ''].join('\n'));
  const { code, r } = runAudit(d);
  ck('退出码 2', code, 2);
  ck('A4 报主题脱节', idsFailed(r), ['A4']);
  ck('点出载体', /sh600118/.test(msgOf(r, 'A4')), true);

  // 载体一旦有人盯 → A4 通过（同一沙箱，把 sh600118 加进 watch）
  const txt = fs.readFileSync(path.join(d, 'watch.conf'), 'utf8').replace(BEGIN, 'watch|sh600118|below|50.00|人工线|作废|至2026-11-05\n' + BEGIN);
  fs.writeFileSync(path.join(d, 'watch.conf'), txt);
  ck('载体进监控后 A4 通过', runAudit(d).r.items.find((i) => i.id === 'A4').ok, true);
}

console.log('T6 池里有行、池块 0 条线（开盘只有 1 条线的形态）→ A5 FAIL');
{
  const d = sandbox();
  fs.writeFileSync(path.join(d, 'pool.md'), [poolRow(1, 'sh900001', '低吸回踩', '7.62', '7.36'), ''].join('\n'));
  writeWatch(d, []);
  const { code, r } = runAudit(d);
  ck('退出码 2', code, 2);
  ck('A5 报覆盖空白', idsFailed(r).includes('A5'), true);
  ck('文案点明"盘中无人在盯"', /盘中无人在盯/.test(msgOf(r, 'A5')), true);
}

console.log('T7 已过期池行不参与覆盖要求（不误报）');
{
  const d = sandbox();
  fs.writeFileSync(path.join(d, 'pool.md'), [poolRow(1, 'sh900001', '低吸回踩', '7.62', '7.36', '2026-10-01'), ''].join('\n'));
  writeWatch(d, []);
  const { code, r } = runAudit(d);
  ck('退出码 0（过期行不要求线）', code, 0);
  ck('池 active 计 0', r.poolActive, 0);
}

console.log('T8 全新安装（文件都不存在）不判 FAIL');
{
  const d = sandbox();
  const { code, r } = runAudit(d);
  ck('退出码 0', code, 0);
  ck('全部 PASS（说明是跳过）', idsFailed(r), []);
}

console.log('T9 线变更留痕：同步增线/删线都写 line-changes.log');
{
  const d = sandbox();
  const pool = path.join(d, 'pool.md'), watch = path.join(d, 'watch.conf');
  const env = Object.assign({}, process.env, { SG_HOME: d, POOL_FILE: pool, WATCH_FILE: watch });
  fs.writeFileSync(pool, [poolRow(1, 'sh900001', '低吸回踩', '7.62', '7.36'), ''].join('\n'));
  execFileSync('node', [SYNC], { env, encoding: 'utf8' });
  let log = fs.readFileSync(path.join(d, 'line-changes.log'), 'utf8').trim().split('\n');
  ck('首次同步记 2 条 sync+', log.filter((l) => /\|sync\+\|/.test(l)).length, 2);
  fs.writeFileSync(pool, '');
  execFileSync('node', [SYNC], { env, encoding: 'utf8' });
  log = fs.readFileSync(path.join(d, 'line-changes.log'), 'utf8').trim().split('\n');
  ck('清池后记 2 条 sync-', log.filter((l) => /\|sync-\|/.test(l)).length, 2);
  ck('留痕含具体线内容', /watch\|sh900001\|below\|7\.62/.test(log.join('\n')), true);
  ck('格式统一（LINECHG|时间戳|动作|…）', /^LINECHG\|2026-\d\d-\d\d \d\d:\d\d:\d\d\|sync\+\|/.test(log[0]), true);
}

console.log('T10 line-changes.js append / tail 可用');
{
  const d = sandbox();
  const env = Object.assign({}, process.env, { SG_HOME: d });
  execFileSync('node', [LC, 'append', 'manual', 'sh900002', '人工撤线', '理由：突破档与低吸档同时挂会自相矛盾'], { env, encoding: 'utf8' });
  const out = execFileSync('node', [LC, 'tail', '5'], { env, encoding: 'utf8' });
  ck('写入并读回', /manual\|sh900002\|人工撤线/.test(out), true);
  ck('空目录 tail 不报错', execFileSync('node', [LC, 'tail'], { env: Object.assign({}, process.env, { SG_HOME: sandbox() }), encoding: 'utf8' }).trim(), '（无线变更记录）');
}

console.log('\n通过 ' + pass + ' 项' + (bad.length ? '，失败 ' + bad.length + ' 项：' + bad.join('、') : '，全部通过'));
process.exit(bad.length ? 1 : 0);
