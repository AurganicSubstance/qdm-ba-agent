---
name: user-analysis
description: 生鲜超市用户 RFM 分层分析（V3）。触发：用户说"用户分析"、"三高用户"、"RFM"、"用户分层"、"用户流转"、"策略人群"、"行动版报告"时使用。生成骨架报告后 AI 润色为两章结构业务报告（数据总览 + 执行策略），PDF 单页连续 + 自动目录。
---

## 概述

V3 版用户分析：RFM 分层 → 骨架报告 → AI 润色（两章结构）→ PDF（单页连续 + 目录）。

---

## 执行步骤

### Step 1: 计算取数周期

> 详见 [references/config.md](references/config.md)

```python
from src.tools.date_utils import get_valid_analysis_periods, load_invalid_days

invalid_days = load_invalid_days()
periods = get_valid_analysis_periods("2026-04-02", invalid_days=invalid_days)
```

### Step 2: 获取数据

> 使用 `skills/data-query/SKILL.md` 中的方法

```python
from src.tools.db_connector import create_connector_from_config

db = create_connector_from_config()
data = db.get_user_order_data(
    start_date=periods["sql_date_range"]["start"],
    end_date=periods["sql_date_range"]["end"],
    invalid_days=list(invalid_days)
)
```

### Step 3: 计算 RFM + 人群分布

> 人群定义见 [references/segments.md](references/segments.md)

```python
from src.analyzers.user_analyzer import UserAnalyzer

analyzer = UserAnalyzer()
current_rfm = analyzer.compute_rfm(current_data, data_end_date, start_date=current_start)
prev_rfm = analyzer.compute_rfm(prev_data, prev_end, start_date=prev_start)

segment_counts = analyzer.get_segment_counts(current_rfm)
current_sales = analyzer.compute_segment_sales(current_rfm)
flow_results = analyzer.compute_flow(prev_rfm, current_rfm)
```

### Step 4: 三高用户分层归因

拆解三高用户为保留/新晋/流失三组：

```python
retention_analysis = analyzer.analyze_high_value_retention(prev_rfm, current_rfm)
# → retained_count, new_joiners_count, churned_count
# → retained_curr_arpu, retained_prev_arpu, new_joiners_arpu, churned_prev_arpu
```

### Step 5: 保留三高 ARPU 增量拆解

按品类和 SKU 拆解，按大类分组（生鲜/新场景/标品）：

```python
retained_increment = analyzer.analyze_retained_increment(
    prev_rfm=prev_rfm, curr_rfm=current_rfm,
    category_field="categoryLevel1Description", top_n=10, min_users=3
)
# → category_increment, sku_increment, sku_by_group
```

### Step 6: 流失三高品类消费分析

```python
churned_decrement = analyzer.analyze_churned_decrement(
    prev_rfm=prev_rfm, curr_rfm=current_rfm,
    category_field="categoryLevel1Description", top_n=10, min_users=3
)
```

### Step 7: P2 羊毛党分层 + 品类结构

> 羊毛党定义见 [references/segments.md](references/segments.md)

```python
p2_classification = analyzer.classify_p2_users(prev_rfm, current_rfm)
# → bargain_hunters_count, normal_count, normal_user_ids

# 品类结构对比（P2 排除羊毛党）
current_category_dist = {}
for seg in ["三高用户", "高M低F高R", "低M高F高R", "高M高F低R"]:
    user_filter = p2_classification.get("normal_user_ids") if seg == "低M高F高R" else None
    current_category_dist[seg] = analyzer.compute_segment_category_distribution(current_rfm, seg, user_filter)
# → groups（大类占比）, categories（中类占比）, categories_freq（人均购买频次）
```

### Step 8: 策略人群升级分析

> F1 评分 + 转化提升度见 [references/f1_scoring.md](references/f1_scoring.md)

对 P1/P2(非羊毛党)/P3 分析升级因素 + 品类驱动 + SKU 推荐：

```python
for seg in ["高M低F高R", "低M高F高R", "高M高F低R"]:
    user_filter = p2_classification.get("normal_user_ids") if seg == "低M高F高R" else None

    upgrade = analyzer.analyze_upgrade_factors(prev_rfm, current_rfm, seg, "三高用户", user_filter)
    category_f1, _ = analyzer.analyze_category_f1(prev_rfm, current_rfm, seg, "三高用户",
        category_field="categoryLevel1Description", min_users=10)
    sku_lift, _, _, _, sku_by_category = analyzer.analyze_sku_conversion_lift(
        prev_rfm, current_rfm, seg, "三高用户", min_buyers=5, top_n=15)
```

### Step 9: 生成报告

> 报告结构见 [references/report_template.md](references/report_template.md)

```bash
# 完整分析（推荐，骨架+润色+PDF）
python scripts/run_complete_analysis.py --date 2026-04-02
```

---

## V3 关键规则

1. **P2 标签一致**：凡涉及 P2 品类/消费/升级，一律写"P2 非羊毛党"，唯一例外是人群分布表人数
2. **P2 拆行**：人群分布表中 P2 必须拆成非羊毛党和羊毛党两行（缩进显示）
3. **流失对比口径**：流失三高品类占比对比**必须用"保留三高"数据**，禁止用"本期三高"全量
4. **加粗范围**：只加粗人群名称（**三高用户**、**P1** 等），禁止将占比/品类/括号纳入加粗
5. **第一章纯数据**：表格下方不添加任何说明文字、注释、脚注
6. **策略标题格式**：升级根因/流失根因等标题用纯文本，不用 `**` 加粗

---

## 运行命令

```bash
# 完整分析（推荐）
python scripts/run_complete_analysis.py --date 2026-04-02

# 仅骨架报告
python scripts/run_user_analysis.py --date 2026-04-02

# 单独润色
python scripts/call_glm5.py --date 2026-04-02

# PDF 生成（单页连续 + 自动目录）
python scripts/md_to_pdf.py reports/action_analysis_20260402.md
```

---

## 依赖

- **数据获取**: `skills/data-query/SKILL.md`
- **底表**: `store_transaction_details`
- **RFM 阈值**: M≥135元, F≥5次, R≤7天
- **羊毛党定义**: 5元以下商品占比 > 80%
