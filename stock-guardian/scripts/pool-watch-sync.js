#!/usr/bin/env node
// pool-watch-sync.js —— 池票→watch.conf 警报线自动同步（2026-10-29 立）
// 复盘背景：池票不自动挂线 → 盘中穿越/异动零通知（观察池票破位、突破、命中全静默）。
// 机制：把 pool.md 中 active/triggered 且在有效期内的行，映射成 watch.conf 机器维护块——
//   突破/追涨类 → above 触发线；低吸/事件回踩类 → below 触发线；两类都加 below 作废线。
//   块内每轮全量重写（幂等，内容不变则不落盘）；块外人工线一律不动。
// 用法：node pool-watch-sync.js [--dry]
//   环境变量：SG_HOME 覆盖数据区根；POOL_FILE / WATCH_FILE 覆盖输入输出（测试用）
const fs = require('fs'), path = require('path');

const SG = process.env.SG_HOME || path.join(process.env.HOME || '/root', '.stock-guardian');
const POOL = process.env.POOL_FILE || path.join(SG, 'pool.md');
const WATCH = process.env.WATCH_FILE || path.join(SG, 'watch.conf');
const DRY = process.argv.includes('--dry');

const BEGIN = '# === POOL-AUTO BEGIN（pool-watch-sync 机器维护：勿手改，改池用 pool.sh；块外人工线不受影响）===';
const END = '# === POOL-AUTO END ===';

const now = new Date();
const today = [now.getFullYear(), String(now.getMonth() + 1).padStart(2, '0'), String(now.getDate()).padStart(2, '0')].join('-');

if (!fs.existsSync(POOL)) { console.log('池文件不存在，跳过'); process.exit(0); }
const rows = fs.readFileSync(POOL, 'utf8').split('\n').filter(l => l.startsWith('POOL|'));

const seen = new Set();
const lines = [];
let active = 0, skipped = 0;
for (const row of rows) {
  const f = row.split('|');
  const id = f[1], code = f[3], name = f[4], dir = f[5] || '', trig = f[6], voidP = f[7], expiry = f[8], status = f[9];
  if (!(status === 'active' || status === 'triggered') || !code || !trig) { skipped++; continue; }
  if (expiry && expiry < today) { skipped++; continue; }
  active++;
  const up = /突破|追涨/.test(dir);
  const add = (cond, arg, label, action) => {
    const key = `${code}|${cond}|${arg}`;
    if (seen.has(key)) return;
    seen.add(key);
    lines.push(`watch|${code}|${cond}|${arg}|${label}|${action}|至${expiry}`);
  };
  if (up) add('above', trig, `池票 ${name} 突破观察触发线（${dir}）`, '越过触发价=系统通知+多维复核，非买入指令勿追高');
  else add('below', trig, `池票 ${name} 低吸观察触发线（${dir}）`, '回落触发价=系统通知+多维复核，非买入指令');
  if (voidP) add('below', voidP, `池票 ${name} 作废线（${dir}）`, '触及作废价=该观察计划失效（通知留档，不动手）');
}

const block = [BEGIN, `# 生成时间 ${today}｜在池 ${active} 行（跳过 ${skipped}）`, ...lines, END].join('\n');
let conf = fs.existsSync(WATCH) ? fs.readFileSync(WATCH, 'utf8') : '';
const bIdx = conf.indexOf(BEGIN), eIdx = conf.indexOf(END);
const hasBlock = bIdx >= 0 && eIdx > bIdx;
const oldBlock = hasBlock ? conf.slice(bIdx, eIdx).split('\n').filter((l) => l.startsWith('watch|')) : [];
const prefix = (hasBlock ? conf.slice(0, bIdx) : conf).replace(/\n+$/, '');
const next = (prefix ? prefix + '\n' : '') + block + '\n';

if (next === conf) { console.log(`池线同步：无变化（在池 ${active} 行 skip ${skipped}）`); process.exit(0); }
if (DRY) { console.log('--- DRY 块内容 ---\n' + block + '\n--- 共 ' + lines.length + ' 条 ---'); process.exit(0); }
// 线变更留痕（2026-10-29 立）：盘中线凭空消失/凭空出现是当天覆盖事故的根源，块内增删一律记一笔
const rec = require('./line-changes.js');
for (const l of oldBlock.filter((x) => !lines.includes(x))) rec.append(SG, ['sync-', l]);
for (const l of lines.filter((x) => !oldBlock.includes(x))) rec.append(SG, ['sync+', l]);
fs.writeFileSync(WATCH, next);
console.log(`池线同步：已写入 ${lines.length} 条（在池 ${active} 行 skip ${skipped}）→ ${WATCH}`);
