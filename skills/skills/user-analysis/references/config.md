# RFM 指标与周期配置

## RFM 定义

| 指标 | 全称 | 计算方式 | 高值阈值 |
|-----|------|---------|---------|
| M | Monetary | `SUM(salesAmt)` | ≥ 135 元 |
| F | Frequency | `COUNT(DISTINCT orderId)` | ≥ 5 次 |
| R | Recency | `DATEDIFF(ref_date, MAX(payAt))` | ≤ 7 天 |

> **R 是反向的**：R 值越小代表越活跃

```python
from src.analyzers.user_analyzer import UserAnalyzer

analyzer = UserAnalyzer()
# 阈值已内置为类常量
# analyzer.M_THRESHOLD = 135
# analyzer.F_THRESHOLD = 5
# analyzer.R_THRESHOLD = 7
```

---

## 取数周期

| 规则 | 说明 |
|-----|------|
| 数据截止日期 | 分析日期 - 1（T-1） |
| 统计周期 | 28 个有效数据日 |
| 连续对比上期 | 本期开始 - 1 天，再往前 28 个有效日 |
| 无效日期 | 节假日自动跳过，向前补足（配置文件 `config/invalid_days.json`） |

```python
from src.tools.date_utils import get_valid_analysis_periods, load_invalid_days

invalid_days = load_invalid_days()  # 从 config/invalid_days.json
periods = get_valid_analysis_periods("2026-04-02", invalid_days=invalid_days)
```

返回结构：
```python
{
    "data_end_date": "2026-04-01",       # 数据截止日期
    "current_period": {"start": "...", "end": "...", "valid_days": 28},
    "previous_period": {"start": "...", "end": "...", "valid_days": 28},
    "sql_date_range": {"start": "...", "end": "..."}  # SQL 查询范围
}
```

---

## 品类分组

用于人群品类结构对比和 SKU 分组展示：

| 大类 | 包含品类 |
|-----|---------|
| **生鲜** | 猪肉类、蔬菜类、肉禽类、水果类、蛋类 |
| **新场景** | 烘焙类、熟食类 |
| **标品** | 乳制品及水饮类、冷藏加工及预制菜类、标品类 |
