#!/usr/bin/env node
// 动态价格锚回归（2026-10-29 立。锁的是"卖出不许只看一个固定价"这件事的基础件）
'use strict';
const A = require('../scripts/dyn-anchor.js');
const { atrPct } = require('../scripts/gate-replay.js');

let pass = 0; const bad = [];
const ck = (n, g, w = true) => { const ok = JSON.stringify(g) === JSON.stringify(w); ok ? pass++ : bad.push(n); console.log(`  ${ok ? '✔' : '✘'} ${n}${ok ? '' : '  got=' + JSON.stringify(g) + ' want=' + JSON.stringify(w)}`); };
// 由收盘序列造日线（开=昨收，高低各让 0.4%）
const mk = (cs) => cs.map((c, i) => { const o = i ? cs[i - 1] : c; return { d: `2026-01-${String(i + 1).padStart(2, '0')}`, o, h: Math.max(o, c) * 1.004, l: Math.min(o, c) * 0.996, c, v: 1e6 }; });
const up = (n, a = 100, step = 0.6) => Array.from({ length: n }, (_, i) => +(a + i * step).toFixed(3));

console.log('T1 与 gate-replay.atrPct 同一把尺子（防两份 ATR 实现漂移）');
{
  const k = mk(up(25));
  const abs = A.atrAbs(k, 20);
  ck('ATR 绝对值 ↔ 百分比一致', Math.abs(abs / k.at(-1).c * 100 - atrPct(k, 20)) < 1e-9, true);
  ck('数据不足返回 null', A.atrAbs(mk([1, 2]), 20), null);
}

console.log('T2 锚只升不降（前值托底）');
{
  const k = mk(up(25));
  const a1 = A.anchorFor(k, undefined, { cost: 100, prevStop: 999 });
  ck('被前值托住', [a1.stop, a1.held], [999, true]);
  const a2 = A.anchorFor(k, undefined, { cost: 100 });
  ck('无前值时自主计算', a2.stop < 999 && a2.stop > 0, true);
  ck('锚低于现价（多头失效位）', a2.stop < a2.px, true);
}

console.log('T3 结构滚动：低点抬高 → 锚抬高');
{
  const low = mk([...up(20), 100.5, 100.4, 100.6, 100.7, 100.8]);
  const high = mk([...up(20), 104.5, 104.4, 104.6, 104.7, 104.8]);
  const a = A.anchorFor(low, undefined, { cost: 100, atrMult: 9 });
  const b = A.anchorFor(high, undefined, { cost: 100, atrMult: 9 });
  ck('结构位高的锚更高', b.stop > a.stop, true);
  ck('结构来源被记录', a.parts.structStop !== null, true);
}

console.log('T4 保本推移：浮盈到线就把锚抬到成本上方');
{
  const k = mk([...up(20, 100, 0.1).slice(0, 19), 104.5]);
  const no = A.anchorFor(k, undefined, { cost: 100, beTrigger: 3 });
  const yes = A.anchorFor(k, undefined, { cost: 100, beTrigger: 3, prevStop: 1 });
  ck('+4.5% 触发保本（成本×1.003）', no.parts.be, 100.3);
  ck('保本生效后锚 ≥ 保本线', yes.stop >= 100.3, true);
  ck('未给成本则不推保本', A.anchorFor(k, undefined, {}).parts.be, null);
}

console.log('T5 证据缺失不许造句');
{
  const a = A.anchorFor(mk([10, 10]), undefined, { cost: 10 });
  ck('stop 为 null', a.stop, null);
  ck('带说明而不是编个数', /不足|证据|算不出/.test(a.note), true);
}

console.log('T6 打穿判定（low 触到锚即算）');
{
  ck('low == 锚 算打穿', A.hitStop({ l: 10, h: 11, c: 10.5 }, 10), true);
  ck('low > 锚 不算', A.hitStop({ l: 10.01, h: 11, c: 10.5 }, 10), false);
  ck('锚为 null 不算', A.hitStop({ l: 1 }, null), false);
}

console.log('T7 trailSeries：长度对齐 + 单调不减');
{
  const k = mk(up(30));
  const t = A.trailSeries(k, 10, { cost: 100 });
  ck('长度 = 从入场到末尾', t.length, k.length - 10);
  ck('全部非空', t.every((x) => x !== null), true);
  ck('单调不减', t.every((x, i) => i === 0 || x >= t[i - 1]), true);
}

console.log('T8 未来数据隔离：算第 i 根时看不到 i 之后');
{
  const k = mk(up(30));
  const i = 20;
  const a1 = A.anchorFor(k, i, { cost: 100 });
  const a2 = A.anchorFor(k.slice(0, i + 1), i, { cost: 100 });
  ck('截断前后锚一致', a1.stop, a2.stop);
  const spiked = k.slice();
  spiked.push({ d: '2026-02-01', o: 500, h: 600, l: 400, c: 550, v: 1e7 });
  const a3 = A.anchorFor(spiked, i, { cost: 100 });
  ck('后面接入暴涨 bar 不影响第 i 根', a3.stop, a1.stop);
}

console.log('\n通过 ' + pass + ' 项' + (bad.length ? '，失败 ' + bad.length + ' 项：' + bad.join('、') : '，全部通过'));
process.exit(bad.length ? 1 : 0);
