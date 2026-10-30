#!/usr/bin/env node
/**
 * runtime-doctor.js — Phase 0 运行时体检（只读诊断，不修改任何文件）
 *
 * 检查项（REBUILD-SPEC.md §13 Phase 0「运行止血」验收面）：
 *  1. node 绝对路径：command -v node 必须是 / 开头的绝对路径；
 *  2. cron 裸 node：crontab 里不允许出现裸 `node`（必须绝对路径）；
 *  3. hub/prox/trend 日志启动失败：日志中存在启动失败特征即 FAIL；
 *  4. holdings/portfolio/watch 数量冲突：holdings.conf 与 portfolio.md 持仓口径不一致，
 *     或 watch.conf 现役行覆盖已清仓票 → FAIL；
 *  5. 重复账户快照：account.jsonl 同一日期同数值 ACCT 行重复 → FAIL；
 *  6. MA 危险 writer：timing-update.sh 若仍向 watch.conf 写主动买卖 watch 线 → FAIL。
 *  7. 覆盖体检：池行↔watch 线缺线/僵尸线/过期线/主题载体无人盯/池有行但池块空 → FAIL。
 *
 * 用法：node runtime-doctor.js [--sg-home <目录>] [--crontab <crontab文本文件>]
 *   --crontab 缺省时读 `crontab -l`（读不到视为无 cron，PASS 并说明）。
 *   退出码：0=全部通过；2=存在 FAIL 项。
 */
'use strict';

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const args = process.argv.slice(2);
const valueOf = (n) => { const i = args.indexOf(n); return i >= 0 ? args[i + 1] : undefined; };
const SG_HOME = valueOf('--sg-home');
const CRONTAB_FILE = valueOf('--crontab');

const results = [];
const fail = (id, msg) => results.push({ id, ok: false, msg });
const pass = (id, msg) => results.push({ id, ok: true, msg });

// ---------- 1. node 绝对路径 ----------
try {
  const p = execSync('command -v node', { shell: '/bin/bash', encoding: 'utf8' }).trim();
  if (p.startsWith('/')) pass('node-path', `node 绝对路径 OK: ${p}`);
  else fail('node-path', `node 不是绝对路径: ${p}`);
} catch (e) {
  fail('node-path', '找不到 node（cron 里写裸 node 会静默失败）');
}

// ---------- 2. cron 裸 node ----------
let cronText = '';
if (CRONTAB_FILE) {
  try { cronText = fs.readFileSync(CRONTAB_FILE, 'utf8'); }
  catch (e) { fail('cron-bare-node', `读 crontab 文件失败: ${e.message}`); }
} else {
  try { cronText = execSync('crontab -l 2>/dev/null', { shell: '/bin/bash', encoding: 'utf8' }); }
  catch (e) { pass('cron-bare-node', '无 crontab（或读取失败），跳过'); }
}
if (cronText) {
  // P0-4a：裸 node 按命令全文匹配（覆盖 flock/wrap/&& 前缀形式，行首裸 node 也命中）
  const bare = cronText.split('\n').filter((L) => {
    const t = L.trim();
    if (!t || t.startsWith('#')) return false;
    const m = t.match(/^(\S+\s+){5}(.*)$/);
    if (!m) return false;
    const cmd = m[2];
    return /(^|[;&|\s])node(\s|$)/.test(cmd);
  });
  if (bare.length > 0) fail('cron-bare-node', `发现 ${bare.length} 行裸 node cron：${bare[0].trim().slice(0, 80)}`);
  else pass('cron-bare-node', 'cron 无裸 node');

  // P0-4b：只校验【实际命令 token】中以 /bin/node 结尾的绝对可执行文件是否存在；
  // 不匹配 PATH=${HOME}/.nvm/versions/node/v20…/bin 之类的目录变量（那是 PATH 赋值，不是可执行文件）
  const nodePaths = [...new Set(cronText.split('\n').flatMap((L) => {
    const t = L.trim();
    if (!t || t.startsWith('#')) return [];
    const m = t.match(/^(\S+\s+){5}(.*)$/);
    if (!m) return [];
    const cmd = m[2];
    // 按 token 切分；KEY=VALUE 环境赋值（如 PATH=/…）不算命令 token，除非值本身是 /bin/node 结尾路径
    return cmd.split(/\s+/).filter((tok) => tok.startsWith('/') && /\/bin\/node$/.test(tok));
  }))];
  const missing = nodePaths.filter((p) => !fs.existsSync(p));
  if (missing.length > 0) fail('cron-node-path', `cron 中 node 绝对路径不存在：${missing.join(', ')}`);
  else if (nodePaths.length > 0) pass('cron-node-path', `cron 中 ${nodePaths.length} 个 node 绝对路径均存在`);
  else pass('cron-node-path', 'cron 无 node 绝对路径命令 token，跳过');
}

// ---------- 3. hub/prox/trend 日志启动失败 ----------
if (!SG_HOME) {
  fail('sg-home', '缺少 --sg-home，无法做文件类检查');
} else if (!fs.existsSync(SG_HOME)) {
  fail('sg-home', `--sg-home 目录不存在: ${SG_HOME}`);
} else {
  const logsRoots = [SG_HOME, path.join(SG_HOME, 'logs')];
  const bootFail = /(启动失败|EADDRINUSE|Cannot find module|FATAL|listen EACCES|failed to start)/i;
  let checked = 0; let bad = [];
  for (const root of logsRoots) {
    if (!fs.existsSync(root)) continue;
    for (const name of ['hub.log', 'prox.log', 'trend.log']) {
      const f = path.join(root, name);
      if (!fs.existsSync(f)) continue;
      checked++;
      try {
        const txt = fs.readFileSync(f, 'utf8');
        if (bootFail.test(txt)) bad.push(`${name}: ${txt.split('\n').find((l) => bootFail.test(l)).trim().slice(0, 80)}`);
      } catch (e) { /* 读失败不判死 */ }
    }
    break; // logs/ 优先，命中即不再扫 SG_HOME 根
  }
  if (bad.length > 0) fail('log-boot', bad.join('；'));
  else if (checked === 0) pass('log-boot', 'hub/prox/trend 日志不存在（未部署或未启用），跳过');
  else pass('log-boot', `已检查 ${checked} 个日志，无启动失败特征`);
}

// ---------- 3.5 警报线同源自检（2026-10-29 立：check-sync.sh 此前无任何自动调用方，
// 靠人记得手动跑 = 又一根人桥。块内线核 pool.md、人工线核 portfolio.md，漂移即报 FAIL） ----------
{
  try {
    const out = execSync('bash ' + path.join(__dirname, 'check-sync.sh'), {
      shell: '/bin/bash', encoding: 'utf8', env: { ...process.env, SG_HOME: SG_HOME },
      stdio: ['ignore', 'pipe', 'pipe']
    }).trim();
    pass('watch-sync', out.split('\n').pop().slice(0, 170));
  } catch (e) {
    const txt = ((e.stdout || '') + (e.stderr || '')).trim().split('\n').filter(Boolean).slice(-2).join(' / ');
    fail('watch-sync', '警报线与档案不同源：' + (txt || e.message).slice(0, 220));
  }
}

// ---------- 4. holdings / portfolio / watch 数量冲突 ----------
if (SG_HOME && fs.existsSync(SG_HOME)) {
  const holdF = path.join(SG_HOME, 'holdings.conf');
  const pfF = path.join(SG_HOME, 'portfolio.md');
  const wcF = path.join(SG_HOME, 'watch.conf');

  const holdings = {};
  if (fs.existsSync(holdF)) {
    for (const L of fs.readFileSync(holdF, 'utf8').split('\n')) {
      const t = L.trim();
      // P0-3：跳过已停用行（PHASE0 标记 / HTML 注释），过期份数不得作为现行事实参与对比
      if (!t || t.startsWith('#') || t.startsWith('<!--') || /\[\s*PHASE0/.test(t)) continue;
      const m = t.match(/^([a-z]{2}[0-9]{6})\s*=\s*([\d,]+)/i);
      if (m) holdings[m[1].toLowerCase()] = +m[2].replace(/,/g, '');
    }
  }

  // 从 portfolio.md「监控代码表」提取持仓口径（份/股均认）
  // P0-3：跳过 HTML 注释 / PHASE0 停用行；P1-2：份/股均认
  const pfHold = {};
  const pfText = fs.existsSync(pfF) ? fs.readFileSync(pfF, 'utf8') : '';
  const pfRows = pfText.split('\n').filter((l) => {
    const t = l.trim();
    return /A股持仓/.test(t) && !t.startsWith('#') && !t.startsWith('<!--') && !/\[\s*PHASE0/.test(t);
  });
  if (pfRows.length > 0) {
    for (const row of pfRows) {
      const re = /(sh|sz|bj)(\d{6})（([^）]*)）/g;
      let m;
      while ((m = re.exec(row)) !== null) {
        const code = (m[1] + m[2]).toLowerCase();
        const num = m[3].match(/([\d,]+)\s*(?:份|股)/);
        if (num) pfHold[code] = +num[1].replace(/,/g, '');
      }
    }
  } else {
    // P0-3：持仓行全部被 Phase 0 停用。2026-10-29 起持仓真相=state → holdings.conf 渲染，
    // portfolio 持仓表不再是真相源 → 只要 holdings.conf 带机器渲染头就按口径迁移处理（PASS）。
    const holdTxt = fs.existsSync(holdF) ? fs.readFileSync(holdF, 'utf8').slice(0, 300) : '';
    if (/机器生成：state/.test(holdTxt)) {
      pass('holdings-conflict', 'portfolio 持仓表已停用；持仓真相=state 渲染的 holdings.conf（口径迁移完成）');
    } else {
      fail('holdings-conflict', 'portfolio.md A股持仓行已被 Phase 0 停用且 holdings.conf 非机器渲染：请按最近实报重写持仓');
    }
  }

  // watch.conf 现役行（非注释、非 PHASE0 停用行）覆盖的代码
  const wcActive = new Set();
  if (fs.existsSync(wcF)) {
    for (const L of fs.readFileSync(wcF, 'utf8').split('\n')) {
      const t = L.trim();
      if (!t || t.startsWith('#') || t.startsWith('<!--') || !t.startsWith('watch|') || /\[\s*PHASE0/.test(t)) continue;
      wcActive.add((t.split('|')[1] || '').trim().toLowerCase());
    }
  }

  const conflicts = [];
  for (const [c, n] of Object.entries(holdings)) {
    if (!(c in pfHold)) conflicts.push(`${c} 在 holdings.conf=${n} 但 portfolio.md 持仓表未登记`);
    else if (pfHold[c] !== n) conflicts.push(`${c} holdings=${n} vs portfolio=${pfHold[c]} 不一致`);
  }
  for (const [c, n] of Object.entries(pfHold)) {
    if (!(c in holdings)) conflicts.push(`${c} portfolio=${n} 但 holdings.conf 缺失`);
  }
  if (conflicts.length > 0) fail('holdings-conflict', conflicts.join('；'));
  else pass('holdings-conflict', `holdings(${Object.keys(holdings).length}) 与 portfolio(${Object.keys(pfHold).length}) 口径一致`);

  // watch 数量冲突：holdings 为零/不存在的票不应有现役 watch 行（已清仓票残留）
  // 判定基准：portfolio.md 中「已清仓」节的票 + watch 现役票必须 ⊆ holdings 票 ∪ 观察池白名单
  const cleared = new Set();
  let curSec = null;
  for (const L of pfText.split('\n')) {
    const h = L.match(/^##\s+(.*)$/);
    if (h) { curSec = h[1]; continue; }
    if (curSec && /已清仓/.test(curSec)) {
      const m2 = L.match(/(sh|sz|bj)(\d{6})/i);
      if (m2) cleared.add((m2[1] + m2[2]).toLowerCase());
    }
  }
  const staleWatch = [...wcActive].filter((c) => cleared.has(c) && !(c in holdings));
  if (staleWatch.length > 0) fail('watch-conflict', `已清仓票仍有现役 watch 线: ${staleWatch.join(',')}`);
  else pass('watch-conflict', 'watch 现役行无已清仓票残留');
}

// ---------- 5. 重复账户快照 ----------
if (SG_HOME && fs.existsSync(path.join(SG_HOME, 'account.jsonl'))) {
  const seen = new Map();
  let dup = 0;
  for (const L of fs.readFileSync(path.join(SG_HOME, 'account.jsonl'), 'utf8').split('\n')) {
    const t = L.trim();
    if (!t.startsWith('ACCT|')) continue;
    const f = t.split('|');
    const key = `${f[1]}|${f[2]}|${f[3]}|${f[4]}`; // 日期|持仓市值|现金|总资产
    seen.set(key, (seen.get(key) || 0) + 1);
  }
  for (const [k, n] of seen) if (n > 1) { dup += n - 1; }
  if (dup > 0) fail('dup-snapshot', `account.jsonl 有 ${dup} 条重复 ACCT 快照（同日期同数值）`);
  else pass('dup-snapshot', '无重复 ACCT 快照');
} else {
  pass('dup-snapshot', 'account.jsonl 不存在，跳过');
}

// ---------- 6. MA 危险 writer ----------
const scriptSelf = path.resolve(__filename, '..', 'timing-update.sh');
const candidates = [scriptSelf];
let tuText = null;
for (const f of candidates) {
  if (fs.existsSync(f)) { tuText = fs.readFileSync(f, 'utf8'); break; }
}
if (tuText === null) {
  pass('ma-writer', '未找到 timing-update.sh，跳过');
} else {
  // 危险特征：向 watch.conf 追加/写入 watch| 主动买卖线（旧版行为）
  const dangerous = /watch\|\$\{?[Cc]ode|watch\|.*MA20|conf \+= .*watch\||fs\.writeFileSync\(wc/.test(tuText)
    || /watch\|\$\{code\}/.test(tuText)
    || /watch\|/i.test(tuText.replace(/^#.*$/gm, '').replace(/PAPER_TIMING/g, ''));
  if (dangerous) fail('ma-writer', 'timing-update.sh 仍疑似向 watch.conf 写主动买卖 watch 线（危险 writer 未下线）');
  else pass('ma-writer', 'timing-update.sh 已 paper-only，不写主动买卖 watch 线');
}

// ---------- 汇总 ----------
console.log('[runtime-doctor] Phase 0 体检结果：');
// ---------- 7. 覆盖体检（池行↔watch 线↔主题载体：盘前必须知道谁没人在盯） ----------
try {
  const { audit } = require('./coverage-audit.js');
  const a = audit(SG_HOME || path.join(process.env.HOME || '/root', '.stock-guardian'));
  if (!a.fails.length) pass('coverage', `覆盖体检全通过（池 ${a.poolActive} 行 / 在册 ${a.watchLines} 线 / 监控 ${a.monitorCodes} 只票）`);
  else fail('coverage', '覆盖体检 FAIL：' + a.fails.map((i) => i.id + ' ' + i.msg).join(' ｜ ').slice(0, 220));
} catch (e) {
  fail('coverage', '覆盖体检无法执行：' + e.message);
}

for (const r of results) console.log(`  ${r.ok ? 'PASS' : 'FAIL'}  ${r.id}  ${r.msg}`);
const bad = results.filter((r) => !r.ok);
console.log(`合计：${results.length} 项，FAIL ${bad.length} 项`);
process.exit(bad.length > 0 ? 2 : 0);
