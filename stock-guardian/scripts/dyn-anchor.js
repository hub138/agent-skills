#!/usr/bin/env node
// dyn-anchor.js —— 动态价格锚（2026-10-29 立）
// 用户原话："不能用最开始的市场的静态定价左右未来市场的动态……价格先改成动态，然后回测给出基于当前的市场的最好的动态。"
//              还有一句更狠的："线是没用的"（指把固定价当通知与门禁）。
//
// 所以这里的"锚"不是买入那天拍死的数字，而是：
//   ① ATR 跟踪：当前价 − k×ATR20（k 由回测选出，随波动率自动放宽/收紧）
//   ② 结构滚动：近 lookback 日最低 ×(1−buffer)（随实际低点推移）
//   ③ 保本推移：浮盈 ≥ beTrigger% 后把锚抬到 成本×(1+beOffset)（先保本，再谈别的）
//   三者取"更紧者"（对多头 = 更高者），并且**只升不降**（单调不减，防锚被市场噪音拉回去）。
//
// 纪律：
//   · 数据不足（<k+1 根日线）→ 返回 null 并说明原因，绝不猜一个数出来；
//   · 锚只是"价格侧"的一条线，**它单独不足以决定卖出**——卖出判定必须走 exit-gate.js 的多维复核；
//   · 与 gate-replay.atrPct 保持同一把尺子（单测断言两者一致，防止两份 ATR 实现漂移）。
'use strict';

const { atrPct } = require(require('path').join(__dirname, 'gate-replay.js'));

const DEFAULTS = {
  atrN: 20,
  atrMult: 2.0,        // 回测选优：见 backtest-exit.js 输出的当前市场最优
  structLookback: 10,
  buffer: 0.002,       // 结构位下方 0.2%
  beTrigger: 3,        // 浮盈 ≥3% 触发保本
  beOffset: 0.3,       // 保本锚 = 成本 ×(1+0.3%)（覆盖双边费用）
};

// 真实波幅绝对值（与 gate-replay.atrPct 同源同口径：TR = max(H-L, |H-prevC|, |L-prevC|) 的 n 日均值）
function atrAbs(bars, n = 20) {
  const b = (bars || []).slice(-(n + 1));
  if (b.length < 3) return null;
  let sum = 0, cnt = 0, prev = null;
  for (const x of b) { if (prev !== null) { sum += Math.max(x.h - x.l, Math.abs(x.h - prev), Math.abs(x.l - prev)); cnt++; } prev = x.c; }
  return cnt ? sum / cnt : null;
}

const structLow = (bars, lookback, upto) => {
  const end = upto === undefined ? bars.length : upto + 1;
  const w = (bars || []).slice(Math.max(0, end - lookback), end);
  return w.length ? Math.min(...w.map((x) => x.l)) : null;
};

// 计算第 i 根（默认最后一根）收盘后应有的锚。
// ctx: { entry, cost, prevStop, ...DEFAULTS 覆盖 }
function anchorFor(bars, i, ctx = {}) {
  const o = Object.assign({}, DEFAULTS, ctx);
  const idx = i === undefined || i === null ? bars.length - 1 : i;
  if (!bars || idx < 1) return { stop: null, note: '日线不足，锚不可算（证据缺失不允许默认"继续持有"）' };
  const k = bars.slice(0, idx + 1);
  const px = k[k.length - 1].c;
  const atr = atrAbs(k, o.atrN);
  // 纪律：ATR 是主源。算不出 ATR（日线不足）时不许退到"只凭结构位"造一个锚出来——那就是造句。
  if (atr === null) {
    return { stop: null, px: +px.toFixed(4), atrPct: null, distPct: null, held: false,
      parts: { atrStop: null, structStop: null, be: null },
      note: `ATR 算不出（日线 ${k.length} 根，不足），证据缺失不允许只凭结构位编锚` };
  }
  const sl = structLow(k, o.structLookback, idx);
  const atrStop = px - o.atrMult * atr;
  const structStop = sl === null ? null : sl * (1 - o.buffer);
  const cands = [atrStop, structStop].filter((x) => x !== null && isFinite(x) && x > 0);
  if (!cands.length) return { stop: null, note: 'ATR 与结构位都算不出，请检查日线长度' };
  let stop = Math.max(...cands);
  const parts = { atrStop: atrStop === null ? null : +atrStop.toFixed(4), structStop: structStop === null ? null : +structStop.toFixed(4), be: null };
  // 保本推移：只在已有浮盈时生效（成本未知则不推）
  const cost = +o.cost || +o.entry || 0;
  if (cost > 0 && (px / cost - 1) * 100 >= o.beTrigger) {
    const be = cost * (1 + o.beOffset / 100);
    parts.be = +be.toFixed(4);
    if (be > stop) stop = be;
  }
  // 只升不降
  const prev = +o.prevStop || 0;
  const monotonic = prev > 0 && stop < prev;
  if (monotonic) stop = prev;
  return {
    stop: +stop.toFixed(4), px: +px.toFixed(4), atrPct: atr === null ? null : +(atr / px * 100).toFixed(2),
    distPct: +((px - stop) / px * 100).toFixed(2), parts, held: monotonic, note: monotonic ? '锚被前值托住（只升不降）' : '',
  };
}

// 回测用：从 entryIdx 逐根推进锚序列（第 i 项 = 第 i 根收盘后的锚），序列只升不降
function trailSeries(bars, entryIdx, ctx = {}) {
  const out = []; let prevStop = 0;
  for (let i = entryIdx; i < bars.length; i++) {
    const a = anchorFor(bars, i, Object.assign({}, ctx, { prevStop }));
    if (a.stop === null) { out.push(null); continue; }
    prevStop = a.stop; out.push(a.stop);
  }
  return out;
}

// 该根是否把锚打穿（用当根最低价判定；保守：锚在该根"生效"即算）
const hitStop = (bar, stop) => stop !== null && stop !== undefined && bar.l <= stop;

module.exports = { atrAbs, structLow, anchorFor, trailSeries, hitStop, DEFAULTS };

if (require.main === module) {
  const { fetchKlineSync } = require(require('path').join(__dirname, 'kline.js'));
  const argv = process.argv.slice(2);
  const code = (argv.find((a) => /^[a-z]{2}\d{6}$/i.test(a)) || '').toLowerCase();
  const cost = +(argv[argv.indexOf('--cost') + 1] || 0) || 0;
  if (!code) { console.error('用法: node dyn-anchor.js sh900001 [--cost 8.72] [--atr-mult 2] [--struct 10] [--be 3]'); process.exit(2); }
  const g = (n, d) => { const i = argv.indexOf(n); return i >= 0 ? +argv[i + 1] : d; };
  const k = fetchKlineSync(code, 60);
  const a = anchorFor(k, undefined, { cost, atrMult: g('--atr-mult', DEFAULTS.atrMult), structLookback: g('--struct', DEFAULTS.structLookback), beTrigger: g('--be', DEFAULTS.beTrigger) });
  console.log(`=== ${code} 动态锚（基准：${k.at(-1).d} 收盘 ${a.px}）`);
  console.log(`锚 = ${a.stop}（距现价 ${a.distPct}%）｜ATR20 ${a.atrPct}%｜来源：ATR跟踪 ${a.parts.atrStop ?? '-'} / 结构${g('--struct', DEFAULTS.structLookback)}日低 ${a.parts.structStop ?? '-'} / 保本 ${a.parts.be ?? '-'}${a.note ? '｜' + a.note : ''}`);
  const ceil = (bars, n2) => { const w = k.slice(-n2); return Math.max(...w.map((x) => x.h)); };
  console.log(`对照：固定 5% 线 = ${(a.px * 0.95).toFixed(4)}｜近 10 日高 = ${ceil(k, 10).toFixed(4)}`);
}
