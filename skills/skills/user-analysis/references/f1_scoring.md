# 品类驱动分析方法

## 三级分析维度

| 维度 | 字段 | 用途 |
|-----|------|------|
| 品类 | `categoryLevel1Description` | 识别核心驱动品类 |
| SPU | `categoryLevel3Description` | 识别细分品类机会 |
| SKU | `articleName` | 精确到商品推荐 |

---

## 指标定义

### F1 评分

| 指标 | 定义 |
|-----|------|
| P (精确率) | 购买该品类的用户中，升级的比例 |
| R (召回率) | 升级的用户中，购买过该品类的比例 |
| **F1** | 2 × P × R / (P + R) |

### 转化提升度

```
转化提升度 = 购买者升级率 − 未购买者升级率
```

含义：买了该品类的用户比没买的用户，升级率高出多少个百分点。值越高说明该品类与升级行为关联越强。

### 综合排名（SKU 维度）

```
综合排名 = 排名(转化提升度) + 排名(F1)
```

- 品类维度：样本量足够，直接用**转化提升度**排序
- SKU 维度：样本量往往不足，必须用**综合排名**避免单靠提升度得出不置信的结论

---

## 代码

```python
from src.analyzers.user_analyzer import UserAnalyzer

analyzer = UserAnalyzer()

# 品类维度 F1 + 转化提升度
category_f1, _ = analyzer.analyze_category_f1(
    data=order_data,
    prev_rfm=prev_rfm,
    curr_rfm=current_rfm,
    source_segment="高M低F高R",
    target_segment="三高用户",
    category_field="categoryLevel1Description",
    min_users=10
)

# SKU 转化提升度 + 综合排名
sku_lift, _, _, _, sku_by_category = analyzer.analyze_sku_conversion_lift(
    prev_rfm=prev_rfm,
    curr_rfm=current_rfm,
    source_segment="高M低F高R",
    target_segment="三高用户",
    min_buyers=5,
    top_n=15
)
```

返回字段（品类）：

| 品类 | 购买人数 | 升级人数 | 提升度 | P | R | F1 |
|-----|---------|---------|-------|---|---|-----|

返回字段（SKU）：

| SKU | 品类 | 购买人数 | 购买者升级率 | 提升度 | 综合排名 |
|-----|-----|---------|------------|-------|---------|

---

## 贡献度拆解

```
ARPU = 频次 × 客单价 = 频次 × 件单数 × 件单价
```

主因判断：贡献度绝对值大的是主因。

```python
upgrade = analyzer.analyze_upgrade_factors(
    prev_rfm=prev_rfm,
    curr_rfm=current_rfm,
    source_segment="高M低F高R",
    target_segment="三高用户"
)
# → contribution: freq_contribution_pct, price_contribution_pct
# → 客单价内部: items_contribution_pct, item_price_contribution_pct
```
