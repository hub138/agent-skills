#!/usr/bin/env node
// 防御逆势候选研究：环境恶化日×防御票逆势 → T+1/T+3/T+5 vs 同日基线+追高对照
// 形态（触发日收盘判定，无未来函数）：
//   环境恶化：创业板/上证 当日跌幅 ≤ -1.5%（用上证）
//   防御票四条：①当日逆势（跑赢上证 ≥1.5 个点）②低波（20日振幅均值<4%）③低位（20日涨幅<10%）④量比近似值<1.5
// 收益分母：触发日收盘（修正口径自欺教训）
// 能力边界：本脚本不模拟低吸挂单、成交、退出和成本，只用于候选研究。
'use strict';
const fs = require('fs'), path = require('path');
const HOME = process.env.HOME || '/root';
const SG = process.env.SG_HOME || path.join(HOME, '.stock-guardian');
const CACHE = path.join(SG, 'cache', 'kline');
const UNIVERSE = process.env.SG_UNIVERSE || path.join(SG, 'universe300.frozen');
const codes = fs.readFileSync(UNIVERSE, 'utf8').split('\n').map(s => s.trim()).filter(Boolean);
const avg = a => a.reduce((x, y) => x + y, 0) / (a.length || 1);
const latestCacheFile = code => {
  const files = fs.readdirSync(CACHE).filter(f => f.startsWith(code + '_640_') && f.endsWith('.json')).sort();
  return files.length ? files[files.length - 1] : null;
};
(async () => {
  // 指数日线（市场环境判定）
  const idxF = latestCacheFile('sh000001');
  if (!idxF) throw new Error('缺少 sh000001 的 640 日缓存');
  const idxRaw = JSON.parse(fs.readFileSync(path.join(CACHE, idxF), 'utf8'));
  const dayMkt = new Map();
  for (let i = 1; i < idxRaw.length; i++) {
    const d = idxRaw[i].d, r = (idxRaw[i].c / idxRaw[i - 1].c - 1) * 100;
    dayMkt.set(d, { r, day: idxRaw[i] });
  }
  // 逐票扫描
  const defense = [], chase = [], allByDay = new Map();
  let scanned = 0;
  for (const code of codes) {
    const f = latestCacheFile(code);
    if (!f) continue;
    const k = JSON.parse(fs.readFileSync(path.join(CACHE, f), 'utf8'));
    if (k.length < 100) continue;
    scanned++;
    for (let i = 25; i < k.length - 12; i++) {
      const t = k[i];
      const mkt = dayMkt.get(t.d); if (!mkt) continue;
      // 记录全部样本（同日基线）
      const fwd = days => i + days < k.length ? k[i + days].c : null;
      const c1 = fwd(1); if (!c1) continue;
      const r1 = (c1 / t.c - 1) * 100;
      const c3 = fwd(3), c5 = fwd(5);
      if (!allByDay.has(t.d)) allByDay.set(t.d, []);
      allByDay.get(t.d).push({ code, r1: +(r1).toFixed(2), r3: c3 ? +((c3 / t.c - 1) * 100).toFixed(2) : null, r5: c5 ? +((c5 / t.c - 1) * 100).toFixed(2) : null });
      // 环境恶化日判定
      if (mkt.r > -1.5) continue;
      // 个股当日
      const stockRet = (t.c / k[i - 1].c - 1) * 100;
      const outperform = stockRet - mkt.r;
      // 追高对照必须独立于防御过滤。
      if (stockRet > 5) chase.push({ code, day: t.d, r1: +r1.toFixed(2) });
      // 防御四条
      if (outperform < 1.5) continue;                      // 逆势 ≥1.5 点
      const atrs = []; for (let q = Math.max(1, i - 20); q <= i; q++) atrs.push((k[q].h - k[q].l) / k[q].c * 100);
      const atr20 = avg(atrs);
      // ATR 低 1/3 阈值动态算不了（需全宇宙截面）——近似用绝对值 <3%
      if (atr20 > 4) continue;                             // 低波
      const trend20 = (t.c / k[i - 20].c - 1) * 100;
      if (trend20 > 10) continue;                          // 非高位
      const turn = t.v / (k.slice(i - 5, i).reduce((a, b) => a + b.v, 0) / 5);
      if (turn > 1.5) continue;                            // 非情绪票（量比近似）
      const c3d = c3 ? +((c3 / t.c - 1) * 100).toFixed(2) : null, c5d = c5 ? +((c5 / t.c - 1) * 100).toFixed(2) : null;
      defense.push({ code, day: t.d, stockRet: +stockRet.toFixed(2), mktRet: +mkt.r.toFixed(2), outp: +outperform.toFixed(2), atr20: +atr20.toFixed(2), trend20: +trend20.toFixed(1), r1: +r1.toFixed(2), r3: c3d, r5: c5d });
    }
  }
  // 同日基线（恶化日全宇宙均值——beta 剥离）
  const dayBase = new Map();
  for (const [d, list] of allByDay.entries()) {
    if (!dayMkt.get(d) || dayMkt.get(d).r > -1.5) continue;
    dayBase.set(d, avg(list.map(x => x.r1)));
  }
  // 汇总
  const w = a => +(a.filter(x => x > 0).length / (a.length || 1) * 100).toFixed(1);
  const m = a => +(a.reduce((x, y) => x + y, 0) / (a.length || 1)).toFixed(2);
  console.log(`\n=== 防御逆势候选研究（${scanned} 只 × 640 天）===`);
  console.log(`形态：环境恶化日（上证≤-1.5%）× 防御逆势票（跑赢大盘≥1.5点+低波+非高位+量比近似值<1.5）× 触发日收盘事件收益`);
  console.log('边界：没有模拟低吸挂单、未成交、退出与成本，本结果不能证明低吸计划能够赚钱。');
  // 异常收益按日聚合（每个恶化日：防御组合均值 - 宇宙均值 → 日级差值分布）
  const defByDay = new Map();
  defense.forEach(r => { if (!defByDay.has(r.day)) defByDay.set(r.day, []); defByDay.get(r.day).push(r.r1); });
  const dayAbn = [];
  for (const [d, list] of defByDay.entries()) { const base = dayBase.get(d); if (base === undefined) continue; dayAbn.push({ day: d, n: list.length, def: +avg(list).toFixed(2), base: +base.toFixed(2), abn: +(avg(list) - base).toFixed(2) }); }
  dayAbn.sort((a, b) => a.day.localeCompare(b.day));
  console.log(`\n【日级聚合（每个恶化日：防御组合 vs 宇宙基线，消除日期聚集失真）】`);
  const winDays = dayAbn.filter(d => d.abn > 0).length;
  console.log(`  恶化日 ${dayAbn.length} 个｜防御跑赢宇宙的天数 ${winDays}（${(winDays / (dayAbn.length || 1) * 100).toFixed(0)}%）｜日均异常 ${avg(dayAbn.map(d => d.abn))} 点`);
  dayAbn.forEach(d => console.log(`    ${d.day}: 防御${d.def}% vs 宇宙${d.base}% → 异常 ${d.abn} 点（${d.n} 票）`));
  console.log(`\n【防御逆势票明细汇总】n=${defense.length}`);
  console.log(`  T+1 ${m(defense.map(r => r.r1))}%（胜率${w(defense.map(r => r.r1))}%）｜T+3 ${m(defense.filter(r => r.r3 !== null).map(r => r.r3))}%｜T+5 ${m(defense.filter(r => r.r5 !== null).map(r => r.r5))}%`);
  console.log(`  同日宇宙基线 T+1：${m([...dayBase.values()])}%`);
  console.log(`\n【追高对照（同日涨幅>5%）】n=${chase.length}｜T+1 ${m(chase.map(r => r.r1))}%（胜率${w(chase.map(r => r.r1))}%）`);
  if (defense.length && chase.length) console.log(`  防御 vs 追高 的 T+1 差：${(m(defense.map(r => r.r1)) - m(chase.map(r => r.r1))).toFixed(2)} 点`);
  // 分年
  const byYear = {};
  defense.forEach(r => { const y = r.day.slice(0, 4); (byYear[y] = byYear[y] || []).push(r); });
  console.log(`\n【分年】`);
  for (const [y, g] of Object.entries(byYear)) console.log(`  ${y}: n=${g.length}｜T+1 ${m(g.map(r => r.r1))}%（胜率${w(g.map(r => r.r1))}%）`);
  const outputDir = path.join(SG, 'factors');
  fs.mkdirSync(outputDir, { recursive: true });
  const output = path.join(outputDir, 'defense_' + new Date().toISOString().slice(0, 10) + '.json');
  fs.writeFileSync(output, JSON.stringify({ ts: new Date().toISOString(), scanned, n: defense.length, boundary: '触发日收盘事件研究，未模拟低吸挂单、成交、退出与成本', defense: defense.slice(0, 300) }, null, 1));
  console.log('\n研究结果已写入 ' + output);
})();
