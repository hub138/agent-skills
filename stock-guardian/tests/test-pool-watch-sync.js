#!/usr/bin/env node
// test-pool-watch-sync.js —— pool-watch-sync 机器测试（全合成数据，禁真实代码/价位）
const assert = require('assert');
const fs = require('fs'), os = require('os'), path = require('path'), { execSync } = require('child_process');

const SCRIPT = path.join(__dirname, '..', 'scripts', 'pool-watch-sync.js');
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'sg-sync-test-'));
const poolF = path.join(tmp, 'pool.md'), watchF = path.join(tmp, 'watch.conf');

// 合成池：突破行 / 低吸行 / 事件驱动回踩行 / 已过期行 / 非 active 态行
const poolRows = [
  '# 合成测试池',
  'POOL|t01|2026-01-02|sh900001|合成突破票|突破追涨|1.11|1.02|2026-12-31|active|0|合成-突破',
  'POOL|t02|2026-01-02|sz900002|合成低吸票|低吸防御|0.99|0.93|2026-12-31|triggered|0|合成-低吸',
  'POOL|t03|2026-01-02|sh900003|合成事件票|事件驱动|2.22|2.05|2026-12-31|active|0|合成-回踩低吸型',
  'POOL|t04|2026-01-02|sz900004|合成超期票|突破追涨|3.33|3.10|2026-01-01|active|0|已过期应跳过',
  'POOL|t05|2026-01-02|sh900005|合成终态票|低吸防御|4.44|4.10|2026-12-31|dropped|0|非active应跳过',
];
fs.writeFileSync(poolF, poolRows.join('\n') + '\n');
fs.writeFileSync(watchF, '# 人工线区\nwatch|sz900002|below|0.80|人工线|保持在块外|至2026-12-31\n');

const env = { ...process.env, SG_HOME: tmp, POOL_FILE: poolF, WATCH_FILE: watchF };
const run = () => execSync(`node ${JSON.stringify(SCRIPT)}`, { env, encoding: 'utf8' });

// ① 首次写入：块生成、映射正确、跳过规则生效
const out1 = run();
const conf1 = fs.readFileSync(watchF, 'utf8');
assert(conf1.includes('# === POOL-AUTO BEGIN'), '应有块开始标记');
assert(conf1.includes('# === POOL-AUTO END'), '应有块结束标记');
assert(conf1.includes('watch|sh900001|above|1.11|'), '突破行应映射 above 触发线');
assert(conf1.includes('watch|sh900001|below|1.02|'), '突破行应带 below 作废线');
assert(conf1.includes('watch|sz900002|below|0.99|'), '低吸行应映射 below 触发线');
assert(conf1.includes('watch|sh900003|below|2.22|'), '事件驱动回踩型应映射 below 触发线');
assert(!conf1.includes('900004'), '过期行应跳过');
assert(!conf1.includes('900005'), '非 active 态应跳过');
assert(conf1.includes('watch|sz900002|below|0.80|人工线'), '块外人工线必须保留');
assert(conf1.indexOf('人工线') < conf1.indexOf('# === POOL-AUTO BEGIN'), '人工线应保持在块外原位');

// ② 幂等：二次运行无变化
const out2 = run();
assert(out2.includes('无变化'), '二次运行应报告无变化，实际: ' + out2.trim());

// ③ 池行出池后：块内对应线自动移除
fs.writeFileSync(poolF, poolRows.filter(l => !l.includes('t01')).join('\n') + '\n');
run();
const conf3 = fs.readFileSync(watchF, 'utf8');
assert(!conf3.includes('sh900001'), '出池后块内线应被移除');
assert(conf3.includes('watch|sz900002|below|0.99|'), '未出池行应保留');
assert(conf3.includes('watch|sz900002|below|0.80|人工线'), '人工线仍保留');

fs.rmSync(tmp, { recursive: true, force: true });
console.log('test-pool-watch-sync: 3/3 通过');
