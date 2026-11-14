#!/usr/bin/env node
// stock-guardian 量化因子引擎 v3（2026-10-21 深夜定稿，subagent 审查修复版）
// 修复清单（对照 2026-10-21 审查报告）：①makeZ 传参致命 bug（已修，TopN 不再恒等于文件顺序）②qt/fflow 缓存按日期失效
// ③prepare：涨跌停不可成交约束（t+1 一字板剔除）/停牌前向填充（幸存者偏差）/RS5 日期轴对齐/mainPct<=0 跳过
// ④block bootstrap（块长5，修 t+3 滚动窗自相关）⑤secid 白名单校验 ⑥fflow https ⑦MF5 按日期定位
// 数据源（零密钥）：腾讯 ifzq 历史K线+qt实时（内外盘=qt[7]/qt[8]）+排行接口；东财 fflow 资金流历史；东财 np-anotice 公告
// 子命令：factors|score <codes> ｜ market [TopN]（v3 避雷打分）｜ pool ｜ backtest [宇宙] [天数] [TopN] [策略] [K线深度]
//         ｜ pullback <codes> [K线深度] [往返成本bp]（突破缩量回调可成交研究）
//         ｜ search [宇宙] [天数] [TopN] [K线深度]（权重网格+样本外验证）｜ intraday <codes> [阈值%] ｜ notices <code> [决策时点] ｜ cache clear
'use strict';
const fs = require('fs'), path = require('path');
const HOME = process.env.HOME || '/root';
const SG = process.env.SG_HOME || path.join(HOME, '.stock-guardian');
const CACHE = path.join(SG, 'cache', 'kline'), FLOWC = path.join(SG, 'cache', 'fflow');
const sleep = ms => new Promise(r => setTimeout(r, ms));
const CODE_RE = /^(sh|sz|bj)\d{6}$/;
const secid = c => (c.startsWith('sh') ? '1.' : '0.') + c.slice(2);
const num = v => (v === undefined || v === null || v === '' || v === '-') ? null : parseFloat(v);
const avg = a => a.reduce((x, y) => x + y, 0) / (a.length || 1);
const r2 = v => (v === null || v === undefined || isNaN(v)) ? '—' : (+v).toFixed(2);
const today = () => new Date(Date.now() + 8 * 3600e3).toISOString().slice(0, 10); // Asia/Shanghai 日界
async function j(url, tries = 2) {
  for (let i = 0; i < tries; i++) {
    try { const r = await fetch(url, { headers: { 'User-Agent': 'Mozilla/5.0', 'Referer': 'http://quote.eastmoney.com/' }, signal: AbortSignal.timeout(12000) }); if (!r.ok) throw new Error('HTTP ' + r.status); return await r.json(); }
    catch (e) { if (i === tries - 1) throw e; await sleep(800 + Math.random() * 600); }
  }
}
async function fetchAll(code, n = 260) {
  const key = code + '_' + n + '_' + today();
  fs.mkdirSync(CACHE, { recursive: true });
  const cf = path.join(CACHE, key + '.json'), qf = path.join(CACHE, code + '_qt_' + today() + '.json');
  let k, qt = null;
  if (fs.existsSync(cf)) k = JSON.parse(fs.readFileSync(cf, 'utf8'));
  else {
    const d = await j(`https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=${code},day,,,${n},qfq`);
    k = (d.data?.[code]?.qfqday || d.data?.[code]?.day || []).map(r => ({ d: r[0], o: +r[1], c: +r[2], h: +r[3], l: +r[4], v: +r[5] }));
    if (!k.length) throw new Error(code + ' K线为空');
    fs.writeFileSync(cf, JSON.stringify(k)); await sleep(250);
  }
  if (fs.existsSync(qf)) qt = JSON.parse(fs.readFileSync(qf, 'utf8'));
  else { try { const d = await j(`https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=${code},day,,,${n},qfq`); qt = d.data?.[code]?.qt?.[code] || null; if (qt) fs.writeFileSync(qf, JSON.stringify(qt)); } catch (e) { console.error(code + ' qt缺'); } await sleep(200); }
  return { k, qt };
}
async function fflow(code, n = 260) {
  fs.mkdirSync(FLOWC, { recursive: true });
  const cf = path.join(FLOWC, code + '_' + n + '.json'); // 永久缓存：历史资金流不变，增量合并，拉取失败回退旧缓存（东财风控不阻塞）
  let cached = fs.existsSync(cf) ? JSON.parse(fs.readFileSync(cf, 'utf8')) : [];
  const lastD = cached.length ? cached[cached.length - 1].d : '';
  const yst = new Date(Date.now() - 864e5 + 8 * 3600e3).toISOString().slice(0, 10);
  if (cached.length && lastD >= yst) return cached;
  try {
    const d = await j(`https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get?secid=${secid(code)}&fields1=f1,f2,f3,f7&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65&klt=101&lmt=${n}`);
    const rows = (d.data?.klines || []).map(r => { const a = r.split(','); return { d: a[0], main: +a[1], mainPct: +a[6] }; });
    if (!rows.length) return cached;
    const seen = new Set(cached.map(r => r.d)); const merged = [...cached, ...rows.filter(r => !seen.has(r.d))]; merged.sort((a, b) => a.d.localeCompare(b.d));
    fs.writeFileSync(cf, JSON.stringify(merged.slice(-n))); await sleep(250); return merged.slice(-n);
  } catch (e) { console.error(code + ' fflow增量失败，回退缓存:' + e.message); return cached.slice(-n); }
}
function factors(code, k, qt, ff, idx5Self) {
  const n = k.length, c = k[n - 1].c;
  const v20 = avg(k.slice(-21, -1).map(r => r.v));
  const LB20 = v20 ? k[n - 1].v / v20 : null;
  const pct = d => n > d && k[n - 1 - d].c ? (c / k[n - 1 - d].c - 1) * 100 : null;
  let trs = []; for (let i = Math.max(1, n - 14); i < n; i++) trs.push(Math.max(k[i].h - k[i].l, Math.abs(k[i].h - k[i - 1].c), Math.abs(k[i].l - k[i - 1].c)));
  const ATR14 = c ? avg(trs) / c * 100 : null;
  let BP = null;
  if (qt && num(qt[7]) !== null && num(qt[8]) !== null) { const o = +qt[7], i = +qt[8]; if (o + i > 0) BP = o / (o + i) * 100; }
  let MF1 = null, MF5 = null;
  if (ff.length) {
    const m1 = ff.find(r => r.d === k[n - 1].d); if (m1) MF1 = m1.mainPct;
    const iD = ff.map(r => r.d).indexOf(k[n - 1].d);
    if (iD >= 4) { const l5 = ff.slice(iD - 4, iD + 1); let sM = 0, sP = 0; l5.forEach(r => { if (r.mainPct === 0 && r.main !== 0) return; const amt = Math.abs(r.main / (r.mainPct / 100 || 1e-9)); sM += r.main; sP += amt; }); if (sP > 0) MF5 = sM / sP * 100; }
  }
  const CHG5 = pct(5), CHG10 = pct(10), CHG20 = pct(20);
  return { code, name: qt ? qt[1] : '', price: c, chg: qt ? num(qt[32]) : null, LB20, BP, CHG5, CHG10, CHG20, ATR14, MF1, MF5, RS5: CHG5 !== null && idx5Self !== null ? +(CHG5 - idx5Self).toFixed(2) : null };
}
const STRATS = {
  momentum: { LB20: .4, CHG5: .3, RS5: .3 },
  reversal: { CHG5: -.5, LB20: -.2, RS5: -.3 },
  lowvol: { ATR14: -.6, LB20: .2 },
  moneyflow: { MF5: -.6, LB20: .2 }, // v3：主力净占比反向（回测 CI[-68,-13] 显著负→避雷）
};
function makeZ(rows, keys) { const z = {}; for (const key of keys) { const vals = rows.map(r => r[key]).filter(v => v !== null && v !== undefined && !isNaN(v)); const mu = vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : 0; const sd = vals.length ? Math.sqrt(vals.reduce((a, b) => a + (b - mu) ** 2, 0) / vals.length) || 1 : 1; z[key] = v => (v === null || v === undefined || isNaN(v)) ? 0 : (v - mu) / sd; } return z; }
function calcScore(f, weights, zs) { let s = 0, tot = 0; for (const [k, w] of Object.entries(weights)) { s += w * zs[k](f[k]); tot += Math.abs(w); } return tot ? s / tot : 0; }
const W = ['code', 'name', 'price', 'chg', 'LB20', 'BP', 'CHG5', 'CHG10', 'CHG20', 'ATR14', 'MF1', 'MF5', 'RS5', 'SCORE'];
function printRows(rows, withScore) { const cols = [...W]; if (!withScore) cols.pop(); console.log('| ' + cols.join(' | ') + ' |'); console.log('|' + cols.map(() => '---').join('|') + '|'); rows.forEach(r => { if (r.err) { console.log('| ' + r.code + ' | ERR ' + r.err + ' |'); return; } console.log('| ' + cols.map(cn => { const v = r[cn]; if (cn === 'SCORE') return v === undefined ? '—' : v.toFixed(3); return v === null || v === undefined ? '—' : (typeof v === 'number' ? r2(v) : v); }).join(' | ') + ' |'); }); }

async function cmdFactors(codes, withScore) {
  const idx = await fetchAll('sh000001'); const ik = idx.k, idx5 = ik.length > 5 ? (ik[ik.length - 1].c / ik[ik.length - 6].c - 1) * 100 : 0;
  const rows = [];
  for (const code of codes.split(',').map(s => s.trim()).filter(c => CODE_RE.test(c))) {
    try { const { k, qt } = await fetchAll(code); const ff = await fflow(code, 30); rows.push(factors(code, k, qt, ff, idx5)); } catch (e) { rows.push({ code, err: e.message }); }
  }
  if (withScore) { const z = makeZ(rows, ['LB20', 'BP', 'CHG5', 'MF5', 'RS5']); rows.forEach(r => { if (!r.err) r.SCORE = calcScore(r, STRATS.momentum, z); }); rows.sort((a, b) => (b.SCORE ?? -9) - (a.SCORE ?? -9)); }
  printRows(rows, withScore);
  const dir = path.join(SG, 'factors'); fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, today() + '.json'), JSON.stringify({ ts: new Date().toISOString(), rows }, null, 1));
  console.log('\n因子快照已落 factors/' + today() + '.json（自有测试集累积）');
}

// 数据准备（一次拉取多组权重复用；2026-10-21 深夜审查修复版：涨跌停约束/停牌前向填充/RS5对齐/mainPct<=0跳过）
async function prepare(codes, N, KLEN, needFlow, sleepMs = 200) {
  const uni = [];
  for (const code of codes) { try { const { k, qt } = await fetchAll(code, KLEN); const ff = needFlow ? await fflow(code, N + 30) : []; uni.push({ code, k, qt, ff, name: qt ? qt[1] : '' }); } catch (e) { console.error('跳过 ' + code + ': ' + e.message); } await sleep(sleepMs); }
  const idx = await fetchAll('sh000001', KLEN);
  const axis = idx.k.map(r => r.d); const axisIdx = new Map(axis.map((d, i) => [d, i]));
  const limUp = code => code.startsWith('sz30') || code.startsWith('sh68') ? 0.198 : code.startsWith('bj') ? 0.298 : 0.0997;
  const ser = uni.filter(u => !/ST/.test(u.name));
  let coveredAtStart = 0; const startD = axis[Math.max(0, axis.length - N)];
  for (const s of ser) if (s.k.length && s.k[0].d <= startD) coveredAtStart++;
  const coverage = ser.length ? (coveredAtStart / ser.length * 100).toFixed(1) : '0';
  const ser2 = uni.map(u => ({ code: u.code, name: u.name, byD: new Map(u.k.map(r => [r.d, r])), ff: u.ff }));
  const perDay = [];
  for (let ai = Math.max(21, axis.length - N); ai < axis.length - 3; ai++) {
    const d = axis[ai], idx5 = ai >= 5 ? (idx.k[ai].c / idx.k[ai - 5].c - 1) * 100 : null; if (idx5 === null) continue;
    const cand = [];
    for (const s of ser2) {
      if (/ST/.test(s.name)) continue;
      const row = s.byD.get(d); if (!row) continue;
      const p5 = s.byD.get(axis[ai - 5])?.c; if (!p5) continue;
      const v20arr = []; for (let q = ai - 20; q < ai; q++) { const r = s.byD.get(axis[q]); if (r) v20arr.push(r.v); }
      if (v20arr.length < 15) continue; const v20 = v20arr.reduce((a, b) => a + b, 0) / v20arr.length; if (!v20) continue;
      const avgAmt = v20 * 100 * row.c; if (avgAmt < 3e7) continue; // 成交额下限 3000 万（审查#5）
      let trs = []; for (let q = Math.max(1, ai - 14); q <= ai; q++) { const r0 = s.byD.get(axis[q - 1]), r1 = s.byD.get(axis[q]); if (r0 && r1) trs.push(Math.max(r1.h - r1.l, Math.abs(r1.h - r0.c), Math.abs(r1.l - r0.c))); }
      if (trs.length < 10) continue; const ATR14 = row.c ? avg(trs) / row.c * 100 : null; if (ATR14 === null) continue;
      const iSelf = axisIdx.get(d); const idx5Self = (iSelf !== undefined && iSelf >= 5) ? (idx.k[iSelf].c / idx.k[iSelf - 5].c - 1) * 100 : idx5;
      const prevC = s.byD.get(axis[ai - 1])?.c;
      const GAP = prevC ? (row.o / prevC - 1) * 100 : null;
      const f = { LB20: row.v / v20, CHG5: (row.c / p5 - 1) * 100, RS5: (row.c / p5 - 1) * 100 - idx5Self, ATR14, BP: null, MF5: null, GAP, avgAmt };
      if (needFlow && s.ff.length) { const iD = s.ff.map(r => r.d).indexOf(d); if (iD >= 4) { const l5 = s.ff.slice(iD - 4, iD + 1); let sM = 0, sP = 0; l5.forEach(r => { if (r.mainPct === 0 && r.main !== 0) return; const amt = Math.abs(r.main / (r.mainPct / 100 || 1e-9)); sM += r.main; sP += amt; }); if (sP > 0) f.MF5 = sM / sP * 100; } }
      const findNext = (from, span) => { for (let q = from; q <= from + span + 5 && q < axis.length; q++) { const r = s.byD.get(axis[q]); if (r) return { c: r.c, o: r.o, d: axis[q] }; } return null; };
      const n1 = findNext(ai + 1, 0); if (!n1) continue;
      const n5 = findNext(ai + 5, 5); if (!n5) continue;
      const n10 = findNext(ai + 10, 8); if (!n10) continue;
      const n3 = findNext(ai + 3, 5); if (!n3) continue;
      if (n1.o / row.c - 1 >= limUp(s.code)) continue; // t+1 一字涨停买不进
      let n3x = { c: n3.c, o: n3.o, d: n3.d };
      if (n3.o / n1.c - 1 <= -limUp(s.code)) { let done = false; for (let q = axis.indexOf(n3.d) + 1; q < axis.length; q++) { const prev = s.byD.get(axis[q - 1]), r = s.byD.get(axis[q]); if (prev && r && r.o / prev.c - 1 > -limUp(s.code)) { n3x = { c: r.c, o: r.o, d: axis[q] }; done = true; break; } } if (!done) continue; } // t+3 一字跌停卖不出顺延
      cand.push({ code: s.code, name: s.name, f, t1: (n1.c / n1.o - 1) * 100, t3: (n3x.c / n1.o - 1) * 100, t5: (n5.c / n1.o - 1) * 100, t10: (n10.c / n1.o - 1) * 100 }); // 成交价=t+1开盘；t5/t10=目标持有期1-2周
    }
    if (cand.length >= 8) perDay.push({ d, cand });
  }
  if (+coverage < 80) console.error('⚠️ 宇宙覆盖度仅 ' + coverage + '%（首日即存在的票占比）——幸存者偏差警告');
  return { perDay, axis, coverage };
}
function blockBoot(arr, block = 5) {
  if (!arr.length) return [null, null];
  const width = Math.min(block, arr.length), out = [];
  for (let b = 0; b < 1000; b++) {
    const sample = [];
    while (sample.length < arr.length) {
      const start = Math.floor(Math.random() * (arr.length - width + 1));
      sample.push(...arr.slice(start, start + width));
    }
    out.push(avg(sample.slice(0, arr.length)));
  }
  out.sort((a, b) => a - b);
  return [out[25], out[975]];
}

function pullbackStats(events) {
  if (!events.length) return { n: 0 };
  const byDay = new Map();
  for (const e of events) {
    if (!byDay.has(e.entryDate)) byDay.set(e.entryDate, []);
    byDay.get(e.entryDate).push(e.netPct);
  }
  const daily = [...byDay.entries()].sort((a, b) => a[0].localeCompare(b[0])).map(([, returns]) => avg(returns));
  const sorted = events.map(e => e.netPct).sort((a, b) => a - b);
  const ci = blockBoot(daily);
  return {
    n: events.length,
    days: daily.length,
    target: events.filter(e => e.outcome === 'target').length,
    stop: events.filter(e => e.outcome === 'stop' || e.outcome === 'entry-day-stop').length,
    timeout: events.filter(e => e.outcome === 'timeout').length,
    winRate: events.filter(e => e.netPct > 0).length / events.length,
    meanNetPct: avg(daily),
    eventMeanNetPct: avg(events.map(e => e.netPct)),
    medianNetPct: sorted[Math.floor(sorted.length / 2)],
    worstNetPct: sorted[0],
    meanR: avg(events.map(e => e.rMultiple)),
    ci95Pct: ci,
  };
}

function printPullbackStats(label, s) {
  if (!s.n) {
    console.log(`| ${label} | 0 | 0 | — | — | — | — | — | — |`);
    return;
  }
  console.log(`| ${label} | ${s.n} | ${s.days} | ${(s.winRate * 100).toFixed(1)}% | ${s.meanNetPct.toFixed(2)}% | ${s.medianNetPct.toFixed(2)}% | ${s.worstNetPct.toFixed(2)}% | [${s.ci95Pct[0].toFixed(2)}, ${s.ci95Pct[1].toFixed(2)}]% | ${s.meanR.toFixed(2)} | ${s.target}/${s.stop}/${s.timeout} |`);
}

async function cmdPullback(codesArg, klen, costBp) {
  const codes = (codesArg || '').split(',').map(s => s.trim()).filter(c => CODE_RE.test(c));
  if (!codes.length) throw new Error('pullback 需要 sh/sz/bj 前缀代码，多个代码使用逗号分隔');
  const KLEN = +(klen || 640), COST_BP = +(costBp || 40);
  if (!Number.isFinite(KLEN) || KLEN < 60) throw new Error('K线深度必须是至少 60 的数字');
  if (!Number.isFinite(COST_BP) || COST_BP < 0) throw new Error('往返成本bp必须是非负数字');
  const events = [];
  const skipped = { noTrigger: 0, highGap: 0, noExitWindow: 0, invalidRisk: 0 };

  for (const code of codes) {
    const { k } = await fetchAll(code, KLEN);
    for (let i = 20; i < k.length - 7; i++) {
      const prior = k.slice(i - 20, i);
      const breakoutLevel = Math.max(...prior.map(r => r.h));
      const priorAvgVolume = avg(prior.map(r => r.v));
      const breakout = k[i];
      if (!(breakout.c > breakoutLevel && breakout.v >= priorAvgVolume * 1.5)) continue;

      let pullbackIndex = -1;
      for (let p = i + 1; p <= Math.min(i + 5, k.length - 7); p++) {
        if (k[p].c < breakoutLevel) break;
        const volumeOk = k[p].v <= breakout.v * 0.7;
        const supportOk = k[p].l >= breakoutLevel * 0.99;
        if (volumeOk && supportOk) { pullbackIndex = p; break; }
      }
      if (pullbackIndex < 0) continue;

      const pullback = k[pullbackIndex], entryBar = k[pullbackIndex + 1];
      const trigger = pullback.h;
      if (!(entryBar.h > trigger)) { skipped.noTrigger++; continue; }
      if (entryBar.o > trigger * 1.02) { skipped.highGap++; continue; }
      const entry = Math.max(entryBar.o, trigger), stop = pullback.l, risk = entry - stop;
      if (!(risk > 0)) { skipped.invalidRisk++; continue; }
      const target = entry + 2 * risk;
      if (pullbackIndex + 6 >= k.length) { skipped.noExitWindow++; continue; }

      let exit = null, exitDate = '', outcome = '';
      const entryDayStop = entryBar.l <= stop;
      for (let q = pullbackIndex + 2; q <= pullbackIndex + 6; q++) {
        const bar = k[q];
        if (entryDayStop && q === pullbackIndex + 2) {
          exit = bar.o;
          exitDate = bar.d;
          outcome = 'entry-day-stop';
          break;
        }
        if (bar.o <= stop) {
          exit = bar.o;
          exitDate = bar.d;
          outcome = 'stop';
          break;
        }
        if (bar.l <= stop) {
          exit = stop;
          exitDate = bar.d;
          outcome = 'stop';
          break;
        }
        if (bar.h >= target) {
          exit = target;
          exitDate = bar.d;
          outcome = 'target';
          break;
        }
        if (q === pullbackIndex + 6) {
          exit = bar.c;
          exitDate = bar.d;
          outcome = 'timeout';
        }
      }
      if (exit === null) continue;
      const grossPct = (exit / entry - 1) * 100;
      const netPct = grossPct - COST_BP / 100;
      events.push({
        code,
        breakoutDate: breakout.d,
        pullbackDate: pullback.d,
        entryDate: entryBar.d,
        exitDate,
        breakoutLevel,
        entry,
        stop,
        target,
        exit,
        outcome,
        grossPct,
        netPct,
        rMultiple: (exit - entry) / risk - COST_BP / 10000 * entry / risk,
      });
    }
    await sleep(200);
  }

  events.sort((a, b) => a.entryDate.localeCompare(b.entryDate) || a.code.localeCompare(b.code));
  const cut = Math.floor(events.length * 0.7);
  const inSample = events.slice(0, cut), outSample = events.slice(cut);
  const allStats = pullbackStats(events), inStats = pullbackStats(inSample), outStats = pullbackStats(outSample);
  let evidence = 'E0';
  if (events.length >= 30) evidence = 'E1';
  if (outStats.n >= 20 && outStats.ci95Pct && outStats.ci95Pct[0] > 0) evidence = 'E2';
  let verdict = '样本不足，只保留观察';
  if (events.length >= 30 && outStats.n && outStats.meanNetPct <= 0) verdict = '未通过：样本外日均组合净收益不为正';
  else if (evidence === 'E2') verdict = '通过历史样本外验证，可进入前向验证';
  else if (events.length >= 30) verdict = '样本外数量或置信区间未达标，只保留观察';

  console.log(`\n=== 突破缩量回调研究（${codes.length} 只，K线深度 ${KLEN}，往返成本 ${COST_BP}bp）===`);
  console.log('定义：收盘突破此前20日最高价且量≥20日均量1.5倍；1至5日内回调量≤突破日70%、收盘守住突破价、最低价不低于突破价99%；次日越过回调高点买入，高开超过2%放弃；回调低点作废、2R目标、5日退出；同日双触发按作废处理。');
  console.log('口径：事件级研究；成交日起遵守T+1，成交日触及作废价时次日开盘退出；收益已扣往返成本。');
  console.log('| 分段 | 事件数 | 独立日期数 | 事件胜率 | 日均组合净收益 | 事件中位净收益 | 最差事件净收益 | 按日期block-bootstrap 95%CI | 平均R | 目标/作废/到期 |');
  console.log('|---|---|---|---|---|---|---|---|---|---|');
  printPullbackStats('全样本', allStats);
  printPullbackStats('前70%', inStats);
  printPullbackStats('后30%', outStats);
  console.log(`证据等级：${evidence}（E0=样本不足；E1=仅历史样本；E2=后30%至少20个事件且平均净收益95%CI下界>0；E3只由前向成交记录授予）`);
  console.log(`方法裁决：${verdict}`);
  console.log(`放弃统计：未触发 ${skipped.noTrigger}｜高开超过2% ${skipped.highGap}｜退出窗口不足 ${skipped.noExitWindow}｜风险距离无效 ${skipped.invalidRisk}`);

  const dir = path.join(SG, 'factors');
  fs.mkdirSync(dir, { recursive: true });
  const runName = codes.length === 1 ? codes[0] : `${codes[0]}_n${codes.length}`;
  const output = path.join(dir, `pullback_${runName}_${today()}.json`);
  fs.writeFileSync(output, JSON.stringify({
    ts: new Date().toISOString(),
    params: { codes, klen: KLEN, costBp: COST_BP },
    definition: { breakoutDays: 20, breakoutVolumeMultiple: 1.5, pullbackWindow: 5, pullbackVolumeRatio: 0.7, supportRatio: 0.99, maxEntryGap: 0.02, targetR: 2, holdingDays: 5 },
    evidence,
    verdict,
    stats: { all: allStats, inSample: inStats, outSample: outStats },
    skipped,
    events,
  }, null, 1));
  console.log('研究报告已写入 ' + output);
}

function runStrat(perDay, weights, TN, costRT = 0.0040, horizon = 't3') {
  const daily = [];
  for (const { d, cand, mkt } of perDay) {
    const z = makeZ(cand.map(c => c.f), Object.keys(weights));
    const scored = cand.map(c => ({ ...c, s: calcScore(c.f, weights, z) })).sort((a, b) => b.s - a.s);
    const top = scored.slice(0, TN);
    const hz = c => c[horizon] === undefined ? c.t3 : c[horizon];
    daily.push({ d, top1: avg(top.map(c => c.t1)), top3: avg(top.map(c => hz(c))), uni1: avg(cand.map(c => c.t1)), uni3: avg(cand.map(c => hz(c))), mkt: mkt || 0 });
  }
  if (!daily.length) return null;
  const ci1 = blockBoot(daily.map(r => r.top1 - r.uni1)), ci3 = blockBoot(daily.map(r => r.top3 - r.uni3));
  const ex1 = avg(daily.map(r => r.top1 - r.uni1));
  const mean3 = avg(daily.map(r => r.top3));
  const ex3 = avg(daily.map(r => r.top3 - r.uni3));
  const costPct = costRT * 100;
  const netMean3 = +(mean3 - costPct).toFixed(2);
  const breakeven = +(mean3 / costPct).toFixed(2);
  return { days: daily.length, win1: daily.filter(r => r.top1 > 0).length / daily.length, mean1: avg(daily.map(r => r.top1)), ex1, win3: daily.filter(r => r.top3 - costPct > 0).length / daily.length, mean3, netMean3, ex3, breakeven, ci1: ci1.map(x => +(x * 100).toFixed(0)), ci3: ci3.map(x => +(x * 100).toFixed(0)), daily };
}
async function cmdBacktest(universeFile, days, topN, strat, klen) {
  const codes = fs.readFileSync(universeFile, 'utf8').split('\n').map(s => s.trim()).filter(s => s && !s.startsWith('#'));
  const N = +(days || 120), TN = +(topN || 3), KLEN = +(klen || 260);
  const want = (!strat || strat === 'all') ? Object.keys(STRATS) : [strat];
  const needFlow = want.some(s => STRATS[s].MF5);
  const { perDay, coverage } = await prepare(codes, N, KLEN, needFlow);
  console.log(`回测宇宙 ${codes.length} 只 × ${perDay.length} 日（K线深度 ${KLEN}，覆盖度 ${coverage}%，含涨跌停约束/停牌填充/成交额下限/block bootstrap），策略 [${want.join('/')}]，Top${TN}`);
  const summary = {};
  for (const sn of want) { const s = runStrat(perDay, STRATS[sn], TN); if (s) summary[sn] = s; }
  console.log('\n=== 策略对照回测（无未来函数；超额含 block-bootstrap 95%CI，跨 0 = 不显著）===');
  console.log('| 策略 | 样本日 | 次日开盘至收盘胜率（纸面/底仓） | 同期超额bp/日[95%CI] | 次日开盘至t+3净胜率 | t+3超额bp/日[95%CI] |');
  console.log('|---|---|---|---|---|---|');
  for (const [k, v] of Object.entries(summary)) console.log(`| ${k} | ${v.days} | ${(v.win1 * 100).toFixed(1)}% | ${(v.ex1 * 100).toFixed(0)} [${v.ci1[0]}, ${v.ci1[1]}] | ${(v.win3 * 100).toFixed(1)}% | ${(v.ex3 * 100).toFixed(0)} [${v.ci3[0]}, ${v.ci3[1]}] | t+3绝对净收益 ${v.netMean3.toFixed(2)}%（扣40bp成本，毛收益/成本倍数${v.breakeven}） |`);
  if (summary.momentum && summary.reversal && Math.sign(summary.momentum.ex1) === Math.sign(summary.reversal.ex1) && Math.abs(summary.momentum.ex1) > 10 && Math.abs(summary.reversal.ex1) > 10) console.log('⚠️ 方向矛盾：momentum 与 reversal 同号——因子无稳健信息，判无效（审查#7）');
  const byYear = {};
  for (const [k, v] of Object.entries(summary)) for (const r of v.daily) { const y = r.d.slice(0, 4); (byYear[y] = byYear[y] || {})[k] = (byYear[y][k] || []).concat([r]); }
  console.log('\n=== 分年度稳定性 ===');
  console.log('| 年份 | 策略 | 样本日 | t+1超额bp/日 | t+3超额bp/日 |');
  console.log('|---|---|---|---|---|');
  for (const [y, strats] of Object.entries(byYear)) for (const [k, days] of Object.entries(strats)) console.log(`| ${y} | ${k} | ${days.length} | ${(avg(days.map(r => r.top1 - r.uni1)) * 100).toFixed(0)} | ${(avg(days.map(r => r.top3 - r.uni3)) * 100).toFixed(0)} |`);
  const bt = path.join(SG, 'factors'); fs.mkdirSync(bt, { recursive: true });
  fs.writeFileSync(path.join(bt, `backtest_${today()}.json`), JSON.stringify({ params: { universe: codes.length, days: N, topN: TN, klen: KLEN }, summary, ts: new Date().toISOString() }, null, 1));
  console.log('回测报告已落 factors/backtest_' + today() + '.json');
}

// 全市场截面（腾讯排行 price 翻页全量+本地量比排序；v3 避雷版：主力净占比反向项）
async function cmdMarket(topN) {
  topN = +(topN || 30); const rows = [];
  for (let pg = 0; pg < 30; pg++) {
    const d = await j(`https://proxy.finance.qq.com/cgi/cgi-bin/rank/hs/getBoardRankList?board_code=aStock&sort_type=price&direct=down&offset=${pg * 200}&limit=200`);
    const list = d.data?.rank_list || []; if (!list.length) break;
    list.forEach(x => { const nm = x.name || ''; if (/ST|退/.test(nm)) return; const ltsz = num(x.ltsz); if (ltsz !== null && ltsz < 20) return;
      const zljlr = num(x.zljlr);
      rows.push({ code: x.code, name: nm, chg: num(x.zdf), turn: num(x.hsl), LB20: num(x.lb), CHG10: num(x.zdf_d10), CHG20: num(x.zdf_d20), cap: ltsz, pe: num(x.pe_ttm), lei: (zljlr !== null && ltsz) ? -(zljlr / (ltsz * 100)) : null }); });
    if (list.length < 200) break; await sleep(200);
  }
  rows.sort((a, b) => (b.LB20 ?? 0) - (a.LB20 ?? 0));
  const z = makeZ(rows, ['LB20', 'chg', 'CHG10', 'lei']);
  const WTS = { LB20: .35, chg: .25, CHG10: .15, lei: .25 }; // v3 避雷：momentum+主力净占比反向（回测显著负→避雷）
  rows.forEach(r => { r.SCORE = calcScore(r, WTS, z); });
  rows.sort((a, b) => b.SCORE - a.SCORE);
  const top = rows.slice(0, topN);
  console.log(`量比榜宇宙 ${rows.length} 只——量价分 v3 Top${topN}（量比.35+涨幅.25+10日.15+避雷.25【主力净占比反向，回测显著】）`);
  console.log('| 排名 | 代码 | 名称 | 量价分 | 涨幅% | 量比 | 10日% | 换手% | 避雷项 | 流通亿 |');
  console.log('|---|---|---|---|---|---|---|---|---|---|');
  top.forEach((r, i) => console.log(`| ${i + 1} | ${r.code} | ${r.name} | ${r.SCORE.toFixed(3)} | ${r2(r.chg)} | ${r2(r.LB20)} | ${r2(r.CHG10)} | ${r2(r.turn)} | ${r2(r.lei)} | ${r2(r.cap)} |`));
  const dir = path.join(SG, 'factors'); fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, 'market_' + today() + '.json'), JSON.stringify({ ts: new Date().toISOString(), top, total: rows.length }, null, 1));
  console.log('\n全市场截面已落 factors/market_' + today() + '.json');
}

// 权重网格搜索+样本外验证（前 70% 选优 → 后 30% 验证，防过拟合）
async function cmdSearch(universeFile, days, topN, klen) {
  const codes = fs.readFileSync(universeFile, 'utf8').split('\n').map(s => s.trim()).filter(s => s && !s.startsWith('#'));
  const N = +(days || 600), TN = +(topN || 3), KLEN = +(klen || 640);
  const { perDay } = await prepare(codes, N, KLEN, true, 250);
  const cut = Math.floor(perDay.length * 0.7);
  const inS = perDay.slice(0, cut), outS = perDay.slice(cut);
  console.log(`搜索宇宙 ${codes.length} 只 × ${perDay.length} 日；样本内 ${inS.length} 日（选优）/ 样本外 ${outS.length} 日（验证）`);
  const CANDS = [
    ['momentum(v2基准)', STRATS.momentum],
    ['mom-MF反向', { LB20: .35, CHG5: .25, RS5: .2, MF5: -.2 }],
    ['mom+低波', { LB20: .3, CHG5: .25, RS5: .25, ATR14: -.2 }],
    ['均衡五因子', { LB20: .25, CHG5: .2, RS5: .2, MF5: -.2, ATR14: -.15 }],
    ['纯资金流反向', { MF5: -.6, LB20: .2, CHG5: .2 }],
    ['短动量强化', { LB20: .3, CHG5: .4, RS5: .3 }],
    ['量比独裁', { LB20: .7, CHG5: .3 }],
    ['反转+隔夜过滤(v4)', { CHG5: -.5, GAP: -.2, LB20: .1 }],
    ['纯反转(v4)', { CHG5: -.6, RS5: -.2 }],
    ['缩量企稳(v4)', { CHG5: .2, LB20: -.3, RS5: -.2 }],
    ['隔夜跳空避雷(v4)', { GAP: -.6, CHG5: .1 }],
    ['mom+跳空避雷', { LB20: .3, CHG5: .25, RS5: .2, GAP: -.25 }],
    ['gap低开反转', { GAP: -.4, CHG5: -.2, LB20: .2 }],
    ['mom+跳空+MF', { LB20: .3, CHG5: .2, RS5: .15, GAP: -.15, MF5: -.2 }],
  ];
  const rows = [];
  for (const [nm, w] of CANDS) { const sIn = runStrat(inS, w, TN), sOut = runStrat(outS, w, TN); if (!sIn || !sOut) continue; rows.push({ nm, w, inEx1: sIn.ex1, outEx1: sOut.ex1, outEx3: sOut.ex3, outWin3: sOut.win3, outCI3: sOut.ci3 }); }
  rows.sort((a, b) => b.inEx1 - a.inEx1);
  console.log('\n=== 权重搜索（按样本内 t+1 超额排序；过拟合检验看样本外列）===');
  console.log('| 权重方案 | 样本内t+1超额 | 样本外t+1超额 | 样本外t+3超额 | 样本外t+3胜率 | 样本外t+3 CI[95%] |');
  console.log('|---|---|---|---|---|---|');
  rows.forEach(r => console.log(`| ${r.nm} | ${(r.inEx1 * 100).toFixed(0)}bp | ${(r.outEx1 * 100).toFixed(0)}bp | ${(r.outEx3 * 100).toFixed(0)}bp | ${(r.outWin3 * 100).toFixed(1)}% | [${r.outCI3[0]}, ${r.outCI3[1]}] |`));
  const best = rows[0];
  if (best) console.log(`\n样本内最优：${best.nm}（+${(best.inEx1 * 100).toFixed(0)}bp/日）→ 样本外：t+1 ${(best.outEx1 * 100).toFixed(0)}bp、t+3 ${(best.outEx3 * 100).toFixed(0)}bp——样本外仍为正才可定型 v3 权重`);
  const bt = path.join(SG, 'factors'); fs.mkdirSync(bt, { recursive: true });
  fs.writeFileSync(path.join(bt, `search_${today()}.json`), JSON.stringify({ ts: new Date().toISOString(), cut, results: rows.map(r => ({ nm: r.nm, w: r.w, inEx1: r.inEx1, outEx1: r.outEx1, outEx3: r.outEx3 })) }, null, 1));
  console.log('搜索报告已落 factors/search_' + today() + '.json');
}

// 随机权重搜索（机器调参替代手挑）+ 随机基线对照：K 组随机权重，训练段(前70%)选优，验证段(后30%)验证
// 判定：Top组验证段超额 必须 > 随机基线中位数（否则"优化"只是随机波动）
async function cmdRandomSearch(universeFile, K, klen) {
  const codes = fs.readFileSync(universeFile, 'utf8').split('\n').map(x => x.trim()).filter(x => x && !x.startsWith('#'));
  const KLEN = +(klen || 640);
  const { perDay } = await prepare(codes, 600, KLEN, true, 250);
  const cut = Math.floor(perDay.length * 0.7);
  const inS = perDay.slice(0, cut), outS = perDay.slice(cut);
  const KEYS = ['LB20', 'CHG5', 'RS5', 'ATR14', 'MF5', 'GAP'];
  const rand = () => { const w = {}; let raw = KEYS.map(() => Math.random() * 2 - 1); const nrm = Math.sqrt(raw.reduce((a, b) => a + b * b, 0)) || 1; KEYS.forEach((k, i) => w[k] = +(raw[i] / nrm).toFixed(3)); return w; };
  const TRIALS = [];
  for (let i = 0; i < K; i++) {
    const w = rand();
    const sIn = runStrat(inS, w, 3, 0.0040, 't5'), sOut = runStrat(outS, w, 3, 0.0040, 't5');
    if (!sIn || !sOut) continue;
    TRIALS.push({ i, w, inEx: sIn.ex1, outEx1: sOut.ex1, outEx5: sOut.ex3 });
    if ((i + 1) % 50 === 0) console.error(`  ...已试 ${i + 1}/${K}`);
  }
  TRIALS.sort((a, b) => b.inEx - a.inEx);
  const outExAll = TRIALS.map(t => t.outEx1), outExAll5 = TRIALS.map(t => t.outEx5);
  const median = a => { const x = [...a].sort((p, q) => p - q); return x[Math.floor(x.length / 2)] || 0; };
  const base1 = median(outExAll), base5 = median(outExAll5);
  const top10 = TRIALS.slice(0, 10), top50 = TRIALS.slice(0, 50);
  console.log(`\n=== 随机权重搜索 ${TRIALS.length} 组（持有期 t+5≈1周；训练 ${inS.length} 日/验证 ${outS.length} 日）===`);
  console.log(`随机基线（全部组验证段中位数）：t+1 ${(base1 * 100).toFixed(0)}bp｜t+5 ${(base5 * 100).toFixed(0)}bp`);
  console.log(`训练段 Top10 的验证段：t+1 ${(avg(top10.map(t => t.outEx1)) * 100).toFixed(0)}bp（相对基线 ${((avg(top10.map(t => t.outEx1)) - base1) * 100).toFixed(0)}bp）｜t+5 ${(avg(top10.map(t => t.outEx5)) * 100).toFixed(0)}bp（相对基线 ${((avg(top10.map(t => t.outEx5)) - base5) * 100).toFixed(0)}bp）`);
  console.log(`Top50 均值：t+1 ${(avg(top50.map(t => t.outEx1)) * 100).toFixed(0)}bp（相对基线 ${((avg(top50.map(t => t.outEx1)) - base1) * 100).toFixed(0)}bp）`);
  console.log('——Top10/Top50 相对随机基线为正且幅度可观，优化才有效；≈0 = 权重调整无意义（alpha 不在权重里）');
  console.log('\n训练段 Top5：');
  top10.slice(0, 5).forEach(t => console.log(`  #${t.i} ${JSON.stringify(t.w)}｜验证 次日开盘至收盘超额 ${(t.outEx1 * 100).toFixed(0)}bp｜次日开盘至t+5超额 ${(t.outEx5 * 100).toFixed(0)}bp`));
  const dir = path.join(SG, 'factors'); fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, 'randomsearch_' + today() + '.json'), JSON.stringify({ ts: new Date().toISOString(), trials: K, base1, base5, top10: top10.map(t => ({ w: t.w, outEx1: t.outEx1, outEx5: t.outEx5 })) }, null, 1));
  console.log('搜索报告已落 factors/randomsearch_' + today() + '.json');
}

// 观察池报告
async function cmdPool() {
  const pf = path.join(SG, 'pool.md');
  if (!fs.existsSync(pf)) { console.log('（观察池空——盘后荐股负责补新，不硬凑）'); return; }
  const items = fs.readFileSync(pf, 'utf8').split('\n').filter(l => l.startsWith('POOL|')).map(l => { const f = l.split('|'); return { id: f[1], code: f[3], name: f[4], dir: f[5], trig: +f[6], void: +f[7], exp: f[8], st: f[9] }; });
  if (!items.length) { console.log('（观察池空——盘后荐股负责补新，不硬凑）'); return; }
  const idx = await fetchAll('sh000001'); const ik = idx.k, idx5 = ik.length > 5 ? (ik[ik.length - 1].c / ik[ik.length - 6].c - 1) * 100 : 0;
  console.log(`📋 观察池报告（${today()}，共 ${items.length} 只，容量 5）\n`);
  for (const it of items) {
    try {
      const { k, qt } = await fetchAll(it.code); const ff = await fflow(it.code, 30);
      const f = factors(it.code, k, qt, ff, idx5);
      const px = f.price, isDip = /低吸/.test(it.dir);
      const dTrig = isDip ? (px - it.trig) / px * 100 : (it.trig - px) / px * 100;
      const dVoid = (px - it.void) / px * 100;
      const stTag = it.st === 'triggered' ? '【已触发·跟踪兑现度】' : (dTrig <= 0 ? '【已进触发区·待你拍板】' : `【观察中·距触发 ${dTrig.toFixed(1)}%】`);
      console.log(`━ ${it.name}（${it.code}）现价 ${px} ${stTag}`);
      console.log(`  ✅ 方向 ${it.dir}｜触发 ${it.trig}｜❌ 作废 ${it.void}（安全垫 ${dVoid.toFixed(1)}%）｜⏰ 有效期至 ${it.exp}`);
      console.log(`  📊 量比 ${r2(f.LB20)}｜买盘 ${r2(f.BP)}%｜5日 ${r2(f.CHG5)}%｜RS5 ${r2(f.RS5)}｜主力5日占比 ${r2(f.MF5)}%｜ATR ${r2(f.ATR14)}%`);
      console.log(`  💬 判读：${f.LB20 >= 1.5 ? '放量' : f.LB20 <= 0.7 ? '缩量' : '量能平'}；${f.MF5 !== null ? (f.MF5 > 0 ? '5日资金净流入' : '5日资金净流出') : '资金流数据缺'}${f.RS5 !== null ? `；相对大盘${f.RS5 > 0 ? '强 ' + r2(f.RS5) : '弱 ' + r2(-f.RS5)} 点` : ''}`);
      await sleep(250);
    } catch (e) { console.log(`━ ${it.name}（${it.code}）数据异常：${e.message}`); }
  }
}

// 分时形态回测：开盘急拉（多阈值敏感性）
async function cmdIntraday(codes, xPct) {
  const X = +(xPct || 2);
  let samples = 0, surge = 0, surgeWin = 0, surgeSum = 0, allSum = 0, allN = 0, nextWin = 0, nextN = 0, nextSum = 0;
  const dist = [], allPulls = [];
  for (const code of codes.split(',').map(s => s.trim()).filter(c => CODE_RE.test(c))) {
    try {
      const d = await j(`https://ifzq.gtimg.cn/appstock/app/kline/mkline?param=${code},m5,,2000`);
      const m5 = d.data?.[code]?.m5 || d.data?.[code]?.m5qfq; if (!m5 || m5.length < 100) continue;
      const byDay = new Map();
      m5.forEach(r => { const day = r[0].slice(0, 8); if (!byDay.has(day)) byDay.set(day, []); byDay.get(day).push({ t: r[0], o: +r[1], c: +r[2] }); });
      const days = [...byDay.keys()].sort();
      for (let i = 1; i < days.length - 1; i++) {
        const bars = byDay.get(days[i]); if (bars.length < 40) continue;
        const openP = bars[0].o, p935 = bars[0].c; if (!openP) continue;
        const pull = (p935 / openP - 1) * 100, closeP = bars[bars.length - 1].c;
        const dayRet = (closeP / p935 - 1) * 100;
        const nextOpen = byDay.get(days[i + 1])?.[0]?.o;
        const nextRet = nextOpen ? (nextOpen / closeP - 1) * 100 : null;
        samples++; allSum += dayRet; allN++; allPulls.push({ pull, dayRet });
        if (pull >= X) { surge++; surgeSum += dayRet; if (dayRet > 0) surgeWin++; if (nextRet !== null) { nextN++; nextSum += nextRet; if (nextRet > 0) nextWin++; dist.push({ code, day: days[i], pull: +pull.toFixed(2), dayRet: +dayRet.toFixed(2), nextRet: +nextRet.toFixed(2) }); } }
      }
      await sleep(250);
    } catch (e) {}
  }
  const allMean = allN ? allSum / allN : 0;
  const statAt = x => { const s = allPulls.filter(p => p.pull >= x); if (!s.length) return `阈值${x}%：样本0`; const m = avg(s.map(p => p.dayRet)); return `阈值${x}%：n=${s.length} 胜率${(s.filter(p => p.dayRet > 0).length / s.length * 100).toFixed(1)}% 均值${m.toFixed(2)}%（相对全样本 ${(m - allMean).toFixed(2)} 点）`; };
  console.log(`\n=== 开盘急拉形态回测（样本 ${samples} 票日，全样本均值 ${allMean.toFixed(2)}%）===`);
  [1, X, X + 1].forEach(x => console.log('  ' + statAt(x)));
  if (nextN) console.log(`急拉日隔夜（阈值${X}%）：平均 ${(nextSum / nextN).toFixed(2)}%（胜率 ${(nextWin / nextN * 100).toFixed(1)}%）`);
  console.log('解读：差值为正=急拉后有惯性；为负=急拉是出货陷阱。单日事件不构成规律，此为形态总体分布。');
  const dir = path.join(SG, 'factors'); fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, 'intraday_' + today() + '.json'), JSON.stringify({ ts: new Date().toISOString(), threshold: X, samples, surge, surgeWinRate: surge ? surgeWin / surge : 0, surgeMean: surge ? surgeSum / surge : 0, surgeN: surge, allMean, nextMean: nextN ? nextSum / nextN : null, dist: dist.slice(-200) }, null, 1));
  console.log('分时回测已落 factors/intraday_' + today() + '.json');
}

// 避雷分独立子命令（v3 终版定位：只过滤不选股）——候选/持仓的主力净占比反向信号 + 连续净流出天数
async function cmdAvoid(codes) {
  console.log('🛡️ 避雷分（moneyflow 反向，回测 CI[-68,-13] 显著——主力持续净流出=降档/剔除信号）');
  console.log('| 代码 | 名称 | 当日净占比% | 5日均值% | 连续净流出日 | 雷情 |');
  console.log('|---|---|---|---|---|---|');
  for (const code of codes.split(',').map(x => x.trim()).filter(c => CODE_RE.test(c))) {
    try {
      const ff = await fflow(code, 30); await sleep(200);
      if (!ff.length) { console.log(`| ${code} | — | 资金流数据缺 | — | — | 无法判定（数据缺，不误报） |`); continue; }
      const last = ff[ff.length - 1], l5 = ff.slice(-5);
      const m5 = avg(l5.map(r => r.mainPct));
      let streak = 0; for (let i = ff.length - 1; i >= 0 && ff[i].mainPct < 0; i--) streak++;
      const mine = m5 < -2 || streak >= 3;
      console.log(`| ${code} | ${ff[ff.length-1].d} 前数据 | ${r2(last.mainPct)} | ${r2(m5)} | ${streak} | ${mine ? '⚠️雷：降档/剔除建议（5日均值<-2%或连续流出≥3日）' : '通过'} |`);
    } catch (e) { console.log(`| ${code} | ERR ${e.message} |`); }
  }
  const dir = path.join(SG, 'factors'); fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, 'avoid_' + today() + '.json'), JSON.stringify({ ts: new Date().toISOString(), codes: codes.split(',') }, null, 1));
}
// 公告时点穿越查询（B1 半回放地基）：某票某决策时点之前可见的全部公告
async function cmdNotices(code, until) {
  const list = [];
  for (let pi = 1; pi <= 10; pi++) {
    const d = await j(`https://np-anotice-stock.eastmoney.com/api/security/ann?sr=-1&page_size=100&page_index=${pi}&ann_type=A&client_source=web&stock_list=${code.slice(2)}`);
    const l = d.data?.list || []; if (!l.length) break;
    l.forEach(x => list.push({ t: (x.display_time || '').slice(0, 19).replace(' ', 'T'), title: x.title }));
    const last = list[list.length - 1].t;
    if (until && new Date(last) < new Date(until.length <= 10 ? until + 'T00:00:00' : until.replace(' ', 'T')) - 90 * 864e5) break;
    await sleep(200);
  }
  const cut = until ? new Date(until.length <= 10 ? until + 'T23:59:59' : until.replace(' ', 'T') + ':00') : new Date();
  const visible = list.filter(x => new Date(x.t) <= cut).sort((a, b) => a.t.localeCompare(b.t));
  console.log(`${code} 截至 ${until || '现在'} 可见的公告 ${visible.length} 条（穿越口径：display_time ≤ 决策时点）:`);
  visible.slice(-20).forEach(x => console.log('  ' + x.t.slice(0, 16) + '  ' + x.title));
  const dir = path.join(SG, 'factors'); fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, `notices_${code}_${(until || 'now').replace(/[^0-9]/g, '')}.json`), JSON.stringify({ code, until, visible }, null, 1));
}

// walk-forward 滚动验证：每 60 交易日用全部历史重选最优权重 → 下 60 日验证（防过拟合的工业标准）
async function cmdWalkForward(universeFile, TN, klen) {
  const codes = fs.readFileSync(universeFile, 'utf8').split('\n').map(s => s.trim()).filter(s => s && !s.startsWith('#'));
  const TNn = +(TN || 3), KLEN = +(klen || 640);
  const { perDay } = await prepare(codes, 600, KLEN, true, 250);
  const CANDS = [['momentum', STRATS.momentum], ['mom-MF反向', { LB20: .35, CHG5: .25, RS5: .2, MF5: -.2 }], ['短动量强化', { LB20: .3, CHG5: .4, RS5: .3 }], ['mom+跳空避雷', { LB20: .3, CHG5: .25, RS5: .2, GAP: -.25 }], ['纯资金流反向', { MF5: -.6, LB20: .2, CHG5: .2 }]];
  const segLen = 60, out = [];
  for (let s = segLen; s + segLen <= perDay.length; s += segLen) {
    const train = perDay.slice(0, s), test = perDay.slice(s, s + segLen);
    let best = null, bestEx = -9;
    for (const [nm, w] of CANDS) { const r = runStrat(train, w, TNn); if (r && r.ex1 > bestEx) { bestEx = r.ex1; best = { nm, w }; } }
    const tr = runStrat(test, best.w, TNn), base = runStrat(test, STRATS.momentum, TNn);
    if (!tr || !base) continue;
    out.push({ start: test[0].d, picked: best.nm, ex1: tr.ex1, baseEx1: base.ex1 });
  }
  const dynEx = avg(out.map(o => o.ex1)), baseEx = avg(out.map(o => o.baseEx1));
  console.log(`\n=== walk-forward 滚动验证（每 ${segLen} 日重选权重，动态 vs 固定 momentum）===`);
  out.forEach(o => console.log(`  ${o.start} 起：选 [${o.picked}] → 验证段 t+1 超额 ${(o.ex1 * 100).toFixed(0)}bp（固定基准 ${(o.baseEx1 * 100).toFixed(0)}bp）`));
  console.log(`汇总：动态选择 ${(dynEx * 100).toFixed(0)}bp/日 vs 固定 momentum ${(baseEx * 100).toFixed(0)}bp/日 —— 动态${dynEx > baseEx ? '优于' : '不优于'}固定（${out.length} 段）`);
  const dir = path.join(SG, 'factors'); fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, 'walkforward_' + today() + '.json'), JSON.stringify({ ts: new Date().toISOString(), out, dynEx, baseEx }, null, 1));
}
(async () => {
  const [cmd, a1, a2, a3, a4, a5] = process.argv.slice(2);
  try {
    if (cmd === 'factors') await cmdFactors(a1, false);
    else if (cmd === 'score') await cmdFactors(a1, true);
    else if (cmd === 'market') await cmdMarket(a1);
    else if (cmd === 'pool') await cmdPool();
    else if (cmd === 'walkforward') await cmdWalkForward(a1 || path.join(SG, 'universe300.txt'), a2, a3);
    else if (cmd === 'backtest') await cmdBacktest(a1 || path.join(SG, 'universe300.txt'), a2, a3, a4, a5);
    else if (cmd === 'pullback') await cmdPullback(a1, a2, a3);
    else if (cmd === 'search') await cmdSearch(a1 || path.join(SG, 'universe300.txt'), a2, a3, a4);
    else if (cmd === 'intraday') await cmdIntraday(a1, a2);
    else if (cmd === 'notices') await cmdNotices(a1, a2);
    else if (cmd === 'avoid') await cmdAvoid(a1);
    else if (cmd === 'randomsearch') await cmdRandomSearch(a1 || path.join(SG, 'universe300.txt'), +(a2 || 300), a3);
    else if (cmd === 'cache' && a1 === 'clear') { fs.rmSync(CACHE, { recursive: true, force: true }); fs.rmSync(FLOWC, { recursive: true, force: true }); console.log('缓存已清'); }
    else console.log('用法：quant.js factors|score <codes> ｜ market [TopN] ｜ pool ｜ backtest [宇宙] [天数] [TopN] [策略] [K线深度] ｜ pullback <codes> [K线深度] [往返成本bp] ｜ search [宇宙] [天数] [TopN] [K线深度] ｜ intraday <codes> [阈值%] ｜ notices <code> [决策时点] ｜ cache clear');
  } catch (e) { console.error('❌ ' + e.message); process.exit(1); }
})();
