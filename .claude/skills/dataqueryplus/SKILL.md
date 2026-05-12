---
name: dataqueryplus
description: 增强版数据查询，使用大妈（商分数据库）取数。触发：用户说"取数"、"查数据"、"SQL"、"表结构"、"大妈"时使用。
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

> 所有查询默认使用**大妈**表体系（运营 + 商品模块）。

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

1. **字段名全中文**（运营表）
2. **百分比是字符串** `'19.77%'`，计算需 `CAST(REPLACE(字段名,'%','') AS DOUBLE)/100`
3. **日期是 timestamp 毫秒**，筛选用 `FROM_UNIXTIME(日期/1000, 'yyyy-MM-dd')`
4. **运营宽表层级** 由 `品类分层` 控制（门店/大分类/中分类/小分类/sku）
5. **运营宽表区域** 由 `门店汇总` + `门店汇总维度` 控制

> 字段详情见 [references/data_dictionary.md](references/data_dictionary.md)
> SQL 模板见 [references/sql_templates.md](references/sql_templates.md)

---

## 执行步骤

### Step 1: 确认数据需求

- 分析目标（门店经营？商品排行？损耗分析？）
- 时间范围
- 区域/门店筛选
- 返回字段

### Step 2: 选表

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

### Step 3: 构建 SQL 并执行

> SQL 模板见 [references/sql_templates.md](references/sql_templates.md)

### Step 4: 返回结果

返回结果是 Python 列表，每行一个字典：

```python
import pandas as pd
df = pd.DataFrame(result)
```

---

## 注意事项

| 项目 | 说明 |
|-----|------|
| 字段名格式 | 中文（运营表）/ 英文（商品表） |
| 百分比 | 运营表返回字符串 `'19.77%'`，需 CAST 处理 |
| 日期格式 | timestamp 毫秒，筛选用 `FROM_UNIXTIME(日期/1000, 'yyyy-MM-dd')` |
| 品类层级 | 运营表用 `品类分层` 字段 |
| 数据量限制 | 单次 50,000 条 |
| 超时 | 300 秒 |

---

## 环境配置

数据库连接通过 `.env` 配置：

- `API_HOST` — API 地址（默认 `https://bdapp.qdama.cn`）
- `API_ID` — API 接口 ID
- `ACCESS_KEY` / `SECRET_KEY` — 认证密钥
- `API_VERSION` — 版本号（默认 `1.0`）
- `ENCRYPT` — 加密模式（默认 `0`）

> 连接器代码见 [db_query.py](db_query.py)，也可直接 `from skills.dataqueryplus.db_query import create_db`。
