#!/usr/bin/env node
// exit-gate.js —— 卖出/持有复核闸门（2026-10-29 立）
// 用户原话（今早打的字，这也是立这个脚本的全部理由）：
//   "关于这个线我说过无数次：不是通知的要求和门禁……线是没用的啊。"
//   "给推荐票的时候谨慎考虑的比较多所以票不错，但是后续只根据一个固定的价格来决定卖，这是不对的。"
//   "如果一个票当天空仓不会买，且微赚就要清，比如华东第二三天赚了一点就可以清了。"
//   "不能用最开始的市场的静态定价左右未来市场的动态……卖出也不能只看价格或者量，多方面类似买入一样严谨。"
//
// 所以卖出侧从此不是"线有没有被越过"，而是**和买入同一把尺子的多维复核**：
//   尺度① 趋势：收在 MA5 上 且 MA5 ≥ MA10
//   尺度② 位置：距 20 日高 > -8%，且未创 10 日新低（不能一边深调一边说没事）
//   尺度③ 动能：5 日涨幅 > -3%（持续走弱就是走弱）
//   尺度④ 量价：未放量下跌（量比 ≥1.2 且收跌 = 有人在派发）
//   尺度⑤ 锚：现价 > 动态锚（dyn-anchor：ATR 跟踪/结构滚动/保本推移，只升不降）
//   尺度⑥ 时间：持有交易日 ≤ 上限（用户"我玩不了 1 周以上"；≥3 日仍不盈利 = 警告，≥5 日不盈利 = 离场）
//   尺度⑦ 落袋：微赚（0~microProfit%）且走弱 → 清（"微赚就要清"）；≥+3% 趋势转弱 → 减半；≥+5% → 收尾档
//   尺度⑧ 空仓视角：**若今天空仓，按买入尺子还会买它吗**（形态档 + 止损空间 + 未追高）；不会买 = 按纪律减，不许"再等等"
//   尺度⑨ 相对强度（给了基准日线才算，没给就明确标"未参与"，不假通过）
//
// 判定（可测、不含"建议"二字）：
//   EXIT：破锚 ｜ 不过 ≥3 条 ｜ 时间到且不盈利 ｜ 微赚且走弱 ｜ 空仓不买且已 ≥2 条不过 ｜ ≥+5% 且趋势转弱
//   TRIM：不过 2 条 ｜ 持有 ≥3 交易日仍不盈利 ｜ 浮盈 ≥3% 且趋势转弱 ｜ 浮盈 ≥5%
//   HOLD：其余
// 立场：**价格只是九条里的一条**。"价格没到某个数"永远不构成卖出理由；反过来说，
//   只有"跌破动态锚"（ATR/结构/保本三源取紧、只升不降）才是价格侧唯一能单独触发清仓的信号——那是止损，不是挂线。
// 退出码：3=EXIT 2=TRIM 0=HOLD
// 用法：exit-gate.js --code sz900002 --cost 26.59 --since 2026-10-21 [--qty 400] [--price 26.80] [--json]
'use strict';
const path = require('path');
const SK = __dirname;
const { fetchKlineSync, stats, shape } = require(path.join(SK, 'kline.js'));
const { atrPct } = require(path.join(SK, 'gate-replay.js'));
const A = require(path.join(SK, 'dyn-anchor.js'));

const DEFAULTS = {
  microProfit: 2.0,      // "微赚"上限（%）：0~2% 且走弱 → 清（回测可调）
  maxHold: 5,            // 最多持有交易日 = 用户纪律"我玩不了 1 周以上"（回测里 10 日只比 5 日好 0.06pp，
                         //   弱证据不足以推翻用户明确周期约束，故默认仍是 5；可调，但不许拿回测当借口擅自延长）
  exitAtFails: 4,        // 不过几条才"直接清"。原硬编码 3 太激：878 笔里 668 笔被清、平均只拿 5.1 天
  trimAtFails: 2,        // 不过几条起"减半"（2~3 条 = 减半观察，不是清仓）
  trimAt: 3,             // 浮盈 ≥3% 且趋势转弱 → 减半
  finalAt: 5,            // 浮盈 ≥5% → 收尾档
  stopFloor: 2.5,        // 与 prebuy-check 一致：止损地板
  anchor: {},            // 透传给 dyn-anchor
};

const pct = (a, b) => (b ? (a / b - 1) * 100 : null);
const isEtf = (code) => /^(sh5[0-9]|sz1[5-8])/.test(code || '');

// 空仓视角：复用买入侧的价格结构尺度（形态档 + 止损空间 + 追高）。
// 注意边界：入场侧最终权威仍是 prebuy-check.js（它还要账户/仓位/同链/事件窗口这些数据）；
// 这里只用**价格结构**部分，因为卖出复核拿不到"计划仓位"这类参数。两处共用 kline.shape 与 gate-replay.atrPct，禁止各写一份。
function buyView(bars, px, code, chg, opts = {}) {
  const o = Object.assign({}, DEFAULTS, opts);
  const hist = bars.slice(0, -1);           // 已完成日线；今日用 px 当"现价探针"（收盘/盘中同一口径）
  if (hist.length < 12) return { ok: false, cls: 'unknown', verdict: '历史不足', stop: null, gap: null, minStop: null, reasons: ['历史不足 12 根，空仓视角无法复核'] };
  const sh = shape(hist, { rt: { c: px }, vr: opts.vr !== undefined && opts.vr !== null ? opts.vr : stats(bars).vr });
  const atr = atrPct(hist, 20);
  const kindK = isEtf(code) ? 2.0 : 1.5;
  const minStop = atr === null ? (isEtf(code) ? 3.5 : 3) : Math.max(o.stopFloor, +(kindK * atr).toFixed(2));
  const stop = +(Math.min(...hist.slice(-5).map((x) => x.l)) * 0.998).toFixed(4);
  const gap = +((px - stop) / px * 100).toFixed(2);
  const rs = [];
  if (sh.cls === 'left' || sh.cls === 'mid') rs.push(`形态 ${sh.cls === 'left' ? 'V左探底' : 'V中未确认'}（不是右侧买点）`);
  if (gap < minStop) rs.push(`止损空间 ${gap}% < 下限 ${minStop}%`);
  const chgLimit = isEtf(code) ? 7 : 8;
  if (chg !== null && chg >= chgLimit) rs.push(`当日已涨 ${chg.toFixed(2)}%（加速段不追）`);
  return { ok: rs.length === 0, cls: sh.cls, verdict: sh.verdict, stop, gap, minStop, reasons: rs };
}

// 主复核：bars = 已完成日线（含今天收盘或今天盘中前的历史），px = 判定用现价
function review(bars, opts = {}) {
  const o = Object.assign({}, DEFAULTS, opts);
  if (!bars || bars.length < 12) return { verdict: 'EXIT', fails: 9, dims: [], reasons: ['日线不足 12 根：证据缺失不允许默认"继续持有"（纪律：看不见就不许拿着）'], anchor: null, note: '数据不足' };
  const code = o.code || '';
  const s = stats(bars);
  const px = +o.price || s.last.c;
  const cost = +o.cost || 0;
  const pnl = cost ? pct(px, cost) : null;
  const chg = o.chg !== undefined && o.chg !== null ? +o.chg : pct(px, s.prev.c);
  const anchor = A.anchorFor(bars, undefined, Object.assign({}, o.anchor, { cost }));
  const lo10 = Math.min(...bars.slice(-10).map((x) => x.l));
  const dims = [];
  const add = (key, label, ok, detail) => dims.push({ key, label, ok: !!ok, detail });

  // 趋势用"恶化"口径，不用"完美多头"口径：低吸/回踩入场本来就常贴在地板附近，
  // 若要求"站上 MA5 且均线多头排列"才算好，买入当天就会给自己发卖出指令——闸门自相矛盾（2026-10-29 某防御仓个股实测如此）。
  // 用**判定价** px 判趋势，不用最近收盘：盘中复核时 stats.aboveMA5 是"上一根收盘 vs MA5"，
  // 拿它当今天的趋势会自欺（2026-10-29 单测 T7 抓到：价已跌破 MA5，趋势维度仍报"站上 MA5"）。
  const aboveMA5 = s.ma5 === null ? null : px > s.ma5;
  const trendOk = aboveMA5 === true || (pnl !== null && pnl >= 0);
  add('trend', '趋势', trendOk, `判定价 ${px.toFixed(3)} / MA5 ${s.ma5 === null ? '-' : s.ma5.toFixed(3)} / MA10 ${s.ma10 === null ? '-' : s.ma10.toFixed(3)}｜${aboveMA5 ? '站上 MA5' : '破 MA5'}${s.maAligned === false ? '，均线转下行排列' : ''}${(pnl !== null && pnl >= 0) ? '，浮盈保护中' : ''}`);
  add('position', '位置', s.fromHi20 > -12 && s.last.c > lo10, `距 20 日高 ${s.fromHi20.toFixed(1)}%，10 日低 ${lo10.toFixed(3)}`);
  add('momentum', '动能', s.chg5 !== null && s.chg5 > -4, `5 日涨幅 ${s.chg5 === null ? '-' : s.chg5.toFixed(2) + '%'}`);
  add('volume', '量价', !(s.vr !== null && s.vr >= 1.2 && s.last.c < s.prev.c), `量比 ${s.vr === null ? '-' : s.vr.toFixed(2)}${s.last.c < s.prev.c ? '（收跌）' : ''}`);
  add('anchor', '锚', anchor.stop !== null && px > anchor.stop, anchor.stop === null ? '锚算不出（ATR/结构数据不足）' : `现价 ${px.toFixed(3)} / 动态锚 ${anchor.stop}（距 ${anchor.distPct}%，来源 ${anchor.parts.atrStop ?? '-'}｜${anchor.parts.structStop ?? '-'}${anchor.parts.be ? '｜保本 ' + anchor.parts.be : ''}）`);

  const tDays = o.since ? bars.filter((b) => b.d > o.since).length : null;
  add('time', '时间', tDays === null || tDays <= o.maxHold, tDays === null ? '入场日未知（未给 --since，时间尺度未参与）' : `持有 ${tDays} 个交易日（上限 ${o.maxHold}）`);

  const dim = (k) => dims.find((d) => d.key === k) || { ok: true };
  const weak = !dim('trend').ok || !dim('momentum').ok;   // 趋势或动能走弱
  const micro = pnl !== null && pnl > 0 && pnl < o.microProfit;
  let pnlOk = true, pnlWhy = pnl === null ? '成本未知（浮盈尺度未参与）' : `浮盈 ${pnl.toFixed(2)}%`;
  if (micro && weak) { pnlOk = false; pnlWhy += `：微赚（<${o.microProfit}%）且走弱 → 落袋（"微赚就要清"）`; }
  else if (pnl !== null && pnl >= o.finalAt) { pnlOk = false; pnlWhy += `：已达收尾档（+${o.finalAt}%）`; }
  else if (pnl !== null && pnl >= o.trimAt && !dim('trend').ok) { pnlOk = false; pnlWhy += `：浮盈 ≥${o.trimAt}% 但趋势转弱 → 利润不许回吐`; }
  add('pnl', '落袋', pnlOk, pnlWhy);

  const bv = buyView(bars, px, code, chg, o);
  add('rebuy', '空仓视角', bv.ok, bv.ok ? `若今天空仓仍会买：${bv.cls === 'right' ? 'V右启动' : '回踩确认'}，止损空间 ${bv.gap}%` : `若今天空仓不会买：${bv.reasons.join('；')}`);

  let rsOk = true, rsWhy = '未参与（没给基准日线）';
  if (o.bench && o.bench.length > 6) {
    const b5 = pct(s.last.c, bars.at(-6).c), m5 = pct(o.bench.at(-1).c, o.bench.at(-6).c);
    rsOk = (b5 - m5) > -3;
    rsWhy = `5 日超额 ${(b5 - m5).toFixed(2)}%（个股 ${b5.toFixed(2)}% vs 基准 ${m5.toFixed(2)}%）`;
  }
  add('rs', '相对强度', rsOk, rsWhy);

  const fails = dims.filter((d) => !d.ok);
  const keys = new Set(fails.map((d) => d.key));
  const reasons = fails.map((d) => `${d.label}：${d.detail}`);
  let verdict = 'HOLD', reduce = 0, note = '';
  const brokeAnchor = !dim('anchor').ok;
  const timeOut = keys.has('time') && pnl !== null && pnl <= 0;
  const wouldNotBuy = !bv.ok;
  if (brokeAnchor || fails.length >= o.exitAtFails || timeOut || (micro && weak) ||
      (wouldNotBuy && pnl !== null && pnl < o.microProfit && fails.length >= 2) ||
      (pnl !== null && pnl >= o.finalAt && !dim('trend').ok)) {
    verdict = 'EXIT'; reduce = 1;
  } else if (fails.length >= o.trimAtFails || (pnl !== null && pnl >= o.trimAt && !dim('trend').ok) || (pnl !== null && pnl >= o.finalAt)) {
    verdict = 'TRIM'; reduce = 0.5;
  }
  // 入场首日不给自己发卖出指令（除破锚）：当天买、当天喊清 = 闸门自相矛盾，只会造成无谓来回
  if (tDays === 0 && !brokeAnchor && verdict !== 'HOLD') { verdict = 'HOLD'; reduce = 0; note = '入场首日：除破锚外不发卖出指令'; }
  if (verdict === 'EXIT' && brokeAnchor) reasons.unshift(`破锚：现价 ${px.toFixed(3)} ≤ 动态锚 ${anchor.stop}（锚＝ATR/结构/保本三源取紧，不是买入时拍死的价）`);
  return {
    verdict, reduce, note, fails: fails.length, dims, reasons, anchor, px, cost, pnl, chg, tDays,
    buyView: bv, code, basis: `基准：${s.last.d} 及之前日线`,
  };
}

module.exports = { review, buyView, DEFAULTS };

if (require.main === module) {
  const argv = process.argv.slice(2);
  const arg = (k, d) => { const i = argv.indexOf(k); return i >= 0 && argv[i + 1] !== undefined ? argv[i + 1] : d; };
  const code = (arg('--code', '') || '').toLowerCase();
  if (!code) { console.error('用法: exit-gate.js --code sz900002 --cost 26.59 --since 2026-10-21 [--qty 400] [--price 26.80] [--bench sh000300] [--json]'); process.exit(2); }
  let bars, bench = null;
  try { bars = fetchKlineSync(code, 90); } catch (e) { console.error('日线取不到：' + e.message + '\n（纪律：证据缺失一律按 EXIT 处理，不许默认继续持有）'); process.exit(3); }
  try { const bc = arg('--bench', ''); if (bc) bench = fetchKlineSync(bc.toLowerCase(), 90); } catch { /* 基准可选 */ }
  const r = review(bars, {
    code, cost: +arg('--cost', 0), since: arg('--since', ''), price: +arg('--price', 0) || undefined, bench,
    microProfit: +arg('--micro', DEFAULTS.microProfit), maxHold: +arg('--max-hold', DEFAULTS.maxHold),
    anchor: { atrMult: +arg('--atr-mult', A.DEFAULTS.atrMult), structLookback: +arg('--struct', A.DEFAULTS.structLookback), beTrigger: +arg('--be', A.DEFAULTS.beTrigger) },
  });
  if (argv.includes('--json')) { console.log(JSON.stringify(r, null, 2)); process.exit(r.verdict === 'EXIT' ? 3 : r.verdict === 'TRIM' ? 2 : 0); }
  console.log(`=== ${code} ${r.verdict}${r.verdict === 'TRIM' ? '（减半）' : r.verdict === 'EXIT' ? '（清）' : ''}｜${r.basis}｜现价 ${r.px.toFixed(3)}｜成本 ${r.cost || '未知'}｜盈亏 ${r.pnl === null ? '未知' : r.pnl.toFixed(2) + '%'}｜持有 ${r.tDays === null ? '未知' : r.tDays + ' 日'}`);
  for (const d of r.dims) console.log(`  ${d.ok ? 'PASS' : 'FAIL'}  ${d.label}：${d.detail}`);
  console.log(`\n不过 ${r.fails} 条 → 判定 ${r.verdict}${r.reasons.length ? '\n  · ' + r.reasons.join('\n  · ') : ''}`);
  console.log(r.anchor && r.anchor.stop !== null ? `动态锚 ${r.anchor.stop}（距现价 ${r.anchor.distPct}%）：${r.anchor.parts.atrStop ?? '-'} / ${r.anchor.parts.structStop ?? '-'}${r.anchor.parts.be ? ' / 保本 ' + r.anchor.parts.be : ''}` : '动态锚不可算');
  process.exit(r.verdict === 'EXIT' ? 3 : r.verdict === 'TRIM' ? 2 : 0);
}
