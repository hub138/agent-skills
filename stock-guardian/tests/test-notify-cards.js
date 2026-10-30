#!/usr/bin/env node
// 通知卡模板离线单测（不联网、不推送）：方向判读、加粗、五段齐全、闸门缺失降级。
'use strict';
const { timingCard, invalidCard } = require('../scripts/notify-cards.js');

let pass = 0;
const fail = [];
function ck(name, cond) {
  if (cond) { pass++; console.log('  ✔ ' + name); } else { fail.push(name); console.log('  ✘ ' + name); }
}
const R = (kind, trigger, invalid) => ({ name: '测试票', code: 'sh900001', kind, trigger, invalid, expire: '2026-11-03', status: 'active' });
const SH = { cls: 'right', verdict: 'V右·启动确认', fromHi: 1.2, items: [[1, true, '站上 MA5'], [2, false, '未满足项']] };
const GATE = { v: 'PASS', sd: '3.75' };

console.log('T1 方向判读：低吸线是"要跌到"的价');
ck('低吸·现价高于触发 = 未到线', /未到线 差2\.42%/.test(timingCard(R('低吸防御', 0.866, 0.834), SH, 0.887, GATE)));
ck('低吸·现价低于触发 = 已到线', /已到线 进入买点区 -0\.50%/.test(timingCard(R('低吸防御', 0.866, 0.834), SH, 0.8617, GATE)));
ck('低吸·现价等于触发 = 已到线', /已到线 进入买点区 -0\.00%/.test(timingCard(R('低吸防御', 1.0, 0.96), SH, 1.0, GATE)));

console.log('T2 方向判读：突破线是"要涨过"的价');
ck('突破·现价高于触发 = 已越过', /已越过 \+1\.94%/.test(timingCard(R('逆势突破', 17.5, 16.9), SH, 17.84, GATE)));
ck('突破·现价低于触发 = 未越过', /未越过 差1\.69%/.test(timingCard(R('突破追涨', 17.5, 16.9), SH, 17.204, GATE)));

console.log('T3 必含字段与加粗');
const card = timingCard(R('低吸防御', 0.866, 0.834), SH, 0.887, GATE);
ck('加粗标题', card.includes('🟡 **池票时机**｜测试票 sh900001｜低吸防御'));
ck('加粗触发价', card.includes('**触发 0.866**'));
ck('加粗作废价与距离', card.includes('**作废 0.834**（-3.7%）'));
ck('含有效期', card.includes('有效期至 2026-11-03'));
ck('含形态且不双括号', card.includes('形态：V右·启动确认（距 20 日高 1.2%）') && !card.includes('（右侧证据成立）（'));
ck('含证据只取命中项', card.includes('右侧证据：站上 MA5') && !card.includes('未满足项'));
ck('加粗闸门结果', card.includes('**prebuy-check PASS**｜止损距离（现价计）3.75%'));
ck('动作含免责', card.includes('**这是时机提醒，不是买入指令**'));
ck('六行结构', card.split('\n').length === 6);

console.log('T4 降级与异常卡');
ck('闸门缺失不假报', timingCard(R('低吸防御', 1, 0.96), SH, 0.95, null).includes('**prebuy-check 未取得**'));
ck('低吸档用"条件"标签', timingCard(R('低吸防御', 1, 0.96), { ...SH, cls: 'pullback' }, 0.95, GATE).includes('低吸档条件：'));
const inv = invalidCard(R('低吸防御', 0.866, 0.834), '0.830', '池线异常');
ck('异常卡红色标题', inv.startsWith('🔴 **池线异常**｜测试票 sh900001｜低吸防御'));
ck('异常卡含破线与动作', inv.includes('已跌破**作废线 0.834**') && inv.includes('**计划作废**'));

console.log('\n通过 ' + pass + ' 项' + (fail.length ? '，失败 ' + fail.length + ' 项：' + fail.join('、') : '，全部通过'));
process.exit(fail.length ? 1 : 0);
