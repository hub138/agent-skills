#!/usr/bin/env node
// stock-guardian 票性仪表盘（stock-behavior.js）——把"这票什么性格"变成可复算的数字，不靠印象。
// 纯工具层，零用户数据，随 skill 整体分发。数据通道：westock-data（缺席时退出并提示）。
// 用法：
//   node stock-behavior.js <代码[,代码...]> [--lookback N] [--index 代码]
//     --lookback N   统计窗口（默认 60 个交易日）
//     --index 代码   相对基准（默认 sh000001 上证指数）
//   node stock-behavior.js <代码A,代码B> --pair [--lookback N]
//     --pair         两票相关性模式：输出近 N 日（默认 20，对齐 rules.md 组合相关性条口径）
//                    同向天数占比，供"同向占比>80% 统计判据"复算
// 输出（每票一段）：
//   1. 日线性格：高开低走率 / 低开高走率 / 阳线率 / 平均振幅（T 票资格）
//   2. 相对强度：RS>0 天数占比、大盘跌日 RS>0 天数（逆势/抗跌天数）、RS 5 日均值、20 日累计 RS（价格法）
//   3. 票性分类：逆势强势 / 顺周期β / 随波逐流（按 RS 分布自动归类）
//   4. 连续性：最长连阳/连阴、量能放大日上涨率（放量跟涨还是放量出货）
//   5. 周五效应：周五样本涨跌率/周五 vs 非周五均涨/周五高开低走/周五 RS（样本<8 禁引用）
//   6. 波动与量能锚（rules.md 止损体系"波动率锚定"与盘面语言库"量比"条口径）：ATR(14) Wilder 平滑、收盘量比
// 保鲜期规则（rules.md 票性章）：画像引用超 2 个交易日必须重算本工具再引用。
'use strict';
const { execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');

function resolveWestock() {
  const cands = [
    process.env.WESTOCK,
    path.join(__dirname, '..', '..', 'westock-data', 'scripts', 'index.js'),
  ].filter(Boolean);
  for (const c of cands) { try { fs.accessSync(c); return c; } catch(e){} }
  console.error('未找到 westock-data（请安装在 skills/westock-data，或设 WESTOCK 环境变量）');
  process.exit(1);
}
const WESTOCK = resolveWestock();

function kline(code, start) {
  const end = new Date().toISOString().slice(0, 10);
  const out = execFileSync('node', [WESTOCK, 'kline', code, '--start', start, '--end', end],
    { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024, timeout: 60000 });
  const rows = [];
  for (const line of out.split('\n')) {
    if (!/^\|\s*\d{4}-/.test(line)) continue;
    const c = line.split('|').map(s => s.trim());
    rows.push({ date: c[1], open: +c[2], last: +c[3], high: +c[4], low: +c[5], volume: +c[6] });
  }
  return rows;
}

function pct(a, b) { return (a - b) / b * 100; }

function classify(rsPosRate, idxDownPosRate, volUpUpRate) {
  // 逆势强势：大盘跌日多数仍强；顺周期β：跟大盘同向且放量跟涨；其余为随波逐流。
  if (idxDownPosRate >= 0.5) return '逆势强势（大盘跌日过半数 RS>0，有独立资金）';
  if (rsPosRate >= 0.55 && volUpUpRate >= 0.6) return '顺周期β（跟大盘同向且放量跟涨）';
  return '随波逐流（无明显独立行情，跟随市场平均）';
}

function analyze(code, lookback, idxCode) {
  const start = new Date(Date.now() - lookback * 1.7 * 86400e3).toISOString().slice(0, 10);
  const [rows, idxRows] = [kline(code, start), kline(idxCode, start)];
  if (!rows.length) { console.log(`\n### ${code}\n无数据`); return; }
  const idxMap = new Map(idxRows.map(r => [r.date, r]));
  // 对齐到两序列共有的日期；kline 返回最新在前，取最近 lookback 根后反转为时间序
  const use = rows.filter(r => idxMap.has(r.date)).slice(0, lookback).reverse();
  const n = use.length;
  if (n < 10) { console.log(`\n### ${code}\n样本不足（${n} < 10）`); return; }

  let gapUp = 0, gapUpLow = 0, gapDown = 0, gapDownHigh = 0, yang = 0;
  let rsPos = 0, rsDays = 0, idxDownDays = 0, idxDownPos = 0;
  let volUpUp = 0, volUpCnt = 0;
  let friN = 0, friUp = 0, friSum = 0, friGapUp = 0, friGapUpLow = 0, friRsSum = 0, friRsN = 0, allSum = 0, allN = 0;
  let maxUp = 0, maxDown = 0, curUp = 0, curDown = 0;
  const rs5 = [];
  for (let i = 1; i < n; i++) {
    const r = use[i], p = use[i - 1];
    const ir = idxMap.get(r.date), ip = idxMap.get(p.date);
    const idxRet = ir && ip ? pct(ir.last, ip.last) : null;
    const chg = pct(r.last, p.last);
    const gap = r.open - p.last;
    if (gap > 0) { gapUp++; if (r.last < r.open) gapUpLow++; }
    else if (gap < 0) { gapDown++; if (r.last > r.open) gapDownHigh++; }
    allSum += chg; allN++;
    if (new Date(r.date).getDay() === 5) {
      friN++; friSum += chg; if (chg > 0) friUp++;
      if (gap > 0) { friGapUp++; if (r.last < r.open) friGapUpLow++; }
    }
    if (r.last >= r.open) yang++;
    if (chg > 0) { curUp++; curDown = 0; } else if (chg < 0) { curDown++; curUp = 0; }
    maxUp = Math.max(maxUp, curUp); maxDown = Math.max(maxDown, curDown);
    if (i >= 2 && r.volume > use[i - 1].volume * 1.5) { volUpCnt++; if (chg > 0) volUpUp++; }
    if (idxRet !== null) {
      const rs = chg - idxRet;
      rsDays++;
      if (rs > 0) rsPos++;
      if (idxRet < 0) { idxDownDays++; if (rs > 0) idxDownPos++; }
      if (new Date(r.date).getDay() === 5) { friRsSum += rs; friRsN++; }
      rs5.push(rs);
    }
  }
  const ampAvg = use.reduce((s, r) => s + (r.high - r.low) / r.low, 0) / n * 100;
  const rs5Avg = rs5.length ? rs5.slice(-5).reduce((a, b) => a + b, 0) / Math.min(5, rs5.length) : 0;
  const rsPosRate = rsDays ? rsPos / rsDays : 0;
  const idxDownPosRate = idxDownDays ? idxDownPos / idxDownDays : 0;
  const volUpUpRate = volUpCnt ? volUpUp / volUpCnt : 0;
  const label = classify(rsPosRate, idxDownPosRate, volUpUpRate);
  // ATR(14) Wilder 平滑：TR=max(高-低, |高-昨收|, |低-昨收|)，首值=首日 TR 的简单均值，其后 ATR=(前值×13+当期TR)/14
  let atr14 = null;
  if (n >= 15) {
    let sumTr = 0, cntTr = 0;
    for (let i = 1; i < n; i++) {
      const r = use[i], p = use[i - 1];
      const tr = Math.max(r.high - r.low, Math.abs(r.high - p.last), Math.abs(r.low - p.last));
      if (atr14 === null) { sumTr += tr; cntTr++; if (cntTr === 14) atr14 = sumTr / 14; }
      else atr14 = (atr14 * 13 + tr) / 14;
    }
  }
  // 20 日累计 RS（价格法）：区间票累计涨幅 - 区间大盘累计涨幅，rules.md 票性节"20 日累计 RS 结构判据"
  const win = Math.min(20, n - 1);
  const rs20 = win >= 10 ? pct(use[n - 1].last, use[n - 1 - win].last) - pct(idxMap.get(use[n - 1].date).last, idxMap.get(use[n - 1 - win].date).last) : null;
  // 收盘量比（日频口径）：当日总量 × 5 ÷ 过去 5 日总量，收盘后等价标准量比定义
  let volRatio = null;
  if (n >= 6) {
    let prev5 = 0;
    for (let i = n - 6; i < n - 1; i++) prev5 += use[i].volume;
    volRatio = prev5 > 0 ? use[n - 1].volume * 5 / prev5 : null;
  }
  const atrPct = atr14 !== null ? (atr14 / use[n - 1].last * 100) : null;

  console.log(`\n### ${code}（近 ${n} 个交易日，基准 ${idxCode}）`);
  console.log(`票性分类：${label}`);
  console.log(`日线性格：高开${gapUp}次·低走${gapUpLow}次（${(gapUp ? gapUpLow / gapUp * 100 : 0).toFixed(0)}%）｜低开${gapDown}次·高走${gapDownHigh}次（${(gapDown ? gapDownHigh / gapDown * 100 : 0).toFixed(0)}%）｜阳线率 ${(yang / n * 100).toFixed(0)}%｜平均振幅 ${ampAvg.toFixed(2)}%`);
  console.log(`相对强度：RS>0 天数占比 ${(rsPosRate * 100).toFixed(0)}%｜大盘跌日 ${idxDownDays} 天中 ${idxDownPos} 天 RS>0（${(idxDownPosRate * 100).toFixed(0)}%）｜RS 近5日均值 ${rs5Avg >= 0 ? '+' : ''}${rs5Avg.toFixed(2)}pp${rs20 === null ? '' : `｜20日累计RS（价格法） ${rs20 >= 0 ? '+' : ''}${rs20.toFixed(2)}pp`}`);
  console.log(`波动与量能锚：ATR(14) ${atrPct === null ? '样本不足（<15 日）' : `${atr14.toFixed(3)} 元（占价 ${atrPct.toFixed(2)}%，止损下限参考 1.5×=${(atrPct * 1.5).toFixed(2)}%，吊灯止盈 3×=${(atrPct * 3).toFixed(2)}%）`}｜收盘量比 ${volRatio === null ? '样本不足（<6 日）' : volRatio.toFixed(2)}`);
  console.log(`连续性：最长连阳 ${maxUp} 天 / 连阴 ${maxDown} 天｜放量日上涨率 ${(volUpUpRate * 100).toFixed(0)}%（放量跟涨 or 出货）`);
  if (friN >= 8) {
    const friAvg = friSum / friN, nonFriAvg = (allN - friN) ? (allSum - friSum) / (allN - friN) : 0;
    const friRs = friRsN ? friRsSum / friRsN : null;
    console.log(`周五效应：${friN} 个周五样本 上涨 ${friUp} 次（${(friUp / friN * 100).toFixed(0)}%）｜周五均涨 ${friAvg >= 0 ? '+' : ''}${friAvg.toFixed(2)}% vs 非周五 ${nonFriAvg >= 0 ? '+' : ''}${nonFriAvg.toFixed(2)}%｜周五高开 ${friGapUp} 次低走 ${friGapUpLow} 次｜周五 RS 均值 ${friRs === null ? '无样本' : (friRs >= 0 ? '+' : '') + friRs.toFixed(2) + 'pp'}`);
  } else {
    console.log(`周五效应：周五样本仅 ${friN} 个（<8 不足以下结论），禁引用`);
  }
  console.log(`日历：样本 ${use[0].date} ~ ${use[n - 1].date}｜本画像保鲜期 2 个交易日，超期引用前必须重算`);
}

// 两票相关性：rules.md「仓位与风险预算」组合相关性条的统计判据出处——同向占比 >80% 的可复算数字
function pairAnalyze(a, b, lookback) {
  const start = new Date(Date.now() - lookback * 1.7 * 86400e3).toISOString().slice(0, 10);
  const rowsA = kline(a, start), rowsB = kline(b, start);
  const mapB = new Map(rowsB.map(r => [r.date, r]));
  const use = rowsA.filter(r => mapB.has(r.date)).slice(0, lookback).reverse();
  const n = use.length;
  if (n < 11) { console.log(`\n### 相关性：${a} vs ${b}\n样本不足（共有 ${n} 个交易日，可用涨跌日 ${n - 1} < 10）`); return; }
  let same = 0, upUp = 0, downDown = 0, flatFlat = 0, diff = 0;
  for (let i = 1; i < n; i++) {
    const ra = use[i], pa = use[i - 1];
    const rb = mapB.get(ra.date), pb = mapB.get(pa.date);
    const sA = Math.sign(pct(ra.last, pa.last)), sB = Math.sign(pct(rb.last, pb.last));
    if (sA === sB) { same++; if (sA > 0) upUp++; else if (sA < 0) downDown++; else flatFlat++; }
    else diff++;
  }
  const days = n - 1;
  const rate = same / days;
  console.log(`\n### 相关性：${a} vs ${b}（近 ${days} 个共有涨跌日）`);
  console.log(`同向 ${same}/${days} 天（占比 ${(rate * 100).toFixed(0)}%）｜同涨 ${upUp} 天·同跌 ${downDown} 天${flatFlat ? `·同平 ${flatFlat} 天` : ''}｜不同向 ${diff} 天`);
  console.log(`口径：同向=两票当日涨跌幅同号（都涨或都跌，同时平盘也算同向）`);
  console.log(`判据参考：同向占比 >80% 即统计判据成立；与结构判据（同行业/监控宇宙同一映射链）任一成立，即按单票上限合并执行（rules.md「仓位与风险预算」组合相关性条）`);
  console.log(`日历：样本 ${use[0].date} ~ ${use[n - 1].date}｜保鲜期 2 个交易日，超期引用前必须重算`);
}

const args = process.argv.slice(2);
if (!args.length) { console.log('用法：node stock-behavior.js <代码[,代码...]> [--lookback 60] [--index sh000001] [--pair]'); process.exit(0); }
let pairMode = false, lookback = null, idxCode = 'sh000001';
const positional = [];
for (let i = 0; i < args.length; i++) {
  if (args[i] === '--pair') pairMode = true;
  else if (args[i] === '--lookback') lookback = +args[++i];
  else if (args[i] === '--index') idxCode = args[++i];
  else positional.push(args[i]);
}
const codes = positional.flatMap(s => s.split(',')).map(s => s.trim()).filter(Boolean);
if (pairMode) {
  if (codes.length !== 2) { console.error('--pair 模式需要恰好两只票（如：node stock-behavior.js 510300,510500 --pair）'); process.exit(1); }
  pairAnalyze(codes[0], codes[1], lookback === null ? 20 : lookback);
} else {
  const lb = lookback === null ? 60 : lookback;
  console.log(`票性仪表盘 ${new Date().toISOString().slice(0, 10)}｜保鲜期 2 日｜数字可复算，不靠印象`);
  for (const c of codes) analyze(c, lb, idxCode);
}
