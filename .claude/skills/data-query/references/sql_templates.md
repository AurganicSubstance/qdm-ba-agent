# SQL 查询模板

## 1. 查询用户订单明细（RFM 分析用）

> ⚠️ 实际使用封装方法 `db.get_user_order_data()` 即可，已内置品类重分类。以下为等效 SQL。

```sql
SELECT
    thirdparty_user_identity,
    customer_phone,
    order_id,
    pay_at,
    sales_amt,
    channel,
    abi_article_id,
    article_name,
    category_level2_description,
    category_level3_description,
    -- 品类重分类：统一为翠花标准品类
    CASE
        WHEN category_level2_description IN ('蛋类','烘焙类') THEN category_level2_description
        WHEN category_level2_description IN ('冷藏奶制品类','饮料类') THEN '乳制品及水饮类'
        WHEN category_level1_description = '肉禽蛋类' AND category_level2_description <> '蛋类' THEN '肉禽类'
        WHEN RIGHT(category_level3_description, 2) = '熟食' THEN '熟食类'
        WHEN category_level1_description IN ('冷藏及加工类','预制菜') THEN '冷藏加工及预制菜类'
        ELSE category_level1_description
    END AS category_level1_description
FROM default_catalog.ads_business_analysis.store_transaction_details
WHERE DATE(pay_at) >= '{start_date}'
  AND DATE(pay_at) <= '{end_date}'
  -- 排除无效日期（节假日）
  AND DATE(pay_at) NOT IN ('2026-01-29', '2026-02-01')
ORDER BY pay_at DESC
```

---

## 2. 品类级 SKU 汇总（品类分析用）

```sql
SELECT
    business_date,
    category_level1_description AS category,
    category_level2_description AS sub_category,
    sku_id,
    category_name AS sku_name,
    SUM(total_sale_amount) AS sales,
    SUM(total_sale_qty) AS qty,
    SUM(total_customer_count) AS customers
FROM default_catalog.ads_business_analysis.strategy_fm_levels_result
WHERE business_date >= '{start_date}'
  AND business_date <= '{end_date}'
  AND level_description = 'sku'
  AND day_clear = '1'
  AND category_level1_description IS NOT NULL
  AND category_level1_description != ''
GROUP BY business_date, category_level1_description, category_level2_description, sku_id, category_name
```

**注意**：
- `level_description = 'sku'`：必须加，否则会包含品类级聚合行导致重复计算
- `day_clear = '1'`：只取日清结算数据，排除未结算数据

---

## 3. 门店日级汇总（经营周报用）

```sql
SELECT
    business_date,
    SUM(total_sale_amount) AS sales,
    SUM(total_customer_count) AS customers,
    SUM(full_link_profit_amount) AS profit
FROM default_catalog.ads_business_analysis.strategy_fm_levels_result
WHERE business_date >= '{start_date}'
  AND business_date <= '{end_date}'
  AND level_description = 'sku'
  AND day_clear = '1'
GROUP BY business_date
ORDER BY business_date
```

> ⚠️ **注意**：上面这个模板的客流是 SKU 级汇总，**不是去重客流**，不能直接算客单价。如需门店去重客流和客单价，用下面的门店级查询。

---

## 3b. 门店日级汇总（去重客流 + 客单价）⭐推荐

> **查门店客流、客单价时必须用这个模板**，不要用模板3！

```sql
SELECT
    business_date,
    total_sale_amount AS sales,
    total_customer_count AS customers,
    full_link_profit_amount AS profit,
    store_profit_amount AS store_profit,
    loss_amount AS loss_amount,
    inbound_amount AS inbound_amount,
    total_per_customer_transaction AS ticket
FROM default_catalog.ads_business_analysis.strategy_fm_levels_result
WHERE business_date >= '{start_date}'
  AND business_date <= '{end_date}'
  AND level_description = '门店'
  AND day_clear = '1'
ORDER BY business_date
```

**为什么用 `level_description = '门店'`**：门店级的 `total_customer_count` 是跨品类去重后的真实客流（~800人），而 sku/小分类级的客流是品类级计数（一个人买3个品类算3次，~1700人）。用错会导致客单价腰斩（~8元 vs 真实 ~19元）。

---

## 4. 小分类级数据（品类下钻用）

> 使用 `category_level3_description` 聚合，需通过 `config/category_remapping.json` 重分类

```sql
SELECT
    business_date,
    category_level3_description AS l3_category,
    SUM(total_sale_amount) AS sales,
    SUM(total_customer_count) AS customers,
    SUM(full_link_profit_amount) AS profit
FROM default_catalog.ads_business_analysis.strategy_fm_levels_result
WHERE business_date >= '{start_date}'
  AND business_date <= '{end_date}'
  AND level_description = '小分类'
  AND day_clear = '1'
  AND category_level3_description IS NOT NULL
  AND category_level3_description != ''
GROUP BY business_date, category_level3_description
```

---

## 时间范围建议

| 分析类型 | 推荐时间范围 | 说明 |
|---------|-------------|------|
| RFM 分析 | 70 天左右 | 覆盖本期 28 天 + 上期 28 天 + 缓冲 |
| 品类分析（周度） | 7 天 | 一个完整周 |
| 经营周报（多周） | 30-45 天 | 覆盖 4-6 周 |
| 月度趋势 | 90 天 | 3 个月趋势 |
