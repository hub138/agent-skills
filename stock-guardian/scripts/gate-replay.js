#!/usr/bin/env node
// gate-replay.js —— 闸门"按当时可见信息回放"的纯函数（2026-10-29 立）
// 由来：用户问"假如不知道今天涨不涨，昨天会推荐买吗？或者今天早盘刚启动，会推荐买吗？"
// 要回答它，必须能用**当时那天及之前**的数据把闸门重跑一遍，而不是拿今天的行情去反推（那是后视镜）。
// 本模块只做一件事：把日线按 asof 截断，并给出该时点的判定价、当日涨幅、当日高点（能不能拿到要说清）。
// 纪律：
//   - 绝不用 asof 之后的任何数据（日线截断、不取实时报价）；
//   - 拿不到的字段（盘中最高价/量比）**明确标为未重建**，不许悄悄当成"合格"；
//   - asof 不是交易日、intraday 模式没给价，直接报错，不猜。
'use strict';

const DATE_RE = /^20\d{2}-\d{2}-\d{2}$/;

// 截断日线：
//   at=close    → 含 asof 当日已完成日线（收盘后决策：你看到的就是当日收盘）
//   at=intraday → 只含 asof 之前（盘中决策：当日 bar 还没走完，禁止用它的 高/低/收）
function truncate(bars, asof, at = 'close') {
  if (!DATE_RE.test(String(asof || ''))) throw new Error('asof 格式应为 YYYY-MM-DD：' + asof);
  if (at !== 'close' && at !== 'intraday') throw new Error('at 只能是 close 或 intraday：' + at);
  const out = (bars || []).filter((b) => (at === 'intraday' ? b.d < asof : b.d <= asof));
  if (!out.length) throw new Error('asof 之前没有日线数据：' + asof);
  if (at === 'close' && out[out.length - 1].d !== asof) throw new Error('asof 不是交易日或无数据：' + asof);
  return out;
}

// 该时点买入的"当日涨幅"（%）：价格 / 前一交易日收盘 − 1
//   close 模式：price 缺省 = asof 当日收盘；基准 = asof 前一日收盘
//   intraday 模式：price 必填（盘中现价）；基准 = 截断后最后一根（＝前一交易日）收盘
function chgAt(bars, px, at = 'close') {
  const i = at === 'intraday' ? bars.length - 1 : bars.length - 2;
  const prev = bars[i];
  if (!prev) throw new Error('日线不足以计算前一日收盘');
  return (px / prev.c - 1) * 100;
}

// ATR20（真实波幅均值，%）——与 prebuy-check 的止损下限同源，回放与实时必须用同一函数
function atrPct(bars, n = 20) {
  const b = (bars || []).slice(-(n + 1));
  if (b.length < 3) return null;
  let sum = 0, cnt = 0, prev = null;
  for (const x of b) {
    if (prev !== null) { sum += Math.max(x.h - x.l, Math.abs(x.h - prev), Math.abs(x.l - prev)); cnt++; }
    prev = x.c;
  }
  const last = b[b.length - 1].c;
  return cnt && last ? (sum / cnt) / last * 100 : null;
}

// 组装回放上下文：截断后的日线 + 判定价 + 当日涨幅 + 当日高点（intraday 取不到就是 null，不编）
function replayContext(bars, opts = {}) {
  const asof = opts.asof, at = opts.at || 'close';
  const kb = truncate(bars, asof, at);
  const lastBar = kb[kb.length - 1];
  let px = +opts.price || 0;
  if (at === 'intraday') {
    if (!px) throw new Error('intraday 回放必须给 --price（就是当时看到的现价）');
  } else if (!px) px = lastBar.c;
  const chg = chgAt(kb, px, at);
  const high = at === 'close' ? lastBar.h : null;
  const basisNote = at === 'close'
    ? `结构取 ${lastBar.d} 及之前（含当日收盘 ${lastBar.c}）；当日涨幅按前一日收盘 ${kb[kb.length - 2].c} 计`
    : `结构取 ${lastBar.d} 及之前（不含 ${asof} 当日未完成 bar）；当日涨幅按前一日收盘 ${lastBar.c} 计`;
  return { bars: kb, px, chg, high, basisNote, unresolved: at === 'intraday' ? ['盘中最高价（"现价即当日最高"一条未参与判定）', '盘中量比（"放量"条目未计入）'] : [] };
}

module.exports = { truncate, chgAt, atrPct, replayContext };

if (require.main === module) {
  console.log('gate-replay.js 是纯函数模块，请用 prebuy-check.js --asof <日期> [--at close|intraday]');
}
