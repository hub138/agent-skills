#!/usr/bin/env node
// alerts-sync.js —— 警报线结构化源（alerts.conf）→ watch.conf ALERT-AUTO 块（2026-10-29 立）
// 复盘背景：watch.conf 的"块外人工线"一直靠人记得把 portfolio.md 的自由文本抄成规则行，
// 抄漏/抄错没人发现（check-sync 的启发式还"宁可漏报"）。此脚本让警报线只有一份结构化真相。
// 幂等：块内全量重写，块外内容（含 POOL-AUTO 块）原样不动。
'use strict';
const fs = require('fs');
const path = require('path');

const SG = process.env.SG_HOME || path.join(require('os').homedir(), '.stock-guardian');
const ALERTS = path.join(SG, 'alerts.conf');
const WATCH = process.env.WATCH_CONF || path.join(SG, 'watch.conf');
const BEGIN = '# === ALERT-AUTO BEGIN（alerts.conf 机器维护：勿手改本块，改线用 alerts.conf）===';
const END = '# === ALERT-AUTO END ===';

const today = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());

function build() {
  const out = [];
  let skipped = 0;
  if (fs.existsSync(ALERTS)) {
    for (const raw of fs.readFileSync(ALERTS, 'utf8').split(/\r?\n/)) {
      const ln = raw.trim();
      if (!ln.startsWith('alert|')) continue;
      const f = ln.split('|').map(x => x.trim());
      const [, code, cond, arg, label, action, exp, st] = f;
      if (!code || !cond || !arg) { skipped++; continue; }
      if ((st || 'active') !== 'active') { skipped++; continue; }
      if (/^至\d{4}-\d{2}-\d{2}$/.test(exp || '') && exp.slice(1) < today) { skipped++; continue; }
      out.push(['watch', code, cond, arg, label || '警报线', action || '触发=通知', exp || '永久'].join('|'));
    }
  }
  const block = [BEGIN, `# 生成时间 ${today}｜生效 ${out.length} 条（跳过 ${skipped}）`, ...out, END].join('\n');
  return { block, n: out.length, skipped };
}

const { block, n, skipped } = build();
let conf = fs.existsSync(WATCH) ? fs.readFileSync(WATCH, 'utf8') : '';
const b = conf.indexOf(BEGIN), e = conf.indexOf(END);
if (b >= 0 && e > b) conf = (conf.slice(0, b) + conf.slice(e + END.length)).replace(/\n{3,}/g, '\n\n');
conf = conf.replace(/\s*$/, '\n\n') + block + '\n';
fs.writeFileSync(WATCH, conf);
console.log(`alerts-sync: ${n} 条生效线已渲染（跳过 ${skipped}）→ ${WATCH}`);
