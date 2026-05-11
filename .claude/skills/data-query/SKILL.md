---
name: data-query
description: 数据查询和取数。触发：用户说"数据"、"取数"、"查数据"、"底表"、"表结构"、"字段"、"SQL"时使用。提供数据库连接、SQL 模板、字段说明，支持用户订单明细查询和品类销售汇总查询。
---

## 快速开始

```python
from dotenv import load_dotenv
load_dotenv()

from src.tools.db_connector import create_connector_from_config

db = create_connector_from_config()

# 方法1: 用户订单明细（RFM 分析用）
data = db.get_user_order_data(
    start_date="2026-02-10",      # SQL 查询起始日期
    end_date="2026-04-01",        # SQL 查询截止日期
    invalid_days=["2026-01-29"]   # 无效日期（节假日）自动过滤
)

# 方法2: 品类销售汇总（品类分析用）
category_data = db.get_category_sales_data(
    start_date="2026-03-20",
    end_date="2026-03-26"
)

# 方法3: 自定义 SQL
result = db.execute_query(sql)
```

---

## 封装方法

### get_user_order_data

从 `store_transaction_details` 获取用户订单明细，用于 RFM 分析。

**特点**：
- 自动将品类重分类为翠花标准品类（通过 SQL CASE 语句）
- 支持排除无效日期（节假日）

```python
data = db.get_user_order_data(
    start_date="2026-02-10",
    end_date="2026-04-01",
    invalid_days=["2026-01-29", "2026-02-01"],
    store_id=None  # 可选，默认全门店
)
```

**品类重分类规则**（在 SQL 层面执行）：

| 原始品类 | 重分类为 |
|---------|---------|
| 冷藏奶制品类、饮料类 | 乳制品及水饮类 |
| 肉禽蛋类（排除蛋类） | 肉禽类 |
| 三级品类以"熟食"结尾 | 熟食类 |
| 冷藏及加工类、预制菜 | 冷藏加工及预制菜类 |
| 蛋类、烘焙类 | 保持不变 |

> 完整 SQL 模板见 [references/sql_templates.md](references/sql_templates.md)

### get_category_sales_data

从 `strategy_fm_levels_result` 获取品类级 SKU 汇总数据，用于品类分析。

```python
data = db.get_category_sales_data(
    start_date="2026-03-20",
    end_date="2026-03-26"
)
# 返回: business_date, category, sub_category, sku_id, sku_name, sales, qty, customers
```

> 字段说明见 [references/data_dictionary.md](references/data_dictionary.md)

---

## 执行步骤

### Step 1: 确认数据需求
- 时间范围（开始/结束日期）
- 筛选条件（用户、品类、渠道等）
- 返回字段

> 字段说明见 [references/data_dictionary.md](references/data_dictionary.md)

### Step 2: 构建 SQL

> SQL 模板见 [references/sql_templates.md](references/sql_templates.md)

### Step 3: 执行查询

返回结果是 Python 列表，每行是一个字典：

```python
# 转为 DataFrame
import pandas as pd
df = pd.DataFrame(result)
```

---

## 注意事项

| 项目 | 说明 |
|-----|------|
| 字段名格式 | SQL 用下划线(`pay_at`)，返回驼峰(`payAt`) |
| 数据量限制 | 单次最多 50,000 条 |
| 超时时间 | 300 秒 |
| T-1 数据 | 截止日期 = 分析日期 - 1 |
| 品类重分类 | `get_user_order_data` 内置 CASE 语句，自动统一品类口径 |

---

## 环境配置

`.env` 文件配置：
- `API_HOST` — API 地址（默认 `https://bdapp.qdama.cn`）
- `API_ID` — API 接口 ID
- `ACCESS_KEY` / `SECRET_KEY` — 认证密钥
- `API_VERSION` — 版本号（默认 `1.0`）
- `ENCRYPT` — 加密模式（默认 `0`）
