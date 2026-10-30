#!/usr/bin/env node
// 池票触发价接近提醒（2026-10-27 立）——每5分钟crontab交易时段跑
const fs = require('fs'), path = require('path'), { execSync } = require('child_process');
const SG = path.join(process.env.HOME || '/root', '.stock-guardian');
const SCRIPT_DIR = __dirname;
const FORCE = process.argv.includes('--force');
const now = new Date();
const dow = now.getDay(), hm = now.getHours() * 60 + now.getMinutes();
if (!FORCE) {
  if (dow === 0 || dow === 6) process.exit(0);
  if (hm < 570 || (hm > 690 && hm < 780) || hm > 900) process.exit(0);
}
const dbg = m => { try { fs.appendFileSync('/tmp/prox-debug.log', '[DBG] ' + m + '\n'); } catch (e) {} };
const pool = fs.readFileSync(path.join(SG, 'pool.md'), 'utf8').split('\n').filter(l => l.startsWith('POOL|'));
const poolMap = {};
for (const line of pool) {
  const f = line.split('|');
  const st = f[9], code = f[3], name = f[4], dir = f[5], trig = f[6];
  // 覆盖全池两侧（2026-10-29 修：此前仅 dir 含"低吸"的行 → 突破候选与"事件驱动"回踩型全漏，
  // 造成池票盘中触发零提醒；突破侧提示文案保持"非买入指令"，避免迟到追高）。
  if ((st === 'active' || st === 'triggered') && code && trig) {
    (poolMap[code] = poolMap[code] || []).push({ name, dir, up: /突破|追涨/.test(dir), trig: +trig, void: +f[7] });
  }
}
dbg('池读取: ' + Object.keys(poolMap).length + ' 只');
if (!Object.keys(poolMap).length) process.exit(0);
const codes = Object.keys(poolMap).join(',');
let pricesRaw = '';
try { pricesRaw = execSync('bash ' + path.join(SCRIPT_DIR, 'quote-public.sh') + ' quote "' + codes + '"', { timeout: 30000, encoding: 'utf8' }); } catch (e) { dbg('行情失败'); }
const lines = pricesRaw.split('\n').filter(l => l.startsWith('|'));
const head = (lines[0] || '').split('|').map(x => x.trim());
const ci = head.indexOf('code'), vi = head.indexOf('price');
if (ci < 0 || vi < 0) { dbg('表头无code/price列'); process.exit(0); }
const TODAY = now.toISOString().slice(0, 10);
const stateFile = path.join(SG, '.prox-state');
const state = fs.existsSync(stateFile) ? fs.readFileSync(stateFile, 'utf8') : '';
let notified = 0;
for (let i = 2; i < lines.length; i++) {
  const f = lines[i].split('|').map(x => x.trim());
  const code = f[ci], price = +f[vi];
  const list = poolMap[code];
  if (!code || !price || !list) continue;
  for (const p of list) {
    const dist = Math.abs(price - p.trig) / price * 100;
    dbg(code + ' 现价' + price + ' 触发' + p.trig + ' 距离' + dist.toFixed(2) + '%');
    if (dist > 1.0) continue;
    const key = 'prox|' + code + '|' + p.trig + '|' + TODAY;
    if (state.includes(key)) continue;
    fs.appendFileSync(stateFile, key + '\n');
    const dirName = p.up ? '突破候选' : '低吸候选';
    const crossed = p.up ? price >= p.trig : price <= p.trig;
    const nearLine = crossed
      ? '现价 ' + price + '，已' + (p.up ? '越过' : '跌破') + '观察触发价 ' + p.trig + '（幅度 ' + dist.toFixed(2) + '%）'
      : '现价 ' + price + '，距离观察触发价 ' + p.trig + ' 只差 ' + dist.toFixed(2) + '%';
    const body = '👀 观察池提醒：' + (p.name || code) + '（' + dirName + '）接近触发条件\n\n'
      + '📍 这只票在观察池里（系统在盯，你没有任何挂单，不需要做任何事）\n'
      + '📍 ' + nearLine + '\n'
      + '📍 它的观察计划：' + (p.up ? '站上 ' : '回落到 ') + p.trig + ' = 触发确认（跌破 ' + p.void + ' 观察作废）\n'
      + '⚠️ 触发 ≠ 买入信号——到价后我会发"触发确认"通知（含当时的量价与避雷检查），**那时候才是你决定买不买的时候**\n'
      + '💡 本条只是预告，无需任何操作，不构成投资建议。';
    try {
      execSync('bash ' + path.join(SCRIPT_DIR, 'notify-webhook.sh') + ' --title "股票管家·接近触发提醒" --tag 观察 --body "' + body.replace(/"/g, '\\"') + '"', { timeout: 30000, stdio: 'ignore' });
      fs.appendFileSync(path.join(SG, 'prox.log'), TODAY + ' 接近提醒: ' + code + ' 现价' + price + ' 距触发' + p.trig + ' ' + dist.toFixed(2) + '%\n');
      notified++;
    } catch (e) { dbg('通知失败: ' + code); }
  }
}
if (notified) console.log('接近提醒推送 ' + notified + ' 条');
