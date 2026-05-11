---
name: category-analysis
description: 品类经营周报和品类下钻分析。触发：用户说"品类分析"、"品类周报"、"经营周报"、"营采销周会"、"品类战队"、"品类表现"时使用。生成多周趋势对比 + 战队视角的营采销周报，以及三级下钻品类报告。
---

## 概述

生成面向老板和管理层的**营采销周会**经营周报，包含多周趋势对比 + 本周战队视角分析。

**场景**：每周四生成周报，汇报各战队品类表现
**周期**：周四至周三为一周，分析日期为周四，数据截止周三（T-1）
**输出**：骨架报告（6张表）→ AI 润色 → 完整报告 → PDF

---

## 两条流水线

### 1. 经营周报（多周趋势 + 战队汇总）

```
scripts/run_weekly_report.py → 骨架（6张表）
scripts/call_glm5_category.py → 润色报告 + 评分
```

核心分析器：`src/analyzers/weekly_report_analyzer.py`

### 2. 品类下钻报告（三级下钻）

```
scripts/run_category_analysis.py → JSON 数据（已删除，功能合并到周报）
scripts/call_glm5_category.py    → 润色报告 + 评分
```

核心分析器：`src/analyzers/category_analyzer.py`

---

## 执行步骤（经营周报）

### Step 1: 计算周期

> 周期定义见 [references/metrics.md](references/metrics.md)

```python
from src.analyzers.weekly_report_analyzer import WeeklyReportAnalyzer

analyzer = WeeklyReportAnalyzer(None)
weeks = analyzer.get_multi_week_periods("2026-04-01", start_date="2026-02-25")
trend_weeks = [w for w in weeks if w["days"] >= 5]  # 过滤不完整周
current_week = weeks[-1]
last_week = analyzer.get_last_week(current_week)
```

### Step 2: 获取数据

> 使用 `skills/data-query/SKILL.md` 中的方法

```python
from src.tools.db_connector import create_connector_from_config

db = create_connector_from_config()
analyzer.db = db

# 一次查询覆盖全部日期范围
store_data = analyzer.get_store_data(range_start, range_end)
category_data = analyzer.get_category_data(range_start, range_end)
new_old_data = analyzer.get_new_old_customer_data(range_start, range_end)
cat_cust_data = analyzer.get_category_customer_data(range_start, range_end)
```

### Step 3: 加载配置

> 品类映射见 [references/category_mapping.md](references/category_mapping.md)

```python
remapping = analyzer.load_remapping()     # config/category_remapping.json
targets = analyzer.load_targets(week_label)  # config/category_targets.json
```

### Step 4: 计算周趋势

```python
trends = analyzer.compute_weekly_trends(trend_weeks, store_data, category_data, new_old_data)
# → sales_table, category_table, category_rate_table
```

### Step 5: 计算本周品类汇总（战队视角）

```python
tables = analyzer.compute_current_week_tables(
    current_week, last_week, store_data, category_data, targets,
    cat_cust_data=cat_cust_data, new_old_data=new_old_data
)
# → category_summary, daily_detail, category_traffic
```

### Step 6: 计算附加指标

```python
# 频次趋势（多周人均购买天数/周）
frequency_data = analyzer.get_category_frequency(range_start, range_end)

# 复购率（次周复购率，逐周）
repurchase_data = analyzer.get_all_category_repurchase_rates(trend_weeks)

# SKU 对比（本周 vs 上周 TOP SKU）
sku_comparison = analyzer.get_sku_comparison(current_week, last_week)
```

### Step 7: 生成骨架报告

```python
report = analyzer.generate_report(
    week_label, current_week, trends, tables,
    sku_data=sku_data, frequency_data=frequency_data,
    repurchase_data=all_repurchase_data, sku_comparison=sku_comparison
)
# → Markdown 骨架（6张表，纯数据无文字分析）
```

### Step 8: AI 润色

使用 `src/llm/prompts/category.py` 中的 `WEEKLY_REPORT_PROMPT` 提示词润色骨架。

> 报告结构见 [references/report_template.md](references/report_template.md)

---

## 战队配置

```python
TEAM_ORDER = [
    ("求实", ["冷藏乳品", "猪肉类", "牛羊禽", "热出熟食"]),
    ("飞哥", ["水果类"]),
    ("永亮", ["蔬菜类", "蛋类"]),
    ("凡姐", ["烘焙类"]),
    ("公用", ["水产类", "标品类", "冷冻", "冷藏加工", "干货调味", "酒水饮料"]),
]
```

> 完整品类映射见 [references/category_mapping.md](references/category_mapping.md)

---

## 运行命令

```bash
# 一键运行（推荐）：骨架 + 润色 + PDF
python scripts/run_complete_category.py --date 2026-04-03

# 仅骨架报告
python scripts/run_weekly_report.py --date 2026-04-03

# 单独润色
python scripts/call_glm5_category.py --date 2026-04-03

# PDF 生成
python scripts/md_to_pdf.py reports/xxx.md
```

---

## 输出文件

输出目录：`reports/品类分析/`

| 类型 | 命名规则 |
|------|---------|
| 骨架报告 | `weekly_report_{YYYYMMDD}.md` |
| 润色报告 | `weekly_report_{YYYYMMDD}_polished.md` |
| 审查评分 | `*.review.json` |
| PDF | `*.pdf` |

---

## 依赖

- **数据获取**: `skills/data-query/SKILL.md`
- **底表**: `strategy_fm_levels_result`, `store_transaction_details`
- **品类映射**: `config/category_remapping.json`
- **目标配置**: `config/category_targets.json`
- **润色提示词**: `src/llm/prompts/category.py`
