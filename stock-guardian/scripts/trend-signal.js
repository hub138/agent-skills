#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const SG = process.env.SG_HOME || path.join(process.env.HOME || '/root', '.stock-guardian');
const SCRIPT_DIR = __dirname;
const POOL_FILE = path.join(SG, 'pool.md');
const STATE_FILE = path.join(SG, '.trend-signals.json');
const BUS_FILE = path.join(SG, 'events.jsonl');
// 主题映射优先读用户数据区（真实映射属用户数据，不随 skill 发布），skill 内文件仅为格式样例
const THEME_FILES = [path.join(SG, 'trend-themes.json'), path.join(SCRIPT_DIR, 'trend-themes.json')];
const CONFIG_FILE = THEME_FILES.find(p => fs.existsSync(p)) || THEME_FILES[1];

const CONFIG = {
  earliestTime: '0945',
  latestTime: '1030',
  seedBodyPct: 0.4,
  pullbackBufferPct: 0.5,
  pullbackVolumeCap: 1.15,
  confirmBodyPct: 0.5,
  breakoutBufferPct: 0.15,
  confirmVolumeFloor: 0.75,
  cumulativeVolumeRatioMin: 0.9,
  cumulativeVolumeRatioMax: 8,
  relativeStrengthMin: 0.5,
  benchmarkReturnMin: 0,
  peerReturnMin: 0.3,
  sectorBreadthMin: 0.6,
  peersRequired: 2,
  invalidationBufferPct: 0.5,
  probePositionFraction: 0.10,
  fetchTimeoutMs: 10000,
  fetchRetries: 2
};

function shanghaiParts(date = new Date()) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false
  }).formatToParts(date).reduce((result, item) => ({ ...result, [item.type]: item.value }), {});
  return {
    day: `${parts.year}${parts.month}${parts.day}`,
    dayDash: `${parts.year}-${parts.month}-${parts.day}`,
    time: `${parts.hour}${parts.minute}`
  };
}

function lastClosedFiveMinuteTime(date = new Date()) {
  const { time } = shanghaiParts(date);
  const hour = +time.slice(0, 2);
  const minute = +time.slice(2);
  const total = hour * 60 + minute - 1;
  const closed = Math.floor(total / 5) * 5;
  return `${String(Math.floor(closed / 60)).padStart(2, '0')}${String(closed % 60).padStart(2, '0')}`;
}

function pct(a, b) {
  return b ? (a / b - 1) * 100 : 0;
}

function typicalPrice(bar) {
  return (bar.high + bar.low + bar.close) / 3;
}

function vwap(bars) {
  const volume = bars.reduce((sum, bar) => sum + bar.volume, 0);
  if (!volume) return 0;
  return bars.reduce((sum, bar) => sum + typicalPrice(bar) * bar.volume, 0) / volume;
}

function parseM5Rows(rows) {
  return (rows || []).map(row => ({
    rawTime: String(row[0]),
    day: String(row[0]).slice(0, 8),
    time: String(row[0]).slice(-4),
    open: +row[1],
    close: +row[2],
    high: +row[3],
    low: +row[4],
    volume: +row[5]
  })).filter(bar => bar.open > 0 && bar.close > 0 && bar.high > 0 && bar.low > 0 && Number.isFinite(bar.volume))
    .sort((a, b) => a.rawTime.localeCompare(b.rawTime));
}

function splitDays(bars) {
  const grouped = new Map();
  for (const bar of bars) {
    if (!grouped.has(bar.day)) grouped.set(bar.day, []);
    grouped.get(bar.day).push(bar);
  }
  return grouped;
}

function barsAtTimes(bars, times) {
  const byTime = new Map(bars.map(bar => [bar.time, bar]));
  const selected = times.map(time => byTime.get(time));
  return selected.every(Boolean) ? selected : null;
}

function historicalWindowVolume(grouped, currentDay, times) {
  const samples = [];
  for (const [day, bars] of grouped.entries()) {
    if (day >= currentDay) continue;
    const selected = barsAtTimes(bars, times);
    if (!selected) continue;
    samples.push(selected.reduce((sum, bar) => sum + bar.volume, 0));
  }
  const recent = samples.slice(-5);
  if (recent.length < 3) return null;
  return recent.reduce((a, b) => a + b, 0) / recent.length;
}

function detectOpeningTrend(bars, benchmarkBars, peerBarsList, options = {}) {
  const cfg = { ...CONFIG, ...options };
  if (!bars || bars.length < 3) return { stage: 'NONE', reason: '闭合5分钟K不足3根' };

  const currentDay = options.currentDay || bars.at(-1).day;
  const asOfTime = options.asOfTime || bars.filter(bar => bar.day === currentDay).at(-1)?.time;
  const currentBars = bars.filter(bar => bar.day === currentDay && (!asOfTime || bar.time <= asOfTime));
  if (currentBars.length < 3) return { stage: 'NONE', reason: '今日闭合5分钟K不足3根' };

  const grouped = splitDays(bars);
  let bestWatch = { stage: 'WATCH', reason: '尚未形成首轮上涨→回踩→二次创高结构' };

  for (let index = 0; index <= currentBars.length - 3; index++) {
    const seed = currentBars[index];
    const pullback = currentBars[index + 1];
    const confirm = currentBars[index + 2];
    if (confirm.time < cfg.earliestTime) continue;
    if (confirm.time > cfg.latestTime) break;

    const seedBody = pct(seed.close, seed.open);
    if (!(seedBody >= cfg.seedBodyPct && seed.close > seed.open)) continue;

    const pullbackHeld = pullback.low >= seed.low * (1 - cfg.pullbackBufferPct / 100);
    const pullbackQuiet = pullback.volume <= seed.volume * cfg.pullbackVolumeCap;
    const pullbackOccurred = pullback.close <= seed.close * 1.005;
    if (!(pullbackHeld && pullbackQuiet && pullbackOccurred)) {
      bestWatch = { stage: 'WATCH', reason: `回踩结构未完成（守低点=${pullbackHeld}，量未放大=${pullbackQuiet}，发生回踩=${pullbackOccurred}）` };
      continue;
    }

    const priorHigh = Math.max(seed.high, pullback.high);
    const confirmBody = pct(confirm.close, confirm.open);
    const confirmBreak = confirm.close >= priorHigh * (1 + cfg.breakoutBufferPct / 100);
    const confirmStrong = confirmBody >= cfg.confirmBodyPct;
    const body = Math.abs(confirm.close - confirm.open);
    const upperWick = Math.max(0, confirm.high - Math.max(confirm.open, confirm.close));
    const wickOkay = upperWick <= Math.max(body * 1.2, confirm.close * 0.001);
    const windowBars = currentBars.slice(0, index + 3);
    const currentVwap = vwap(windowBars);
    const vwapOkay = confirm.close > currentVwap;
    const confirmVolumeOkay = confirm.volume >= ((seed.volume + pullback.volume) / 2) * cfg.confirmVolumeFloor;
    if (!(confirmBreak && confirmStrong && wickOkay && vwapOkay && confirmVolumeOkay)) {
      bestWatch = {
        stage: 'WATCH',
        reason: `二次上攻未确认（有效创高=${confirmBreak}，阳线=${confirmStrong}，上影=${wickOkay}，VWAP=${vwapOkay}，确认量=${confirmVolumeOkay}）`
      };
      continue;
    }

    const times = [seed.time, pullback.time, confirm.time];
    const historicalVolume = historicalWindowVolume(grouped, currentDay, times);
    if (historicalVolume === null) return { stage: 'WATCH', reason: '同时间窗历史量能不足3日，不能确认' };
    const currentVolume = [seed, pullback, confirm].reduce((sum, bar) => sum + bar.volume, 0);
    const cumulativeVolumeRatio = currentVolume / historicalVolume;
    if (cumulativeVolumeRatio < cfg.cumulativeVolumeRatioMin || cumulativeVolumeRatio > cfg.cumulativeVolumeRatioMax) {
      return { stage: 'WATCH', reason: `同期量能异常（${cumulativeVolumeRatio.toFixed(2)}倍）` };
    }

    const benchmarkToday = barsAtTimes((benchmarkBars || []).filter(bar => bar.day === currentDay), times);
    if (!benchmarkToday) return { stage: 'WATCH', reason: '基准同期数据不完整，不能确认相对强度' };
    const benchmarkReturn = pct(benchmarkToday[2].close, benchmarkToday[0].open);
    const relativeStrength = pct(confirm.close, seed.open) - benchmarkReturn;
    if (benchmarkReturn < cfg.benchmarkReturnMin || relativeStrength < cfg.relativeStrengthMin) {
      return { stage: 'WATCH', reason: `环境/相对强度不足（基准${benchmarkReturn.toFixed(2)}%，RS${relativeStrength.toFixed(2)}%）` };
    }

    let peersUp = 0;
    let peersAvailable = 0;
    for (const peerBars of peerBarsList || []) {
      const selected = barsAtTimes(peerBars.filter(bar => bar.day === currentDay), times);
      if (!selected) continue;
      peersAvailable++;
      if (pct(selected[2].close, selected[0].open) >= cfg.peerReturnMin) peersUp++;
    }
    const sectorBreadth = peersAvailable ? peersUp / peersAvailable : null;
    if (peersAvailable < cfg.peersRequired || sectorBreadth < cfg.sectorBreadthMin) {
      return {
        stage: 'WATCH',
        reason: peersAvailable < cfg.peersRequired ? `同主题可比标的不足${cfg.peersRequired}只` : `板块联动不足（${peersUp}/${peersAvailable}）`
      };
    }

    const invalidation = Math.min(pullback.low, confirm.low) * (1 - cfg.invalidationBufferPct / 100);
    const entry = confirm.close;
    const riskPct = Math.abs(entry / invalidation - 1) * 100;
    return {
      stage: 'PROBE',
      signalTime: confirm.time,
      entry,
      invalidation,
      riskPct,
      firstTarget: entry + (entry - invalidation),
      secondTarget: entry + 2 * (entry - invalidation),
      seedBody,
      confirmBody,
      vwap: currentVwap,
      cumulativeVolumeRatio,
      relativeStrength,
      benchmarkReturn,
      sectorBreadth,
      peersUp,
      peersAvailable,
      reason: '首轮上涨→回踩不破且量未放大→二次阳线有效创高；同期量能、VWAP、相对强度和板块联动同向'
    };
  }

  return bestWatch;
}

function loadPool() {
  if (!fs.existsSync(POOL_FILE)) return [];
  const byCode = new Map();
  for (const line of fs.readFileSync(POOL_FILE, 'utf8').split('\n').filter(item => item.startsWith('POOL|'))) {
    const fields = line.split('|');
    if (fields.length < 10) continue;
    const candidate = {
      id: fields[1], code: fields[3], name: fields[4], direction: fields[5],
      trigger: +fields[6], voidPrice: +fields[7], state: fields[9], note: fields.slice(11).join('|')
    };
    if (!['active', 'triggered'].includes(candidate.state) || !candidate.code || !Number.isFinite(candidate.trigger) || !Number.isFinite(candidate.voidPrice)) continue;
    const existing = byCode.get(candidate.code);
    if (!existing || (!candidate.direction.includes('低吸') && existing.direction.includes('低吸'))) byCode.set(candidate.code, candidate);
  }
  return [...byCode.values()];
}

function loadThemes() {
  try { return JSON.parse(fs.readFileSync(CONFIG_FILE, 'utf8')).themes || []; } catch (error) { return []; }
}

function resolveTheme(candidate, themes) {
  const exact = themes.find(theme => theme.codes.includes(candidate.code));
  if (exact) return exact;
  return themes.find(theme => theme.keywords.some(keyword => `${candidate.name}${candidate.note}`.includes(keyword))) || null;
}

async function fetchWithTimeout(url, timeoutMs) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try { return await fetch(url, { signal: controller.signal }); } finally { clearTimeout(timer); }
}

async function fetchM5(code, count = 320) {
  let lastError;
  for (let attempt = 0; attempt <= CONFIG.fetchRetries; attempt++) {
    try {
      const response = await fetchWithTimeout(`https://ifzq.gtimg.cn/appstock/app/kline/mkline?param=${code},m5,,${count}`, CONFIG.fetchTimeoutMs);
      const text = await response.text();
      if (!text.trim().startsWith('{')) throw new Error('m5接口返回非JSON');
      const json = JSON.parse(text);
      return parseM5Rows(json.data?.[code]?.m5 || json.data?.[code]?.m5qfq || []);
    } catch (error) {
      lastError = error;
      if (attempt < CONFIG.fetchRetries) await new Promise(resolve => setTimeout(resolve, 300 * (attempt + 1)));
    }
  }
  throw new Error(`${code} m5拉取失败：${lastError?.message || '未知错误'}`);
}

function latestAccountTotal() {
  const accountFile = path.join(SG, 'account.jsonl');
  if (!fs.existsSync(accountFile)) return 50000;
  const line = fs.readFileSync(accountFile, 'utf8').split('\n').filter(item => item.startsWith('ACCT|')).at(-1);
  const value = line ? +line.split('|')[4] : NaN;
  return Number.isFinite(value) && value > 0 ? value : 50000;
}

function loadSignalState() {
  if (!fs.existsSync(STATE_FILE)) return {};
  try { return JSON.parse(fs.readFileSync(STATE_FILE, 'utf8')); } catch (error) { return {}; }
}

function saveSignalState(state) {
  const tempFile = `${STATE_FILE}.tmp`;
  fs.writeFileSync(tempFile, JSON.stringify(state, null, 2));
  fs.renameSync(tempFile, STATE_FILE);
}

function buildBody(candidate, theme, result, accountTotal) {
  const budget = Math.min(5000, accountTotal * CONFIG.probePositionFraction);
  const shares = Math.max(100, Math.floor(budget / result.entry / 100) * 100);
  const actualAmount = shares * result.entry;
  const riskAmount = actualAmount * result.riskPct / 100;
  return [
    `🟠 ${candidate.name}出现早盘趋势启动，可试探买入`, '',
    `时间：${result.signalTime.slice(0, 2)}:${result.signalTime.slice(2)}｜参考价：${result.entry.toFixed(3)}`,
    `为什么现在：首轮上涨后回踩守住，随后二次阳线有效创高；价格在VWAP ${result.vwap.toFixed(3)} 上方。`,
    `板块联动：${theme.name}同向 ${result.peersUp}/${result.peersAvailable}；基准同期 ${result.benchmarkReturn.toFixed(2)}%，相对强度 +${result.relativeStrength.toFixed(2)}%。`,
    `量能：开盘结构段累计量为近5日同期 ${result.cumulativeVolumeRatio.toFixed(2)} 倍。`, '',
    `动作：如愿意参与，可试探买入约 ${shares} 份（约 ${actualAmount.toFixed(0)} 元，账户约10%），不要一次买满。`,
    `结构失效位：${result.invalidation.toFixed(3)}；按参考价估算1R约亏 ${riskAmount.toFixed(0)} 元；第一目标 ${result.firstTarget.toFixed(3)}，第二目标 ${result.secondTarget.toFixed(3)}。`,
    `重要：A股股票ETF为T+1，当天买入不能卖；即使当天跌破失效位也无法退出，次日才能处理，所以只给试探仓。`, '',
    `这不是固定价突破提醒；即使未站上原观察价 ${candidate.trigger}，结构确认也可以先给试探机会。`,
    '不构成投资建议。'
  ].join('\n');
}

function appendEvent(event) {
  fs.appendFileSync(BUS_FILE, `${JSON.stringify(event)}\n`);
}

async function runLive({ notify = true, now = new Date() } = {}) {
  const local = shanghaiParts(now);
  const closedTime = lastClosedFiveMinuteTime(now);
  const pool = loadPool();
  const themes = loadThemes();
  const cache = new Map();
  const getBars = async code => {
    if (!cache.has(code)) cache.set(code, await fetchM5(code));
    return cache.get(code);
  };
  const state = loadSignalState();
  for (const day of Object.keys(state)) if (day !== local.dayDash) delete state[day];
  state[local.dayDash] = state[local.dayDash] || {};
  const outputs = [];

  for (const candidate of pool) {
    const theme = resolveTheme(candidate, themes);
    if (!theme) { outputs.push({ code: candidate.code, stage: 'WATCH', reason: '未配置主题联动映射' }); continue; }
    try {
      const allBars = await getBars(candidate.code);
      const latestDataDay = allBars.at(-1)?.day;
      if (latestDataDay !== local.day) { outputs.push({ code: candidate.code, stage: 'WATCH', reason: `数据停留在${latestDataDay || '未知日期'}` }); continue; }
      const bars = allBars.filter(bar => bar.day !== local.day || bar.time <= closedTime);
      const benchmarkBars = (await getBars(theme.benchmark)).filter(bar => bar.day !== local.day || bar.time <= closedTime);
      const peerBarsList = [];
      for (const peerCode of theme.codes.filter(code => code !== candidate.code)) {
        try { peerBarsList.push((await getBars(peerCode)).filter(bar => bar.day !== local.day || bar.time <= closedTime)); } catch (error) { /* 数量闸门会降级 */ }
      }
      const result = detectOpeningTrend(bars, benchmarkBars, peerBarsList, { currentDay: local.day, asOfTime: closedTime });
      outputs.push({ code: candidate.code, name: candidate.name, theme: theme.name, latestClosed: closedTime, ...result });
      if (result.stage !== 'PROBE' || result.signalTime !== closedTime) continue;
      const key = `${candidate.code}|PROBE`;
      if (state[local.dayDash][key]) continue;
      const body = buildBody(candidate, theme, result, latestAccountTotal());
      const event = {
        ts: `${local.dayDash}T${result.signalTime.slice(0, 2)}:${result.signalTime.slice(2)}:00+08:00`,
        type: 'trend_signal', subtype: 'PROBE', code: candidate.code,
        title: `${candidate.name}早盘趋势启动`, severity: 'P1',
        dedupeKey: `trend|${candidate.code}|${local.dayDash}|PROBE`,
        summary: `${candidate.name} ${result.signalTime}结构确认，可试探10%仓`, body,
        processed: false, metrics: result
      };
      state[local.dayDash][key] = { status: 'queued', time: result.signalTime, entry: result.entry };
      saveSignalState(state);
      try { appendEvent(event); } catch (error) { delete state[local.dayDash][key]; saveSignalState(state); throw error; }
      if (notify) execFileSync('node', [path.join(SCRIPT_DIR, 'notify-hub.js')], { timeout: 30000, stdio: 'ignore' });
    } catch (error) {
      outputs.push({ code: candidate.code, stage: 'ERROR', reason: error.message });
    }
  }
  saveSignalState(state);
  return outputs;
}

if (require.main === module) {
  runLive({ notify: !process.argv.includes('--no-notify') }).then(outputs => {
    if (process.argv.includes('--json')) console.log(JSON.stringify(outputs, null, 2));
    else outputs.forEach(output => console.log(`${output.code} ${output.stage}: ${output.reason || ''}`));
  }).catch(error => { console.error(error.stack || error.message); process.exit(1); });
}

module.exports = {
  CONFIG,
  detectOpeningTrend,
  parseM5Rows,
  splitDays,
  vwap,
  shanghaiParts,
  lastClosedFiveMinuteTime
};
