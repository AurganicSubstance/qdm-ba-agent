---
name: dataqueryplus
description: 增强版数据查询，支持大妈（商分数据库）和翠花双品牌取数。触发：用户说"取数"、"查数据"、"SQL"、"表结构"、"大妈"、"翠花"时使用。默认查大妈表，用户明确说"翠花"时切换到翠花表。
---

## 快速开始

```python
# 方式1：使用 skill 自带连接器（推荐）
from skills.dataqueryplus.db_query import create_db

db = create_db()
result = db.execute_query(sql)

# 方式2：使用项目公共连接器
from src.tools.db_connector import create_connector_from_config
db = create_connector_from_config()
result = db.execute_query(sql)

# 转为 DataFrame
import pandas as pd
df = pd.DataFrame(result)
```

**CLI 快速查询**：
```bash
python skills/dataqueryplus/db_query.py "SELECT * FROM default_catalog.ads_business_analysis.operation_center_wide_daily LIMIT 5"
```

---

## 品牌路由

| 用户表达 | 路由到 | 表范围 |
|---------|-------|--------|
| 大妈、商分、默认（没说翠花） | **大妈表** | 运营 + 商品模块 |
| 翠花 | **翠花表** | strategy_fm_levels_result + store_transaction_details |

> 用户只说"取数"、"查数据"等通用词 → 默认走**大妈**。

---

## 大妈表体系（默认）

按营采销分三个模块，当前已接入**运营**和**商品**：

### 运营模块（4张表）

| 表名 | 用途 | 常用场景 |
|-----|------|---------|
| operation_center_wide_daily | 运营宽表 ⭐核心 | 门店日报、品类排行、损耗分析 |
| operation_center_dim_store_profile_di | 门店资料表 | 查门店信息、组织架构 |
| operation_center_new_store_90d_weekly_store_di | 新店门店维度 | 新店经营跟踪 |
| operation_center_new_store_90d_weekly_region_di | 新店区域维度 | 区域新店汇总 |

### 商品模块（2张表）

| 表名 | 用途 | 常用场景 |
|-----|------|---------|
| product_center_business_v3_info_di | 商品表 SPU | 品类级汇总 |
| product_center_business_sku_v3_info_di ⭐ | 商品表 SKU | SKU 级分析、复购、价格竞争 |

### 物流模块（待接入）

> 暂无，后续提供表结构后补充。

### 大妈表核心特点

1. **字段名全中文**（与翠花英文蛇形命名不同）
2. **百分比是字符串** `'19.77%'`，计算需 `CAST(REPLACE(字段名,'%','') AS DOUBLE)/100`
3. **日期是 timestamp 毫秒**，筛选用 `FROM_UNIXTIME(日期/1000, 'yyyy-MM-dd')`
4. **运营宽表层级** 由 `品类分层` 控制（门店/大分类/中分类/小分类/sku）
5. **运营宽表区域** 由 `门店汇总` + `门店汇总维度` 控制

> 字段详情见 [references/data_dictionary.md](references/data_dictionary.md)
> SQL 模板见 [references/sql_templates.md](references/sql_templates.md)

---

## 翠花表体系

当用户明确说"翠花"时使用，走原有 data-query skill 的两张表：

| 表名 | 用途 |
|-----|------|
| strategy_fm_levels_result | 商品经营分析主表 |
| store_transaction_details | 订单明细表 |

> 翠花表的字段说明和 SQL 模板见 `skills/data-query/references/` 目录。
> 封装方法 `db.get_user_order_data()` 和 `db.get_category_sales_data()` 仅适用于翠花。

---

## 执行步骤

### Step 1: 判断品牌

- 用户提到"翠花" → 走翠花表体系
- 用户提到"大妈" 或 未指明 → 走大妈表体系

### Step 2: 确认数据需求

- 分析目标（门店经营？商品排行？损耗分析？）
- 时间范围
- 区域/门店筛选
- 返回字段

### Step 3: 选表

**大妈运营场景：**

| 分析目标 | 推荐表 |
|---------|-------|
| 门店日报/周报 | operation_center_wide_daily（`品类分层='门店'`） |
| 品类销售排行 | operation_center_wide_daily（`品类分层='中分类'`） |
| 损耗分析 | operation_center_wide_daily |
| 新店跟踪 | new_store_90d_weekly_store_di |
| 门店信息 | operation_center_dim_store_profile_di |

**大妈商品场景：**

| 分析目标 | 推荐表 |
|---------|-------|
| SKU 级销售/利润 | product_center_business_sku_v3_info_di ⭐ |
| 品类级汇总 | product_center_business_v3_info_di |
| 复购分析 | product_center_business_sku_v3_info_di |
| 价格竞争力 | product_center_business_sku_v3_info_di |
| 必采分析 | product_center_business_sku_v3_info_di |

### Step 4: 构建 SQL 并执行

> SQL 模板见 [references/sql_templates.md](references/sql_templates.md)

### Step 5: 返回结果

返回结果是 Python 列表，每行一个字典：

```python
import pandas as pd
df = pd.DataFrame(result)
```

---

## 注意事项

| 项目 | 大妈表 | 翠花表 |
|-----|-------|-------|
| 字段名格式 | 中文 | 英文下划线 |
| 百分比 | 字符串 `'19.77%'` | 小数 `0.1977` |
| 日期格式 | timestamp 毫秒 | 字符串 `'YYYY-MM-DD'` |
| 品类层级 | `品类分层` 字段 | `level_description` 字段 |
| 封装方法 | 无（用 execute_query） | get_user_order_data / get_category_sales_data |
| 数据量限制 | 单次 50,000 条 | 单次 50,000 条 |
| 超时 | 300 秒 | 300 秒 |

---

## 环境配置

与翠花共用数据库连接，`.env` 配置不变：

- `API_HOST` — API 地址（默认 `https://bdapp.qdama.cn`）
- `API_ID` — API 接口 ID
- `ACCESS_KEY` / `SECRET_KEY` — 认证密钥
- `API_VERSION` — 版本号（默认 `1.0`）
- `ENCRYPT` — 加密模式（默认 `0`）

> 连接器代码见 [db_query.py](db_query.py)，也可直接 `from skills.dataqueryplus.db_query import create_db`。
