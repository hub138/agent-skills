#!/usr/bin/env node
// hold-review.js —— 持仓复审执行器（2026-10-29 重写：从"自己五问"改为调用 exit-gate 九维）
//
// 为什么重写（不是再加一份）：
//   ① 本文件原先自带一套五问判定（趋势/位置/动能/量价/破失效价），与 exit-gate.js 的九维**重复实现**，
//      两把尺子迟早漂移；② 原实现的止损只看 alerts.conf 里的"失效价"——**又是拿一根线当判据**，
//      正是用户反复否定的东西（"线是没用的啊……后续只根据一个固定的价格来决定卖，这是不对的"）；
//   ③ 因此这里只干三件事：读持仓 → 取日线 → 把判定交给 exit-gate（动态锚 + 九维），自己不再判。
//
// 数据源：state（MASTER.md 的 POSITION/EXECUTION）+ 日线。不看 watch.conf、不读 alerts.conf、不要求挂线。
//   —— 这是"开盘那一刻只有 1 条线在册"的根治：持仓复核**不依赖任何线**，有线没线都照扫。
// 退出码：3=有 EXIT 2=有 TRIM 0=全部 HOLD
// 用法：hold-review.js [--code sz900002 --cost 26.59 --since 2026-10-21] [--json]
'use strict';
const fs = require('fs');
const path = require('path');
const SG = process.env.SG_HOME || path.join(require('os').homedir(), '.stock-guardian');
const { fetchKline } = require(path.join(__dirname, 'kline.js'));
const E = require(path.join(__dirname, 'exit-gate.js'));

const args = process.argv.slice(2);
const arg = (k, d) => { const i = args.indexOf(k); return i >= 0 && args[i + 1] ? args[i + 1] : d; };

// 从 state 记录抽持仓（纯函数，可单测）：quantity>0 的 POSITION + 最近一笔 BUY 的 known_at 当入场日
function positionsFromState(recs) {
  const holds = (recs || []).filter((r) => r && r.type === 'POSITION' && Number(r.quantity) > 0)
    .map((r) => ({ code: r.code, qty: Number(r.quantity), cost: Number(r.cost || r.avg_cost || r.cost_basis || 0) || 0 }));
  const buyDate = (c) => (recs || []).filter((r) => r.type === 'EXECUTION' && String(r.side || '').toUpperCase() === 'BUY' && r.code === c)
    .map((r) => r.known_at || r.date || '').sort().pop() || '';
  return holds.map((h) => Object.assign(h, { since: buyDate(h.code) }));
}

function readMaster(dir) {
  const f = path.join(dir || SG, 'MASTER.md');
  if (!fs.existsSync(f)) return [];
  const m = fs.readFileSync(f, 'utf8').match(/```jsonl([\s\S]*?)```/);
  if (!m) return [];
  return m[1].split('\n').filter((l) => l.trim().startsWith('{'))
    .map((l) => { try { return JSON.parse(l); } catch { return null; } }).filter(Boolean);
}

// 单只判定（纯函数：bars 由调用方给，便于离线单测）
function reviewOne(h, bars, opts = {}) {
  if (!bars || bars.length < 12) {
    return { code: h.code, verdict: 'EXIT', fails: 9, dims: [], reasons: ['日线不足 12 根：证据缺失不允许默认继续持有'], anchor: null, note: '数据不足', qty: h.qty };
  }
  const r = E.review(bars, Object.assign({ code: h.code, cost: h.cost || 0, since: h.since || '' }, opts));
  return Object.assign({}, r, { qty: h.qty });
}

async function run(opts = {}) {
  const sg = opts.sg || SG;
  const dryCode = opts.code || arg('--code', '');
  let holds = dryCode
    ? [{ code: dryCode.toLowerCase(), qty: +arg('--qty', 0), cost: +arg('--cost', 0), since: arg('--since', '') }]
    : positionsFromState(readMaster(sg));
  if (!holds.length) {
    const line = '当前持仓 0 只（state 无 POSITION）——无复检对象。';
    if (opts.json) console.log(JSON.stringify({ holds: 0, note: line }, null, 2));
    else { console.log(line); console.log('预演用法：node hold-review.js --code sz900002 --cost 26.59 --since 2026-10-21'); }
    return { exitCode: 0, rows: [] };
  }
  const rows = [];
  let exitN = 0, trimN = 0;
  for (const h of holds) {
    let bars = null;
    try { bars = await fetchKline(h.code, 90); } catch (e) { bars = null; }
    const r = reviewOne(h, bars, opts.gate || {});
    rows.push(r);
    if (r.verdict === 'EXIT') exitN++; else if (r.verdict === 'TRIM') trimN++;
  }
  const exitCode = exitN ? 3 : trimN ? 2 : 0;
  if (opts.json) { console.log(JSON.stringify({ holds: rows.length, exitN, trimN, rows }, null, 2)); return { exitCode, rows }; }
  console.log(`=== 持仓复审 ${holds.length} 只（判定=exit-gate 九维，止损=动态锚，不依赖任何挂线）`);
  for (const r of rows) {
    const a = r.anchor;
    console.log(`\n=== ${r.code} === ${r.verdict}${r.verdict === 'EXIT' ? '（清）' : r.verdict === 'TRIM' ? '（减半）' : ''}｜${r.qty || '-'} 份/股｜成本 ${r.cost || '未知'}｜现价 ${r.px === undefined ? '-' : r.px.toFixed(3)}｜盈亏 ${r.pnl === null ? '未知' : r.pnl.toFixed(2) + '%'}｜持有 ${r.tDays === null ? '未知' : r.tDays + ' 日'}`);
    for (const d of (r.dims || [])) console.log(`  ${d.ok ? 'PASS' : 'FAIL'}  ${d.label}：${d.detail}`);
    console.log(` 动态锚 ${a && a.stop !== null ? a.stop + '（距现价 ' + a.distPct + '%，来源 ATR ' + (a.parts.atrStop ?? '-') + ' / 结构 ' + (a.parts.structStop ?? '-') + (a.parts.be ? ' / 保本 ' + a.parts.be : '') + '）' : '不可算'}`);
    if (r.reasons && r.reasons.length) console.log(` 不过 ${r.fails} 条 → ${r.verdict}\n  · ` + r.reasons.join('\n  · '));
    if (r.note) console.log(' 注：' + r.note);
  }
  console.log(`\n汇总：EXIT ${exitN}｜TRIM ${trimN}｜HOLD ${rows.length - exitN - trimN}`);
  return { exitCode, rows };
}

module.exports = { positionsFromState, reviewOne, run, readMaster };

if (require.main === module) {
  run({ json: args.includes('--json'), code: arg('--code', '') })
    .then(({ exitCode }) => process.exit(exitCode))
    .catch((e) => { console.error('复检失败:', e.message); process.exit(1); });
}
