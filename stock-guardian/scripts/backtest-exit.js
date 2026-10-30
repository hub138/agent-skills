#!/usr/bin/env node
// backtest-exit.js —— 卖出策略回测（2026-10-29 立）
// 用户原话："价格先改成动态，然后回测给出基于当前的市场的最好的动态，这个策略调整，大量测试。"
//            "后续只根据一个固定的价格来决定卖，这是不对的……卖出也不能只看价格或者量，多方面类似买入一样严谨。"
//
// 要回答：① 固定价格线（买入价 ±5%，或买入时的结构位一动不动）比动态锚差多少？
//          ② 动态锚（ATR 跟踪/结构滚动/保本推移）在当前市场用什么参数最好？
//          ③ 多维复核（exit-gate 8 维）加进去值不值？
// 纪律（回测最容易骗人的地方）：入场只用当日收盘及之前；第 i 根开始前只能用 bars[0..i−1] 算锚（trailing 不许偷看当根）；
//   触价类当日成交（跳空按 min(锚,开盘) 更差价）；判定类**收盘判定 → 次日开盘成交**；数据取不到报错，不换假数据；
//   sina 为不复权日线，长周期个股受分红除权影响 → 结论按"策略间横向比较"读，不当绝对收益。
'use strict';
const fs = require('fs');
const path = require('path');
const SK = __dirname;
const K = require(path.join(SK, 'kline.js'));
const A = require(path.join(SK, 'dyn-anchor.js'));
const E = require(path.join(SK, 'exit-gate.js'));
const { atrPct } = require(path.join(SK, 'gate-replay.js'));

const CACHE = '/tmp/sg-bt-cache';
function series(code, n = 260, useCache = true) {
  fs.mkdirSync(CACHE, { recursive: true });
  const f = path.join(CACHE, `${code}-${n}-${new Date().toISOString().slice(0, 10)}.json`);
  if (useCache && fs.existsSync(f)) return JSON.parse(fs.readFileSync(f, 'utf8'));
  const k = K.fetchKlineSync(code, n);
  if (!k || k.length < 60) throw new Error(`日线不足（${code}: ${k ? k.length : 0} 根）`);
  fs.writeFileSync(f, JSON.stringify(k));
  return k;
}

const isEtf = (c) => /^(sh5[0-9]|sz1[5-8])/.test(c || '');
function entrySignal(bars, i, code) {
  if (i < 20) return null;
  const w = bars.slice(0, i + 1);
  const px = w.at(-1).c;
  const sh = K.shape(w);
  if (sh.cls !== 'right' && sh.cls !== 'pullback') return null;
  const atr = atrPct(w, 20);
  if (atr === null) return null;
  const minStop = Math.max(2.5, (isEtf(code) ? 2.0 : 1.5) * atr);
  const stop0 = Math.min(...w.slice(-5).map((x) => x.l)) * 0.998;
  const gap = (px - stop0) / px * 100;
  if (gap < minStop) return null;
  const chg = (px / w.at(-2).c - 1) * 100;
  if (chg >= (isEtf(code) ? 7 : 8)) return null;
  return { px, stop0, atr, gap, cls: sh.cls, chg };
}

const initStop = (bars, i) => Math.min(...bars.slice(Math.max(0, i - 4), i + 1).map((b) => b.l)) * 0.998;
const trailStop = (st, bars, i) => {
  // 锚参数必须从**策略 opts**（= 网格在搜的东西）取，不能用 simulate 传进来的 {entryPx,frac}；
  // 2026-10-29 实测：写成后者时网格里 atrMult/structLookback 换任何值结果一模一样——参数根本没到锚。
  const o = Object.assign({}, st.opts, st.opts.anchor || {});
  const a = A.anchorFor(bars, i - 1, Object.assign({}, o, { cost: st.cost, prevStop: st.stop }));
  if (a.stop !== null) st.stop = Math.max(st.stop, a.stop);
  return { stop: st.stop, target: null };
};
function verdictOf(st, bars, i) {
  const r = E.review(bars.slice(0, i + 1), Object.assign({}, st.opts, { code: st.code, cost: st.cost, since: st.since }));
  if (r.verdict === 'EXIT') return { action: 'EXIT', reason: '多维清：' + (r.reasons[0] || '').slice(0, 40) };
  if (r.verdict === 'TRIM') return { action: 'TRIM', reason: '多维减：' + (r.reasons[0] || '').slice(0, 40) };
  return { action: 'HOLD' };
}

const STRATEGIES = {
  fixedPct: () => ({
    name: 'fixedPct', label: '固定 ±5%（不可动）',
    init: ({ entryPx }) => ({ stop: entryPx * 0.95, target: entryPx * 1.05 }),
    preBar: (st) => ({ stop: st.stop, target: st.target }),
    atClose: () => ({ action: 'HOLD' }),
  }),
  fixedStruct: () => ({
    name: 'fixedStruct', label: '静态结构位（挂线现状）',
    init: ({ bars, entryIdx }) => ({ stop: initStop(bars, entryIdx), target: null }),
    preBar: (st) => ({ stop: st.stop, target: null }),
    atClose: () => ({ action: 'HOLD' }),
  }),
  atrTrail: (opts = {}) => ({
    name: 'atrTrail', label: `ATR 跟踪 ${opts.atrMult ?? 2}×`,
    init: ({ bars, entryIdx }) => ({ stop: initStop(bars, entryIdx), k: opts.atrMult ?? 2 }),
    preBar: (st, bars, i) => {
      const p = bars.slice(0, i);
      if (p.length < 21) return { stop: st.stop, target: null };
      st.stop = Math.max(st.stop, +(p.at(-1).c - st.k * A.atrAbs(p, 20)).toFixed(4));
      return { stop: st.stop, target: null };
    },
    atClose: () => ({ action: 'HOLD' }),
  }),
  dynAnchor: (opts = {}) => ({
    name: 'dynAnchor', label: '动态锚（ATR+结构+保本）',
    init: ({ bars, entryIdx, entryPx }) => ({ stop: initStop(bars, entryIdx), cost: entryPx, opts }),
    preBar: trailStop,
    atClose: () => ({ action: 'HOLD' }),
  }),
  multiDim: (opts = {}) => ({
    name: 'multiDim', label: '多维复核（静态价 + 8 维）',
    init: ({ bars, entryIdx, entryPx, code }) => ({ stop: initStop(bars, entryIdx), cost: entryPx, code, opts, since: bars[entryIdx].d, target: null }),
    preBar: (st) => ({ stop: st.stop, target: null }),
    atClose: verdictOf,
  }),
  // 基线对照组：买了不管。如果"放着不动"比所有卖出策略都好，那说明卖出侧在帮倒忙——
  // 这个对照不上，卖出策略调得再漂亮也是自娱自乐（2026-10-29 补：第一轮跑完全策略负期望后加的）。
  hold5: () => ({
    name: 'hold5', label: '买了不管（满 5 日卖）',
    init: () => ({}),
    preBar: () => ({ stop: null, target: null }),
    atClose: (st, bars, i, x) => (x.days >= 5 ? { action: 'EXIT', reason: '持有满 5 日' } : { action: 'HOLD' }),
  }),
  hold10: () => ({
    name: 'hold10', label: '买了不管（满 10 日卖）',
    init: () => ({}),
    preBar: () => ({ stop: null, target: null }),
    atClose: (st, bars, i, x) => (x.days >= 10 ? { action: 'EXIT', reason: '持有满 10 日' } : { action: 'HOLD' }),
  }),
  dynMulti: (opts = {}) => ({
    name: 'dynMulti', label: '动态锚 + 多维复核',
    init: ({ bars, entryIdx, entryPx, code }) => ({ stop: initStop(bars, entryIdx), cost: entryPx, code, opts, since: bars[entryIdx].d, target: null }),
    preBar: trailStop,
    atClose: verdictOf,
  }),
};

// ---------- 单笔模拟 ----------
function simulate(bars, entryIdx, strategy, opts) {
  const entryPx = bars[entryIdx].c;
  const st = strategy.init({ bars, entryIdx, entryPx, opts, code: opts.code });
  let frac = 1, ret = 0, last = entryIdx;
  const reasons = [];
  const forceDays = opts.forceExitDays ?? 30;
  for (let i = entryIdx + 1; i < bars.length; i++) {
    const bar = bars[i];
    const { stop, target } = strategy.preBar(st, bars, i, { entryPx, frac });
    if (stop !== null && bar.l <= stop) {                       // 触价：跳空按更差价成交
      const fill = Math.min(stop, bar.o);
      ret += frac * (fill / entryPx - 1) * 100; frac = 0; last = i; reasons.push('破锚/止损'); break;
    }
    if (target !== null && bar.h >= target) {
      ret += frac * (target / entryPx - 1) * 100; frac = 0; last = i; reasons.push('达固定目标'); break;
    }
    const dec = strategy.atClose(st, bars, i, { entryPx, frac, days: i - entryIdx });
    const forced = (i - entryIdx) >= forceDays;
    if (forced || (dec && dec.action !== 'HOLD')) {
      const fill = bars[i + 1] ? bars[i + 1].o : bar.c;         // 收盘判定 → 次日开盘成交
      const part = (!forced && dec.action === 'TRIM') ? frac / 2 : frac;
      ret += part * (fill / entryPx - 1) * 100;
      frac -= part; last = Math.min(i + 1, bars.length - 1);
      if (dec && dec.reason) reasons.push(dec.reason);
      if (forced) reasons.push('超 ' + forceDays + ' 日强制离场');
      if (frac <= 0.001) { frac = 0; break; }
    }
  }
  if (frac > 0) { ret += frac * (bars.at(-1).c / entryPx - 1) * 100; reasons.push('区间结束未平'); last = bars.length - 1; }
  return { retPct: +ret.toFixed(3), days: last - entryIdx, reasons, entryDate: bars[entryIdx].d, exitDate: bars[last].d };
}

// ---------- 汇总 ----------
function summarize(trades) {
  if (!trades.length) return { n: 0 };
  const rs = trades.map((t) => t.retPct).sort((a, b) => a - b);
  const wins = rs.filter((x) => x > 0), losses = rs.filter((x) => x <= 0);
  const avgWin = wins.length ? wins.reduce((a, b) => a + b, 0) / wins.length : 0;
  const avgLoss = losses.length ? losses.reduce((a, b) => a + b, 0) / losses.length : 0;
  const seq = trades.slice().sort((a, b) => (a.exitDate < b.exitDate ? -1 : 1));
  let eq = 1, peak = 1, dd = 0;
  for (const t of seq) { eq *= 1 + t.retPct / 100; peak = Math.max(peak, eq); dd = Math.min(dd, eq / peak - 1); }
  // 退出原因分布：用来回答"动态锚到底有没有参与判定"——若清仓几乎全由多维/时间触发，
  // 那网格搜出来的就是闸门参数，不是锚参数，排序再好看也是假的。
  const exits = {};
  for (const t of trades) for (const r of (t.reasons || [])) { const k = String(r).split('：')[0]; exits[k] = (exits[k] || 0) + 1; }
  return {
    n: rs.length, mean: +(rs.reduce((a, b) => a + b, 0) / rs.length).toFixed(2), exits,
    median: +rs[Math.floor(rs.length / 2)].toFixed(2),
    winRate: +(wins.length / rs.length * 100).toFixed(1),
    avgWin: +avgWin.toFixed(2), avgLoss: +avgLoss.toFixed(2),
    payoff: avgLoss ? +Math.abs(avgWin / avgLoss).toFixed(2) : null,
    maxLoss: +rs[0].toFixed(2), maxWin: +rs.at(-1).toFixed(2),
    avgDays: +(trades.reduce((a, t) => a + t.days, 0) / trades.length).toFixed(1),
    // 串接值（不是真实资金曲线）：入场点已做 5 根冷却去重，但不同票/不同波仍可能同时在场，
    // 把几百笔按退出日串起来乘，只是"同额单笔连续下注"的示意；判策略好坏只看 mean/胜率/盈亏比/最大单笔亏。
    totalRet: +((eq - 1) * 100).toFixed(1), maxDD: +(dd * 100).toFixed(1),
  };
}

// ---------- 跑策略 / 网格 ----------
// 入场点**与策略参数无关**，先算一次：既省掉 50+ 次网格里重复跑闸门，也保证所有策略站在同一批入场点上比（不同入场点 = 不可比）。
// 去重：同一只票入场后 COOLDOWN 根内不再入场——连续日日日入场会把同一波行情算成 10 笔，"复利/回撤"直接失真成 -99%。
function entriesOf(seriesMap, opts = {}, cooldown = 5) {
  const out = [];
  for (const [code, bars] of Object.entries(seriesMap)) {
    let next = 0;
    for (let i = 20; i < bars.length - 2; i++) {
      if (i < next) continue;
      if (opts.entryFrom && bars[i].d < opts.entryFrom) continue;
      if (!entrySignal(bars, i, code)) continue;
      out.push({ code, i }); next = i + cooldown;
    }
  }
  return out;
}

function runStrategy(seriesMap, entries, name, opts = {}) {
  const trades = [];
  for (const { code, i } of entries) {
    const bars = seriesMap[code];
    trades.push(Object.assign(simulate(bars, i, STRATEGIES[name](opts), Object.assign({ code }, opts)), { code }));
  }
  return trades;
}

function runAll(seriesMap, entries, opts = {}) {
  const res = {};
  for (const name of Object.keys(STRATEGIES)) {
    const s = summarize(runStrategy(seriesMap, entries, name, opts));
    res[name] = Object.assign({ label: STRATEGIES[name](opts).label }, s);
  }
  return res;
}

// 目标函数：每笔期望（并列 → 回撤浅 → 盈亏比高）。"大量测试"= 把下面两组网格全跑一遍。
// 两组分开搜：锚参数（ATR 倍数 × 结构回看 × 保本触发）与闸门参数（微赚阈值 × 持有上限）不是一回事，
// 混在一张网格里搜出来的"最优"只是被闸门参数顶住的假象。
const better = (a, b) => (b.stat.mean - a.stat.mean) || (a.stat.maxDD - b.stat.maxDD) || ((b.stat.payoff || 0) - (a.stat.payoff || 0));
function gridSearch(seriesMap, entries, opts = {}) {
  const run = (o) => summarize(runStrategy(seriesMap, entries, 'dynMulti', o));
  const anchor = [], gate = [];
  for (const atrMult of [1.2, 1.5, 2, 2.5, 3])
    for (const structLookback of [5, 10, 20])
      for (const beTrigger of [2, 3, 5]) {
        const p = { atrMult, structLookback, beTrigger };
        const s = run(Object.assign({}, opts, p, { anchor: p }));
        if (s.n >= 30) anchor.push({ params: p, stat: s });
      }
  for (const microProfit of [1, 2, 3])
    for (const maxHold of [3, 5, 10]) {
      const p = { microProfit, maxHold };
      const s = run(Object.assign({}, opts, p));
      if (s.n >= 30) gate.push({ params: p, stat: s });
    }
  anchor.sort(better); gate.sort(better);
  return { anchor, gate };
}

// ---------- CLI ----------
const SAMPLE = [
  'sh510300', 'sh510500', 'sh588000', 'sh511220', 'sh515220', 'sh512880', 'sh512010', 'sh512660',
  'sh516160', 'sh510900', 'sh562000', 'sh588100', 'sh518880', 'sh513050', 'sh512400',
  'sh600519', 'sh601288', 'sh600036', 'sh601318', 'sh600030', 'sh601999', 'sh600900', 'sh601857',
  'sh600028', 'sh601988', 'sh600118', 'sh603867', 'sh603854', 'sh600741', 'sh601225', 'sz000962',
  'sz300750', 'sz000001', 'sz002594', 'sz000858', 'sz300059', 'sh688981', 'sh688111', 'sh600887',
  'sh600276', 'sh601012', 'sh600438', 'sh601166', 'sh600309', 'sh601668', 'sh600585', 'sh601601',
  'sh600050', 'sh601390', 'sh601398', 'sh600000', 'sz000002', 'sh601288', 'sh600019', 'sh601628',
];

function ARGVX(argv) {
  const arg = (k, d) => { const i = argv.indexOf(k); return i >= 0 && argv[i + 1] !== undefined ? argv[i + 1] : d; };
  return {
    atrMult: +arg('--atr-mult', A.DEFAULTS.atrMult),
    structLookback: +arg('--struct', A.DEFAULTS.structLookback),
    beTrigger: +arg('--be', A.DEFAULTS.beTrigger),
    microProfit: +arg('--micro', E.DEFAULTS.microProfit),
    maxHold: +arg('--max-hold', E.DEFAULTS.maxHold),
    forceExitDays: +arg('--force-days', 30),
  };
}

function main() {
  const argv = process.argv.slice(2);
  const arg = (k, d) => { const i = argv.indexOf(k); return i >= 0 && argv[i + 1] !== undefined ? argv[i + 1] : d; };
  const days = +arg('--days', 260);
  const symbols = arg('--symbols', '') ? arg('--symbols', '').split(',') : SAMPLE;
  const map = {};
  for (const c of symbols) {
    try { map[c] = series(c, days, !argv.includes('--no-cache')); } catch (e) { console.error('跳过 ' + c + '：' + e.message); }
  }
  const n = Object.keys(map).length;
  const firstKey = Object.keys(map)[0];
  if (!n) { console.error('一只数据都没取到，退出'); process.exit(1); }
  const lastDate = map[firstKey].at(-1).d;
  const recentFrom = map[firstKey].at(-61).d;
  const X = ARGVX(argv);
  const entFull = entriesOf(map, {});
  const entRecent = entriesOf(map, { entryFrom: recentFrom });
  const full = runAll(map, entFull, X);
  const recent = runAll(map, entRecent, X);
  const grid = gridSearch(map, entFull, X);
  const gridRecent = gridSearch(map, entRecent, X);

  const row = (k, s) => [k.padEnd(11), String(s.label || '').padEnd(20), String(s.n).padStart(5), String(s.mean).padStart(7),
    String(s.winRate).padStart(6), String(s.payoff ?? '-').padStart(6), String(s.maxLoss).padStart(7),
    String(s.avgDays).padStart(5), String(s.totalRet).padStart(8), String(s.maxDD).padStart(7)].join(' ');
  const head = ['策略'.padEnd(11), '说明'.padEnd(20), '笔数'.padStart(5), '期望%'.padStart(7), '胜率%'.padStart(6),
    '盈亏比'.padStart(6), '最大亏'.padStart(7), '天数'.padStart(5), '串接%'.padStart(8), '回撤%'.padStart(7)].join(' ');
  const ex = (s) => Object.entries(s.exits || {}).map(([k2, v]) => `${k2}×${v}`).join(' ');
  console.log('=== 样本 ' + n + ' 只 × ' + days + ' 日线（简化买入闸门入场，同一票 5 根内不重复入场），截止 ' + lastDate);
  console.log('    入场点：全样本 ' + entFull.length + ' 个｜当前市场 ' + entRecent.length + ' 个（所有策略共用，可比）');
  console.log('\n【全样本】\n' + head);
  for (const k of Object.keys(STRATEGIES)) console.log(row(k, full[k]) + '\n' + ' '.repeat(12) + '退出原因：' + ex(full[k]));
  console.log('\n【当前市场：' + recentFrom + ' 起入场】\n' + head);
  for (const k of Object.keys(STRATEGIES)) console.log(row(k, recent[k]) + '\n' + ' '.repeat(12) + '退出原因：' + ex(recent[k]));
  const gA = (list, title) => {
    console.log('\n' + title);
    console.log(['atrMult'.padStart(7), 'struct'.padStart(6), 'beTrig'.padStart(6), '笔数'.padStart(5),
      '期望%'.padStart(7), '胜率%'.padStart(6), '盈亏比'.padStart(6), '最大亏'.padStart(7), '天数'.padStart(5),
      '串接%'.padStart(8), '回撤%'.padStart(7)].join(' '));
    for (const x of list.slice(0, 10)) {
      const p = x.params, s = x.stat;
      console.log([String(p.atrMult).padStart(7), String(p.structLookback).padStart(6), String(p.beTrigger).padStart(6),
        String(s.n).padStart(5), String(s.mean).padStart(7), String(s.winRate).padStart(6),
        String(s.payoff ?? '-').padStart(6), String(s.maxLoss).padStart(7), String(s.avgDays).padStart(5),
        String(s.totalRet).padStart(8), String(s.maxDD).padStart(7)].join(' '));
    }
  };
  const gG = (list, title) => {
    console.log('\n' + title);
    console.log(['micro'.padStart(5), 'maxHold'.padStart(7), '笔数'.padStart(5), '期望%'.padStart(7), '胜率%'.padStart(6),
      '盈亏比'.padStart(6), '最大亏'.padStart(7), '天数'.padStart(5), '串接%'.padStart(8), '回撤%'.padStart(7)].join(' '));
    for (const x of list) {
      const p = x.params, s = x.stat;
      console.log([String(p.microProfit).padStart(5), String(p.maxHold).padStart(7), String(s.n).padStart(5),
        String(s.mean).padStart(7), String(s.winRate).padStart(6), String(s.payoff ?? '-').padStart(6),
        String(s.maxLoss).padStart(7), String(s.avgDays).padStart(5), String(s.totalRet).padStart(8),
        String(s.maxDD).padStart(7)].join(' '));
    }
  };
  gA(grid.anchor, '【锚参数网格 · 全样本 Top10】(dynMulti)');
  gG(grid.gate, '【闸门参数网格 · 全样本】(dynMulti)');
  gA(gridRecent.anchor, '【锚参数网格 · 当前市场 Top10】(dynMulti)');
  gG(gridRecent.gate, '【闸门参数网格 · 当前市场】(dynMulti)');

  const bA = gridRecent.anchor[0], bAF = grid.anchor[0], bG = gridRecent.gate[0], bGF = grid.gate[0];
  console.log('\n当前市场最优 = 锚' + JSON.stringify(bA && bA.params) + ' + 闸门' + JSON.stringify(bG && bG.params) +
    '｜全样本最优 = 锚' + JSON.stringify(bAF && bAF.params) + ' + 闸门' + JSON.stringify(bGF && bGF.params));
  if (bA && bG) {
    const comb = Object.assign({}, X, bA.params, { anchor: bA.params }, bG.params);
    const v = summarize(runStrategy(map, entRecent, 'dynMulti', comb));
    console.log('组合后复核（当前市场）：笔数 ' + v.n + '｜期望 ' + v.mean + '%｜胜率 ' + v.winRate + '%｜盈亏比 ' + v.payoff +
      '｜最大亏 ' + v.maxLoss + '%｜平均持有 ' + v.avgDays + ' 日｜回撤 ' + v.maxDD + '%');
    console.log('  退出原因分布：' + ex(v));
  }
  if (full.dynMulti.n && full.fixedPct.n) {
    console.log('对照（每笔期望）：动态锚+多维 ' + full.dynMulti.mean + '% ｜ 固定±5% ' + full.fixedPct.mean +
      '% ｜ 静态结构位 ' + full.fixedStruct.mean + '% ｜ 纯ATR跟踪 ' + full.atrTrail.mean + '%');
    console.log('对照（当前市场每笔期望）：动态锚+多维 ' + recent.dynMulti.mean + '% ｜ 固定±5% ' + recent.fixedPct.mean +
      '% ｜ 静态结构位 ' + recent.fixedStruct.mean + '% ｜ 纯ATR跟踪 ' + recent.atrTrail.mean + '%');
  }
  const out = arg('--out', '');
  if (out) {
    fs.writeFileSync(out, JSON.stringify({
      full, recent, symbols: n, days, lastDate, entries: { full: entFull.length, recent: entRecent.length },
      grid: { anchor: grid.anchor, gate: grid.gate }, gridRecent: { anchor: gridRecent.anchor, gate: gridRecent.gate },
    }, null, 2));
    console.log('已写出 ' + out);
  }
}

module.exports = { series, entrySignal, entriesOf, simulate, summarize, runStrategy, runAll, gridSearch, STRATEGIES, SAMPLE, ARGVX };
if (require.main === module) main();
