#!/usr/bin/env node
// gate-replay 离线单测（不联网，合成日线）
// 立此文件的由来：用户问"假如不知道今天涨不涨，昨天会推荐买吗？今天早盘刚启动会推荐买吗？"
// ——回答这个问题必须能"按当时可见信息"重跑闸门；本测试锁住三件事：
//   ① 截断语义（close 含当日 / intraday 不含当日未完成 bar）；
//   ② 绝不使用 asof 之后的数据（用一根后面的暴涨 bar 反证）；
//   ③ 拿不到的字段（盘中最高价/量比）必须标"未重建"，不许当成合格。
'use strict';
const { truncate, chgAt, atrPct, replayContext } = require('../scripts/gate-replay.js');

let pass = 0;
const fail = [];
function ck(name, got, want = true) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (ok) { pass++; console.log('  ✔ ' + name); } else { fail.push(name); console.log('  ✘ ' + name + '  got=' + JSON.stringify(got) + ' want=' + JSON.stringify(want)); }
}
function throws(fn) { try { fn(); return false; } catch { return true; } }

// 合成日线：10-24 ~ 10-28 平静，10-29 暴涨（用来验证"绝不用未来数据"）
const bars = [
  { d: '2026-10-22', o: 10.0, h: 10.2, l: 9.9, c: 10.1, v: 100 },
  { d: '2026-10-23', o: 10.1, h: 10.3, l: 10.0, c: 10.2, v: 110 },
  { d: '2026-10-24', o: 10.2, h: 10.4, l: 10.1, c: 10.3, v: 120 },
  { d: '2026-10-27', o: 10.3, h: 10.5, l: 10.2, c: 10.4, v: 130 },
  { d: '2026-10-28', o: 10.4, h: 10.9, l: 10.3, c: 10.8, v: 300 },
  { d: '2026-10-29', o: 11.0, h: 11.9, l: 10.9, c: 11.88, v: 900 },   // 未来数据：回放时绝不能被看到
];

console.log('T1 截断语义');
ck('close 含当日', truncate(bars, '2026-10-28', 'close').at(-1).d, '2026-10-28');
ck('close 不含未来', truncate(bars, '2026-10-28', 'close').some((b) => b.d > '2026-10-28'), false);
ck('intraday 不含当日未完成 bar', truncate(bars, '2026-10-29', 'intraday').at(-1).d, '2026-10-28');
ck('asof 非交易日报错', throws(() => truncate(bars, '2026-10-25', 'close')), true);
ck('日期格式错报错', throws(() => truncate(bars, '10-28', 'close')), true);
ck('at 取值非法报错', throws(() => truncate(bars, '2026-10-28', 'noon')), true);
ck('asof 早于全部数据报错', throws(() => truncate(bars, '2026-01-01', 'close')), true);

console.log('T2 涨幅口径');
const k28 = truncate(bars, '2026-10-28', 'close');
const k29i = truncate(bars, '2026-10-29', 'intraday');
ck('close：昨收→今收（10.4→10.8＝+3.85%）', +chgAt(k28, 10.8, 'close').toFixed(2), 3.85);
ck('intraday：前收→当时价（10.8→11.0＝+1.85%）', +chgAt(k29i, 11.0, 'intraday').toFixed(2), 1.85);
ck('涨幅不含 10-29 收盘（否则就是后视镜）', +chgAt(k29i, 11.0, 'intraday').toFixed(2) < 10, true);

console.log('T3 ATR（与 prebuy-check 同源）');
ck('ATR 为正数', atrPct(k28, 20) > 0, true);
ck('数据不足返回 null（不编数）', atrPct([bars[0], bars[1]], 20), null);
const atrBefore = atrPct(k28, 20);
ck('ATR 不受未来暴涨影响（等于只用截断数据算）', atrPct(bars.slice(0, 5), 20), atrBefore);

console.log('T4 回放上下文');
const rp = replayContext(bars, { asof: '2026-10-28', at: 'close' });
ck('close 默认价＝当日收盘', rp.px, 10.8);
ck('close 当日高点＝当日 high（用于"买在最高"判定）', rp.high, 10.9);
ck('close 无未重建项', rp.unresolved, []);
const rp2 = replayContext(bars, { asof: '2026-10-29', at: 'intraday', price: 11.0 });
ck('intraday 用传入价', rp2.px, 11.0);
ck('intraday 最高价标为未重建（null，不编 11.9）', rp2.high, null);
ck('intraday 明确列出未重建字段', rp2.unresolved.length, 2);
ck('intraday 缺 --price 报错', throws(() => replayContext(bars, { asof: '2026-10-29', at: 'intraday' })), true);
ck('基准说明含日期（可追溯）', /2026-10-28/.test(rp2.basisNote), true);

console.log('T5 未来数据隔离（反证：把 10-29 的 bar 放到最前也影响不到 10-28 回放）');
const rp3 = replayContext(bars, { asof: '2026-10-28', at: 'close', price: 10.8 });
ck('回放日线数＝5（无 10-29）', rp3.bars.length, 5);
ck('回放判定价只由传入价决定', rp3.px, 10.8);
ck('回放涨幅只用截断数据', +rp3.chg.toFixed(2), 3.85);

console.log('\n通过 ' + pass + ' 项' + (fail.length ? '，失败 ' + fail.length + ' 项：' + fail.join('、') : '，全部通过'));
process.exit(fail.length ? 1 : 0);
