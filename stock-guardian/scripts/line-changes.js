#!/usr/bin/env node
'use strict';
/**
 * line-changes.js — 线变更留痕（2026-10-29 立）
 *
 * 由来：2026-10-29 实测心跳 rules 在 1→5→6→8→12→14→15→8 之间跳，
 * 但 watch.log 只有计数、没有"谁在几点加了/撤了哪条线、为什么"。
 * 结果：要回答"当时为什么没通知"，只能靠事后重建，不是取证。
 *
 * 格式（一行一条，append-only）：
 *   LINECHG|<YYYY-MM-DD HH:MM:SS>|<action>|<字段...>
 *   action：pool-add / pool-drop / sync+ / sync- / manual
 *
 * 用法：line-changes.js append <action> <字段...>     （SG_HOME 可用环境变量覆盖）
 *       line-changes.js tail [N]                      看最近 N 条（默认 20）
 */
const fs = require('fs');
const path = require('path');

const stamp = (d = new Date()) => {
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
};

function fileOf(sgHome) {
  return path.join(sgHome || process.env.SG_HOME || path.join(process.env.HOME || '/root', '.stock-guardian'), 'line-changes.log');
}

function append(sgHome, fields) {
  try { fs.appendFileSync(fileOf(sgHome), ['LINECHG', stamp(), ...fields].join('|') + '\n'); return true; } catch (e) { return false; }
}

module.exports = { append, stamp, fileOf };

if (require.main === module) {
  const [cmd, ...rest] = process.argv.slice(2);
  if (cmd === 'append') {
    if (!rest.length) { console.error('用法：line-changes.js append <action> <字段...>'); process.exit(2); }
    process.exit(append(undefined, rest) ? 0 : 1);
  } else if (cmd === 'tail') {
    const n = +rest[0] || 20;
    const f = fileOf();
    if (!fs.existsSync(f)) { console.log('（无线变更记录）'); process.exit(0); }
    const all = fs.readFileSync(f, 'utf8').trim().split('\n');
    console.log(all.slice(-n).join('\n'));
    process.exit(0);
  } else {
    console.error('用法：line-changes.js append <action> <字段...>  |  line-changes.js tail [N]');
    process.exit(2);
  }
}
