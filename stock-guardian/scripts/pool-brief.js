#!/usr/bin/env node
// pool-brief.js —— 观察池确定性播报行（2026-10-29 立）
// 背景：整点任务的"观察池一行带过"此前靠人工回忆，发生过列错/漏票（列了已出池的、
//   漏了在池且当日有异动的）。本脚本从 pool.md 机器行 + 实时行情生成可直接粘贴的池行，
//   整点任务（快照/尾盘等）必须粘贴本输出原文，禁止手写回忆。
// 用法：node pool-brief.js [--json]
const fs = require('fs'), path = require('path'), { execSync } = require('child_process');
const SG = process.env.SG_HOME || path.join(process.env.HOME || '/root', '.stock-guardian');
const SCRIPT_DIR = __dirname;
const JSON_OUT = process.argv.includes('--json');

const now = new Date();
const today = [now.getFullYear(), String(now.getMonth() + 1).padStart(2, '0'), String(now.getDate()).padStart(2, '0')].join('-');
const pool = fs.readFileSync(path.join(SG, 'pool.md'), 'utf8').split('\n').filter(l => l.startsWith('POOL|'));
const rows = [];
for (const line of pool) {
  const f = line.split('|');
  const [, id, , code, name, dir, trig, voidP, expiry, status] = f;
  if (!(status === 'active' || status === 'triggered') || !code || !trig) continue;
  if (expiry && expiry < today) continue;
  rows.push({ id, code, name, dir, trig: +trig, voidP: +voidP, expiry, status, up: /突破|追涨/.test(dir) });
}
if (!rows.length) { console.log('（池空）'); process.exit(0); }

const codes = [...new Set(rows.map(r => r.code))].join(',');
let prices = {};
try {
  const raw = execSync('bash ' + path.join(SCRIPT_DIR, 'quote-public.sh') + ' quote "' + codes + '"', { timeout: 30000, encoding: 'utf8' });
  const lines = raw.split('\n').filter(l => l.startsWith('|'));
  const head = (lines[0] || '').split('|').map(x => x.trim());
  const ci = head.indexOf('code'), vi = head.indexOf('price'), pi = head.indexOf('pct');
  for (let i = 2; i < lines.length; i++) {
    const f = lines[i].split('|').map(x => x.trim());
    if (f[ci]) prices[f[ci]] = { price: +f[vi], pct: pi >= 0 ? f[pi] : '' };
  }
} catch (e) { /* 行情失败降级为无价播报 */ }

const out = [], json = [];
for (const r of rows) {
  const q = prices[r.code] || {};
  const price = q.price;
  let distTxt = '';
  if (price) {
    const d = (Math.abs(price - r.trig) / price * 100).toFixed(1);
    const crossed = r.up ? price >= r.trig : price <= r.trig;
    distTxt = crossed ? `已${r.up ? '越过' : '跌破'}触发价 ${d}%` : `距触发 ${d}%`;
  }
  const side = r.up ? '突破' : '低吸';
  const flag = r.status === 'triggered' ? '已触发跟踪' : '观察中';
  const line = `- ${r.name}（${r.code}）${price ? price : '—'}${q.pct ? `（${q.pct}）` : ''}｜${side}触发 ${r.trig}${distTxt ? `（${distTxt}）` : ''}｜作废 ${r.voidP}｜${flag}｜至${r.expiry}`;
  out.push(line);
  json.push({ ...r, price: price || null, pct: q.pct || null });
}
if (JSON_OUT) console.log(JSON.stringify(json, null, 1));
else console.log('🟡 观察池（均未持有·仅监控，原文粘贴自 pool-brief 机器输出）：\n' + out.join('\n'));
