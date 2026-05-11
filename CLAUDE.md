# QDM BA Agent - 数据取数规则

## 数据库连接

通过 REST API 连接公司 SQL Server，使用 `.env` 中的凭据。

## 取数 Skill

使用 `/data-query` skill 进行数据查询，参考 `skills/data-query/SKILL.md`。

## 核心表

| 表 | 路径 | 用途 |
|---|------|------|
| 经营分析主表 | `default_catalog.ads_business_analysis.strategy_fm_levels_result` | 销售/利润/损耗/库存/客流 |
| 订单明细表 | `default_catalog.ads_business_analysis.store_transaction_details` | 用户级订单明细 |

## 关键取数规则

1. 门店级客流/客单价必须用 `level_description='门店'`，否则客流会计重复
2. 必须加 `day_clear='1'` 过滤未结算数据
3. 数据从 2025-09-15 开始可用
4. 当前仅一家门店：广州滨江宏岸店 (food mart)

## 自进化规则

以下规则由专家反馈自动追加，不要手动修改本节。
