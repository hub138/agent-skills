#!/usr/bin/env node
// hold-review 回归（2026-10-29 立）
// 锁三件事：① 持仓判定只有一把尺子（exit-gate 九维），本文件不许再写一份五问；
//          ② 判定不依赖任何"线"（watch.conf / alerts.conf 的失效价都不参与）；
//          ③ 持仓从 state 读，零持仓要明说，不许静默跳过。
'use strict';
const fs = require('fs');
const path = require('path');
const H = require('../scripts/hold-review.js');
const E = require('../scripts/exit-gate.js');

let pass = 0; const bad = [];
const ck = (n, g, w = true) => { const ok = JSON.stringify(g) === JSON.stringify(w); ok ? pass++ : bad.push(n); console.log(`  ${ok ? '✔' : '✘'} ${n}${ok ? '' : '  got=' + JSON.stringify(g) + ' want=' + JSON.stringify(w)}`); };
const mk = (cs) => cs.map((c, i) => { const o = i ? cs[i - 1] : c; return { d: `2026-03-${String(i + 1).padStart(2, '0')}`, o, h: Math.max(o, c) * 1.004, l: Math.min(o, c) * 0.996, c, v: 1e6 }; });
const up = (n, a = 100, step = 0.6) => Array.from({ length: n }, (_, i) => +(a + i * step).toFixed(3));

console.log('T1 持仓从 state 抽（quantity>0 才叫持仓，入场日取最近一笔 BUY）');
{
  const recs = [
    { type: 'POSITION', code: 'sh900001', quantity: 5000, cost: 0.872 },
    { type: 'POSITION', code: 'sz900002', quantity: 0, cost: 26.59 },
    { type: 'EXECUTION', code: 'sh900001', side: 'BUY', qty: 5000, known_at: '2026-10-21' },
    { type: 'EXECUTION', code: 'sh900001', side: 'BUY', qty: 100, known_at: '2026-10-27' },
  ];
  const p = H.positionsFromState(recs);
  ck('只留 quantity>0 的', p.length, 1);
  ck('代码/成本/份数对', [p[0].code, p[0].cost, p[0].qty], ['sh900001', 0.872, 5000]);
  ck('入场日取最近一笔 BUY', p[0].since, '2026-10-27');
}

console.log('T2 零持仓要明说（不许静默跳过）');
{
  const dir = fs.mkdtempSync('/tmp/sg-hr-');
  const r = H.readMaster(dir);
  ck('无 MASTER.md → 空', r.length, 0);
  ck('零持仓 → 抽不出持仓', H.positionsFromState(r).length, 0);
  fs.rmSync(dir, { recursive: true, force: true });
}

console.log('T3 证据缺失：日线不足不许默认继续持有');
{
  const r = H.reviewOne({ code: 'sz000001', qty: 100, cost: 10, since: '' }, mk(up(10)));
  ck('日线不足 → EXIT', r.verdict, 'EXIT');
  ck('并给出说明', /不足/.test(r.note || r.reasons.join('')), true);
}

console.log('T4 判定走的是 exit-gate 九维（不是另一套）');
{
  const bars = mk(up(25));
  const r = H.reviewOne({ code: 'sz000001', qty: 100, cost: 110.5, since: bars.at(-3).d }, bars);
  ck('九维全在场', r.dims.length, 9);
  ck('健康持仓 → HOLD', r.verdict, 'HOLD');
  ck('与直接调 exit-gate 同结果', r.verdict, E.review(bars, { code: 'sz000001', cost: 110.5, since: bars.at(-3).d }).verdict);
}

console.log('T5 止损是动态锚，不是"失效价"那根线');
{
  const bars = mk(up(25));
  const px = +(bars.at(-1).c * 0.8).toFixed(3);
  const r = H.reviewOne({ code: 'sz000001', qty: 100, cost: bars[20].c, since: bars.at(-3).d }, bars, { price: px });
  ck('跌破动态锚 → EXIT', r.verdict, 'EXIT');
  ck('首条理由是破锚', /破锚/.test(r.reasons[0] || ''), true);
  ck('锚来自 ATR/结构/保本三源', r.anchor && r.anchor.stop !== null && r.anchor.parts && 'atrStop' in r.anchor.parts, true);
}

console.log('T6 不重复开发：本文件不许再自带判定，也不许读 alerts.conf');
{
  const src = fs.readFileSync(path.join(__dirname, '..', 'scripts', 'hold-review.js'), 'utf8');
  // 只看代码行：注释里"为什么不再读某文件"恰恰是要保留的说明，不能算违规
  const code = src.split('\n').filter((l) => !l.trim().startsWith('//')).join('\n');
  ck('不读 alerts.conf（不再拿失效价当判据）', /alerts\.conf/.test(code), false);
  ck('不读 watch.conf（复核不依赖挂线）', /watch\.conf/.test(code), false);
  ck('不自带 FAIL 计数判定（交给 exit-gate）', /fails\.length\s*>=?\s*3|fails\.push/.test(code), false);
  ck('确实 require 了 exit-gate', /require\(.*exit-gate\.js'\)/.test(code), true);
  ck('注释里写明为什么不读线（免得后人又加回来）', /线是没用的|不依赖任何线|不再.*失效价/.test(src), true);
}

console.log('\n通过 ' + pass + ' 项' + (bad.length ? '，失败 ' + bad.length + ' 项：' + bad.join('、') : '，全部通过'));
process.exit(bad.length ? 1 : 0);
