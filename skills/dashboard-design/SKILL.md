---
name: dashboard-design
description: This skill should be used when creating data dashboards, visualization reports, data long-image pages, or operational cockpits. Provides a complete design system with ice-blue glassmorphism aesthetic, CSS design tokens, animated background glow, material system, layout grids, chart type selection guide, dimension specifications, color palette, and interactive components. Triggers on keywords such as 数据看板, dashboard, 可视化, 报表, 大屏, 数据页面, 看板原型, 运营驾驶舱, data visualization.
---

# 数据看板 / 可视化报表设计规范

> 适用于：制作数据看板、可视化报表、数据长图、运营驾驶舱类页面时遵循的统一设计规范。
> 风格定位：冰蓝毛玻璃 · 柔光渐变 · 轻质浮层 · 呼吸感留白。

---

## 〇、视觉风格总纲

整体风格关键词：**冰蓝毛玻璃 · 柔光渐变 · 轻质浮层 · 呼吸感留白**。
设计语言偏向 Apple Human Interface Guidelines 的"材质"理念——半透明叠加、饱和度增强模糊、极浅投影、大圆角、渐变光晕背景。

---

## 一、背景与氛围层

### 1.1 页面背景（必须完整还原）
```css
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC',
               'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
  color: #1a2332;
  min-height: 100vh;
  position: relative;
  background:
    radial-gradient(ellipse 800px 600px at 15% 10%, rgba(165,195,245,.55), transparent 60%),
    radial-gradient(ellipse 700px 500px at 85% 20%, rgba(140,175,235,.5),  transparent 60%),
    radial-gradient(ellipse 900px 700px at 50% 60%, rgba(175,200,250,.55), transparent 65%),
    radial-gradient(ellipse 600px 500px at 80% 75%, rgba(210,190,240,.45), transparent 60%),
    radial-gradient(ellipse 650px 500px at 20% 80%, rgba(150,185,240,.5),  transparent 60%),
    linear-gradient(135deg, #edf2fb 0%, #e8eef8 100%);
  background-attachment: fixed;
}
```
- 5 层椭圆径向渐变叠加在 135° 线性底色上，营造不均匀的冰蓝-淡紫光晕
- `background-attachment: fixed` 保证滚动时背景不动，产生视差深度

### 1.2 浮动光球（呼吸动画）
```css
body::before, body::after {
  content: '';
  position: fixed;
  border-radius: 50%;
  pointer-events: none;
  z-index: 0;
  filter: blur(60px);
}
body::before {
  width: 700px; height: 700px; top: -150px; left: -100px;
  background: radial-gradient(circle, rgba(160,190,245,.4), transparent 70%);
  animation: float1 22s ease-in-out infinite;
}
body::after {
  width: 650px; height: 650px; bottom: -200px; right: -100px;
  background: radial-gradient(circle, rgba(160,170,235,.35), transparent 70%);
  animation: float2 26s ease-in-out infinite;
}
@keyframes float1 {
  0%,100% { transform: translate(0,0) scale(1) }
  50%     { transform: translate(60px,40px) scale(1.08) }
}
@keyframes float2 {
  0%,100% { transform: translate(0,0) scale(1) }
  50%     { transform: translate(-50px,-60px) scale(1.1) }
}
```
- 两个 700/650px 的模糊圆形光球，60px 高斯模糊，缓慢浮动
- 动画周期 22s/26s 错开，避免同步感

---

## 二、设计令牌（Design Tokens）

### 2.1 CSS 变量（必须原样使用）
```css
:root {
  /* 卡片 */
  --card: rgba(255,255,255,.45);
  --card-hover: rgba(255,255,255,.6);
  --card-solid: #fff;
  /* 边框 */
  --border: rgba(255,255,255,.5);
  --border-soft: rgba(200,210,230,.35);
  /* 文字三级 */
  --text:  #1a2332;   /* 标题/主体数值 */
  --text2: #5a6a80;   /* 卡片标题/次要文字 */
  --text3: #8c9ab0;   /* 标签/辅助说明 */
  /* 色板 */
  --blue:  #4a7cff;
  --blue2: #6c9cff;
  --green: #22c55e;
  --amber: #f59e0b;
  /* 圆角 */
  --radius:    18px;   /* 卡片 */
  --radius-sm: 10px;   /* 按钮/输入框/小组件 */
  /* 阴影 */
  --shadow:    0 4px 24px rgba(80,100,160,.08);
  --shadow-lg: 0 12px 40px rgba(80,100,160,.12);
}
```

### 2.2 色彩语义
| 用途 | 色值 | 说明 |
|------|------|------|
| 主色 | `#4a7cff` | 蓝，链接/按钮/选中态/装饰线默认色 |
| 辅色 | `#6c9cff` | 浅蓝，渐变终点/图表第二色 |
| 成功/增长 | `#22c55e` | 绿 |
| 警告/次分类 | `#f59e0b` | 琥珀橙 |
| 独立模块 | `#c084fc` | 紫，仅在独立图表中单独使用 |
| 补充色 | `#14b8a6` | 青 |
| 同图第二色 | `#f59e0b` / `#d97706` | 蓝+X 同图时用橙，**不用紫** |

### 2.3 字体体系
| 层级 | 字号 | 字重 | 色值 |
|------|------|------|------|
| 一级标题（section-title） | 17px | 700 | --text |
| 卡片标题 | 14px | 600 | --text2 |
| 数值（大） | 22-26px | 800 | --text |
| 数值单位 | 11-13px | 500 | --text3 |
| 标签/说明 | 11px | 400 | --text3 |
| 正文/表格 | 13px | 400 | --text |
| 增长标记 | 10.5px | 500 | --green / 红 |

---

## 三、毛玻璃材质系统

### 3.1 卡片
```css
.card {
  background: var(--card);                    /* rgba(255,255,255,.45) */
  backdrop-filter: saturate(180%) blur(20px);
  -webkit-backdrop-filter: saturate(180%) blur(20px);
  border: 1px solid var(--border);            /* rgba(255,255,255,.5) */
  border-radius: var(--radius);               /* 18px */
  padding: 20px 24px;
  box-shadow: var(--shadow);
  transition: all .3s;
}
.card:hover {
  background: var(--card-hover);              /* rgba(255,255,255,.6) */
  box-shadow: var(--shadow-lg);
  transform: translateY(-1px);
}
```
- 关键：`saturate(180%) blur(20px)` 先增饱和再模糊，颜色更鲜润
- 边框半透明白，和背景光晕融合

### 3.2 顶部导航栏
```css
.topbar {
  position: sticky; top: 0; z-index: 300;
  background: rgba(255,255,255,.4);
  backdrop-filter: saturate(180%) blur(20px);
  border-bottom: 1px solid var(--border);
}
```

### 3.3 控件（筛选器/按钮）
```css
.control {
  background: rgba(255,255,255,.55);
  backdrop-filter: blur(10px);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);            /* 10px */
}
```

### 3.4 弹出面板（时间选择器/下拉菜单）
```css
.panel {
  background: rgba(255,255,255,.95);          /* 接近不透明，保证可读 */
  backdrop-filter: saturate(180%) blur(20px);
  border: 1px solid var(--border);
  border-radius: 12px;
  box-shadow: 0 12px 40px rgba(30,40,60,.15); /* 比卡片更深 */
}
```

---

## 四、整体布局原则

### 4.1 页面结构
- 顶部 sticky 导航栏（logo + 视图切换 + 筛选器 + 导出按钮）
- 按业务模块分 section，每个 section 有 `section-title` 一级标题
- 内容区 max-width 1280px 居中，大屏一屏可看完主体
- 底部 footer 标注数据截止时间和更新频率

### 4.2 卡片标题装饰
- 所有卡片标题带左侧竖线（`::before` 伪元素，3px × 14px，圆角 2px）
- 不同 section 用不同颜色，避免全蓝单调
- 标题居左，筛选器（日/周/月）用 `margin-left:auto` 推到右端

### 4.3 栅格比例
- 两张同类图表并排：`1fr 1fr` 等宽
- 左图右列表：`3fr 2fr` 或 `2fr 3fr`
- 左小指标 + 右大图表：`1fr 2fr`
- 三列等宽：`repeat(3, 1fr)`
- 并排卡片默认 stretch 撑满同行高度
- 移动端断点 1024px / 640px 逐级单列

---

## 五、图表规范

### 5.1 尺寸与比例
- **折线/柱状/堆叠/面积图**：`aspect-ratio: 2/1` + `min-height: 180px`
- **饼图/环图**：方形 canvas 居中，不随卡片拉伸
- **地图（ECharts）**：360-400px 高，zoom 放大主体
- **热力图**：标题在顶部，图表用 flex wrapper 在剩余空间垂直居中

### 5.2 地图交互
- hover 保持 visualMap 原色（`areaColor: 'inherit'`），只叠加白色描边 + 阴影
- 禁用 select 态

### 5.3 环图交互
- 点击色块联动细分图表/列表
- 图例可点击高亮

### 5.4 图表选型速查

根据**数据性质 → 图表类型**选择，不要乱配：

| 数据需求 | 推荐图表 | 说明 |
|---------|---------|------|
| 时间序列趋势（UV/PV、日活、某指标随日期变化） | **折线图** | 平滑曲线 + 渐变填充，多指标叠加用不同色折线 |
| 多时间点对比累积量（新增 vs 累计） | **面积图**（堆叠/重叠） | 趋势感 + 量级感 |
| 分类对比（对象排行、来源量级） | **水平条形图** 或 **表格** | 类别多（>5）用表格+进度条，少用柱状 |
| 结构占比（两/三/四分类的比例） | **环图**（doughnut，cutout 70%） | 不用饼图实心；2-4 类别最合适 |
| 细分下钻（一级分类 → 二级明细） | **双环联动** 或 **环图 + 图例列表** | 左主图点击联动右细分图 |
| 目标完成度 / 进度 | **水平堆叠进度条** | 已完成段 + 待完成段；不用 Gauge |
| 地域分布 | **ECharts 中国地图**（choropleth） | visualMap 蓝色深浅，禁用 select |
| 时段分布（24 小时） | **热力格子** 12×2 网格 | 不用 ECharts heatmap，CSS grid 即可 |
| 转化漏斗（曝光→点击→转化） | **水平漏斗** 或 **条形阶梯** | 每级显示绝对值+转化率 |
| 多指标并列（多个核心数字） | **指标卡网格** stat-metric | 不画图，大数值+标签 |
| 文本型排行 / 榜单 | **表格**（detail-table） | 序号、名称、多列数值，支持分页 |
| 留存率（次日/7日/30日） | **大数字 + 标签** retention-item | 不画图，简洁明确 |

选型红线：
- **禁用 3D 图表**、**禁用雷达图**（除非明确要求）、**禁用词云**
- 类别 ≥ 6 时不用饼/环图，改用表格或条形
- 时间序列 ≥ 2 个指标时优先折线，不用分组柱状
- 占比类图表旁必配**图例 + 数值百分比**，不能只看颜色

### 5.5 图表排布宽高规范

**单张图表的容器尺寸**（卡片内的 chart-wrap）：
| 图表类型 | 宽度 | 高度规则 | min-height |
|---------|------|---------|-----------|
| 折线/柱状/面积 | 100% | `aspect-ratio: 2/1` | 180px |
| 环图（单个） | `width: 130-160px` 方形 | 同宽 | — |
| 双环并列 | 每侧各占 50% | canvas-box 130×130 固定 | — |
| 中国地图 | 100% | 固定 `360-400px` | 360px |
| 热力图（24×2） | 100% | 按 `repeat(12,1fr)` gap:4px 自然撑开 | — |
| 漏斗图 | 100% | 每级 `36-42px` 高 × N 级 | — |

**卡片内嵌多元素时的行高**：
- 卡片 padding: `20px 24px`
- 卡片标题 margin-bottom: 16px
- 图表和下方说明文字（图例/时间轴标签）间距: 6-8px
- 指标网格（stat-group-body）行间距: 10-14px

**并排卡片的行高对齐**：
- 默认 stretch 撑满同行最高者
- 内部图表用 flex wrapper 居中填充剩余空间
- 双环图所在卡片比表格卡片短时，不要硬拉高，让高度自然差

**响应式断点下的图表缩放**：
- `max-width: 1024px`：双列变单列，图表宽度自动扩展到满宽，高度按 aspect-ratio 重算
- `max-width: 640px`：地图高度可降至 280px；环图 canvas 降至 110×110
- 所有 Chart.js 实例必须设 `maintainAspectRatio: false` + `responsive: true`

### 5.6 迭代红线：新增/调整卡片时必做检查

每次新增卡片、新增横向数据、改变栅格比例时，**必须显式检查以下三项**：

| 检查项 | 要求 |
|--------|------|
| **grid/flex 容器的 gap** | 不仅设 `grid-template-columns`，必须同时设 `gap`（建议 14-18px）；单列布局下 gap 变成上下间距，同样必须合理 |
| **响应式断点覆盖** | inline style 的 grid 布局必须换成 class，以便在 `@media(max-width:1024px)` 下覆盖为单列；忘记覆盖会导致移动端拥挤 |
| **卡片 class 是否与看板风格匹配** | B 端用 `.stat-group-body` / `.stat-metric`，产品看板用 `.health-grid` / `.health-metric` / `.ai-stat-row`，不要混用（混用会塌样式） |

**常见翻车**：
- 只改列数没加 gap → 卡片紧贴或间距不均
- inline style 写死 grid → 移动端仍然挤成多列不可读
- B 端的 class 拿到产品看板用 → 样式没生效导致布局崩坏

---

## 六、数据指标卡片

### 6.1 统一样式
- 数值 22px / 800 / 居左
- 单位 11px / 500 / --text3
- 标签 11px / --text3 / margin-top 4-6px
- 增长标记 10.5px / 绿或红 / 同行
- **严禁居中**

### 6.2 分组
- stat-group 分组，grid 2-3 列
- 分组标题带竖线装饰
- **不加虚线分隔**

---

## 七、列表与分页

- 每页 **5 行**（双列时 10 条）
- 极简分页器 `‹ 1/N ›` 居中
- 排行前 3 用圆形彩色序号

---

## 八、图片网格

- 小尺寸模式：8 列、1:1 方形、5px gap、圆角 5px
- 叠加用户昵称 + 日期（9px/8px 缩小字号）
- 概览 1 行（8 张）、详情 3 行（24 张）
- 带分页器

---

## 九、交互组件

### 9.1 时间选择器
- 320px 毛玻璃面板、日期范围输入 → 单月日历 → 快捷按钮（一行 nowrap）→ 取消/确定
- 选中态蓝底白字、区间浅蓝底

### 9.2 视图切换器
- logo icon 30×30 + 视图名 + ▽ + 副标"点击切换视图"
- 毛玻璃下拉菜单

### 9.3 对象选择器（单选 + 搜索）
- 点击弹出带搜索框的单选列表
- 列表按热度/权重降序
- 仅展示对象名，选中态蓝色 + 勾
- 支持白名单过滤（如仅显示当前用户有权限的对象）

---

## 十、视觉禁忌

| 禁止项 | 说明 |
|--------|------|
| 居中数据指标 | 一律居左 |
| 标题下虚线 | 不加 dashed border |
| 无意义 badge | 不加装饰标签 |
| 地图 hover 变色 | 只描边阴影 |
| 图表写死高度 | 用 aspect-ratio |
| 冗余前缀 | 子标题去重复 |
| 过大占位图 | 小尺寸 |
| 内部过程信息 | 不写进输出物 |
| 纯白/纯灰背景 | 必须用冰蓝渐变光晕背景 |
| 实色不透明卡片 | 必须用半透明毛玻璃 |
| 粗黑边框 | 边框只用半透明白/浅灰 |

---

## 十一、技术栈

- Chart.js 4.x（折线/柱状/环图）
- ECharts 5.x（中国地图、热力图）
- 纯 CSS Grid/Flex，无 UI 框架
- 单 HTML 自包含（CSS + JS inline）
- `createPager()` 统一分页
