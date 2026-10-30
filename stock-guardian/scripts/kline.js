#!/usr/bin/env node
// kline.js —— 日线数据与形态判定公共模块（2026-10-29 立）
// 由来：用户问"银行 ETF 昨天低点适合低吸，是 V 左探底还是 V 右启动？这种时机应该能被判断并通知我"。
// 此前 skill 内只有当日快照（quote-public.sh），没有历史日线，所以 V 形、均线、前高前低、5 日涨幅都判不了；
// delay-bill.js 里已经有腾讯 fqkline 取数（20 根 qfq 日线），本模块把它抽成公共能力，禁止各脚本各自乱抓。
// 数据源：腾讯公开 K 线（qfq 前复权）。用法：node kline.js sh900001 [--n 30]
'use strict';

const { execFileSync } = require('child_process');
const TENCENT = 'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=';
const SINA = (c, n) => `https://quotes.sina.cn/cn/api/jsonp_v2.php/var=/CN_MarketDataService.getKLineData?symbol=${c}&scale=240&ma=no&datalen=${n}`;
const HDR = { Referer: 'https://finance.sina.com.cn/', 'User-Agent': 'Mozilla/5.0' };

function parseSina(txt) {
  const i = txt.indexOf('['), j = txt.lastIndexOf(']');
  if (i < 0 || j < 0) return [];
  return JSON.parse(txt.slice(i, j + 1)).map((x) => ({ d: x.day, o: +x.open, c: +x.close, h: +x.high, l: +x.low, v: +x.volume }));
}

// 主源：sina JSONP（本机实测可用）；备源：腾讯 ifzq（本机被 WAF 拦，仅作异地可用）。
// 两源都失败必须抛错，绝不静默返回空数组——空数组会被上层当成"没有数据所以放行"。
async function fetchKline(code, n = 60) {
  try {
    const r = await fetch(SINA(code, n), { headers: HDR });
    const k = parseSina(await r.text());
    if (k.length) return k;
  } catch { /* 落备源 */ }
  const r2 = await fetch(`${TENCENT}${code},day,,,${n},qfq`);
  const j2 = await r2.json();
  const arr = (j2.data?.[code]?.qfqday || j2.data?.[code]?.day) || [];
  if (!arr.length) throw new Error('两个日线源都没取到 ' + code);
  return arr.map((x) => ({ d: x[0], o: +x[1], c: +x[2], h: +x[3], l: +x[4], v: +(x[5] || 0) }));
}

// 同步版：给 prebuy-check 这类必须同步判定的脚本用（curl 子进程，禁止各脚本各写一份抓取）
function fetchKlineSync(code, n = 60) {
  const raw = execFileSync('curl', ['-s', '--max-time', '15', '-H', 'Referer: https://finance.sina.com.cn/', '-H', 'User-Agent: Mozilla/5.0', SINA(code, n)], { encoding: 'utf8', timeout: 20000 });
  const k = parseSina(raw);
  if (!k.length) throw new Error('日线源返回异常（被拦或代码错误）：' + code);
  return k;
}

const ma = (k, n) => (k.length < n ? null : +(k.slice(-n).reduce((a, x) => a + x.c, 0) / n).toFixed(4));
const pct = (a, b) => (b ? (a / b - 1) * 100 : null);

function stats(k) {
  const last = k.at(-1), prev = k.at(-2) || last;
  const w20 = k.slice(-20), w3 = k.slice(-3), w5 = k.slice(-6, -1);
  const hi20 = Math.max(...w20.map((x) => x.h));
  const lo20 = Math.min(...w20.map((x) => x.l));
  const ma5 = ma(k, 5), ma10 = ma(k, 10), ma20 = ma(k, 20);
  const chg5 = k.length >= 6 ? pct(last.c, k.at(-6).c) : null;
  const vol5 = w5.length ? w5.reduce((a, x) => a + x.v, 0) / w5.length : 0;
  const vr = last.v && vol5 ? last.v / vol5 : null;
  const hi5 = w5.length ? Math.max(...w5.map((x) => x.h)) : last.h;
  const lo5 = w5.length ? Math.min(...w5.map((x) => x.l)) : last.l;
  return {
    last, prev, ma5, ma10, ma20, hi20, lo20, hi5, lo5, chg5, vr,
    lo3: Math.min(...w3.map((x) => x.l)),
    hi3: Math.max(...w3.map((x) => x.h)),
    fromHi20: pct(last.c, hi20), fromLo20: pct(last.c, lo20),
    aboveMA5: ma5 === null ? null : last.c > ma5,
    aboveMA10: ma10 === null ? null : last.c > ma10,
    maAligned: ma5 !== null && ma10 !== null ? ma5 >= ma10 : null,
  };
}

// V 形判定：四条右侧证据（站上 5 日线 / 收复前一日 / 放量 / 突破前 5 日高），命中 ≥3 = V 右启动；
// 创 3 日新低且收在 5 日线下方 = V 左探底未确认（禁止接飞刀）。
function shape(k, opts = {}) {
  const s = stats(k);                       // 结构统计（MA/前高前低）一律基于已完成日线，不用盘中价污染
  const rtC = opts.rt && opts.rt.c ? +opts.rt.c : null;
  const price = rtC || s.last.c;            // 判定用价：盘中=现价，收盘后=当日收盘
  const rtLow = opts.rt && opts.rt.l ? +opts.rt.l : (rtC ? price : s.last.l);
  const vr = opts.vr !== undefined && opts.vr !== null && !Number.isNaN(+opts.vr) ? +opts.vr : (rtC ? null : s.vr);
  const fromHi = pct(price, s.hi20);
  const items = [
    ['站上 5 日线', s.ma5 !== null ? price > s.ma5 : false, `价${price.toFixed(3)} / MA5 ${s.ma5 === null ? '-' : s.ma5.toFixed(3)}`],
    ['收复前一日', price > s.last.c, `价${price.toFixed(3)} / 昨收${s.last.c.toFixed(3)}`],
    ['放量', vr !== null && vr >= 1.2, vr !== null ? `量能比 ${vr.toFixed(2)}` : '当日量能未取到（该条不计入，须人工补量比）'],
    ['突破前 5 日高', price >= s.hi5, `价${price.toFixed(3)} / 前5日高 ${s.hi5.toFixed(3)}`],
  ];
  const pass = items.filter((x) => x[1]).length;
  const freshLow = rtLow <= Math.min(s.lo5, s.last.l) * 1.001 && s.ma5 !== null && price < s.ma5;
  const pullback = !freshLow && s.ma10 !== null && price >= s.ma10 && fromHi > -8 && price < s.hi5;
  let verdict, cls;
  if (freshLow) { verdict = 'V左·探底未确认（下跌未止，不是低吸点）'; cls = 'left'; }
  else if (pass >= 3) { verdict = 'V右·启动确认（右侧证据成立）'; cls = 'right'; }
  else if (pullback) { verdict = `回踩确认（低吸档：守住 MA10、未创 3 日新低、未破前 5 日高、距 20 日高 ${fromHi.toFixed(1)}%）`; cls = 'pullback'; }
  else { verdict = `V中·未确认（${pass}/4 条右侧证据）`; cls = 'mid'; }
  return { items, pass, verdict, s, cls, price, fromHi, vr, rt: !!rtC };
}

module.exports = { fetchKline, fetchKlineSync, stats, shape, ma, pct };

if (require.main === module) {
  const argv = process.argv.slice(2);
  const code = (argv.find((a) => /^[a-z]{2}\d{6}$/i.test(a)) || '').toLowerCase();
  const n = +(argv[argv.indexOf('--n') + 1] || 30);
  if (!code) { console.error('用法: node kline.js sh900001 [--n 30]'); process.exit(2); }
  (async () => {
    const k = await fetchKline(code, Math.max(n, 30));
    const s = stats(k), sh = shape(k);
    console.log(`=== ${code} 近 ${n} 交易日 ===`);
    k.slice(-n).forEach((x) => console.log(`${x.d}  开${x.o.toFixed(3)} 高${x.h.toFixed(3)} 低${x.l.toFixed(3)} 收${x.c.toFixed(3)} 量${(x.v / 10000).toFixed(0)}万`));
    console.log(`\nMA5 ${s.ma5}  MA10 ${s.ma10}  MA20 ${s.ma20}`);
    console.log(`20日高 ${s.hi20.toFixed(3)}（距 ${s.fromHi20.toFixed(1)}%）  20日低 ${s.lo20.toFixed(3)}（距 +${s.fromLo20.toFixed(1)}%）`);
    console.log(`5日涨幅 ${s.chg5 === null ? '-' : s.chg5.toFixed(2) + '%'}  量能比 ${s.vr === null ? '-' : s.vr.toFixed(2)}`);
    console.log(`\n形态判定（基准：最后完成日线 ${s.last.d}）:${sh.verdict}`);
    sh.items.forEach(([n2, ok, ev]) => console.log(`  ${ok ? '✔' : '✘'} ${n2}（${ev}）`));
  })().catch((e) => { console.error('拉取失败:', e.message); process.exit(1); });
}