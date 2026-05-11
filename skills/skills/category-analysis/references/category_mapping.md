# 品类战队映射

## 报表品类（14个）

按战队顺序：

| 战队 | 报表品类 | 数据库来源（L3 小分类） |
|------|---------|----------------------|
| **求实** | 冷藏乳品 | 冷藏乳品类 |
| | 猪肉类 | 猪分割肉类、猪副件类、猪骨类、边猪类、猪内脏类等 |
| | 牛羊禽 | 牛肉类、羊肉类、鸡类、鸭类、其他禽类等 |
| | 热出熟食 | 即食类、即烹类等 |
| **飞哥** | 水果类 | 仁果类、柑橘类、核果类、浆果类、热带果类、瓜类等 |
| **永亮** | 蔬菜类 | 叶菜结球类、根茎类、瓜果类、菌菇类、调味类、净配菜类 |
| | 蛋类 | 蛋类 |
| **凡姐** | 烘焙类 | 烘焙类 |
| **公用** | 水产类 | 海水鱼类、淡水鱼类、虾蟹类、贝类等 |
| | 标品类 | 休闲零食类、方便速食类、日杂用品类、粮油副食类、调味品类、酒类等 |
| | 冷冻 | 冷冻食品类、冰淇淋类等 |
| | 冷藏加工 | 即热类、即烹类、米面制品类、肉制品类、豆制品类等 |
| | 干货调味 | 干货类、调味品类 |
| | 酒水饮料 | 酒类、饮料类 |

---

## 重分类机制

数据库 `category_level3_description`（L3 小分类）通过 `config/category_remapping.json` 映射到上表的 14 个报表品类。

```python
# weekly_report_analyzer.py / category_analyzer.py
remapping = analyzer.load_remapping()  # 加载映射
report_cat = analyzer.apply_remapping(l3_category)  # L3 → 报表品类
```

---

## SQL 查询

```sql
-- 品类级数据（小分类，需重分类）
SELECT
    business_date,
    category_level3_description AS l3_category,
    total_sale_amount,
    total_customer_count,
    full_link_profit_amount
FROM default_catalog.ads_business_analysis.strategy_fm_levels_result
WHERE business_date >= '{start}' AND business_date <= '{end}'
  AND level_description = '小分类'
  AND day_clear = '1'
  AND category_level3_description IS NOT NULL
  AND category_level3_description != ''
```

---

## MECE 校验

14 个报表品类覆盖所有有效 L3 小分类，互斥且完备。未映射的 L3 会被排除或归入对应品类。
