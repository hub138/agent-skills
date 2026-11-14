# 出处与外部标杆

本技能每条规则都有来源。要深挖时按这里的入口去读原文，不要凭印象。

## 已读并提炼的技能（装在使用者的技能目录下，路径因环境而异）

| 技能 | 从这里取了什么 |
|---|---|
| `ui-ux-pro-max` | ux-guidelines.csv（99 条 UX 规则，可 `python3 scripts/search.py "<关键词>" --domain ux` 检索）；交付前四段清单；禁用 emoji 当图标；hover 稳定性；浅色玻璃卡不透明度 |
| `tdesign-design-skill` | M03 字号/行高/间距/圆角 Token 表；M04 栅格 24px 边距、三级底色、侧栏 flex 写法、顶栏 56px 与 `min-height` 双保险 |
| `frontend-design` | 排版三旋钮、动效时长与 `prefers-reduced-motion`、背景细节、禁止硬编码色值、避免"通用 AI 美学" |
| `theme-factory` | 10 套成套主题（配色 + 字体配对），换风格时从 `themes/` 取成套方案，不要自己单点调色 |
| `canvas-design` | 视觉哲学的写法（先立意再画），做海报/头图类单幅视觉时用它 |
| `icon-designer` | 16 条图标规范（统一视角色板、正面视角、禁描边/投影/发光），生成图标时用它 |
| `archify`（若已安装） | 画图判断与验收的来源：五类图路由、主路径唯一、边标签语义、validate→deliver→visual-check 三关验收；工具本体与 schema 归它，本技能 `references/diagrams.md` 只沉淀判断标准 |

`ui-ux-pro-max` 检索示例：

```
cd <skill 目录> && python3 scripts/search.py "contrast dark mode" --domain ux -n 8
python3 scripts/search.py "dashboard" --domain product
python3 scripts/search.py "elegant" --domain typography
```

## 交互行为对标站（默认就要学，不等用户给参考站）

**交互不是想出来的，是照行业默认做的。** 动手前先打开下面的站真操作一遍（滚一滚、点一点、收起展开一次），记下行为再对照本站。自己发明的交互多半是退步——用户早被成熟站训练过。

| 站 | 学什么（学行为，不是学配色） |
|---|---|
| 稀土掘金 | 下滚时搜索框与头部自动收起、上滚复现；列表页筛选栏吸顶；滚动方向决定显隐 |
| 知乎 | 下滑立刻吸顶显示文章标题（含进度）；长文滚动时当前位置可见；返回时位置保持 |
| 少数派 | 长文目录吸顶与当前节高亮；主题切换不闪白；图片加载占位不顶开版面 |
| 思否 / SegmentFault | 搜索建议下拉支持键盘上下选与 Esc 关闭；标签切换保持滚动位置 |
| GitHub / MDN | 文件树与目录 sticky；锚点跳转不被顶栏盖住（留 `scroll-margin-top`）；当前节高亮跟随滚动 |
| 掘金 / 知乎（移动端） | 面包屑反映层级且每层可点回；筛选、排序、Tab 状态写进 URL，刷新与分享链接后仍保持；移动端左右滑动切 Tab 或返回、下拉刷新 |

学的是**行为**：滚动怎么响应、状态怎么保持、焦点去哪、什么时机收起展开。视觉风格（配色、圆角、字体）一律照本项目 token，不照抄对标站。

## 待补

未核实来源（Refactoring UI 条目、Nielsen 十条、Gestalt 原则）：规则暂按上面已读来源 + 本项目实测写，别当依据引用。
