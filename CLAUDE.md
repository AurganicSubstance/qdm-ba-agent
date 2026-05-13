# QDM BA Agent - 数据取数规则

## 数据库连接

通过 REST API 连接公司 SQL Server，使用 `.env` 中的凭据。

## 取数 Skill

使用 dataqueryplus skill 进行数据查询，参考 `.claude/skills/dataqueryplus/SKILL.md`。

## 核心表 (大妈商分数据库)

| 模块 | 表 | 路径 | 用途 |
|------|---|------|------|
| 运营 | 运营宽表 | `default_catalog.ads_business_analysis.operation_center_wide_daily` | 销售/利润/损耗/客流/折扣 |
| 运营 | 门店画像 | `default_catalog.ads_business_analysis.operation_center_dim_store_profile_di` | 门店基础信息 |
| 商品 | SKU销售 | `default_catalog.ads_business_analysis.product_center_business_sku_v3_info_di` | SKU级销售/利润/复购 |
| 商品 | SPU销售 | `default_catalog.ads_business_analysis.product_center_business_v3_info_di` | SPU级销售/物流指标 |

## 关键取数规则

1. 运营表门店级必须用 `品类分层='门店'`，否则会计重复
2. 运营表 `日期` 字段为毫秒时间戳，需 `FROM_UNIXTIME(日期/1000, 'yyyy-MM-dd')` 转换
3. 商品表用 `ym='YYYY-MM'` 过滤月份，SKU/SPU表只支持 `SELECT *`
4. 中文表名字段必须用反引号：`` `销售额` ``。英文表名字段不加引号：`articleName`
5. 数据从 2025-09-15 开始可用

## 自进化规则

以下规则由专家反馈自动追加，不要手动修改本节。
