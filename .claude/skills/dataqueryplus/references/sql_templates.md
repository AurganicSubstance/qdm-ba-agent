# SQL 查询模板 — 大妈（商分数据库）

> 所有表路径前缀：`default_catalog.ads_business_analysis.`
> 字段名为**中文**，百分比返回字符串需 CAST 处理。

---

## 运营模块

### 1. 运营宽表 — 门店日级汇总（去重客流）

```sql
SELECT
    `日期`,
    `门店汇总` AS store_name,
    `门店汇总维度` AS dim,
    `销售额` AS sales,
    `全天来客数` AS customers,
    `客单价` AS ticket,
    `全链路毛利额` AS profit,
    `门店损耗额` AS loss,
    `进货金额` AS inbound
FROM default_catalog.ads_business_analysis.operation_center_wide_daily
WHERE `品类分层` = '门店'
  AND `门店汇总维度` = '管理区域'
  AND FROM_UNIXTIME(`日期`/1000, 'yyyy-MM-dd') >= '{start_date}'
  AND FROM_UNIXTIME(`日期`/1000, 'yyyy-MM-dd') <= '{end_date}'
ORDER BY `日期`
```

### 2. 运营宽表 — 品类销售排行

```sql
SELECT
    `品类名称` AS category,
    `销售额` AS sales,
    `全天来客数` AS customers,
    `全链路毛利额` AS profit,
    CAST(REPLACE(`全链路毛利率`, '%', '') AS DOUBLE)/100 AS profit_rate,
    CAST(REPLACE(`门店损耗率`, '%', '') AS DOUBLE)/100 AS loss_rate
FROM default_catalog.ads_business_analysis.operation_center_wide_daily
WHERE `品类分层` = '中分类'
  AND `门店汇总维度` = '管理区域'
  AND `门店汇总` = '{区域名}'
  AND FROM_UNIXTIME(`日期`/1000, 'yyyy-MM-dd') >= '{start_date}'
  AND FROM_UNIXTIME(`日期`/1000, 'yyyy-MM-dd') <= '{end_date}'
ORDER BY `销售额` DESC
```

### 3. 运营宽表 — 高损耗品类 TOP20

```sql
SELECT
    `品类名称` AS category,
    `销售额` AS sales,
    `门店损耗额` AS loss,
    CAST(REPLACE(`门店损耗率`, '%', '') AS DOUBLE)/100 AS loss_rate
FROM default_catalog.ads_business_analysis.operation_center_wide_daily
WHERE `品类分层` IN ('中分类', '小分类')
  AND FROM_UNIXTIME(`日期`/1000, 'yyyy-MM-dd') >= '{start_date}'
  AND FROM_UNIXTIME(`日期`/1000, 'yyyy-MM-dd') <= '{end_date}'
ORDER BY loss_rate ASC
LIMIT 20
```

### 4. 门店资料 — 按区域查门店列表

```sql
SELECT
    newSpStoreId AS store_id,
    newSpStoreName AS store_name,
    manageAreaName AS area,
    cityDescription AS city,
    storeTypeName AS store_type,
    CAST(totalArea AS DOUBLE) AS area_sqm,
    spOriginStartDate AS open_date,
    CAST(openDays AS INT) AS open_days,
    sapStoreStatusName AS status
FROM default_catalog.ads_business_analysis.operation_center_dim_store_profile_di
WHERE manageAreaName = '{区域名}'
  AND sapStoreStatusName = '营业中'
ORDER BY newSpStoreId
```

### 5. 新店跟踪 — 按区域查新店列表

```sql
SELECT
    storeId AS store_id,
    storeName AS store_name,
    manageAreaName AS area,
    openDateStr AS open_date,
    orderAmtDailyStr AS daily_sales,
    bf19CustDailyStr AS daily_cust,
    profitDailyStr AS daily_profit,
    achieveTier1 AS sales_tier,
    achieveTier2 AS profit_tier,
    orderWowStr AS sales_wow,
    profitWowStr AS profit_wow
FROM default_catalog.ads_business_analysis.operation_center_new_store_90d_weekly_store_di
WHERE manageAreaName = '{区域名}'
ORDER BY sortOrd
```

### 6. 新店区域汇总

```sql
SELECT
    manageAreaName AS area,
    areaClass AS area_class,
    newStoreCnt AS new_store_count,
    problemStoreCnt AS problem_count,
    avgOrderAmt AS avg_sales,
    avgBf19Cust AS avg_cust,
    avgProfitDaily AS avg_profit
FROM default_catalog.ads_business_analysis.operation_center_new_store_90d_weekly_region_di
ORDER BY rowSeq
```

---

## 商品模块

### 7. SKU 表 — 品类销售排行（SKU级）

```sql
SELECT
    categoryLevel1Description AS l1_category,
    categoryLevel2Description AS l2_category,
    categoryLevel3Description AS l3_category,
    articleName AS sku_name,
    totalSaleAmt AS sales,
    salesWeight AS sales_weight,
    custNum AS customers,
    finArticleProfit AS profit,
    storeLostAmt AS loss
FROM default_catalog.ads_business_analysis.product_center_business_sku_v3_info_di
WHERE areaName = '{区域名}'
  AND ym = '{YYYY-MM}'
ORDER BY totalSaleAmt DESC
LIMIT 50
```

### 8. SPU 表 — 品类汇总（SPU级）

```sql
SELECT
    categoryLevel1Description AS l1_category,
    spuName AS spu_name,
    totalSaleAmt AS sales,
    custNum AS customers,
    finArticleProfit AS profit,
    storeLostAmt AS loss,
    skuNum AS sku_count,
    storeNum AS store_count
FROM default_catalog.ads_business_analysis.product_center_business_v3_info_di
WHERE areaName = '{区域名}'
  AND ym = '{YYYY-MM}'
ORDER BY totalSaleAmt DESC
```

### 9. SKU 表 — 复购率排行

```sql
SELECT
    categoryLevel1Description AS l1_category,
    articleName AS sku_name,
    buyMemberNum AS buyers,
    buyAgainMemberNum AS repeat_buyers,
    repurchaseRate AS repurchase_rate
FROM default_catalog.ads_business_analysis.product_center_business_sku_v3_info_di
WHERE areaName = '{区域名}'
  AND ym = '{YYYY-MM}'
  AND buyMemberNum > 0
ORDER BY repurchaseRate DESC
LIMIT 30
```

### 10. SKU 表 — 价格竞争力分析

```sql
SELECT
    categoryLevel1Description AS l1_category,
    articleName AS sku_name,
    purchasePrice AS purchase_price,
    marketPrice AS market_price,
    priceIndex AS price_index,
    highPrice AS high_price
FROM default_catalog.ads_business_analysis.product_center_business_sku_v3_info_di
WHERE areaName = '{区域名}'
  AND ym = '{YYYY-MM}'
  AND priceIndex IS NOT NULL
ORDER BY priceIndex DESC
LIMIT 30
```

### 11. SKU 表 — 高损耗商品 TOP20

```sql
SELECT
    categoryLevel1Description AS l1_category,
    articleName AS sku_name,
    totalSaleAmt AS sales,
    storeLostAmt AS loss,
    CASE WHEN totalSaleAmt > 0
         THEN storeLostAmt / totalSaleAmt
         ELSE 0 END AS loss_rate
FROM default_catalog.ads_business_analysis.product_center_business_sku_v3_info_di
WHERE areaName = '{区域名}'
  AND ym = '{YYYY-MM}'
  AND storeLostAmt > 0
ORDER BY loss_rate DESC
LIMIT 20
```

### 12. SKU 表 — 必采分析

```sql
SELECT
    categoryLevel1Description AS l1_category,
    articleName AS sku_name,
    mustOrderOrderAmt AS order_amt,
    mustOrderReceiveAmt AS receive_amt,
    mustOrderStoreNum AS store_num,
    CASE WHEN mustOrderOrderAmt > 0
         THEN mustOrderReceiveAmt / mustOrderOrderAmt
         ELSE 0 END AS fulfill_rate
FROM default_catalog.ads_business_analysis.product_center_business_sku_v3_info_di
WHERE areaName = '{区域名}'
  AND ym = '{YYYY-MM}'
  AND mustOrderOrderAmt > 0
ORDER BY mustOrderOrderAmt DESC
LIMIT 30
```

---

## 时间筛选技巧

大妈表的日期字段有两种格式：

| 表 | 日期字段 | 格式 | 筛选写法 |
|---|---------|------|---------|
| 运营宽表 | `日期` | timestamp 毫秒 | `FROM_UNIXTIME(\`日期\`/1000, 'yyyy-MM-dd') >= '{date}'` |
| 门店资料表 | reportDate | timestamp 毫秒 | 同上 |
| 新店表 | reportDate | timestamp 毫秒 | 同上 |
| 商品表 | incDay | timestamp 毫秒 | 同上 |
| 商品表 | ym | 字符串 `'YYYY-MM'` | `ym = '{YYYY-MM}'` |
| 商品表 | year | 字符串 `'YYYY'` | `year = '{YYYY}'` |
| 商品表 | weekWid | 字符串 `'YYYYWW'` | `weekWid = '{YYYYWW}'` |

> **商品表推荐用 `ym` 按月筛选**，数据量小、速度快。如需精确到天，用 incDay 时间戳筛选。

## 百分比字段处理

大妈表百分比返回字符串 `'19.77%'`，转数值：

```sql
CAST(REPLACE(`门店损耗率`, '%', '') AS DOUBLE) / 100
```

## 门店名筛选注意

运营宽表的 `门店汇总` 和 `门店汇总维度` 决定了数据的聚合层级：
- `门店汇总维度 = '管理区域'` + `门店汇总 = '华东区'` → 华东区汇总
- `门店汇总维度 = '门店'` + `门店汇总 = '广州华景北店'` → 单店数据
- `门店汇总维度 = '全司'` → 全司汇总
