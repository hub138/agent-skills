#!/usr/bin/env node
'use strict';
/**
 * coverage-audit.js — 覆盖体检（只读，2026-10-29 立）
 *
 * 立此脚本的由来（当天实测暴露，不是设想）：
 *   09:30:02 心跳 `rules=1 codes=1` —— 开盘那一刻全市场只有 1 条线在盯；
 *   神华/卫星当天有 ATR 级机会摆在盘面上，却连"待扫描"都算不上（15:29 收盘后才登记）；
 *   全天 rules 在 1→5→6→8→12→14→15→8 之间跳，线的增删无痕、无理由记录。
 *   结论：闸门再准也只能覆盖"已经在册的线"——**覆盖本身不能是人肉手工**，必须有机器审计。
 *
 * 检查项（全部只读）：
 *   A1 池行 → watch 线齐全：每行 active/triggered 的触发线＋作废线都必须在 watch.conf 池块里；
 *   A2 反向漂移：池块里有、但池里已经没有的线（僵尸线）；
 *   A3 过期线：`至YYYY-MM-DD` 已过期却仍现役；
 *   A4 主题欠账：themes.md 里 active 主题的候选载体，没有一个在监控集合（池 ∪ watch）；
 *   A5 覆盖空白：池里有 active 行，池块却 0 条线（= "开盘只有 1 条线"的那种形态）。
 *
 * 用法：node coverage-audit.js [--sg-home <目录>] [--date YYYY-MM-DD] [--json]
 *   退出码：0=全通过；2=存在 FAIL。runtime-doctor（每天 08:02 cron）会调用它——盘前暴露欠账。
 */
const fs = require('fs');
const path = require('path');

const BEGIN = '# === POOL-AUTO BEGIN（pool-watch-sync 机器维护：勿手改，改池用 pool.sh；块外人工线不受影响）===';
const END = '# === POOL-AUTO END ===';

const args = process.argv.slice(2);
const valueOf = (n) => { const i = args.indexOf(n); return i >= 0 ? args[i + 1] : undefined; };
const SG = valueOf('--sg-home') || process.env.SG_HOME || path.join(process.env.HOME || '/root', '.stock-guardian');
const AS_JSON = args.includes('--json');
// 时区必须用 Asia/Shanghai：toISOString() 是 UTC，08:00 前会把"今天"算成昨天，
// 于是过期线判断与当日去重全错位（与 state 的 nowStamp 同族 bug）。
const today = valueOf('--date') ||
  new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
// 2026-10-29 补闭环：体检 FAIL 只写日志 = 没人看。--notify 时按"日期|FAIL项"去重推一次企微。
const NOTIFY = args.includes('--notify');
const NSTATE = path.join(SG, '.coverage-notify.json');

const eq = (a, b) => Math.abs(Number(a) - Number(b)) < 1e-9;
const readLines = (f) => (fs.existsSync(f) ? fs.readFileSync(f, 'utf8').split('\n') : null);

function audit(sgHome, opts = {}) {
  const sgh = sgHome || SG;
  const day = opts.today || today;
  const items = [];
  const put = (id, ok, msg) => { items.push({ id, ok, msg }); return ok; };

  // ---- 读池（active/triggered 且未过期） ----
  const poolLines = readLines(path.join(sgh, 'pool.md'));
  const pool = [];
  if (poolLines) {
    for (const l of poolLines) {
      if (!l.startsWith('POOL|')) continue;
      const f = l.split('|');
      if (!(f[9] === 'active' || f[9] === 'triggered')) continue;
      if (f[8] && f[8] < day) continue;                       // 已过期，不参与覆盖要求
      if (!f[3] || !f[6]) continue;
      pool.push({ id: f[1], code: f[3], name: f[4], dir: f[5] || '', trig: f[6], void: f[7] || '', exp: f[8] || '' });
    }
  }

  // ---- 读 watch（池块内 / 全部） ----
  const watchText = fs.existsSync(path.join(sgh, 'watch.conf')) ? fs.readFileSync(path.join(sgh, 'watch.conf'), 'utf8') : null;
  const allWatch = [];
  let block = [];
  if (watchText !== null) {
    for (const l of watchText.split('\n')) if (l.startsWith('watch|')) allWatch.push(l);
    const b = watchText.indexOf(BEGIN), e = watchText.indexOf(END);
    if (b >= 0 && e > b) block = watchText.slice(b, e).split('\n').filter((l) => l.startsWith('watch|'));
  }
  const wf = (l) => { const f = l.split('|'); return { code: f[1], cond: f[2], arg: f[3], label: f[4] || '', exp: (f[6] || '').replace(/^至/, '') }; };
  const blockRows = block.map(wf);
  const monitorCodes = new Set([...pool.map((p) => p.code), ...allWatch.map((l) => wf(l).code)]);

  // ---- A1：池行 → 线齐全 ----
  if (!poolLines || !watchText) {
    put('A1', true, '跳过（pool.md 或 watch.conf 不存在——全新安装不判 FAIL）');
    put('A2', true, '跳过（同上）');
  } else {
    const miss = [];
    for (const p of pool) {
      const cond = /突破|追涨/.test(p.dir) ? 'above' : 'below';
      if (!blockRows.some((w) => w.code === p.code && w.cond === cond && eq(w.arg, p.trig))) miss.push(`${p.code} 触发线 ${cond} ${p.trig}`);
      if (p.void && !blockRows.some((w) => w.code === p.code && w.cond === 'below' && eq(w.arg, p.void))) miss.push(`${p.code} 作废线 below ${p.void}`);
    }
    put('A1', miss.length === 0, miss.length
      ? `池行缺线 ${miss.length} 条（池里有票、盘中没人盯）：${miss.join('；')}`
      : `池行→watch 线齐全（${pool.length} 行 / ${blockRows.length} 线）`);

    // ---- A2：反向漂移（僵尸线） ----
    const zombies = blockRows.filter((w) => !pool.some((p) => {
      const cond = /突破|追涨/.test(p.dir) ? 'above' : 'below';
      return p.code === w.code && ((w.cond === cond && eq(w.arg, p.trig)) || (p.void && w.cond === 'below' && eq(w.arg, p.void)));
    })).map((w) => `${w.code} ${w.cond} ${w.arg}`);
    put('A2', zombies.length === 0, zombies.length
      ? `池块里有 ${zombies.length} 条已不在池的线（幽灵线/漂移）：${zombies.join('；')}`
      : '池块无僵尸线（块内线与池行一一对应）');
  }

  // ---- A3：过期线仍现役 ----
  const expired = allWatch.map(wf).filter((w) => w.exp && w.exp < day).map((w) => `${w.code} ${w.arg}（至${w.exp}）`);
  put('A3', expired.length === 0, expired.length
    ? `${expired.length} 条线已过期仍现役：${expired.join('；')}`
    : `无过期僵尸线（在册 ${allWatch.length} 条）`);

  // ---- A4：主题欠账（候选载体是否有人在盯） ----
  const themeLines = readLines(path.join(sgh, 'themes.md'));
  if (!themeLines) put('A4', true, '跳过（themes.md 不存在）');
  else {
    const dead = [];
    let activeThemes = 0;
    for (const l of themeLines) {
      if (!l.startsWith('THEME|')) continue;
      const f = l.split('|');
      if (f[5] !== 'active') continue;
      activeThemes++;
      const cands = (f[7] || '').split(/[,，\s]+/).filter(Boolean);
      if (!cands.length) { dead.push(`${f[1]}（未登记候选载体）`); continue; }
      if (!cands.some((c) => monitorCodes.has(c))) dead.push(`${f[1]}（载体 ${cands.join('/')} 全部无人盯）`);
    }
    put('A4', dead.length === 0, dead.length
      ? `${dead.length} 个活跃主题与监控脱节：${dead.join('；')}`
      : `活跃主题载体均在监控（${activeThemes} 个主题）`);
  }

  // ---- A5：覆盖空白 ----
  put('A5', !(pool.length > 0 && blockRows.length === 0), pool.length > 0 && blockRows.length === 0
    ? `覆盖空白：池内 ${pool.length} 行在册，watch 池块 0 条线（盘中无人在盯——2026-10-29 开盘 rules=1 的形态）`
    : `无覆盖空白（池 ${pool.length} 行 / 监控 ${monitorCodes.size} 只票）`);

  const fails = items.filter((i) => !i.ok);
  return { items, fails, poolActive: pool.length, watchLines: allWatch.length, monitorCodes: monitorCodes.size, sgHome: sgh, date: day };
}

// 当日去重推送：同一个 FAIL 项一天只推一次，避免每 10 分钟刷屏
// 2026-10-30 接入推送窗守卫：欠账属"每日配额"类推送，必须落在 08:30-15:30 交易时段窗内，
// 防止 00:00 日历日翻转后的第一个 tick 拿昨日数据零点推送（与 line-audit 零点 bug 同族，
// 时钟错位母题「跨轮去重作用域」家族）。窗外静默跳过且不写去重状态（不占当日配额）。
function notifyFails(r) {
  if (!r.fails.length) return 0;
  const { blockedReason } = require(path.join(__dirname, 'push-window.js'));
  const w = blockedReason();
  if (w) { console.log(`静默：覆盖体检欠账 ${w}——不推送、不占当日配额（窗内首 tick 补推）`); return 0; }
  let st = {};
  try { st = JSON.parse(fs.readFileSync(NSTATE, 'utf8')); } catch { st = {}; }
  if (st.date !== r.date) st = { date: r.date, sent: {} };
  const fresh = r.fails.filter((i) => !st.sent[i.id]);
  if (!fresh.length) return 0;
  const body = fresh.map((i) => `**${i.id}** ${i.msg}`).join('\n\n');
  try {
    require('child_process').execFileSync('bash',
      [path.join(__dirname, 'notify-webhook.sh'), '--title', '覆盖体检欠账（开盘前必看）', '--tag', '覆盖', '--body',
        `体检日期 ${r.date}｜池 ${r.poolActive} 行 / 在册 ${r.watchLines} 线 / 监控 ${r.monitorCodes} 只票\n\n${body}\n\n（同一项当日只推一次；修池/补线后下一轮体检自动消项）`],
      { encoding: 'utf8', timeout: 20000 });
  } catch (e) {
    console.error('覆盖体检推送失败（不标记为已推，下轮重试）：' + e.message);
    return 0;
  }
  for (const i of fresh) st.sent[i.id] = new Date().toISOString();
  try { fs.writeFileSync(NSTATE, JSON.stringify(st, null, 2)); } catch { /* 状态写不进不影响推送 */ }
  return fresh.length;
}

function main() {
  const r = audit(SG);
  if (AS_JSON) { console.log(JSON.stringify(r, null, 2)); process.exit(r.fails.length ? 2 : 0); }
  console.log(`覆盖体检（${r.date}）｜${r.sgHome}｜池 ${r.poolActive} 行 / 在册 ${r.watchLines} 线 / 监控 ${r.monitorCodes} 只票`);
  for (const i of r.items) console.log(`  ${i.ok ? 'PASS' : 'FAIL'}  ${i.id}  ${i.msg}`);
  if (NOTIFY) { const n = notifyFails(r); console.log(`推送：${n ? '已推 ' + n + ' 项欠账' : '无新增欠账（当日已推过或全通过）'}`); }
  console.log(`合计：${r.items.length} 项，FAIL ${r.fails.length} 项`);
  process.exit(r.fails.length ? 2 : 0);
}

module.exports = { audit, BEGIN, END };
if (require.main === module) main();
