# 用户人群定义

## 8 类人群矩阵

| 人群 | M | F | R | 特征 |
|-----|---|---|---|------|
| **三高用户** | 高 | 高 | 高 | 核心用户，高消费高频次高活跃 |
| **高M低F高R** | 高 | 低 | 高 | 高消费低频次，有提升空间 → **P1** |
| **低M高F高R** | 低 | 高 | 高 | 频次高消费低，客单价低 → **P2** |
| **高M高F低R** | 高 | 高 | 低 | 曾是优质用户，有流失风险 → **P3** |
| 高M低F低R | 高 | 低 | 低 | 高价值流失用户 |
| 低M高F低R | 低 | 高 | 低 | 频次高但已流失 |
| 低M低F高R | 低 | 低 | 高 | 新用户或低价值活跃 |
| 低M低F低R | 低 | 低 | 低 | 低价值流失用户 |

---

## 策略人群（P1/P2/P3）

| 策略 | 人群 | 目标 | 营销方向 |
|-----|-----|------|---------|
| **P1** | 高M低F高R | 提ARPU（主攻频次）→ 三高 | 高客单用户推复购 |
| **P2** | 低M高F高R | 提ARPU（频次或客单价）→ 三高 | 高频用户推高客单 |
| **P3** | 高M高F低R | 召回激活 → 三高 | 流失用户激活召回 |

---

## P2 羊毛党分层

**定义**：5元以下商品占比 > 80%

| 分组 | 说明 |
|-----|------|
| 羊毛党 | 主要买低价商品，升级率极低 |
| 非羊毛党 | 正常消费行为，有升级潜力 |

> P2 所有升级分析**排除羊毛党**，仅针对非羊毛党。人群分布表中 P2 人数为全量（含羊毛党）。

```python
p2_classification = analyzer.classify_p2_users(prev_rfm, current_rfm)
# → bargain_hunters_count, normal_count, normal_user_ids
# → bargain_hunters_upgrade_rate, normal_upgrade_rate
```

---

## 升级分析对比组

| 分组 | 定义 | 用途 |
|-----|------|------|
| 升级组 | 上期为 source_segment，本期升级为 target_segment | 成功升级的用户 |
| 保持不变组 | 上期为 source_segment，本期仍为 source_segment | 对比基准 |

> P2 的升级分析使用 `user_filter=p2_classification["normal_user_ids"]` 排除羊毛党。

---

## 三高用户分层

| 分组 | 定义 |
|-----|------|
| 保留三高 | 上期三高且本期仍为三高 |
| 新晋三高 | 上期非三高，本期升级为三高 |
| 流失三高 | 上期三高，本期不再为三高 |

```python
retention_analysis = analyzer.analyze_high_value_retention(prev_rfm, current_rfm)
# → retained_count, new_joiners_count, churned_count
# → retained_curr_arpu, retained_prev_arpu, new_joiners_arpu, churned_prev_arpu
```
