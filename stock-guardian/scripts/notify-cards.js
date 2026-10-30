#!/usr/bin/env node
// 通知卡模板（2026-10-29 立：用户"你的通知有这么清晰吗？这个很清晰啊 我很喜欢 还有加粗"）
// 与荐股卡同构的五段：方向标签 / 价格与有效期 / 形态证据 / 闸门 / 动作。
// 参考价与结论一律加粗（企微 markdown 支持 **粗体**，见 notify-webhook.sh 头部说明）。
// 单独成文件的原因：推送正文要能被离线单测（tests/test-notify-cards.js 注入假闸门，不联网、不推送）。
'use strict';

const isDip = (kind) => /低吸|回调|回踩/.test(kind || '');
const isBreak = (kind) => /突破|追涨|轮动/.test(kind || '');

// r: {name,code,kind,trigger,invalid,expire,status}；sh: {cls,verdict,fromHi,items}；px: 现价；gate: {v,sd}
function timingCard(r, sh, px, gate) {
  const gap = (px / r.trigger - 1) * 100;
  // 两侧方向必须分开判：低吸线是"要跌到"的价（现价 ≤ 触发 = 已进买点区），突破线是"要涨过"的价（现价 ≥ 触发 = 已越过）。
  // 第一版写成同一条 gap >= 0 分支 → 某池票现价 0.887 高于低吸触发 0.866，却被写成"已到线"，方向刚好反了。
  const touch = isDip(r.kind)
    ? (gap <= 0 ? `已到线 进入买点区 -${Math.abs(gap).toFixed(2)}%` : `未到线 差${gap.toFixed(2)}%`)
    : (gap >= 0 ? `已越过 +${gap.toFixed(2)}%` : `未越过 差${Math.abs(gap).toFixed(2)}%`);
  const dIn = ((r.invalid / r.trigger - 1) * 100).toFixed(1);
  const ev = (sh.items || []).filter((i) => i[1]).map((i) => i[2]).join('；') || '—';
  // 形态文案里自带的括号说明先去掉，避免"…（右侧证据成立）（距 20 日高 x%）"双括号；止损距离按现价计，标注清楚
  const verdict = String(sh.verdict || '').replace(/（[^）]*）\s*$/, '');
  const g = gate && gate.v ? `**prebuy-check ${gate.v}**${gate.sd ? `｜止损距离（现价计）${gate.sd}%` : ''}` : '**prebuy-check 未取得**（自行复核）';
  return [
    `🟡 **池票时机**｜${r.name} ${r.code}｜${r.kind}`,
    `**触发 ${r.trigger}**（现价 ${px}，${touch}）｜**作废 ${r.invalid}**（${dIn}%）｜有效期至 ${r.expire}`,
    `形态：${verdict}（距 20 日高 ${sh.fromHi.toFixed(1)}%）`,
    `${sh.cls === 'right' ? '右侧证据' : '低吸档条件'}：${ev}`,
    `闸门：${g}`,
    `动作：**这是时机提醒，不是买入指令**——想动手先按闸门与仓位上限复核，成交后报实价记账`,
  ].join('\n');
}

// 池线异常卡：破作废线（P0）
function invalidCard(r, px, hitLine) {
  const dIn = ((r.invalid / r.trigger - 1) * 100).toFixed(1);
  return [
    `🔴 **${hitLine}**｜${r.name} ${r.code}｜${r.kind}`,
    `**现价 ${px}** 已跌破**作废线 ${r.invalid}**（作废线距触发 ${dIn}%）｜有效期至 ${r.expire}`,
    `动作：**计划作废**——立即出池核销，禁止抄底；台账落终态后不再改判`,
  ].join('\n');
}

module.exports = { timingCard, invalidCard, isDip, isBreak };
