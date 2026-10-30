#!/usr/bin/env node
'use strict';

// 全部行情数据为合成序列（虚构日期/价位/量能），不得引用任何真实标的与实盘数据。
const assert = require('assert');
const { detectOpeningTrend, parseM5Rows } = require('./trend-signal');

function rows(day, values) {
  return values.map(([time, open, close, high, low, volume]) => [
    `${day}${time}`,
    String(open),
    String(close),
    String(high),
    String(low),
    String(volume)
  ]);
}

const candidate = parseM5Rows([
  ...rows('20260119', [['0935', 1.092, 1.095, 1.096, 1.091, 120000], ['0940', 1.095, 1.094, 1.096, 1.093, 90000], ['0945', 1.094, 1.098, 1.099, 1.093, 110000]]),
  ...rows('20260120', [['0935', 1.098, 1.101, 1.102, 1.097, 130000], ['0940', 1.101, 1.100, 1.102, 1.099, 85000], ['0945', 1.100, 1.103, 1.104, 1.099, 120000]]),
  ...rows('20260121', [['0935', 1.103, 1.106, 1.107, 1.102, 110000], ['0940', 1.106, 1.104, 1.107, 1.103, 95000], ['0945', 1.104, 1.108, 1.109, 1.103, 100000]]),
  ...rows('20260122', [['0935', 1.105, 1.108, 1.109, 1.104, 125000], ['0940', 1.108, 1.107, 1.109, 1.106, 88000], ['0945', 1.107, 1.110, 1.111, 1.106, 115000]]),
  ...rows('20260123', [['0935', 1.100, 1.107, 1.108, 1.099, 150000], ['0940', 1.106, 1.105, 1.108, 1.102, 100000], ['0945', 1.106, 1.120, 1.120, 1.104, 150000]])
]);

const benchmark = parseM5Rows(rows('20260123', [
  ['0935', 995.00, 993.00, 996.00, 992.00, 9000000],
  ['0940', 993.00, 991.00, 994.00, 990.00, 7000000],
  ['0945', 991.00, 997.00, 997.50, 990.50, 8000000]
]));

const peerA = parseM5Rows(rows('20260123', [
  ['0935', 30.00, 30.10, 30.15, 29.98, 50000],
  ['0940', 30.10, 30.20, 30.25, 30.05, 40000],
  ['0945', 30.20, 30.60, 30.65, 30.18, 60000]
]));

const peerB = parseM5Rows(rows('20260123', [
  ['0935', 95.00, 95.20, 95.30, 94.90, 30000],
  ['0940', 95.20, 95.40, 95.45, 95.10, 25000],
  ['0945', 95.40, 96.50, 96.60, 95.35, 35000]
]));

function run() {
  const todayStart = candidate.findIndex(bar => bar.day === '20260123');

  const at0935 = detectOpeningTrend(candidate.slice(0, todayStart + 1), benchmark.slice(0, 1), [peerA.slice(0, 1), peerB.slice(0, 1)]);
  assert.notStrictEqual(at0935.stage, 'PROBE', '09:35 不得给可试探信号');

  const at0940 = detectOpeningTrend(candidate.slice(0, todayStart + 2), benchmark.slice(0, 2), [peerA.slice(0, 2), peerB.slice(0, 2)]);
  assert.notStrictEqual(at0940.stage, 'PROBE', '09:40 不得给可试探信号');

  const at0945 = detectOpeningTrend(candidate, benchmark, [peerA, peerB]);
  assert.strictEqual(at0945.stage, 'PROBE', `09:45 应识别为可试探，实际 ${at0945.stage}: ${at0945.reason}`);
  assert.strictEqual(at0945.signalTime, '0945');
  assert.strictEqual(at0945.entry, 1.12);
  assert(at0945.relativeStrength > 1.5, '应明显跑赢基准');
  assert.strictEqual(at0945.peersUp, 2, '两个同行应同向');

  const noPeers = detectOpeningTrend(candidate, benchmark, []);
  assert.strictEqual(noPeers.stage, 'WATCH', '无板块联动证据不得给可试探');

  const weakPeer = parseM5Rows(rows('20260123', [
    ['0935', 10, 10, 10.1, 9.9, 1000],
    ['0940', 10, 9.9, 10, 9.8, 900],
    ['0945', 9.9, 9.8, 9.9, 9.7, 800]
  ]));
  const noBreadth = detectOpeningTrend(candidate, benchmark, [weakPeer, weakPeer]);
  assert.strictEqual(noBreadth.stage, 'WATCH', '板块同行下跌不得给可试探');

  const falseDay = parseM5Rows(rows('20260120', [
    ['0935', 1.115, 1.125, 1.125, 1.110, 1400000],
    ['0940', 1.124, 1.121, 1.125, 1.121, 680000],
    ['0945', 1.122, 1.113, 1.122, 1.113, 470000]
  ]));
  const falseBench = parseM5Rows(rows('20260120', [
    ['0935', 100, 100.1, 100.1, 99.9, 1000],
    ['0940', 100.1, 100.0, 100.1, 99.9, 900],
    ['0945', 100.0, 100.1, 100.2, 100.0, 800]
  ]));
  const falseBreakout = detectOpeningTrend(falseDay, falseBench, [peerA.map(bar => ({ ...bar, day: '20260120' })), peerB.map(bar => ({ ...bar, day: '20260120' }))]);
  assert.notStrictEqual(falseBreakout.stage, 'PROBE', '冲高回落假突破不得给可试探');

  const missingBenchmark = detectOpeningTrend(candidate, benchmark.slice(0, 2), [peerA, peerB]);
  assert.strictEqual(missingBenchmark.stage, 'WATCH', '基准数据不完整不得静默放行');

  const tinyPeer = parseM5Rows(rows('20260123', [
    ['0935', 10, 10, 10.01, 9.99, 1000],
    ['0940', 10, 10.001, 10.01, 9.99, 900],
    ['0945', 10.001, 10.002, 10.01, 9.99, 800]
  ]));
  const microBreadth = detectOpeningTrend(candidate, benchmark, [tinyPeer, tinyPeer]);
  assert.strictEqual(microBreadth.stage, 'WATCH', '同行微涨 0.01% 不得算板块联动');

  const microBreakRows = candidate.map(bar => ({ ...bar }));
  const last = microBreakRows.at(-1);
  last.close = 1.1085;
  last.high = 1.109;
  const microBreak = detectOpeningTrend(microBreakRows, benchmark, [peerA, peerB]);
  assert.notStrictEqual(microBreak.stage, 'PROBE', '只高一个 tick 的假突破不得触发');

  const downBenchmark = benchmark.map(bar => ({ ...bar }));
  downBenchmark[0].open = 1000;
  downBenchmark[2].close = 990;
  const badEnvironment = detectOpeningTrend(candidate, downBenchmark, [peerA, peerB]);
  assert.strictEqual(badEnvironment.stage, 'WATCH', '基准下跌日不得仅凭相对抗跌触发');

  const noHistory = detectOpeningTrend(candidate.slice(todayStart), benchmark, [peerA, peerB]);
  assert.strictEqual(noHistory.stage, 'WATCH', '同时间窗历史不足 3 日不得静默放行');

  const extremeVolume = candidate.map(bar => ({ ...bar }));
  extremeVolume.slice(-3).forEach(bar => { bar.volume *= 100; });
  const volumeShock = detectOpeningTrend(extremeVolume, benchmark, [peerA, peerB]);
  assert.strictEqual(volumeShock.stage, 'WATCH', '极端放量不得当作普通趋势确认');

  console.log('趋势启动检测 13 项断言全部通过（合成行情序列）');
}

run();
