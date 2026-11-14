#!/usr/bin/env node
// prebuy-check.js —— 买入前硬闸门（2026-10-29 立：本轮亏损全部发生在"买"这一侧，通知链路再准也补不回来）
// 复盘依据（真实案例，已泛化）：
//   某持仓ETF 0.838 底仓+0.839 加仓 13600 份（定案 5000，实际 2.7 倍）→ 崩到 0.65，亏约 -20%；
//   某防御仓个股 26.59 买 400 股（我称"防御仓"实为财报赌注）→ 25.80 卖，-3%；
//   某池票ETF 0.880-0.892 回踩买点、止损 0.86（仅 2.3%）→ 次日 0.865 打掉止损；
//   某半导体链第二票 0.850 低吸 → 当日 -5.3% 击穿作废线（同链重复暴露）。
// 闸门规则（机器判定，不出"建议"二字）：
//   1 BLOCK 向下摊薄：已有持仓 且 现价 < 成本（禁止亏损加仓/补仓）
//   2 BLOCK 止损缺失：未给 --stop
//   3 BLOCK 止损过窄：止损距离 < 下限（2026-10-29 起按波动率自适应：max(地板 2.5%, k×ATR20)；
//                       原先固定 ETF 3.5%/个股 3% —— 对低波动品种虚高、对高波动品种虚低）
//   4 BLOCK 追高：当日涨幅 ≥ +8%，或现价 ≥ 当日最高 - 0.1%（买在最高）
//   5 WARN  当日涨幅 ≥ +5%
//   6 BLOCK 同链重复暴露：与现有持仓同链
//   7 BLOCK 单票过重：计划金额 > 总资产 40%
//   8 WARN  事件窗口：--event-days ≤ 5（财报/决议前建仓=赌事件，不是配置）
// 分档（2026-10-29 用户："ETF 不需要过于保守"）：ETF 档 止损≥3.5%、单票≤60%、当日涨幅 BLOCK 7%/WARN 4%；
// 个股档 止损≥3%、单票≤40%、BLOCK 8%/WARN 5%。
// V 形判定（10-29 补）：V右启动/回踩确认 = 可买；V中未确认 = WARN；V左探底 = BLOCK。
// 退出码：0=PASS 1=WARN 3=BLOCK（BLOCK 时禁止在通知里出现买入字样）
// 回放（2026-10-29 立：用户"假如不知道今天涨不涨，昨天会推荐买吗？今天早盘刚启动会推荐买吗？"）：
//   --asof YYYY-MM-DD  [--at close|intraday]  —— 只用该时点及之前已完成日线重跑同一套闸门，**不取实时报价**
//   at=close（默认）：含 asof 当日收盘，price 缺省=该日收盘；at=intraday：不含 asof 未完成 bar，必须给 --price
//   拿不到的字段（盘中最高价、盘中量比）明确标"未重建"，不当作合格；asof 非交易日直接报错。
//   实现：scripts/gate-replay.js（纯函数，离线单测 tests/test-gate-replay.js）
'use strict';
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const SG = process.env.SG_HOME || path.join(require('os').homedir(), '.stock-guardian');
const SK = __dirname;
const args = process.argv.slice(2);
const arg = (k, d) => { const i = args.indexOf(k); return i >= 0 && args[i + 1] ? args[i + 1] : d; };

const code = arg('--code');
const price = +arg('--price', 0);
const qty = +arg('--qty', 0);
const stop = +arg('--stop', 0);
const eventDays = +arg('--event-days', 99);
const asof = arg('--asof', '');
const at = (arg('--at', 'close') || 'close').toLowerCase();
const REPLAY = !!asof;

// 2026-10-29 分档（用户原话："而且 ETF 不需要过于保守"）：ETF 是一篮子、不会单票暴雷，止损与集中度单列宽容档；
// 个股沿用严档。可用 --kind etf|stock 强制覆盖。
const isEtf = /^(sh5[0-9]|sz1[5-8])/.test(code || '');
const kind = (arg('--kind', '') || (isEtf ? 'etf' : 'stock')).toLowerCase();
const T = kind === 'etf'
  ? { label: 'ETF 档', minStop: 3.5, maxPos: 60, blockChg: 7, warnChg: 4 }
  : { label: '个股档', minStop: 3, maxPos: 40, blockChg: 8, warnChg: 5 };
if (!code || (!price && !REPLAY)) { console.error('用法: prebuy-check.js --code sh900001 --price 8.84 --qty 10000 --stop 8.50 [--kind etf|stock] [--event-days 3]\n    回放: prebuy-check.js --code sz900002 --asof 2026-10-28 --at close --stop 47.90 [--price 49.65]'); process.exit(2); }
if (REPLAY && !/^20\d{2}-\d{2}-\d{2}$/.test(asof)) { console.error('--asof 格式应为 YYYY-MM-DD：' + asof); process.exit(2); }

const out = [];
let blocked = 0, warned = 0;
const B = (r, m) => { blocked++; out.push('BLOCK ' + r + '：' + m); };
const W = (r, m) => { warned++; out.push('WARN  ' + r + '：' + m); };
const P = (r, m) => out.push('PASS  ' + r + '：' + m);

// ---- 状态：持仓成本、总资产、链条 ----
function readMaster() {
  const f = path.join(SG, 'MASTER.md');
  if (!fs.existsSync(f)) return [];
  const txt = fs.readFileSync(f, 'utf8');
  const m = txt.match(/```jsonl([\s\S]*?)```/);
  if (!m) return [];
  return m[1].split('\n').filter(l => l.trim().startsWith('{')).map(l => { try { return JSON.parse(l); } catch { return null; } }).filter(Boolean);
}
const recs = readMaster();
const pos = recs.filter(r => r.type === 'POSITION' && Number(r.quantity) > 0);
const mine = pos.find(r => r.code === code);
const cost = mine ? Number(mine.cost || mine.avg_cost || mine.cost_basis || 0) : 0;

let total = 0;
try {
  const lines = fs.readFileSync(path.join(SG, 'account.jsonl'), 'utf8').split('\n').filter(l => l.startsWith('ACCT|'));
  if (lines.length) total = Number(lines[lines.length - 1].split('|')[4]) || 0;
} catch { /* 无账本则跳过仓位检查 */ }

let chains = {};
try { chains = JSON.parse(fs.readFileSync(path.join(SG, 'chains.json'), 'utf8')); } catch { /* 可选 */ }
const myChain = chains[code];
if (myChain) {
  const dup = pos.filter(r => r.code !== code && chains[r.code] === myChain);
  if (dup.length) B('同链重复暴露', '已持有同链 ' + myChain + '：' + dup.map(r => r.code + '(' + r.quantity + ')').join(',') + ' —— 同一条映射链只算一个风险敞口');
  else P('同链重复暴露', '无同链持仓（链=' + myChain + '）');
} else P('同链重复暴露', '未登记链条，跳过（建议补 chains.json）');

// ---- 报价 ----
let q = null;
if (REPLAY) q = null;   // 回放：一律不取实时报价（用了就是拿今天的数据去解释昨天）
else try {
  const raw = execFileSync('bash', [path.join(SK, 'quote-public.sh'), 'quote', code], { encoding: 'utf8', timeout: 20000 });
  // 输出是 markdown 表：| code | market_type | ... | price | ... | change_percent | ... | volume_ratio |
  // 早期版本按数字序号取，取到过 change=7.65 之类错值 → 闸门会给出错误 WARN，等于又一个假的判定器。改为按表头字段名取。
  const rows = raw.split('\n').map(l => l.trim()).filter(l => l.startsWith('|'));
  if (rows.length >= 2) {
    const head = rows[0].split('|').map(x => x.trim());
    const data = rows.find(r => r.split('|').map(x => x.trim())[1] === code);
    if (data) {
      const vals = data.split('|').map(x => x.trim());
      const get = k => vals[head.indexOf(k)];
      q = { last: +get('price'), chg: +get('change_percent'), high: +get('high'), low: +get('low'), vr: +get('volume_ratio') };
    }
  }
} catch { /* 取不到就只用传参 */ }

let px = price || (q && q.last);
let high = q && q.high ? q.high : 0;
let chg = q && isFinite(q.chg) ? q.chg : null;

// 日线提前取：止损下限要按波动率算（原先在 V 形判定处才取，阈值只能写死百分比）
const { fetchKlineSync, stats: kStats, shape: kShape } = require(path.join(SK, 'kline.js'));
let k = null;
try { k = fetchKlineSync(code, 30); } catch { k = null; }

// 回放：把日线截到 asof，判定价/涨幅全部换成"当时可见"的
// 这一步必须发生在 ATR 与 V 形之前——否则 ATR 会用到 asof 之后的波动，等于给回放偷偷开后门
const R = require(path.join(SK, 'gate-replay.js'));
if (REPLAY) {
  const raw2 = k;
  const rp = R.replayContext(raw2, { asof, at, price });
  k = rp.bars; px = rp.px; chg = rp.chg; high = rp.high;
  console.log('回放模式：asof=' + asof + ' at=' + at + '（不取实时报价，只用该时点可见日线）');
  console.log('  ' + rp.basisNote);
  for (const u of rp.unresolved) console.log('  INFO  未重建：' + u);
}

// ATR20（真实波幅均值，%）——止损下限的波动率基准。
// 2026-10-29 用户质疑"闸门是不是太严格或畸形"：固定下限对低波动品种虚高（红利ETF 3.49% 被判"过窄"，实际是 4 个日波幅）、
// 对高波动个股虚低（ATR 3% 的票挂 3% 止损等于送人头）。改为 max(地板, k×ATR20)：地板 2.5% 来自历史教训
// （562500 挂 2.3% 止损，次日 0.865 即被打掉）。日线取不到时退回原固定档阈值，不静默放宽。
const atrPctOf = R.atrPct;   // 与 gate-replay 共用（回放/实时同一把尺子）
const ATR = k && k.length >= 6 ? atrPctOf(k, Math.min(20, k.length - 1)) : null;
const STOP_FLOOR = 2.5;
const STOP_K = T.label === 'ETF 档' ? 2.0 : 1.5;
const effMinStop = ATR ? Math.max(STOP_FLOOR, +(STOP_K * ATR).toFixed(2)) : T.minStop;
const atrNote = ATR ? `＝max(地板 ${STOP_FLOOR}%, ${STOP_K}×ATR20 ${ATR.toFixed(2)}%)` : '（日线取不到，用固定档阈值）';

// 1/2/3 止损纪律
if (!stop) B('止损缺失', '没有失效价就不能买——买入即定失效价是唯一硬约束');
else {
  const d = Math.abs(px - stop) / px * 100;
  if (d < effMinStop) B('止损过窄', '止损 ' + stop + ' 距买点仅 ' + d.toFixed(2) + '%（' + T.label + ' 下限 ' + effMinStop + '%' + atrNote + '），日内正常波动即触发，属"注定被洗"');
  else P('止损距离', d.toFixed(2) + '%（下限 ' + effMinStop + '%' + atrNote + '）');
}

// 1 向下摊薄
if (mine && cost > 0 && px < cost) B('向下摊薄', '已持有 ' + code + ' 成本 ' + cost + '，现价 ' + px + ' 低于成本——亏损头寸禁止加仓（马丁格尔）');
else if (mine && cost > 0) P('向下摊薄', '现价 ' + px + ' 高于成本 ' + cost + '（盈利加仓允许）');
else P('向下摊薄', '无持仓，非加仓');

// 4/5 追高
if (chg !== null && chg >= T.blockChg) B('追高', '当日已涨 ' + chg + '%（' + T.label + ' 上限 ' + T.blockChg + '%）——情绪段禁止入场');
else if (chg !== null && chg >= T.warnChg) W('追高', '当日已涨 ' + chg + '%，属加速段');
else if (high && px >= high * 0.999) W('追高', '现价即当日最高（' + px + '），无回踩缓冲');
else if (REPLAY && at === 'intraday') out.push('INFO  追高：盘中最高价未重建，"现价即当日最高"一条未参与判定（当日已涨 ' + (chg === null ? '-' : chg.toFixed(2) + '%') + '，按涨幅判）');
else P('追高', '未处于当日加速段');

// 6b V 形判定（2026-10-29 立：用户问"昨天低点适不适合低吸、是 V 左探底还是 V 右启动"——这类时机必须机器能判）
// 用日线（腾讯 qfq）同步取数，四类结论：V右启动 = 可买；回踩确认 = 低吸档可买；V中 = 未确认（小注+更严止损）；
// V左探底 = 禁买（接飞刀）。这就是"重要时机能被发现并提醒"的口径来源。
if (!k || k.length < 11) W('V形判定', '日线取不到或不足 11 根，右侧证据无法验证——证据缺失不作为买点依据');
else {
  const shArgs = REPLAY
    ? (at === 'intraday' ? { rt: { c: px, h: px, l: px } } : {})
    : { rt: { c: px, h: high || px, l: (q && q.low) || px }, vr: q && q.vr ? q.vr : null };
  const sh = kShape(k, shArgs), s1 = kStats(k);
  const basis = '（判定基准：' + (sh.rt ? '现价 ' + px + '，结构取 ' + s1.last.d + ' 及之前日线' : '最后完成日线 ' + s1.last.d) + '）';
  if (sh.cls === 'right') P('V形', sh.verdict + '｜' + sh.items.filter((i) => i[1]).map((i) => i[2]).join('；') + basis);
  else if (sh.cls === 'pullback') P('V形', sh.verdict + '：低吸档成立（距 20 日高 ' + sh.fromHi.toFixed(1) + '%，近 6 日低 ' + Math.min(s1.lo5, s1.last.l).toFixed(3) + '）' + basis);
  else if (sh.cls === 'left') B('V形未确认', sh.verdict + '：价 ' + sh.price.toFixed(3) + ' < MA5 ' + (s1.ma5 === null ? '-' : s1.ma5.toFixed(3)) + ' 且创近 6 日新低——禁接飞刀，等右侧证据' + basis);
  else W('V形未确认', sh.verdict + '：缺 ' + sh.items.filter((i) => !i[1]).map((i) => i[0]).join('/') + '（若做，注码减半且止损收紧）' + basis);
  if (s1.chg5 !== null && s1.chg5 >= 15) W('5日涨幅', s1.chg5.toFixed(1) + '%（短线过热，等回踩）');
}

// 7 仓位集中
if (total > 0 && qty > 0) {
  const amt = qty * px;
  const pct = amt / total * 100;
  if (pct > T.maxPos) B('单票过重', '计划金额 ' + amt.toFixed(0) + ' 元 = 总资产 ' + pct.toFixed(1) + '%（> ' + T.maxPos + '%）；某持仓 ETF 曾达 64% 是这轮亏损放大器');
  else P('单票仓位', pct.toFixed(1) + '%（' + T.label + ' ≤' + T.maxPos + '%）');
}

// 8 事件窗口
if (eventDays <= 5) W('事件窗口', '距事件 ' + eventDays + ' 天——这是赌事件不是配置，必须单列理由与更严止损');

console.log(out.join('\n'));
const verdict = blocked ? 'BLOCK' : (warned ? 'WARN' : 'PASS');
console.log('\n判定：' + verdict + (blocked ? '（禁止出现买入字样；先改条件再谈）' : ''));
process.exit(blocked ? 3 : (warned ? 1 : 0));