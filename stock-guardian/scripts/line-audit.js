#!/usr/bin/env node
// line-audit.js —— 池线偏离自检（2026-10-29 立）
// 由来：某银行 ETF 池票的低吸线 0.850 从 10-26 挂到 10-29 无人复核；10-27 现价 0.866 未触发、10-28 回踩到 0.866 一线仍未触发、
// 10-29 直接破 52 周高 0.878 走成 V 右启动。用户 10-29 说"我觉得昨天低点是适合低吸的……这种重要时机就是我应该能收到通知买入的时机"。
// 结论：低吸线不能拍"更便宜的价"，要挂在"回踩确认位"（近期实际低点 ±1.5% 内）；偏离就是结构性踏空。
// 本脚本每天对池内在池行做偏离体检，输出"过深/合理/已越线未同步/作废线已破"。
// 退出码：3=有越线未同步或作废线已破（P0）2=有待复核线 0=全合理
'use strict';
const fs = require('fs');
const path = require('path');
const SG = process.env.SG_HOME || path.join(require('os').homedir(), '.stock-guardian');
const { fetchKline, stats, shape: kShape } = require(path.join(__dirname, 'kline.js'));
const { execFileSync } = require('child_process');
// 2026-10-29：用户要的是"重要买点能被发现并通知我"。形态档（V右启动/回踩确认）与池线 P0 必须主动推，
// 不能只写在 pool-sync.log 里等人看。当日同码同类只推一次（去重键 = 代码|类|日期）。
const NOTIFY = process.argv.includes('--notify');
// 2026-10-29：用户要"通知要像推荐卡一样清晰 + 加粗"。加 --preview 打印将要推送的正文原文
// （不占当日去重键、不发送），保证"我在群里看到的"与"我在终端看到的"是同一段文字。
const PREVIEW = process.argv.includes('--preview');
const STF = path.join(SG, 'line-audit.state.json');
const sent = (() => { try { return JSON.parse(fs.readFileSync(STF, 'utf8')); } catch { return {}; } })();
const today = new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' });
// 调试参数（与 coverage-audit --date 对齐）：--at 'YYYY-MM-DDTHH:MM' 把"当下"钉死在指定时刻，
// 用于测试推送窗与跨日翻转，不影响线上 cron（不带参数即用真实时间）
const AT = (() => { const i = process.argv.indexOf('--at'); return i >= 0 ? new Date(process.argv[i + 1]) : new Date(); })();
const push = [];
// 现场跑买入闸门，把结论写进通知卡（用户要的是"通知里就带闸门"，不是让他自己再跑一遍）
function gateOf(code, px, stop) {
  const { execFileSync } = require('child_process');
  let out = '';
  try {
    out = execFileSync('node', [path.join(__dirname, 'prebuy-check.js'), '--code', code, '--price', String(px), '--stop', String(stop)], { encoding: 'utf8', timeout: 90000, stdio: ['ignore', 'pipe', 'pipe'] });
  } catch (e) { out = String(e.stdout || '') + String(e.stderr || ''); }
  const v = (out.match(/判定：\s*(PASS|BLOCK|WARN)/) || [])[1] || '未取得';
  const sd = (out.match(/止损距离：([\d.]+)%/) || [])[1];
  return { v, sd };
}

const { timingCard, invalidCard } = require(path.join(__dirname, 'notify-cards.js'));
// 2026-10-30：零点 bug 修复（时钟错位母题「跨轮去重作用域」家族第 2 例）。时机卡是"每日配额"类推送，
// 必须落在交易时段窗内、且行情数据必须是今天的——两个守卫缺一不可：只挡时间不挡旧数据，
// 假日/凌晨的 tick 仍会拿昨天收盘价当"新一天首次时机"；只挡数据不挡时间，窗口判断散落各处必再犯。
// 守卫挡下 = 静默跳过且不占当日去重键（emit 里 return 在写 sent[key] 之前）。
const { blockedReason } = require(path.join(__dirname, 'push-window.js'));
// 行情数据新鲜度：quote-public 的 time 列=行情日期（watch.sh 已用它判新鲜度）。undefined=没取到实时行情（盘中源故障），
// 此时形态判级退化用日线（日线尾根=上一交易日），旧数据嫌疑仍在——不推，把配额留给数据修好的下一轮。
let quoteDay = undefined;

function emit(kind, code, text) {
  // 只有真正开启推送时才占用当日去重键：否则白天手动跑一次（不带 --notify）就会把当日首次正式推送吞掉
  if (PREVIEW && !NOTIFY) { push.push(text); return; }
  if (!NOTIFY) return;
  const key = `${code}|${kind}|${today}`;
  if (sent[key]) return;
  // 推送窗守卫：窗外（夜间/周末/盘中窗外）不推不占键；数据新鲜度：行情日期≠今天不推不占键
  const w = blockedReason(AT);
  if (w) { console.log(`静默：${code} ${kind} ${w}——不推送、不占当日配额`); return; }
  if (quoteDay !== undefined && quoteDay !== today) { console.log(`静默：${code} ${kind} 行情日期 ${quoteDay} ≠ 今日 ${today}（旧数据复读，不推送、不占当日配额）`); return; }
  sent[key] = new Date().toISOString();
  push.push(text);
}

(async () => {
  const f = path.join(SG, 'pool.md');
  if (!fs.existsSync(f)) { console.log('无 pool.md'); process.exit(0); }
  const rows = fs.readFileSync(f, 'utf8').split('\n')
    .filter((l) => l.startsWith('POOL|')).map((l) => {
      const c = l.split('|');
      return { id: c[1], date: c[2], code: c[3], name: c[4], kind: c[5], trigger: +c[6], invalid: +c[7], expire: c[8], status: c[9] };
    }).filter((r) => /active|triggered/.test(r.status || ''));
  if (!rows.length) { console.log('池内无在池行（active/triggered）'); process.exit(0); }

  let p0 = 0, warn = 0; const lines = [];
  // 当日实时覆盖：日线源盘中不含当日 bar（实测 sina 尾根=上一交易日），只用日线会漏判"今天刚越线"
  const rt = {};
  try {
    const { execFileSync } = require('child_process');
    const raw = execFileSync('bash', [path.join(__dirname, 'quote-public.sh'), 'quote', rows.map((r) => r.code).join(',')], { encoding: 'utf8', timeout: 30000 });
    const t = raw.split('\n').map((l) => l.trim()).filter((l) => l.startsWith('|'));
    const head = t[0].split('|').map((x) => x.trim());
    t.slice(1).forEach((line) => {
      const v = line.split('|').map((x) => x.trim());
      const g = (k2) => v[head.indexOf(k2)];
      if (g('code')) rt[g('code')] = { last: +g('price'), high: +g('high'), low: +g('low'), chg: +g('change_percent'), vr: +g('volume_ratio') };
      // 行情日期（取首个非空 time；time 列语义=行情日期，见 quote-public.sh 头注释）
      const t2 = g('time');
      if (t2 && quoteDay === undefined) quoteDay = t2;
    });
  } catch { /* 取不到就用日线 */ }
  for (const r of rows) {
    const k = await fetchKline(r.code, 40);
    if (!k || k.length < 11) { lines.push(`SKIP ${r.code} 日线不足`); continue; }
    const q2 = rt[r.code];
    const s = stats(k);
    const sh = kShape(k, q2 ? { rt: { c: q2.last, h: q2.high, l: q2.low }, vr: q2.vr } : {});
    const shapeNote = `形态=${sh.verdict}（距20日高 ${sh.fromHi.toFixed(1)}%）`;
    const isDip = /低吸|回调|回踩/.test(r.kind || '');
    const isBreak = /突破/.test(r.kind || '');
    const pxNow = q2 ? q2.last : s.last.c;
    // 通用检查：任何类型的在池行，现价跌破作废线都必须报 P0（原实现只在低吸分支里查，某事件驱动行因此漏判）
    if (pxNow <= r.invalid) { p0++; lines.push(`P0 ${r.code} ${r.name}｜现价 ${pxNow.toFixed(3)} 已破作废线 ${r.invalid}（${r.kind}），池状态仍是 ${r.status} → 立即出池核销`); emit('P0', r.code, invalidCard(r, pxNow.toFixed(3), '池线异常')); continue; }
    if (isDip) {
      const gap = (s.lo3 / r.trigger - 1) * 100; // 近 3 日最低价比触发价高多少
      const px = q2 ? q2.last : s.last.c;
      if (px <= r.invalid) { p0++; lines.push(`P0 ${r.code} ${r.name}｜现价 ${px.toFixed(3)} 已破作废线 ${r.invalid}，池状态仍是 ${r.status}`); }
      else if (r.status === 'triggered' && px >= r.trigger * 1.03) {
        // 2026-10-29 核心缺口：低吸线触发一次后不会二次提醒。某银行 ETF 10-26 触发 0.850 → 10-28 回踩 0.864（+1.6%）不再报
        // → 用户说的"昨天低点适合低吸却零通知"就是这个机制缺的。已触发且结构上移的线必须按新结构重挂。
        warn++; lines.push(`复核 ${r.code} ${r.name}｜低吸线 ${r.trigger} 已触发过且现价 ${px.toFixed(3)}（+${((px / r.trigger - 1) * 100).toFixed(2)}%）→ 触发线不会二次提醒，需按新结构重挂回踩位；${shapeNote}`);
      } else if (gap > 1.5) { warn++; lines.push(`复核 ${r.code} ${r.name}｜低吸线 ${r.trigger} 偏深：近 3 日最低 ${s.lo3.toFixed(3)} 高出线 ${gap.toFixed(2)}%（挂线以来价格根本没到，结构性踏空）→ 建议改挂回踩确认位（近 3 日低 ±1%）；${shapeNote}`); }
      else lines.push(`OK ${r.code} ${r.name}｜低吸线 ${r.trigger}｜近 3 日低 ${s.lo3.toFixed(3)}（偏离 ${gap.toFixed(2)}%）｜${shapeNote}`);
    } else if (isBreak) {
      // 2026-10-29：只用"近 3 日高"会漏判今天刚越过的线（日线源盘中不含当日 bar）——现价也算穿越
      const pxR = q2 ? q2.last : s.last.c;
      const cross = s.hi3 >= r.trigger || pxR >= r.trigger;
      if (cross && r.status === 'active') { p0++; lines.push(`P0 ${r.code} ${r.name}｜突破线 ${r.trigger} 已被穿越（近 3 日高 ${s.hi3.toFixed(3)}），池状态仍是 active → 同步滞后`); }
      else if (!cross && s.last.c >= r.trigger) { p0++; lines.push(`P0 ${r.code} ${r.name}｜现价 ${s.last.c.toFixed(3)} ≥ 突破线 ${r.trigger}，未标记 triggered`); }
      else lines.push(`OK ${r.code} ${r.name}｜突破线 ${r.trigger}｜近 3 日高 ${s.hi3.toFixed(3)}｜现价 ${(q2 ? q2.last : s.last.c).toFixed(3)}｜${shapeNote}`);
    } else lines.push(`OK ${r.code} ${r.name}｜${r.kind}｜线 ${r.trigger}/${r.invalid}｜现价 ${(q2 ? q2.last : s.last.c).toFixed(3)}｜${shapeNote}`);
    // 重要买点时机：V右启动确认 / 回踩确认 档 → 主动提醒（含动手前提，避免被当成买入指令）
    if (sh.cls === 'right' || sh.cls === 'pullback') {
      const pxT = (q2 ? q2.last : s.last.c).toFixed(3);
      emit(sh.cls, r.code, timingCard(r, sh, pxT, gateOf(r.code, pxT, r.invalid)));
    }
  }
  if (PREVIEW && !NOTIFY) {
    console.log('\n=== 将要推送的正文原文（--preview，未发送、未占用去重键）===');
    console.log(push.join('\n\n') || '（无待推内容）');
  }
  if (NOTIFY && push.length) {
    try {
      // 2026-10-29：必须用 --title/--tag/--body 具名参数。第一版传了位置参数 → 推送脚本按未知参数丢弃，
      // 群里收到的是空正文「通知」（push-log 显示 len=0）。又一次"日志说成功、内容为空"，当场修掉。
      execFileSync('bash', [path.join(__dirname, 'notify-webhook.sh'), '--title', '池票时机播报', '--tag', '操作思路', '--body', push.join('\n\n')], { encoding: 'utf8', timeout: 20000 });
      console.log(`\n已推送 ${push.length} 条重要时机`);
    } catch (e) { console.log('\n推送失败（记住：日志说成功不等于送达）:', e.message.slice(0, 120)); }
  }
  try { fs.writeFileSync(STF, JSON.stringify(sent, null, 0)); } catch { /* 状态写不了不算致命，但会重复推 */ }
  console.log('=== 池线偏离体检 ===');
  lines.forEach((l) => console.log(l));
  console.log(`\n汇总：待复核 ${warn}｜P0 ${p0}｜共 ${rows.length} 行`);
  process.exit(p0 ? 3 : warn ? 2 : 0);
})().catch((e) => { console.error('体检失败:', e.message); process.exit(1); });