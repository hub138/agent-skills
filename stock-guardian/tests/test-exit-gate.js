#!/usr/bin/env node
// exit-gate 回归（2026-10-29 立）
// 锁的是三件用户反复强调、且最容易被"改回去"的事：
//   ① 卖出不是"线有没有被越过"——价格只是九条里的一条（锚/趋势/位置/动能/量价/时间/落袋/空仓视角/相对强度）；
//   ② "如果一个票当天空仓不会买，且微赚就要清"——微赚且走弱 = EXIT，不许"再等等"；
//   ③ 证据缺失不许默认继续持有；入场首日不给自己发卖出指令（除破锚）。
'use strict';
const E = require('../scripts/exit-gate.js');
const A = require('../scripts/dyn-anchor.js');

let pass = 0; const bad = [];
const ck = (n, g, w = true) => { const ok = JSON.stringify(g) === JSON.stringify(w); ok ? pass++ : bad.push(n); console.log(`  ${ok ? '✔' : '✘'} ${n}${ok ? '' : '  got=' + JSON.stringify(g) + ' want=' + JSON.stringify(w)}`); };
const mk = (cs) => cs.map((c, i) => { const o = i ? cs[i - 1] : c; return { d: `2026-03-${String(i + 1).padStart(2, '0')}`, o, h: Math.max(o, c) * 1.004, l: Math.min(o, c) * 0.996, c, v: 1e6 }; });
const up = (n, a = 100, step = 0.6) => Array.from({ length: n }, (_, i) => +(a + i * step).toFixed(3));
const dim = (r, k) => r.dims.find((d) => d.key === k) || {};

console.log('T1 证据缺失：看不见就不许拿着');
{
  const r = E.review(mk(up(10)), { code: 'sz000001', cost: 100 });
  ck('日线不足 → EXIT（不是默认继续持有）', r.verdict, 'EXIT');
  ck('并说明是数据不足', /不足/.test(r.note), true);
}

console.log('T2 破动态锚 = 清（锚是 ATR/结构/保本三源取紧，不是买入时拍死的价）');
{
  const bars = mk(up(25));
  const px = +(bars.at(-1).c * 0.8).toFixed(3);
  const r = E.review(bars, { code: 'sz000001', cost: bars[20].c, price: px, since: bars.at(-3).d });
  ck('跌破动态锚 → EXIT', r.verdict, 'EXIT');
  ck('首条理由写明破锚', /破锚/.test(r.reasons[0] || ''), true);
  ck('判定用的确实是动态锚', r.anchor.stop !== null && px < r.anchor.stop, true);
}

console.log('T3 九条全过 → 拿着（价格涨得动就不折腾）');
{
  const bars = mk(up(25));
  const r = E.review(bars, { code: 'sz000001', cost: 110.5, since: bars.at(-3).d });
  ck('全过 → HOLD', r.verdict, 'HOLD');
  ck('不过条数 0', r.fails, 0);
  ck('九条都在场', r.dims.length, 9);
}

console.log('T4 微赚且走弱 → 清（"华东第二三天赚了一点就可以清了"）');
{
  const bars = mk([...up(20, 100, 0.6), 111.4, 109.5, 107.6, 105.7, 104.0]);
  const r = E.review(bars, { code: 'sz000001', cost: 103.0, since: bars.at(-3).d });
  ck('微赚 + 走弱 → EXIT', r.verdict, 'EXIT');
  ck('浮盈确实落在微赚区间', r.pnl > 0 && r.pnl < E.DEFAULTS.microProfit, true);
  ck('落袋维度写明微赚', /微赚/.test(dim(r, 'pnl').detail), true);
  ck('动能维度同时 FAIL（是"走弱"，不是"赚得少"）', dim(r, 'momentum').ok, false);
}

console.log('T5 空仓视角：今天空仓还会不会买它');
{
  const bars = mk([...up(12, 100, 1.0), 112, 110, 108, 106, 104, 102]);
  const bv = E.buyView(bars, bars.at(-1).c, 'sz000001', -1.9);
  ck('下跌末端 → 不会买', bv.ok, false);
  ck('给出具体理由（不是空口）', bv.reasons.length > 0, true);
  const okCase = E.buyView(mk(up(25)), 114.4, 'sz000001', 0.5);
  ck('右侧启动 → 仍会买', okCase.ok, true);
}

console.log('T6 时间到且不盈利 → 清（"我玩不了 1 周以上"）');
{
  const bars = mk(up(25));
  const r = E.review(bars, { code: 'sz000001', cost: +(bars.at(-1).c * 1.02).toFixed(3), since: bars.at(-8).d, maxHold: 5 });
  ck('超上限且浮亏 → EXIT', r.verdict, 'EXIT');
  ck('时间维度 FAIL', dim(r, 'time').ok, false);
  ck('持有天数算对', r.tDays, 7);
}

console.log('T7 入场首日不发卖出指令（当天买当天喊清 = 闸门自相矛盾）');
{
  const bars = mk(up(25));
  const px = +(bars.at(-1).c * 0.97).toFixed(3);
  const o = { code: 'sz000001', cost: 112, price: px, anchor: { atrMult: 4 } };
  const d0 = E.review(bars, Object.assign({}, o, { since: bars.at(-1).d }));
  const d2 = E.review(bars, Object.assign({}, o, { since: bars.at(-3).d }));
  ck('首日 → HOLD', d0.verdict, 'HOLD');
  ck('并注明是首日例外', /入场首日/.test(d0.note), true);
  ck('第 3 日同样情形 → EXIT（例外不是免死金牌）', d2.verdict, 'EXIT');
  ck('清仓理由写明"空仓不会买"', /空仓/.test(d2.reasons.join('')), true);
  ck('首日未破锚（所以才适用例外）', d0.anchor.stop === null || px > d0.anchor.stop, true);
}

console.log('T8 相对强度：给了基准才算，没给不许假通过');
{
  const bars = mk(up(25));
  const no = E.review(bars, { code: 'sz000001', cost: 110.5, since: bars.at(-3).d });
  ck('没给基准 → 明写未参与', /未参与/.test(dim(no, 'rs').detail), true);
  const yes = E.review(bars, { code: 'sz000001', cost: 110.5, since: bars.at(-3).d, bench: mk(up(25, 100, 0.2)) });
  ck('给了基准 → 算 5 日超额', /5 日超额/.test(dim(yes, 'rs').detail), true);
}

console.log('T9 同尺子：闸门里的锚就是 dyn-anchor 算出来的那个');
{
  const bars = mk(up(25));
  const r = E.review(bars, { code: 'sz000001', cost: 110.5, since: bars.at(-3).d });
  ck('锚值一致（防两份实现漂移）', r.anchor.stop, A.anchorFor(bars, undefined, { cost: 110.5 }).stop);
}

console.log('T10 反向：微赚但没走弱 → 不因为"赚得少"就清');
{
  const bars = mk(up(25));
  const r = E.review(bars, { code: 'sz000001', cost: +(bars.at(-1).c / 1.008).toFixed(3), since: bars.at(-3).d });
  ck('浮盈在微赚区间', r.pnl > 0 && r.pnl < E.DEFAULTS.microProfit, true);
  ck('趋势动能都好 → HOLD', r.verdict, 'HOLD');
}

console.log('\n通过 ' + pass + ' 项' + (bad.length ? '，失败 ' + bad.length + ' 项：' + bad.join('、') : '，全部通过'));
process.exit(bad.length ? 1 : 0);
