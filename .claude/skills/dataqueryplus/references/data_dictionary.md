# 数据字典 — 大妈（商分数据库）

## 底表总览

大妈底表按营采销分为三块，当前已接入 **运营** 和 **商品** 两个模块。

| 模块 | 表名 | 中文名 | 数据粒度 |
|-----|------|-------|---------|
| 运营 | operation_center_wide_daily | 运营宽表 | 每行 = 某层级（门店/品类/全司）× 某日 |
| 运营 | operation_center_dim_store_profile_di | 门店资料表 | 每行 = 一个门店的静态属性 |
| 运营 | operation_center_new_store_90d_weekly_store_di | 新店门店维度 | 每行 = 一个新店×一周 |
| 运营 | operation_center_new_store_90d_weekly_region_di | 新店区域维度 | 每行 = 一个区域的新店汇总×一周 |
| 商品 | product_center_business_v3_info_di | 商品表（SPU） | 每行 = 一个 SPU × 区域 × 周/月 |
| 商品 | product_center_business_sku_v3_info_di | 商品表（SKU） | 每行 = 一个 SKU × 区域 × 周/月 |

**完整表路径**：`default_catalog.ads_business_analysis.{表名}`

---

## 一、运营模块

### 1. operation_center_wide_daily（运营宽表）⭐核心

大妈运营最常用的宽表，包含销售、利润、损耗、折扣、进销存全链路指标。

#### 维度字段

| 字段名 | 中文 | 说明 | 示例 |
|-------|------|------|------|
| 日期 | 业务日期 | timestamp 格式 | 1743696000000 |
| 品类分层 | 数据层级 | 门店/大分类/中分类/小分类/sku | '中分类' |
| 品类名称 | 品类名 | 当前层级的品类名称 | '两栖类' |
| 门店汇总 | 区域/门店名 | 当前行的区域或门店 | '华东区' |
| 门店汇总维度 | 汇总维度 | 管理区域/大区/门店 等 | '管理区域' |

> **筛选层级**：`品类分层` 决定数据粒度，与翠花 `level_description` 类似。
> - `'门店'` = 门店全天汇总（客流已去重）
> - `'大分类'/'中分类'/'小分类'` = 品类聚合
> - `'sku'` = SKU 级明细

#### 销售指标

| 字段名 | 中文 | 说明 |
|-------|------|------|
| 销售额 | 销售金额（元） | 全天总销售 |
| 销售重量 | 销售重量(kg) | - |
| 全天来客数 | 客流数 | 注意：门店层级是去重客流 |
| 客单价 | 客单价（元） | 销售额÷来客数 |
| 平均售价 | 均价（元） | - |
| 原价 | 原价单价 | - |
| 原价销售额 | 原价总额 | - |
| 理论销售额 | 理论销售额 | 含预期 |
| 在售sku | 在售 SKU 数 | - |

#### 19点前指标

| 字段名 | 中文 | 说明 |
|-------|------|------|
| 19点前销售额 | 19点前销售金额 | - |
| 19点前来客数 | 19点前客流 | - |
| 19点前客单价 | 19点前客单价 | - |
| 19点前pi | 19点前渗透率 | 百分比字符串 |
| 19点前售价 | 19点前均价 | - |
| 19点前销售重量 | 19点前销售重量(kg) | - |
| 19点前客单重量 | 19点前客单重量(kg) | - |

#### 利润指标

| 字段名 | 中文 | 说明 |
|-------|------|------|
| 全链路毛利额 | 全链路利润（元） | - |
| 全链路毛利率 | 全链路利润率 | 百分比字符串 |
| 门店毛利额 | 门店利润（元） | - |
| 门店毛利率 | 门店利润率 | 百分比字符串 |
| 供应链毛利额 | 供应链利润（元） | - |
| 供应链毛利率 | 供应链利润率 | 百分比字符串 |
| 供应链预期毛利率 | 预期利润率 | 百分比字符串 |
| 补贴前毛利额 | 补贴前利润（元） | - |
| 补贴前毛利率 | 补贴前利润率 | 百分比字符串 |
| 门店定价毛利率 | 定价利润率 | 百分比字符串 |

#### 进销存指标

| 字段名 | 中文 | 说明 |
|-------|------|------|
| 进货金额 | 进货总额（元） | - |
| 进货重量 | 进货重量(kg) | - |
| 门店进货价 | 门店进货单价 | - |
| 采购价 | 采购单价 | - |
| 理论进货额 | 理论进货金额 | - |
| 门店出库额 | 出库金额 | - |
| 门店出库额不含税 | 出库不含税金额 | - |
| 预期出库金额 | 预期出库金额 | - |
| 出库到店成本 | 出库到店成本 | - |

#### 损耗指标

| 字段名 | 中文 | 说明 |
|-------|------|------|
| 门店损耗额 | 损耗金额（元） | - |
| 门店损耗率 | 损耗率 | 百分比字符串 |

#### 折扣指标

| 字段名 | 中文 | 说明 |
|-------|------|------|
| 促销折扣额 | 促销折扣金额 | - |
| 促销折扣率 | 促销折扣率 | 百分比字符串 |
| 时段折扣额 | 时段折扣金额 | - |
| 时段折扣率 | 时段折扣率 | 百分比字符串 |
| 出库折让率 | 出库折让率 | 百分比字符串 |
| 出库让利总额 | 出库让利总金额 | - |

#### 其他指标

| 字段名 | 中文 | 说明 |
|-------|------|------|
| 营业店日数 | 营业店日数 | - |
| 营业门店数 | 营业门店数 | - |
| 门店退货率 | 门店退货率 | 百分比字符串 |
| 门店退货额 | 门店退货金额 | - |
| 顾客退货率 | 顾客退货率 | 百分比字符串 |
| 顾客退货额 | 顾客退货金额 | - |

---

### 2. operation_center_dim_store_profile_di（门店资料表）

门店静态属性维表，与运营宽表通过门店编号关联。

#### 核心字段

| 字段名 | 中文 | 说明 | 示例 |
|-------|------|------|------|
| newSpStoreId | 新门店编号 | ⭐主键 | 'A008' |
| newSpStoreName | 新门店名称 | 门店名称 | '广州华景北店' |
| originalStoreId | 原门店编号 | SAP 编号 | '101002' |
| spStoreName | 原门店名称 | SAP 名称 | '广州华景北店' |
| storeFlagName | 门店品牌 | 实体店/mini 等 | '实体店' |
| storeTypeName | 经营类型 | 直营/加盟 | '直营' |
| newSpLevelName | 门店级别 | - | '实体店' |
| spScale | 门店规模 | - | '20' |
| totalArea | 门店面积(㎡) | - | 58.0 |
| spOriginStartDate | 开业日期 | - | '2014-03-22' |
| openDays | 营业天数 | - | '4423' |
| sapStoreStatusName | 门店状态 | 营业中/已关闭 | '营业中' |

#### 组织架构字段

| 字段名 | 中文 | 说明 | 示例 |
|-------|------|------|------|
| manageAreaName | 管理区域 | ⭐常用筛选 | '运营中心直管' |
| areaDescription | 区域描述 | 子区域 | '直管一区' |
| area2Name | 大区名称 | 二级大区 | '运营中心直管' |
| regionName | 区域名称 | 省区 | '粤东粤西' |
| proDescription | 省份 | - | '广东' |
| cityDescription | 城市 | - | '广州' |
| distDescription | 区/县 | - | '天河区' |
| spAddress | 详细地址 | - | '广东省广州市天河区...' |

#### 人员字段

| 字段名 | 中文 | 说明 |
|-------|------|------|
| groupManager | 组长 | 姓名 |
| groupManagerCode | 组长工号 | - |
| groupManagerTel | 组长电话 | - |
| mallSupervisorName | 商场主管 | 姓名 |
| mallSupervisorPhone | 商场主管电话 | - |
| zoneSupperManager | 区域督导 | 姓名 |
| zoneSupperPhone | 区域督导电话 | - |
| zmanName | 经营者类型 | 公司直营/外部加盟 |

#### 其他字段

| 字段名 | 中文 | 说明 |
|-------|------|------|
| businessArea | 商圈类型 | 住宅区/商业区/综合区 |
| eblcLatitude | 纬度 | - |
| eblcLongitude | 经度 | - |
| storeServiceName | 门店服务 | 扫码购,收银机,... |
| spCompanyId | 公司代码 | - |
| spType | 门店类型代码 | 10=直营, 20=加盟 |
| transferDate | 转让日期 | - |
| franchiseeName | 加盟商名称 | 直营店为空 |

---

### 3. operation_center_new_store_90d_weekly_store_di（新店门店维度）

开店90天内的新店，按周跟踪。

| 字段名 | 中文 | 说明 | 示例 |
|-------|------|------|------|
| storeId | 门店编号 | ⭐主键 | 'A4B1' |
| storeName | 门店名称 | - | '广州保利珑玥公馆' |
| manageAreaName | 管理区域 | - | '粤西区' |
| openDateStr | 开业日期 | - | '2026-03-28' |
| reportDate | 报告日期 | timestamp | 1776873600000 |
| sortOrd | 排序序号 | - | 37 |
| orderAmtDailyStr | 日均销售额 | - | '8003.21' |
| bf19SaleDailyStr | 19点前日均销售 | - | '7393.2' |
| bf19CustDailyStr | 19点前日均客流 | - | '366.2857' |
| profitDailyStr | 日均利润 | - | '2292.03' |
| orderWowStr | 销售环比 | 环比变化量 | '80.93' |
| bf19SaleWowStr | 19点前销售环比 | - | '118.47' |
| bf19CustWowStr | 19点前客流环比 | - | '19.5714' |
| profitWowStr | 利润环比 | - | '192.29' |
| achieveTier1 | 销售达成档位 | - | '70%-85%' |
| achieveTier2 | 利润达成档位 | - | '70%-85%' |
| orderTarget | 销售目标 | - | - |
| profitTarget | 利润目标 | - | - |
| orderTargetGap | 销售目标差距 | - | - |
| profitTargetGap | 利润目标差距 | - | - |
| cityBf19SaleStr | 城市均值-销售 | 城市平均19点前销售 | '9275.06' |
| cityBf19CustStr | 城市均值-客流 | 城市平均19点前客流 | '441.06' |
| vsCitySaleStr | VS城市-销售 | 与城市均值比值 | '0.797105' |
| vsCityCustStr | VS城市-客流 | 与城市均值比值 | '0.830467' |
| scmPromoDAvgStr | 供应链促销日均 | - | - |
| goodsDiscM23Str | 商品折扣率M23 | - | - |
| allowanceFmStr | 补贴-毛利 | - | '142.45' |
| allowanceLossStr | 补贴-损耗 | - | - |
| vsHeadPromoStr | VS总部-促销 | - | - |
| vsHeadDiscStr | VS总部-折扣 | - | - |

---

### 4. operation_center_new_store_90d_weekly_region_di（新店区域维度）

新店按管理区域汇总，周维度。

| 字段名 | 中文 | 说明 | 示例 |
|-------|------|------|------|
| manageAreaName | 管理区域 | ⭐主键 | '长沙区' |
| areaClass | 区域分类 | 大外区/直管等 | '大外区' |
| reportDate | 报告日期 | timestamp | 1776873600000 |
| rowSeq | 行序号 | - | 4 |
| newStoreCnt | 新店数量 | - | 6 |
| problemStoreCnt | 问题店数量 | - | 3 |
| avgOrderAmt | 平均销售额 | - | 8529.0 |
| avgBf19Cust | 平均19点前客流 | - | 602.0 |
| avgProfitDaily | 平均日利润 | - | 1239.0 |
| avgAllowFm | 平均补贴-毛利 | - | 628.7 |
| avgAllowLoss | 平均补贴-损耗 | - | - |
| cntFmSubsidy | 毛利补贴店数 | - | 5 |
| cntLossSubsidy | 损耗补贴店数 | - | 0 |
| cntM23Disc | M23折扣超标店数 | - | 3 |
| goodsDiscM23Str | 商品折扣率M23 | - | '0.62%' |
| orderTargetGap | 销售目标差距 | - | - |
| profitTargetGap | 利润目标差距 | - | - |
| vsHeadAmtStr | VS总部-金额 | - | '-99.12' |
| vsHeadDiscStr | VS总部-折扣 | - | '-0.45%' |

---

## 二、商品模块

### 5. product_center_business_v3_info_di（商品表 SPU）

SPU 维度的商品经营数据，按区域×周/月聚合。

#### 维度字段

| 字段名 | 中文 | 说明 | 示例 |
|-------|------|------|------|
| areaName | 区域名称 | ⭐常用筛选 | '华东区' |
| operateName | 运营区域 | 同 areaName | '华东区' |
| categoryDimension | 维度类型 | 'SPU维度' | - |
| categoryLevel1Description | 一级品类 | - | '冷藏及加工类' |
| categoryLevel2Description | 二级品类 | - | '冷藏奶制品类' |
| categoryLevel3Description | 三级品类 | - | '乳酸菌饮品' |
| spuName | SPU名称 | - | '乳酸菌饮品' |

#### 时间字段

| 字段名 | 中文 | 说明 | 示例 |
|-------|------|------|------|
| incDay | 数据日期 | timestamp | 1704038400000 |
| year | 年份 | - | '2024' |
| ym | 年月 | - | '2024-01' |
| weekWid | 自然周 | - | '202401' |
| week54Wid | 54周序号 | - | '202452' |

#### 销售指标

| 字段名 | 中文 | 说明 |
|-------|------|------|
| totalSaleAmt | 总销售额（元） | - |
| bf19SaleAmt | 19点前销售 | - |
| lpSaleAmt | LP销售 | - |
| preSaleAmt | 预售金额 | - |
| salesWeight | 销售重量(kg) | - |
| bf19SalesWeight | 19点前销售重量(kg) | - |

#### 客流指标

| 字段名 | 中文 | 说明 |
|-------|------|------|
| custNum | 总客流 | - |
| bf19CustNum | 19点前客流 | - |
| custSpu | SPU客流 | - |
| bf19CustSpu | 19点前SPU客流 | - |
| buyMemberNum | 购买会员数 | - |
| buyAgainMemberNum | 复购会员数 | - |
| bf19CustSpu | 19点前SPU客流 | - |
| buyAgainMemberNumBf19 | 19点前复购会员数 | - |
| buyMemberNum | 购买会员数 | - |

#### 利润指标

| 字段名 | 中文 | 说明 |
|-------|------|------|
| finArticleProfit | 商品利润 | 最终利润 |
| dcFinArticleProfit | DC最终利润 | 含税调整后 |
| dcFinArticleProfitD195 | DC利润(D195) | - |
| articleProfitAmt | 商品利润额 | - |
| dcArticleExpectProfit | DC预期利润 | - |

#### 进货/成本指标

| 字段名 | 中文 | 说明 |
|-------|------|------|
| inboundAmount | 进货金额（元） | - |
| preInboundAmount | 预进货金额 | - |
| expectOutstockAmt | 预期出库金额 | - |
| outStockPayAmt | 出库含税金额 | - |
| outStockPayAmtNotax | 出库不含税金额 | - |
| outStockAmtCb | 出库成本金额 | - |
| purchaseWeight | 进货重量(kg) | - |

#### 损耗指标

| 字段名 | 中文 | 说明 |
|-------|------|------|
| storeLostAmt | 门店损耗金额 | 正数为损耗 |
| dcWastage | DC损耗 | - |

#### 折扣指标

| 字段名 | 中文 | 说明 |
|-------|------|------|
| discountAmt | 总折扣金额 | - |
| hourDiscountAmt | 时段折扣金额 | - |
| shopPromotionAmt | 门店促销金额 | - |
| scmPromotionAmt | 供应链促销金额 | - |
| scmPromotionAmtGift | 供应链赠品金额 | - |
| scmPromotionAmtTotal | 供应链促销总额 | - |

#### 门店/库存指标

| 字段名 | 中文 | 说明 |
|-------|------|------|
| storeNum | 有货门店数 | - |
| storeOrderAmt | 门店订货金额 | - |
| storeSpu | 门店SPU数 | - |
| skuNum | SKU数 | - |
| businessDays | 营业天数 | - |

#### 配送指标

| 字段名 | 中文 | 说明 |
|-------|------|------|
| deliverNum | 配送次数 | - |
| normalNum | 正常配送次数 | - |
| ontimeNum | 准时配送次数 | - |
| qualifyNum | 合格配送次数 | - |

#### 必采字段组

| 字段名 | 中文 | 说明 |
|-------|------|------|
| mustOrderOrderAmt | 必采下单金额 | - |
| mustOrderReceiveAmt | 必采收货金额 | - |
| mustOrderBasicOrderAmt | 必采基础品下单 | - |
| mustOrderBasicReceiveAmt | 必采基础品收货 | - |
| mustOrderActivityOrderAmt | 必采活动品下单 | - |
| mustOrderActivityReceiveAmt | 必采活动品收货 | - |
| mustOrderPlOrderAmt | 必采大宗下单 | - |
| mustOrderPlReceiveAmt | 必采大宗收货 | - |
| mustOrderPjOrderAmt | 必采配件下单 | - |
| mustOrderPjReceiveAmt | 必采配件收货 | - |
| mustOrderElseOrderAmt | 必采其他下单 | - |
| mustOrderElseReceiveAmt | 必采其他收货 | - |
| mustOrderStoreNum | 必采门店数 | - |
| mustOrderMoreStoreNum | 必采多店数 | - |

#### 其他指标

| 字段名 | 中文 | 说明 |
|-------|------|------|
| repurchaseRate | 复购率 | - |
| threeRate | 三单率 | - |
| saleBudget | 销售预算 | - |
| saleGrossBudget | 毛利预算 | - |
| stockGrossBudget | 库存毛利预算 | - |
| stockIncomeBudget | 库存收入预算 | - |
| returnAmt | 退货金额 | - |
| saleReturnAmt | 销售退货金额 | - |
| user19d | 19点用户数 | - |
| product | 生产量 | - |
| qdmBearPromotionFee | QDM承担促销费 | - |

---

### 6. product_center_business_sku_v3_info_di（商品表 SKU）⭐推荐

SKU 粒度，比 SPU 表多商品属性字段和价格竞争字段。

#### 与 SPU 表的差异字段

| 字段名 | 中文 | 说明 | 示例 |
|-------|------|------|------|
| articleId | 商品ID | SKU 编号 | '20000011' |
| articleName | 商品名称 | SKU 名称 | '麦菜' |
| articleGroupId | SPU ID | SPU 编号 | '20000011' |
| articleGroupName | SPU 名称 | SPU 名称 | '麦菜' |
| purchasePrice | 采购价 | SKU 采购单价 | 897.791 |
| priceIndex | 价格指数 | - | 933.1238 |
| priceIndexCore | 核心价格指数 | - | 0.0 |
| highPrice | 高价 | - | 535.6417 |
| highPriceCore | 核心高价 | - | 0.0 |
| marketPrice | 市场价 | - | 318.6604 |
| skuPriceNum | SKU比价数量 | - | 1.0 |
| skuPriceNumCore | 核心SKU比价数量 | - | 0.0 |
| skuRowPriceMarket | SKU行市场价格 | - | 1.0 |
| weightMarket | 市场重量 | - | 138.548 |

> SPU 表的其他字段（categoryDimension 值为 `'SKU维度'`）结构相同，参见上方 SPU 表说明。

---

## 三、选表指南

### 按分析目标选表

| 分析目标 | 推荐表 | 原因 |
|---------|-------|------|
| **门店经营日报/周报** | operation_center_wide_daily | 最全的运营指标宽表 |
| **门店信息查询** | operation_center_dim_store_profile_di | 门店静态属性 |
| **新店跟踪** | new_store_90d_weekly_store_di | 新店 KPI 和达成情况 |
| **新店区域汇总** | new_store_90d_weekly_region_di | 区域级新店经营 |
| **商品经营分析（SPU级）** | product_center_business_v3_info_di | SPU 聚合，适合品类分析 |
| **商品经营分析（SKU级）** | product_center_business_sku_v3_info_di ⭐ | SKU 粒度，含价格竞争指标 |
| **损耗分析** | operation_center_wide_daily / product_center_* | 均含损耗字段 |
| **折扣/促销分析** | 上述所有表 | 均含折扣字段 |
| **复购分析** | product_center_business_sku_v3_info_di | 含 repurchaseRate 和 buyAgainMemberNum |
| **价格竞争力** | product_center_business_sku_v3_info_di | 含 priceIndex、marketPrice 等 |

### 关联关系

```
operation_center_wide_daily
    └── 门店编号 ──→ operation_center_dim_store_profile_di (newSpStoreId)

product_center_business_sku_v3_info_di
    └── articleGroupId ──→ product_center_business_v3_info_di (SPU 聚合)
    └── areaName ──→ 可关联运营表

operation_center_new_store_90d_weekly_store_di
    └── storeId ──→ operation_center_dim_store_profile_di (newSpStoreId)
    └── manageAreaName ──→ new_store_90d_weekly_region_di
```

---

## 数据特点

| 项目 | 说明 |
|-----|------|
| 字段名 | 全中文（与翠花英文蛇形命名不同） |
| 百分比字段 | 返回字符串如 `'19.77%'`，计算时需 `CAST(REPLACE(字段名,'%','') AS DOUBLE)/100` |
| 日期字段 | timestamp 毫秒格式，筛选用 `FROM_UNIXTIME(日期/1000, 'yyyy-MM-dd')` |
| 数据限制 | 单次查询最多 50,000 条，超时 300 秒 |
