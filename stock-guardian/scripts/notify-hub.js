#!/usr/bin/env node
'use strict';

// 通知中枢 v2：生产层→events.jsonl→分级/去重/聚合→用户
// P0/P1 立即推；P2 在早/午/尾盘窗口合并；P3 仅尾盘合并。
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const SG = process.env.SG_HOME || path.join(process.env.HOME || '/root', '.stock-guardian');
const BUS = path.join(SG, 'events.jsonl');
const HUB_STATE = path.join(SG, '.hub-state');
const NOTIFY = path.join(__dirname, 'notify-webhook.sh');

function shanghaiNow(date = new Date()) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hour12: false
  }).formatToParts(date).reduce((result, item) => ({ ...result, [item.type]: item.value }), {});
  return { day: `${parts.year}-${parts.month}-${parts.day}`, hour: +parts.hour, minute: +parts.minute };
}

function readJsonLines(file) {
  if (!fs.existsSync(file)) return [];
  return fs.readFileSync(file, 'utf8').split('\n').filter(Boolean).map(line => {
    try { return JSON.parse(line); } catch (error) { return null; }
  }).filter(Boolean);
}

function writeJsonLines(file, rows) {
  const temp = `${file}.tmp`;
  fs.writeFileSync(temp, rows.map(row => JSON.stringify(row)).join('\n') + (rows.length ? '\n' : ''));
  fs.renameSync(temp, file);
}

function loadState() {
  try { return JSON.parse(fs.readFileSync(HUB_STATE, 'utf8')); } catch (error) { return {}; }
}

function saveState(state) {
  const temp = `${HUB_STATE}.tmp`;
  fs.writeFileSync(temp, JSON.stringify(state, null, 2));
  fs.renameSync(temp, HUB_STATE);
}

function push(title, body) {
  if (process.env.HUB_DRY_RUN === '1') return true;
  try {
    execFileSync('bash', [NOTIFY, '--title', title, '--tag', '中枢', '--body', body || '无正文'], {
      timeout: 30000,
      stdio: 'ignore',
      env: { ...process.env, NOTIFY_HUB_INTERNAL: '1' }
    });
    return true;
  } catch (error) {
    fs.appendFileSync(path.join(SG, 'hub.log'), `${new Date().toISOString()} push失败 ${title}: ${error.message}\n`);
    return false;
  }
}

function eventDate(event) {
  return String(event.ts || '').slice(0, 10);
}

function isOlderThanDays(day, referenceDay, days) {
  const a = Date.parse(`${day}T00:00:00Z`);
  const b = Date.parse(`${referenceDay}T00:00:00Z`);
  return Number.isFinite(a) && Number.isFinite(b) && b - a > days * 86400000;
}

function run(now = new Date()) {
  const local = shanghaiNow(now);
  let events = readJsonLines(BUS);
  if (!events.length) return { pushed: 0, message: '事件总线为空' };

  const state = loadState();
  state[local.day] = state[local.day] || { sent: [], digest: 0 };
  for (const day of Object.keys(state)) if (isOlderThanDays(day, local.day, 7)) delete state[day];

  const pending = events.filter(event => !event.processed && eventDate(event) === local.day);
  if (!pending.length) {
    events = events.filter(event => !isOlderThanDays(eventDate(event), local.day, 7));
    writeJsonLines(BUS, events);
    saveState(state);
    return { pushed: 0, message: '无待处理事件' };
  }

  let pushed = 0;
  const instant = pending.filter(event => ['P0', 'P1'].includes(event.severity || 'P2'));
  for (const event of instant) {
    const key = event.dedupeKey || `${event.type}|${event.code || ''}|${local.day}`;
    if (state[local.day].sent.includes(key)) { event.processed = true; continue; }
    const prefix = event.severity === 'P0' ? '🚨' : '✅';
    if (push(`${prefix} ${event.title || '股票管家通知'}`, event.body || event.summary)) {
      state[local.day].sent.push(key);
      event.processed = true;
      event.processedAt = new Date().toISOString();
      pushed++;
    }
  }

  const isDigestWindow = [7, 12, 15].includes(local.hour) && local.minute <= 20;
  const digestBudgetAvailable = state[local.day].digest < 3;
  const digestEvents = pending.filter(event => !event.processed && (event.severity || 'P2') === 'P2');
  if (digestEvents.length && isDigestWindow && digestBudgetAvailable) {
    const body = `📋 情报汇总（${digestEvents.length}条合并）\n\n${digestEvents.map(event => `• ${event.summary || event.title}`).join('\n')}`;
    if (push('📋 股票管家·情报汇总', body)) {
      for (const event of digestEvents) { event.processed = true; event.processedAt = new Date().toISOString(); }
      state[local.day].digest++;
      pushed++;
    }
  }

  const p3Events = pending.filter(event => !event.processed && event.severity === 'P3');
  if (p3Events.length && local.hour === 15 && local.minute <= 20 && digestBudgetAvailable) {
    const body = `🗓️ 明日预告（${p3Events.length}条合并）\n\n${p3Events.map(event => `• ${event.summary || event.title}`).join('\n')}`;
    if (push('🗓️ 股票管家·明日预告', body)) {
      for (const event of p3Events) { event.processed = true; event.processedAt = new Date().toISOString(); }
      state[local.day].digest++;
      pushed++;
    }
  }

  events = events.filter(event => !isOlderThanDays(eventDate(event), local.day, 7));
  writeJsonLines(BUS, events);
  saveState(state);
  const remaining = events.filter(event => !event.processed && eventDate(event) === local.day).length;
  return { pushed, remaining, message: `中枢处理完成：推送${pushed}条，待汇总${remaining}条` };
}

if (require.main === module) {
  const result = run();
  console.log(result.message);
}

module.exports = { run, shanghaiNow };
