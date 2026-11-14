// 拖延账单：对给定代码，算「决策时点价 vs 最新收盘价」的拖延代价（份数自动读 holdings.conf 实时值）。
// 用法：node delay-bill.js <code> [--shares N] [--points FILE] [--from YYYY-MM-DD]
//   --shares 缺省时读 $SG_HOME/holdings.conf 该代码行（SG_HOME 默认 ~/.stock-guardian）
//   --points 为 JSON 数组 [[日期,事件,当时价],...]；不给则只打印近 20 日 OHLC
// 数据源：腾讯公开 K 线（20 根 qfq 日线）
'use strict';
const fs = require('fs');
const path = require('path');

const argv = process.argv.slice(2);
const code = (argv.find((a) => /^[a-z]{2}\d{6}$/i.test(a)) || '').toLowerCase();
if (!code) {
  console.error('用法: node delay-bill.js <code> [--shares N] [--points FILE] [--from YYYY-MM-DD]');
  process.exit(1);
}
const flag = (n) => { const i = argv.indexOf(n); return i >= 0 ? argv[i + 1] : null; };
const sgHome = process.env.SG_HOME || path.join(process.env.HOME || '/root', '.stock-guardian');

let shares = flag('--shares') ? +flag('--shares') : null;
if (shares === null) {
  const hf = path.join(sgHome, 'holdings.conf');
  if (fs.existsSync(hf)) {
    const m = fs.readFileSync(hf, 'utf8').match(new RegExp('^' + code + '\\s*=\\s*([\\d,]+)', 'mi'));
    if (m) shares = +m[1].replace(/,/g, '');
  }
}
if (!shares || !Number.isFinite(shares)) {
  console.error(`未指定 --shares 且 holdings.conf 中无 ${code} 行（禁止凭空推算份数）`);
  process.exit(1);
}
const from = flag('--from') || '';

(async () => {
  const r = await fetch(`https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=${code},day,,,20,qfq`);
  const j = await r.json();
  const arr = (j.data && j.data[code] && (j.data[code].qfqday || j.data[code].day)) || [];
  const k = arr.map((x) => ({ d: x[0], o: +x[1], c: +x[2], h: +x[3], l: +x[4] }));
  console.log(`=== ${code} 近 ${k.length} 交易日 OHLC${from ? `（${from} 起）` : ''} ===`);
  k.filter((x) => !from || x.d >= from).forEach((x) => console.log(`${x.d}  开${x.o.toFixed(3)} 高${x.h.toFixed(3)} 低${x.l.toFixed(3)} 收${x.c.toFixed(3)}`));

  const pf = flag('--points');
  if (!pf || !k.length) return;
  const now = k[k.length - 1].c;
  const nowLabel = k[k.length - 1].d;
  const points = JSON.parse(fs.readFileSync(pf, 'utf8'));
  console.log(`\n=== 拖延账单（${shares} 份：各时点执行 vs ${nowLabel} 收 ${now.toFixed(3)} 成交）===`);
  console.log('| 决策时点 | 事件 | 当时价格 | 当时执行 vs 现在成交 差额 |');
  console.log('|---|---|---|---|');
  let first = null;
  for (const [d, ev, px] of points) {
    if (!px) { console.log(`| ${d} | ${ev} | — | — |`); continue; }
    const diff = (now - px) * shares;
    if (first === null) first = diff;
    console.log(`| ${d} | ${ev} | ${(+px).toFixed(3)} | ${diff >= 0 ? '+' : ''}${diff.toFixed(0)} 元 |`);
  }
  if (first !== null) console.log(`\n📌 最早可执行时点至今的拖延总代价：${(-first).toFixed(0)} 元（${shares} 份）`);
})().catch((e) => { console.error('拉取失败:', e.message); process.exit(1); });
