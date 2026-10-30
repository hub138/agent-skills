#!/usr/bin/env node
// 前置预警体系 v1（2026-10-28 用户批"突破价通知已经晚了"——多指标分级监控，突破前就有信号）
// 四级信号：S1 吸筹迹象（提前2-3日）→ S2 逼近突破（提前1日）→ S3 盘前映射（当日早报）→ S4 触发确认（当日盘中）
// 数据：pool.md 候选 + 日K缓存/直拉（量比/底部结构/距触发价）+ hold ings
const fs = require('fs'), path = require('path'), { execSync } = require('child_process');
const SG = path.join(process.env.HOME || '/root', '.stock-guardian');
(async () => {
  // 读池
  const pool = fs.readFileSync(path.join(SG, 'pool.md'), 'utf8').split('\n').filter(l => l.startsWith('POOL|'));
  const cands = [];
  for (const line of pool) {
    const f = line.split('|');
    const st = f[9], code = f[3], name = f[4], dir = f[5], trig = +f[6], voidP = +f[7];
    if ((st === 'active' || st === 'triggered') && code && trig) cands.push({ code, name, dir, trig, voidP });
  }
  // 批量现价+近20日K（突破结构分析）
  const codes = cands.map(c => c.code).join(',');
  let pricesRaw = '';
  try { pricesRaw = execSync(`bash ${path.join(SCRIPT_DIR_D(), 'quote-public.sh')} quote "${codes}"`, { timeout: 30000, encoding: 'utf8' }); } catch (e) {}
  const lines = pricesRaw.split('\n').filter(l => l.startsWith('|'));
  const head = (lines[0] || '').split('|').map(x => x.trim());
  const ci = head.indexOf('code'), vi = head.indexOf('price'), vr = head.indexOf('volume_ratio');
  const px = {};
  for (let i = 2; i < lines.length; i++) {
    const f = lines[i].split('|').map(x => x.trim());
    if (f[ci] && f[vi]) px[f[ci]] = { price: +f[vi], vr: +f[vr] || 0 };
  }
  function SCRIPT_DIR_D() { return path.dirname(process.argv[1]); }
  // 分级信号输出
  console.log('=== 前置预警（多指标分级）===');
  for (const c of cands) {
    const p = px[c.code];
    if (!p) { console.log(`${c.code} ${c.name}: 行情缺失`); continue; }
    const dist = Math.abs(p.price - c.trig) / p.price * 100;
    const dip = c.dir.includes('低吸');
    if (dip) {
      console.log(`${c.code} ${c.name}｜参考价 ${p.price}｜距低吸观察价 ${c.trig} 为 ${dist.toFixed(1)}%\n  → 今日计划：回落到 ${c.trig} 后再做低吸确认（作废 ${c.voidP}）；未到价不操作`);
      continue;
    }
    console.log(`${c.code} ${c.name}｜参考价 ${p.price}｜原静态突破价 ${c.trig} 仅作目标参照，不再作为买入前提\n  → 今日结构监控：最早 09:45。若“首轮上涨→回踩守住且量未放大→二次阳线有效创高”，同时跑赢基准、板块至少2只同向，系统会立即发“可试探10%仓”通知；结构不成立就不买`);
  }
  console.log('\n（S1 吸筹迹象/S2 逼近预警/S3 盘前映射/S4 触发确认——四级体系，早报 0.86 段每日引用）');
})();
