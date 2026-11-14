#!/usr/bin/env node
'use strict';

// state-core.js — MASTER.md 单一当前事实核心（通用，零用户硬编码）
// 设计：MASTER.md 是普通 Markdown；机器真相处是 SG:STATE 标记之间的 jsonl 区块。
// 规则：所有写命令必须带 --expect-revision（CAS）；unknown 合法；AI 建议≠成交。

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const SG_ENV = 'STOCK_GUARDIAN_HOME';
const DEFAULT_SG = path.join(process.env.HOME || '/root', '.stock-guardian');
const LOCK = '.state-core.lock';
const LOCK_MAX_AGE_MS = 10 * 60 * 1000;
const BEGIN = '<!-- SG:STATE:BEGIN -->';
const END = '<!-- SG:STATE:END -->';
const ALLOWED_PREFIXES = ['/tmp', '/data/tmp', path.join(process.env.HOME || '/root', '.stock-guardian')];
const MAX_QTY = 100000000;
const MAX_MONEY = 10000000000;

let SG_HOME = process.env[SG_ENV] || DEFAULT_SG;

function resolveDir(dir) { return path.resolve(dir || ''); }
function nowStamp() {
  // 2026-10-29 修：原实现 new Date().toISOString() 是 UTC，写出的时间戳比本地/
  // 档案时间早 8 小时（resolved_at 02:39 vs 真实 10:39），排障时间线对不上。
  // 与 today() 口径统一走 Asia/Shanghai（机器 TZ 可能是 UTC，不能依赖本地时区）。
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23'
  }).formatToParts(new Date());
  const g = t => parts.find(x => x.type === t).value;
  return `${g('year')}-${g('month')}-${g('day')} ${g('hour')}:${g('minute')}:${g('second')}`;
}
function today() { const p = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date()).reduce((a, i) => ({ ...a, [i.type]: i.value }), {}); return `${p.year}-${p.month}-${p.day}`; }

function assertAllowed(dir) {
  const r = resolveDir(dir);
  for (const p of ALLOWED_PREFIXES) {
    const rp = resolveDir(p);
    if (r === rp || r.startsWith(rp + path.sep)) return;
  }
  throw new Error(`path not allowed: ${dir}`);
}

function masterPath() { return path.join(SG_HOME, 'MASTER.md'); }
function lockPath() { return path.join(SG_HOME, LOCK); }
function viewsPath() { return path.join(SG_HOME, 'views'); }

function acquireLock() {
  fs.mkdirSync(path.dirname(lockPath()), { recursive: true });
  try {
    if (fs.existsSync(lockPath())) {
      const st = fs.statSync(lockPath());
      if (Date.now() - st.mtimeMs > LOCK_MAX_AGE_MS) fs.unlinkSync(lockPath());
    }
    const fd = fs.openSync(lockPath(), 'wx');
    fs.writeSync(fd, `${process.pid} ${nowStamp()}`);
    fs.closeSync(fd);
    return true;
  } catch (e) {
    if (e.code === 'EEXIST') return false;
    throw e;
  }
}
function releaseLock() { try { fs.unlinkSync(lockPath()); } catch (e) {} }
let lockHeld = false;
process.on('exit', () => { if (lockHeld) releaseLock(); });

function withLock(fn) {
  if (!acquireLock()) throw new Error('lock held by another writer');
  lockHeld = true;
  try { return fn(); } finally { releaseLock(); lockHeld = false; }
}

function atomicWrite(file, content) {
  const tmp = `${file}.tmp.${crypto.randomUUID().slice(0, 8)}`;
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(tmp, content);
  fs.renameSync(tmp, file);
}

// ---------- 解析 / 渲染 ----------
function parseMaster(text) {
  const b = text.indexOf(BEGIN);
  const e = text.indexOf(END);
  const before = b >= 0 ? text.slice(0, b) : text;
  const after = e >= 0 ? text.slice(e + END.length) : '';
  const inner = b >= 0 && e > b ? text.slice(b + BEGIN.length, e) : '';
  const records = [];
  for (const line of inner.split('\n')) {
    const t = line.trim();
    if (!t || t.startsWith('```')) continue;
    try { const o = JSON.parse(t); if (o && typeof o === 'object') records.push(o); }
    catch (err) { throw new Error(`invalid jsonl line: ${t.slice(0, 80)}`); }
  }
  return { before, after, records };
}

function defaultHeader() {
  return `# MASTER.md — 单一当前事实源\n\n> 任何 AI 可读写，但必须通过 state-core.js 原子命令；直接手改后运行 \`state-core.js validate\`。\n> unknown 合法；AI 建议永远不等于成交；成交只认用户实报。\n> 标记之间为机器真相，标记外可写人类说明。\n\n`;
}

function renderMaster(state) {
  const body = state.records.map(r => JSON.stringify(r)).join('\n');
  return `${state.before || defaultHeader()}${BEGIN}\n\`\`\`jsonl\n${body}\n\`\`\`\n${END}${state.after || ''}`;
}

function readState() {
  if (!fs.existsSync(masterPath())) throw new Error(`MASTER.md not found at ${masterPath()}; run init`);
  return parseMaster(fs.readFileSync(masterPath(), 'utf8'));
}
function writeState(state) {
  atomicWrite(masterPath(), renderMaster(state));
  // 2026-10-29 立：holdings.conf 是从属视图，由 state 渲染——此前靠人手抄份数，
  // 卖出后 state 置 0 而 holdings.conf 仍留旧份数，两边口径分叉无人发现（人桥=断链）。
  renderHoldings(state);
}

// state → holdings.conf（份数唯一真相在 state；CASH 状态机尚无确认值，沿用现有行不丢）
function renderHoldings(state) {
  const HOLD = path.join(SG_HOME, 'holdings.conf');
  const prev = fs.existsSync(HOLD) ? fs.readFileSync(HOLD, 'utf8') : '';
  const prevCash = (prev.match(/^CASH=(\S+)/m) || [])[1];
  const pos = state.records.filter(r => r.type === 'POSITION' && Number(r.quantity) > 0);
  const acc = state.records.filter(r => r.type === 'ACCOUNT').pop();
  const cash = acc && acc.cash && typeof acc.cash.amount === 'number' ? String(acc.cash.amount) : prevCash;
  const out = [
    '# 机器生成：state → holdings.conf（份数来自 state，勿手改；改仓走 set-position / record-execution 后自动重渲）',
    '# 生成 ' + nowStamp() + '｜持仓 ' + pos.length + ' 只｜state revision ' + revision(state)
      + (cash === undefined ? '｜CASH 未取到：快照会缺现金，请校对账' : ''),
  ];
  for (const r of pos) out.push(r.code + '=' + r.quantity);
  if (cash !== undefined) out.push('CASH=' + cash);
  fs.writeFileSync(HOLD, out.join('\n') + '\n');
  return { positions: pos.length, cash: cash || null };
}

// ---------- 记录访问 ----------
function getRec(state, type, key, val) {
  return state.records.find(r => r.type === type && String(r[key]) === String(val));
}
function revision(state) {
  const m = state.records.find(r => r.type === 'META');
  return m && Number.isInteger(m.revision) ? m.revision : -1;
}
function bump(state, writer) {
  const m = state.records.find(r => r.type === 'META') || {};
  m.type = 'META';
  m.schema_version = 1;
  m.revision = (Number.isInteger(m.revision) ? m.revision : -1) + 1;
  m.updated_at = nowStamp();
  m.last_writer = writer || 'state-core';
  if (!state.records.includes(m)) state.records.unshift(m);
  return m.revision;
}
function upsert(state, rec) {
  const i = state.records.findIndex(r => r.type === rec.type && (
    (rec.type === 'POSITION' && r.code === rec.code) ||
    (rec.type === 'EXECUTION' && r.id === rec.id) ||
    (rec.type === 'CANDIDATE' && r.code === rec.code) ||
    (rec.type === 'DECISION' && r.id === rec.id) ||
    (rec.type === 'STRATEGY' && r.id === rec.id) ||
    (['META', 'ACCOUNT'].includes(rec.type))
  ));
  if (i >= 0) state.records[i] = { ...state.records[i], ...rec };
  else state.records.push(rec);
}

// ---------- 校验 ----------
const VALID_STATUS = ['confirmed', 'estimated', 'unknown'];
const VALID_SOURCE = ['user_report', 'broker_import', 'machine_estimate', 'ai_estimate'];

function checkCode(code) {
  if (!/^(sh|sz|bj)\d{6}$/.test(code)) throw new Error(`invalid code: ${code}`);
  return code.toLowerCase();
}
function checkQty(v, name = 'quantity', allowZero = false) {
  const n = Number(v);
  // allowZero：2026-10-29 立。此前 quantity 禁 0 → 清仓后无法把持仓置零，
  // 已卖出标的会以"幽灵持仓"留在状态里继续被监控/报警。0 = 该标的已清仓。
  const bad = !Number.isSafeInteger(n) || n > MAX_QTY || (allowZero ? n < 0 : n <= 0);
  if (bad) throw new Error(`${name} must be ${allowZero ? 'non-negative' : 'positive'} integer <= ${MAX_QTY}`);
  return n;
}
function checkMoney(v, name = 'money', allowNull = true) {
  if (v === null || v === undefined || v === 'unknown' || v === '') { if (allowNull) return null; throw new Error(`${name} required`); }
  const n = Number(v);
  if (!Number.isFinite(n) || n < 0 || n > MAX_MONEY) throw new Error(`${name} invalid`);
  return n;
}
function checkStatus(v, name = 'status') {
  if (!VALID_STATUS.includes(v)) throw new Error(`${name} must be one of ${VALID_STATUS.join('/')}`);
  return v;
}
function checkSource(v) {
  if (!VALID_SOURCE.includes(v)) throw new Error(`source must be one of ${VALID_SOURCE.join('/')}`);
  return v;
}
function expectRev(args, state) {
  const i = args.indexOf('--expect-revision');
  if (i < 0 || i + 1 >= args.length) throw new Error('--expect-revision N is required for write commands');
  const want = Number(args[i + 1]);
  if (!Number.isInteger(want)) throw new Error('--expect-revision must be integer');
  const cur = revision(state);
  if (cur !== want) throw new Error(`revision mismatch: expected ${want}, current ${cur}`);
}

function validateRecords(state) {
  const errs = [];
  const types = state.records.map(r => r.type);
  for (const t of ['META', 'ACCOUNT']) if (types.filter(x => x === t).length !== 1) errs.push(`${t} must exist exactly once`);
  const pos = state.records.filter(r => r.type === 'POSITION');
  for (const p of pos) {
    try { checkCode(p.code); } catch (e) { errs.push(`POSITION ${p.code}: ${e.message}`); }
    if (!Number.isInteger(p.quantity) || p.quantity < 0) errs.push(`POSITION ${p.code}: quantity invalid`);
    if (!Number.isInteger(p.sellable) || p.sellable < 0 || p.sellable > (p.quantity || 0)) errs.push(`POSITION ${p.code}: sellable invalid`);
  }
  const acc = state.records.find(r => r.type === 'ACCOUNT');
  if (acc && !VALID_STATUS.includes(acc.data_status)) errs.push('ACCOUNT.data_status invalid');
  const dec = state.records.filter(r => r.type === 'DECISION');
  const byCode = new Map();
  for (const d of dec) {
    if (byCode.has(d.code)) errs.push(`DECISION conflict: multiple active decisions for ${d.code}`);
    byCode.set(d.code, d);
  }
  return errs;
}

// ---------- 命令 ----------
function cmdInit(dir) {
  const target = dir || SG_HOME;
  assertAllowed(target);
  SG_HOME = target;
  fs.mkdirSync(target, { recursive: true });
  if (fs.existsSync(masterPath())) return { ok: true, msg: 'MASTER.md already exists', revision: revision(readState()) };
  const state = { before: defaultHeader(), after: '', records: [] };
  state.records.push({ type: 'META', schema_version: 1, revision: 0, updated_at: nowStamp(), last_writer: 'init' });
  state.records.push({ type: 'ACCOUNT', cash: { amount: null, status: 'unknown' }, total_assets: null, data_status: 'unknown' });
  writeState(state);
  return { ok: true, msg: 'MASTER.md initialized', revision: 0 };
}

function cmdValidate() {
  const state = readState();
  const errs = validateRecords(state);
  return { ok: errs.length === 0, errors: errs, revision: revision(state), records: state.records.length };
}

function cmdShow() {
  const state = readState();
  return { ok: true, revision: revision(state), records: state.records };
}

function cmdSetAccount(args) {
  const state = readState();
  expectRev(args, state);
  const get = f => { const i = args.indexOf(f); return i >= 0 && i + 1 < args.length ? args[i + 1] : undefined; };
  const cur = state.records.find(r => r.type === 'ACCOUNT') || { type: 'ACCOUNT' };
  const cashAmount = get('--cash') !== undefined ? checkMoney(get('--cash'), 'cash') : (cur.cash && cur.cash.amount);
  const cashStatus = get('--cash-status') !== undefined ? checkStatus(get('--cash-status'), 'cash_status') : (cur.cash && cur.cash.status);
  const total = get('--total-assets') !== undefined ? checkMoney(get('--total-assets'), 'total_assets') : cur.total_assets;
  const dataStatus = get('--data-status') !== undefined ? checkStatus(get('--data-status'), 'data_status') : cur.data_status;
  const acc = { type: 'ACCOUNT', cash: { amount: cashAmount, status: cashStatus || 'unknown' }, total_assets: total, data_status: dataStatus || 'unknown' };
  if (acc.cash.amount === null && acc.cash.status === 'confirmed') throw new Error('cash amount unknown cannot be confirmed');
  upsert(state, acc);
  bump(state, 'set-account');
  writeState(state);
  return { ok: true, revision: revision(state), account: acc };
}

function cmdSetPosition(args) {
  const state = readState();
  expectRev(args, state);
  const pos = args.filter(a => !a.startsWith('--') && !args[args.indexOf(a) - 1]?.startsWith('--'));
  const [code, qty, sellable, cost, source, knownAt] = pos;
  const c = checkCode(code);
  const q = checkQty(qty, 'quantity', true);
  const s = checkQty(sellable === undefined ? q : sellable, 'sellable', true);
  if (s > q) throw new Error('sellable cannot exceed quantity');
  const rec = {
    type: 'POSITION', code: c, quantity: q, sellable: s,
    cost: cost === undefined || cost === 'unknown' || cost === '' ? null : checkMoney(cost, 'cost'),
    source: checkSource(source || 'user_report'),
    known_at: knownAt || today()
  };
  upsert(state, rec);
  bump(state, 'set-position');
  writeState(state);
  return { ok: true, revision: revision(state), position: rec };
}

function cmdRecordExecution(args) {
  const state = readState();
  expectRev(args, state);
  const get = f => { const i = args.indexOf(f); return i >= 0 && i + 1 < args.length ? args[i + 1] : undefined; };
  const id = get('--id'); if (!id) throw new Error('--id required');
  if (getRec(state, 'EXECUTION', 'id', id)) return { ok: true, idempotent: true, id };
  const code = checkCode(get('--code'));
  const side = get('--side'); if (!['BUY', 'SELL'].includes(side)) throw new Error('--side must be BUY or SELL');
  const qty = checkQty(get('--qty'), 'qty');
  const priceRaw = get('--price');
  const price = priceRaw === undefined || priceRaw === 'unknown' || priceRaw === '' ? null : checkMoney(priceRaw, 'price', false);
  const knownAt = get('--known-at') || today();
  const hist = args.includes('--historical'); // 历史补录：只登记事实，不改持仓
  // 2026-10-29 护栏：补录数天以前的成交会把现值改错——历史买入被当作实时成交后，状态里会多出一份
  // 本不存在的持仓，现金也被重复扣减，且只有 runtime-doctor 的 holdings-conflict 能查出来。
  // 注释里不写具体标的与数量：私有字面量一律不进代码（test-state-core 的私有字面量用例就是查这个）。
  const daysAgo = (Date.parse(today()) - Date.parse(knownAt)) / 86400000;
  if (!hist && daysAgo > 3) throw new Error('known_at=' + knownAt + ' 距今 ' + Math.round(daysAgo) + ' 天：补录历史成交必须显式加 --historical（只登记事实，不改持仓与现金）');
  const acc = state.records.find(r => r.type === 'ACCOUNT') || { type: 'ACCOUNT', cash: { amount: null, status: 'unknown' }, data_status: 'unknown' };
  const pos = getRec(state, 'POSITION', 'code', code);

  if (!hist) {
    if (side === 'SELL') {
      if (!pos) throw new Error(`cannot sell ${code}: no position`);
      if (qty > pos.sellable) throw new Error(`cannot sell ${qty}: sellable=${pos.sellable} (T+1)`);
      pos.quantity -= qty; pos.sellable -= qty;
    } else {
      if (!pos) state.records.push({ type: 'POSITION', code, quantity: 0, sellable: 0, cost: price, source: 'user_report', known_at: knownAt });
      const p = getRec(state, 'POSITION', 'code', code);
      p.quantity += qty; // T+1：当日买入不增加 sellable
      p.last_buy_date = knownAt;
    }
  }
  // 现金：历史补录只登记事实、不改任何现值；实时成交价格已知才更新数值；价格未知降级 estimated
  let cash = acc.cash && acc.cash.amount;
  let cashStatus = acc.cash && acc.cash.status;
  if (price === null) {
    cashStatus = 'estimated';
  } else if (!hist && Number.isFinite(cash)) {
    cash = side === 'BUY' ? cash - qty * price : cash + qty * price;
    if (cash < 0) throw new Error('cash would become negative');
  }
  const rec = {
    type: 'EXECUTION', id, code, side, qty, price,
    cash_change: price === null ? 'estimated' : (side === 'BUY' ? -(qty * price) : qty * price),
    known_at: knownAt, source: checkSource(get('--source') || 'user_report'), historical: !!hist
  };
  upsert(state, rec);
  upsert(state, { type: 'ACCOUNT', cash: { amount: cash ?? null, status: cashStatus || 'unknown' }, total_assets: acc.total_assets ?? null, data_status: price === null ? 'estimated' : (acc.data_status || 'unknown') });
  bump(state, 'record-execution');
  writeState(state);
  return { ok: true, revision: revision(state), execution: rec, position: getRec(state, 'POSITION', 'code', code) };
}

function cmdSettleT1(args) {
  const state = readState();
  expectRev(args, state);
  const get = f => { const i = args.indexOf(f); return i >= 0 && i + 1 < args.length ? args[i + 1] : undefined; };
  const code = get('--code') ? checkCode(get('--code')) : null;
  const settleDate = get('--date') || today();
  let n = 0;
  for (const p of state.records.filter(r => r.type === 'POSITION')) {
    if (code && p.code !== code) continue;
    if (p.sellable !== p.quantity) { p.sellable = p.quantity; p.t1_settled_on = settleDate; n++; }
  }
  bump(state, 'settle-t1');
  writeState(state);
  return { ok: true, settled: n, revision: revision(state) };
}

function cmdAddQuestion(args) {
  const state = readState();
  expectRev(args, state);
  const i = args.indexOf('--text');
  if (i < 0 || i + 1 >= args.length) throw new Error('--text required');
  const text = args[i + 1];
  const ev = args.indexOf('--evidence');
  const rec = {
    type: 'OPEN_QUESTION', id: crypto.randomUUID().slice(0, 8), question: text,
    evidence: ev >= 0 ? args[ev + 1] : null,
    raised_at: nowStamp(), resolved_at: null
  };
  state.records.push(rec);
  bump(state, 'add-question');
  writeState(state);
  return { ok: true, revision: revision(state), question: rec };
}

function cmdResolveQuestion(args) {
  const state = readState();
  expectRev(args, state);
  const i = args.indexOf('--id');
  if (i < 0 || i + 1 >= args.length) throw new Error('--id required');
  const id = args[i + 1];
  const rec = state.records.find(r => r.type === 'OPEN_QUESTION' && r.id === id);
  if (!rec) throw new Error(`question not found: ${id}`);
  if (rec.resolved_at) return { ok: true, revision: revision(state), question: rec, note: 'already resolved' };
  const ai = args.indexOf('--answer');
  rec.resolved_at = nowStamp();
  if (ai >= 0) rec.answer = args[ai + 1];
  bump(state, 'resolve-question');
  writeState(state);
  return { ok: true, revision: revision(state), question: rec };
}

function cmdUpsertJson(args, type) {
  const state = readState();
  expectRev(args, state);
  const i = args.indexOf('--json');
  if (i < 0 || i + 1 >= args.length) throw new Error('--json <file> required');
  const raw = fs.readFileSync(args[i + 1], 'utf8');
  const obj = JSON.parse(raw);
  obj.type = type;
  upsert(state, obj);
  bump(state, `upsert-${type}`);
  writeState(state);
  return { ok: true, revision: revision(state), record: obj };
}

function cmdImportPool(args) {
  const state = readState();
  expectRev(args, state);
  const i = args.indexOf('--source');
  if (i < 0 || i + 1 >= args.length) throw new Error('--source <pool file> required');
  const lines = fs.readFileSync(args[i + 1], 'utf8').split('\n');
  const map = new Map();
  for (const line of lines) {
    const t = line.trim();
    if (!t.startsWith('POOL|')) continue;
    const f = t.split('|');
    if (f.length < 11) continue;
    let code = (f[3] || '').trim().toLowerCase();
    try { code = checkCode(code); } catch (e) { continue; }
    const plan = {
      plan_id: (f[1] || '').trim(), direction: (f[5] || '').trim(),
      trigger: (f[6] || '').trim(), void: (f[7] || '').trim(), expiry: (f[8] || '').trim(),
      status: (f[9] || '').trim(), reason: (f.slice(11).join('|') || '').trim()
    };
    if (!map.has(code)) map.set(code, { type: 'CANDIDATE', code, name: (f[4] || '').trim(), source: 'pool', raised_at: (f[2] || '').trim(), entry_plans: [] });
    const c = map.get(code);
    if (!c.entry_plans.some(p => p.plan_id === plan.plan_id)) c.entry_plans.push(plan);
  }
  for (const c of map.values()) upsert(state, c);
  bump(state, 'import-pool');
  writeState(state);
  return { ok: true, imported: map.size, revision: revision(state) };
}

function cmdRenderViews() {
  const state = readState();
  const vp = viewsPath();
  fs.mkdirSync(vp, { recursive: true });
  const acc = state.records.find(r => r.type === 'ACCOUNT') || {};
  const positions = state.records.filter(r => r.type === 'POSITION');
  const cands = state.records.filter(r => r.type === 'CANDIDATE');
  const decs = state.records.filter(r => r.type === 'DECISION');
  const qs = state.records.filter(r => r.type === 'OPEN_QUESTION' && !r.resolved_at);
  const warn = [`> ⚠️ 数据状态：${acc.data_status || 'unknown'}｜未决问题 ${qs.length} 项`, `> 现金：${acc.cash && acc.cash.amount !== null ? acc.cash.amount : 'unknown'} (${acc.cash && acc.cash.status || 'unknown'})`];
  let pf = `# portfolio.current.md（由 MASTER.md 生成，只读）\n\n${warn.join('\n')}\n\n| 代码 | 数量 | 可卖 | 成本 | 来源 | 已知时间 |\n|---|---|---|---|---|---|\n`;
  for (const p of positions) pf += `| ${p.code} | ${p.quantity} | ${p.sellable} | ${p.cost ?? 'unknown'} | ${p.source} | ${p.known_at} |\n`;
  if (!positions.length) pf += '| — | — | — | — | — | — |\n';
  atomicWrite(path.join(vp, 'portfolio.current.md'), pf);

  let pool = `# pool.current.md（由 MASTER.md 生成，只读）\n\n${warn.join('\n')}\n\n`;
  for (const c of cands) {
    pool += `## ${c.code} ${c.name || ''}\n\n| 计划 | 方向 | 触发 | 作废 | 有效期 | 状态 |\n|---|---|---|---|---|---|\n`;
    for (const p of (c.entry_plans || [])) pool += `| ${p.plan_id} | ${p.direction} | ${p.trigger} | ${p.void} | ${p.expiry} | ${p.status} |\n`;
    if (!(c.entry_plans || []).length) pool += '| — | — | — | — | — | — |\n';
  }
  if (!cands.length) pool += '（无候选）\n';
  atomicWrite(path.join(vp, 'pool.current.md'), pool);

  let wc = `# watch.current.md（由 MASTER.md 生成，只读）\n\n${warn.join('\n')}\n\n| 决策 | 代码 | 动作 | 数量 | 价格区间 | 最大亏损 | 失效 | 策略 | 证据 | 有效至 |\n|---|---|---|---|---|---|---|---|---|---|\n`;
  for (const d of decs) wc += `| ${d.id} | ${d.code} | ${d.action} | ${d.quantity ?? '-'} | ${d.price_range ?? '-'} | ${d.max_loss ?? '-'} | ${d.invalidation ?? '-'} | ${d.strategy_id ?? '-'} | ${d.evidence_level ?? '-'} | ${d.expires_at ?? '-'} |\n`;
  if (!decs.length) wc += '| — | — | — | — | — | — | — | — | — | — |\n';
  atomicWrite(path.join(vp, 'watch.current.md'), wc);
  return { ok: true, views: vp, revision: revision(state) };
}

function help() {
  return `Usage: state-core.js <command> [options]

Commands:
  init --sg-home <path>
  validate
  show
  set-account --cash N|unknown --cash-status confirmed|estimated|unknown --total-assets N --data-status ... --expect-revision N
  set-position <code> <qty> <sellable> <cost|unknown> <source> <known_at> --expect-revision N
  record-execution --id ID --code CODE --side BUY|SELL --qty N --price N|unknown [--known-at TS] [--source S] [--historical] --expect-revision N
  settle-t1 [--code CODE] [--date D] --expect-revision N
  add-question --text T [--evidence E] --expect-revision N
  resolve-question --id ID [--answer A] --expect-revision N
  upsert-candidate --json FILE --expect-revision N
  set-decision --json FILE --expect-revision N
  set-strategy --json FILE --expect-revision N
  import-pool --source FILE --expect-revision N
  render-views
Options:
  --sg-home <path>  (before or after command)
`;
}

function main() {
  const argv = process.argv.slice(2);
  const gi = argv.indexOf('--sg-home');
  if (gi >= 0 && gi + 1 < argv.length) SG_HOME = argv[gi + 1];
  const args = argv.filter((a, i) => !(a === '--sg-home' || (i > 0 && argv[i - 1] === '--sg-home')));
  const cmd = args[0];
  if (!cmd || cmd === '--help' || cmd === '-h') { console.log(help()); return; }
  let out;
  try {
    out = withLock(() => {
      switch (cmd) {
        case 'init': return cmdInit(args[1] === '--sg-home' ? args[2] : null);
        case 'validate': return cmdValidate();
        case 'show': return cmdShow();
        case 'set-account': return cmdSetAccount(args.slice(1));
        case 'set-position': return cmdSetPosition(args.slice(1));
        case 'record-execution': return cmdRecordExecution(args.slice(1));
        case 'settle-t1': return cmdSettleT1(args.slice(1));
        case 'add-question': return cmdAddQuestion(args.slice(1));
        case 'resolve-question': return cmdResolveQuestion(args.slice(1));
        case 'sync-holdings': return renderHoldings(readState());
        case 'upsert-candidate': return cmdUpsertJson(args.slice(1), 'CANDIDATE');
        case 'set-decision': return cmdUpsertJson(args.slice(1), 'DECISION');
        case 'set-strategy': return cmdUpsertJson(args.slice(1), 'STRATEGY');
        case 'import-pool': return cmdImportPool(args.slice(1));
        case 'render-views': return cmdRenderViews();
        default: throw new Error(`unknown command: ${cmd}`);
      }
    });
  } catch (e) {
    console.error(`ERROR: ${e.message}`);
    process.exit(1);
  }
  console.log(JSON.stringify(out, null, 1));
}

if (require.main === module) main();
module.exports = { parseMaster, renderMaster, validateRecords, readState, writeState };
