# 数据字典

## 底表清单

| 表名 | 中文名 | 用途 | 数据粒度 |
|-----|-------|------|---------|
| strategy_fm_levels_result | **商品经营分析主表** | 翠花最全的底表，包含销售、利润、损耗、库存等全链路经营指标 | 每行 = 一个门店+SKU+日期 |
| store_transaction_details | 订单明细表 | 存储每笔订单的商品明细，用于用户维度分析 | 每行 = 一个商品 |

**完整表路径**:
- `default_catalog.ads_business_analysis.strategy_fm_levels_result`
- `default_catalog.ads_business_analysis.store_transaction_details`

---

## 表结构详情

### strategy_fm_levels_result（商品经营分析主表）⭐推荐

> **这是翠花最全的底表**，包含销售、利润、损耗、库存、价格等全链路经营指标

#### ⚠️ 关键筛选条件（必加）

```sql
WHERE level_description = '???'
  AND day_clear = '1'              -- 只取日清结算数据
```

| `level_description` 值 | 含义 | 数据粒度 |
|----------------------|------|---------|
| `门店` | **门店级（去重）** | 每行 = 门店全天汇总，客流已去重 |
| `sku` | SKU 级 | 每行 = 一个 SKU 的数据 |
| `小分类` | 三级品类聚合 | 每行 = 一个三级品类的汇总 |
| `中分类` | 二级品类聚合 | 每行 = 一个二级品类的汇总 |
| `大分类` | 一级品类聚合 | 每行 = 一个一级品类的汇总 |

> **🚨 客流和客单价的层级选择极其重要！**
>
> - **门店客流/客单价**：必须用 `level_description = '门店'`，此时客流是跨品类去重的真实客流（~800人），客单价 = 总销售/去重客流（~19元）
> - **sku/小分类的客流是品类级客流**：一个顾客买了蔬菜+猪肉+水果，在 sku 级会被算 3 次。用 sku 级算客流会虚高（~1700人）、客单腰斩（~8元），**完全错误**
> - **品类客流**：如需单品类客流（PI/渗透率），应从 `store_transaction_details` 用 `thirdparty_user_identity` 去重计算

#### 📍 维度字段（筛选/分组用）

| SQL 字段名 | 返回字段名 | 中文 | 说明 | 示例 |
|-----------|-----------|------|------|------|
| store_flag | storeFlag | 门店品牌 | 门店所属品牌/业态 | "翠花"、"菜花" |
| store_no | storeNo | 门店编号 | 门店唯一标识 | "food mart" |
| store_name | storeName | 门店名称 | 门店全称 | "杭州滨江西兴店" |
| business_date | businessDate | 业务日期 | 数据统计日期 | "2026-03-19" |
| sku_id | skuId | 商品ID | SKU唯一标识 | "21281785" |
| category_name | categoryName | 商品名称 | SKU名称 | "鸡蛋仔30枚1.5kg" |
| category_level1_description | categoryLevel1Description | 一级品类 | 品类一级分类 | "蛋奶低温" |
| category_level2_description | categoryLevel2Description | 二级品类 | 品类二级分类 | "蛋类" |
| category_level3_description | categoryLevel3Description | 三级品类 | 品类三级分类 | "鲜鸡蛋" |
| level_description | levelDescription | 数据层级 | 数据聚合层级 | "sku" / "category" |
| day_clear | dayClear | 日清标识 | 是否日清商品 | "1" / "0" |
| day_clear_flag | dayClearFlag | 日清标记 | 日清标记说明 | - |

#### 💰 销售指标

| SQL 字段名 | 返回字段名 | 中文 | 说明 | 示例 |
|-----------|-----------|------|------|------|
| total_sale_amount | totalSaleAmount | 销售金额 | 销售总金额（元） | 149.99 |
| total_sale_qty | totalSaleQty | 销售数量 | 销售总件数 | 20.0 |
| sales_weight | salesWeight | 销售重量 | 销售重量（kg） | 19.2 |
| total_customer_count | totalCustomerCount | 客流数 | 购买顾客数 | 18.0 |
| total_per_customer_transaction | totalPerCustomerTransaction | 客单价 | 平均每客消费 | 45.5 |
| original_sale_amount | originalSaleAmount | 原价销售额 | 按原价计算的销售额 | 180.0 |
| sale_amount_before_19 | saleAmountBefore19 | 19点前销售 | 19点前的销售金额 | 120.0 |
| customer_count_before_19 | customerCountBefore19 | 19点前客流 | 19点前的顾客数 | 12.0 |
| sale_qty_before_19 | saleQtyBefore19 | 19点前销量 | 19点前的销售数量 | 15.0 |
| sale_piece_qty | salePieceQty | 销售片数 | 销售片数（切配商品） | 10.0 |

#### 💵 利润指标

| SQL 字段名 | 返回字段名 | 中文 | 说明 | 示例 |
|-----------|-----------|------|------|------|
| full_link_profit_amount | fullLinkProfitAmount | 全链利润额 | 全链路利润金额（元） | 33.4 |
| full_link_profit_rate | fullLinkProfitRate | 全链利润率 | 全链路利润率 | 0.2227 (22.27%) |
| supply_chain_profit_amount | supplyChainProfitAmount | 供应链利润 | 供应链环节利润 | 20.0 |
| supply_chain_profit_rate | supplyChainProfitRate | 供应链利润率 | 供应链利润率 | 0.15 |
| store_profit_amount | storeProfitAmount | 门店利润 | 门店环节利润 | 13.4 |
| store_profit_rate | storeProfitRate | 门店利润率 | 门店利润率 | 0.08 |
| supply_chain_expected_profit_rate | supplyChainExpectedProfitRate | 供应链预期利润率 | 供应链预期利润率 | 0.18 |
| store_expected_profit_rate | storeExpectedProfitRate | 门店预期利润率 | 门店预期利润率 | 0.10 |
| store_expected_profit_amount | storeExpectedProfitAmount | 门店预期利润额 | 门店预期利润金额 | 15.0 |

#### 📦 进销存指标

| SQL 字段名 | 返回字段名 | 中文 | 说明 | 示例 |
|-----------|-----------|------|------|------|
| inbound_amount | inboundAmount | 进货金额 | 进货总金额 | 200.0 |
| inbound_qty | inboundQty | 进货数量 | 进货数量 | 50.0 |
| inbound_price | inboundPrice | 进货单价 | 进货单价 | 4.0 |
| initial_inventory_amount | initialInventoryAmount | 期初库存金额 | 期初库存金额 | 100.0 |
| init_stock_qty | initStockQty | 期初库存数量 | 期初库存数量 | 25.0 |
| ending_inventory_amount | endingInventoryAmount | 期末库存金额 | 期末库存金额 | 80.0 |
| end_stock_qty | endStockQty | 期末库存数量 | 期末库存数量 | 20.0 |
| turnover_rate | turnoverRate | 周转率 | 库存周转率 | 2.1739 |
| active_sku_count | activeSkuCount | 活跃SKU数 | 有销售的SKU数 | 150 |

#### 🗑️ 损耗指标

| SQL 字段名 | 返回字段名 | 中文 | 说明 | 示例 |
|-----------|-----------|------|------|------|
| loss_amount | lossAmount | 损耗金额 | 损耗金额（元），负数为损耗 | -6.73 |
| loss_rate | lossRate | 损耗率 | 损耗率 | -0.0244 (2.44%损耗) |
| loss_qty | lossQty | 损耗数量 | 损耗数量 | 2.0 |
| loss_rate_qty | lossRateQty | 损耗率(数量) | 按数量计算的损耗率 | 0.05 |
| store_know_lost_amt | storeKnowLostAmt | 门店已知损耗 | 门店已知损耗金额 | 5.0 |
| store_unknow_lost_amt | storeUnknowLostAmt | 门店未知损耗 | 门店未知损耗金额 | 1.73 |

#### ⏰ 售罄指标

| SQL 字段名 | 返回字段名 | 中文 | 说明 | 示例 |
|-----------|-----------|------|------|------|
| soldout_rate_16 | soldoutRate16 | 16点售罄率 | 16点售罄商品比例 | 0.0 (0%) |
| soldout_rate_20 | soldoutRate20 | 20点售罄率 | 20点售罄商品比例 | 0.0 (0%) |

#### 💲 价格指标

| SQL 字段名 | 返回字段名 | 中文 | 说明 | 示例 |
|-----------|-----------|------|------|------|
| purchase_price | purchasePrice | 采购价 | 采购单价 | 3.5 |
| average_selling_price | averageSellingPrice | 平均售价 | 实际平均销售单价 | 7.5 |
| average_sales_original_price | averageSalesOriginalPrice | 平均原价 | 平均原价 | 8.0 |
| discount_rate | discountRate | 折扣率 | 总折扣率 | 0.0625 (6.25%折扣) |
| promotional_discount_rate | promotionalDiscountRate | 促销折扣率 | 促销活动折扣率 | 0.05 |
| time_period_discount_rate | timePeriodDiscountRate | 时段折扣率 | 时段折扣率 | 0.0125 |
| discount_amount | discountAmount | 折扣金额 | 折扣总金额 | 10.0 |
| promotional_discount_amount | promotionalDiscountAmount | 促销折扣金额 | 促销折扣金额 | 8.0 |
| time_period_discount_amount | timePeriodDiscountAmount | 时段折扣金额 | 时段折扣金额 | 2.0 |

#### 🏪 门店经营指标

| SQL 字段名 | 返回字段名 | 中文 | 说明 | 示例 |
|-----------|-----------|------|------|------|
| operating_store_days | operatingStoreDays | 营业天数 | 营业天数 | 1 |
| operating_store_count | operatingStoreCount | 营业门店数 | 营业门店数 | 1 |
| product_efficiency | productEfficiency | 商品效率 | 商品坪效/人效 | 150.5 |
| sales_proportion_within_group | salesProportionWithinGroup | 组内销售占比 | 在分组中的销售占比 | 0.15 |
| sales_rank_in_middle_category | salesRankInMiddleCategory | 中类销售排名 | 在中类中的销售排名 | "TOP10" |
| sales_rank_in_large_category | salesRankInLargeCategory | 大类销售排名 | 在大类中的销售排名 | "TOP20" |
| return_rate | returnRate | 退货率 | 退货率 | 0.01 |
| per_item_price_before_19 | perItemPriceBefore19 | 19点前单品价 | 19点前单品均价 | 8.0 |
| item_per_customer_before_19 | itemPerCustomerBefore19 | 19点前连带率 | 19点前人均购买件数 | 1.5 |
| lp_sale_amt | lpSaleAmt | LP销售 | LP销售金额 | 50.0 |
| avg_7d_sale_qty | avg7dSaleQty | 7日平均销量 | 7日平均销售数量 | 18.5 |

---

### store_transaction_details（订单明细表）

> **重要说明**：
> 1. SQL 中使用下划线格式字段名（如 `pay_at`），返回结果自动转为驼峰格式（如 `payAt`）
> 2. `get_user_order_data()` 内置品类重分类 CASE 语句，`category_level1_description` 返回的是重分类后的标准品类，非数据库原始值

#### 品类重分类规则

数据库原始品类名与翠花标准品类的映射（在 `get_user_order_data` SQL 中自动执行）：

| 条件 | 重分类为 |
|-----|---------|
| `蛋类`、`烘焙类` | 保持不变 |
| `冷藏奶制品类`、`饮料类` | → `乳制品及水饮类` |
| `肉禽蛋类` 且非 `蛋类` | → `肉禽类` |
| 三级品类以"熟食"结尾 | → `熟食类` |
| `冷藏及加工类`、`预制菜` | → `冷藏加工及预制菜类` |
| 其他 | 保持一级品类不变 |

#### 用户字段

| SQL 字段名 | 返回字段名 | 中文 | 类型 | 说明 | 示例 |
|-----------|-----------|------|------|------|------|
| thirdparty_user_identity | thirdpartyUserIdentity | 用户ID | string | 用户唯一标识（支付ID） | "AockJ67eAKDVacfoYvE8wAIEpV7Oc" |
| customer_phone | customerPhone | 手机号 | string | 脱敏手机号，用于营销触达 | "138****1234" |

#### 订单字段

| SQL 字段名 | 返回字段名 | 中文 | 类型 | 说明 | 示例 |
|-----------|-----------|------|------|------|------|
| order_id | orderId | 订单号 | string | 订单唯一标识 | "8153010480054324" |
| pay_at | payAt | 支付时间 | datetime | 支付时间，格式 YYYY-MM-DD HH:MM:SS | "2026-03-18 10:30:00" |
| sales_amt | salesAmt | 销售金额 | decimal | 商品销售金额（元） | 15.90 |
| channel | channel | 渠道 | string | 购买渠道 | "线上" / "线下" |

#### 商品字段

| SQL 字段名 | 返回字段名 | 中文 | 类型 | 说明 | 示例 |
|-----------|-----------|------|------|------|------|
| abi_article_id | abiArticleId | 商品ID | string | 商品唯一标识 | "21281785" |
| article_name | articleName | 商品名称 | string | 商品名称 | "鸡蛋仔30枚1.5kg" |
| category_level1_description | categoryLevel1Description | 一级品类 | string | 品类一级分类 | "蛋奶低温" |
| category_level2_description | categoryLevel2Description | 二级品类 | string | 品类二级分类 | "蛋类" |
| category_level3_description | categoryLevel3Description | 三级品类 | string | 品类三级分类 | "鲜鸡蛋" |

---

## 数据特点

### 数据更新周期

| 概念 | 说明 | 示例 |
|-----|------|------|
| 分析日期 | 执行分析当天的日期 | 2026-03-18 |
| 数据截止日期 | 数据库中最新完整数据的日期 | 2026-03-17（通常是分析日期-1） |

> **重要**：所有 SQL 查询的 `{end_date}` 应使用**数据截止日期**，而非分析日期

### 数据限制

- 单次查询最多返回 50,000 条
- 建议使用时间范围筛选减少数据量
- API 超时时间 300 秒

---

## 🎯 根据分析目标选表选字段

### 选表指南

| 分析目标 | 推荐表 | 原因 |
|---------|-------|------|
| **用户分析/RFM分层** | store_transaction_details | 包含用户ID，可追踪用户购买行为 |
| **商品经营分析** | strategy_fm_levels_result ⭐ | 最全面，包含销售+利润+损耗+库存 |
| **门店经营分析** | strategy_fm_levels_result ⭐ | 包含门店维度的完整经营指标 |
| **品类分析** | strategy_fm_levels_result ⭐ | 包含品类层级和销售排名 |
| **损耗分析** | strategy_fm_levels_result ⭐ | 包含完整的损耗指标 |
| **利润分析** | strategy_fm_levels_result ⭐ | 包含全链路利润指标 |

### 按需求快速选字段

| 需求 | 使用字段 | ⚠️ 注意 |
|-----|---------|---------|
| **查销售额** | totalSaleAmount | 任意层级均可 |
| **查销售量** | totalSaleQty, salesWeight | 任意层级均可 |
| **查门店客流（去重）** | totalCustomerCount | **必须** `level_description='门店'`，否则重复计数 |
| **查门店客单价** | totalPerCustomerTransaction 或 销售额÷客流 | **必须** `level_description='门店'` |
| **查品类客流（PI）** | 从 store_transaction_details 用 thirdparty_user_identity 去重 | 不能直接用 sku/小分类 的 totalCustomerCount |
| **查利润** | fullLinkProfitAmount, fullLinkProfitRate |
| **查损耗** | lossAmount, lossRate |
| **查售罄** | soldoutRate16, soldoutRate20 |
| **查周转** | turnoverRate |
| **查折扣** | discountRate, promotionalDiscountRate |
| **查进价** | purchasePrice, inboundPrice |
| **查售价** | averageSellingPrice |
| **按门店筛选** | storeFlag, storeNo, storeName |
| **按品类筛选** | categoryLevel1Description, categoryLevel2Description, categoryLevel3Description |
| **按商品筛选** | skuId, categoryName |
| **按日期筛选** | businessDate |

### 常用 SQL 模板

```sql
-- 查询某日某门店的商品销售情况
SELECT
    sku_id,
    category_name,
    total_sale_amount,
    total_sale_qty,
    full_link_profit_rate,
    loss_rate
FROM default_catalog.ads_business_analysis.strategy_fm_levels_result
WHERE business_date = '2026-03-19'
  AND store_no = 'food mart'
ORDER BY total_sale_amount DESC
LIMIT 100
```

```sql
-- 查询高损耗商品 TOP20
SELECT
    category_level1_description,
    category_name,
    total_sale_amount,
    loss_amount,
    loss_rate
FROM default_catalog.ads_business_analysis.strategy_fm_levels_result
WHERE business_date = '2026-03-19'
  AND loss_rate < 0  -- 负数表示有损耗
ORDER BY loss_rate ASC
LIMIT 20
```

```sql
-- 按品类汇总销售
SELECT
    category_level1_description,
    SUM(total_sale_amount) as total_sales,
    SUM(total_customer_count) as total_customers,
    AVG(full_link_profit_rate) as avg_profit_rate
FROM default_catalog.ads_business_analysis.strategy_fm_levels_result
WHERE business_date = '2026-03-19'
GROUP BY category_level1_description
ORDER BY total_sales DESC
```
