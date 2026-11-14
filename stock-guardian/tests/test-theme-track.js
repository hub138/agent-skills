#!/usr/bin/env node
// 主题跟踪队列离线单测（不联网）：入队/每日tick/欠账可见/超期闭环/幂等/非法输入。
// 立此文件的原因：2026-10-29 用户质疑"是不是前两天或者昨天要持续观察"——雷达主题此前一次性、无跟踪。
'use strict';
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');

const SG = '<skill 根目录>';
const T = path.join(SG, 'scripts/theme-track.sh');
const HOME = fs.mkdtempSync(path.join(os.tmpdir(), 'tt-'));
const env = Object.assign({}, process.env, { SG_HOME: HOME });

let pass = 0;
const fail = [];
function ck(name, got, want = true) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (ok) { pass++; console.log('  ✔ ' + name); } else { fail.push(name); console.log('  ✘ ' + name + '  got=' + JSON.stringify(got) + ' want=' + JSON.stringify(want)); }
}
function run(args, wantFail) {
  try { return execFileSync('bash', [T].concat(args), { env, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }); }
  catch (e) { if (wantFail) return String(e.stdout || '') + String(e.stderr || ''); throw e; }
}
function code(args) {
  try { execFileSync('bash', [T].concat(args), { env, stdio: 'ignore' }); return 0; } catch (e) { return e.status || 1; }
}
const rows = () => (fs.existsSync(path.join(HOME, 'themes.md')) ? fs.readFileSync(path.join(HOME, 'themes.md'), 'utf8').trim().split('\n').filter(Boolean) : []);
const wdAgo = (n) => { // n 个交易日前的日期
  const d = new Date(); let left = n;
  while (left > 0) { d.setDate(d.getDate() - 1); if (d.getDay() !== 0 && d.getDay() !== 6) left--; }
  return d.toISOString().slice(0, 10);
};

console.log('T1 入队（目录不存在时自动创建，不许假报成功）');
ck('add 成功', /已入队主题/.test(run(['add', '卫星互联网', '商业航天·卫星', '10-27政策+10-28落地', 'sh600118,sh600879'])), true);
ck('写入 1 行 THEME', rows().length, 1);
ck('字段顺序正确', rows()[0].startsWith('THEME|卫星互联网|商业航天·卫星|'), true);

console.log('T2 幂等与输入校验');
ck('重复 add 被拒', /已在队列/.test(run(['add', '卫星互联网', 'x', 'y'], true)), true);
ck('竖线拒绝', /禁竖线/.test(run(['add', 'a|b', 'x', 'y'], true)), true);
ck('缺参数被拒', /用法/.test(run(['add', '只有主题'], true)), true);

console.log('T3 欠账可见（主题出现几天后才补登记，不许藏）');
run(['add', '能源保供', '煤炭·能源红利', '10-28发改委部署', 'sh900002', wdAgo(2)]);
const ls1 = run(['ls']);
ck('ls 标出补登记欠账', /能源保供[\s\S]*起始后\d+交易日才补登记/.test(ls1), true);
ck('due 只列欠账那条', /## 主题跟踪 · 待动作[\s\S]*能源保供[\s\S]*补登记/.test(run(['due'])) && !/卫星互联网/.test(run(['due'])), true);

console.log('T4 每日 tick');
run(['tick', '卫星互联网', '无新进展，跟踪中']);
ck('tick 追加日志', rows().some((r) => r.startsWith('THEME_LOG|卫星互联网|')), true);
ck('tick 更新最后动作日', /卫星互联网[\s\S]*\|active\|/.test(rows().find((r) => r.startsWith('THEME|卫星互联网'))), true);
ck('tick 不存在被拒', /没有活跃主题/.test(run(['tick', '不存在', 'x'], true)), true);

console.log('T5 超期与未 tick 告警（交易日口径，跳过周末）');
run(['add', '超期主题', '测试链', '证据', 'sh600000', wdAgo(3)]);
ck('超期标出未闭环', /超期主题[\s\S]*超3交易日未闭环/.test(run(['ls'])), true);
ck('due 含超期主题', /超期主题/.test(run(['due'])), true);

console.log('T6 闭环');
ck('非法终态被拒', /终态二选一/.test(run(['close', '卫星互联网', '也许吧', 'x'], true)), true);
ck('close 已覆盖', /已闭环/.test(run(['close', '卫星互联网', '已覆盖', '载体已转池行'])), true);
ck('THEME 行被摘掉', rows().some((r) => r.startsWith('THEME|卫星互联网|')), false);
ck('留 THEME_CLOSE 档', rows().some((r) => r.startsWith('THEME_CLOSE|卫星互联网|已覆盖|')), true);
ck('已闭环主题不可重复入队', /已闭环过/.test(run(['add', '卫星互联网', 'x', 'y'], true)), true);

console.log('T7 空队列与退出码');
run(['close', '能源保供', '已覆盖', 'x']); run(['close', '超期主题', '不参与', 'x']);
const out = run(['ls']);
ck('空队列提示', /（队列空）/.test(out), true);
ck('ls 退出码 0', code(['ls']), 0);
ck('due 退出码 0', code(['due']), 0);

fs.rmSync(HOME, { recursive: true, force: true });
console.log('\n通过 ' + pass + ' 项' + (fail.length ? '，失败 ' + fail.length + ' 项：' + fail.join('、') : '，全部通过'));
process.exit(fail.length ? 1 : 0);
