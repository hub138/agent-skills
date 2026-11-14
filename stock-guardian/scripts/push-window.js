#!/usr/bin/env node
// push-window.js —— P2 时机/欠账类推送的时段窗守卫（2026-10-30 立）
// 由来：10-30 00:00:04 零点「池票时机播报」把 10-29 收盘数据当新一天首推——
//   "每票每形态每日一次"的配额在 00:00 零信息量时刻重置，被 00:00 的第一个全天候 tick 消费掉，
//   盘中真形态反而哑火。归因：时钟错位母题，「跨轮去重作用域」家族第 2 例
//   （第 1 例：10-27 过期线清理提醒 16 连推）。
// 规则：非紧急的"每日配额"类推送必须落在交易时段窗内（周一至周五 08:30-15:30 上海时间）。
//   窗外 = 静默跳过且不占当日去重键（配额只在窗内首个有效 tick 消费，重置点事实上从 00:00 挪到窗首）。
//   数据新鲜度（行情 time 列=今天）由调用方自查——本模块只管时钟，不碰行情。
//   P0 破线/止损类不接入本守卫：紧急度优先，宁可半夜叫醒。
// 接入方（新增配额类推送一律 require 本模块，禁止各自手写时间判断）：
//   line-audit.js（时机卡）｜coverage-audit.js（覆盖体检欠账）
'use strict';

// 上海时区当前时刻的 { date: 'YYYY-MM-DD', weekday: 'Mon'..'Sun', hhmm: 'HH:MM' }
function shanghaiParts(d = new Date()) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', weekday: 'short', hourCycle: 'h23',
  }).formatToParts(d);
  const get = (t) => (parts.find((p) => p.type === t) || {}).value || '';
  return { date: `${get('year')}-${get('month')}-${get('day')}`, weekday: get('weekday'), hhmm: `${get('hour')}:${get('minute')}` };
}

const OPEN = '08:30';   // 窗首：覆盖体检 09:25 专班任务之前，盘前集合竞价数据落地后
const CLOSE = '15:30';  // 窗尾：收盘后留 30 分钟给"收盘确认"形态，再往后归盘后任务管

function inWindow(d = new Date()) {
  const { weekday, hhmm } = shanghaiParts(d);
  if (['Sat', 'Sun'].includes(weekday)) return false;
  return hhmm >= OPEN && hhmm <= CLOSE;
}

// 窗外原因（供日志说清楚"为什么静默"），窗内返回 null
function blockedReason(d = new Date()) {
  const { weekday, hhmm } = shanghaiParts(d);
  if (['Sat', 'Sun'].includes(weekday)) return `非交易日（${weekday}）`;
  if (hhmm < OPEN || hhmm > CLOSE) return `推送窗外（${OPEN}-${CLOSE}，此刻 ${hhmm}）`;
  return null;
}

module.exports = { inWindow, blockedReason, shanghaiParts, OPEN, CLOSE };
