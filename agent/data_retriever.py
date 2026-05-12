"""
Data Retriever Agent.
Takes a question → builds SQL via LLM → executes via db_connector → returns table + SQL.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from src.tools.db_connector import create_connector_from_config, DBConnectorError
from agent.config import MAX_RESULT_ROWS
from agent.llm_client import chat as llm_chat
import json
import re


def _build_sql(question: dict) -> str:
    """Use LLM to build a SQL query for the given question."""
    prompt = f"""You are a SQL expert for a fresh-food supermarket (翠花 brand). Write a SINGLE SQL query.

DEFAULT TABLE — 大妈运营宽表 (default_catalog.ads_business_analysis.operation_center_wide_daily):
This is the PRIMARY table. One row = one aggregation level × one day. ALL Chinese field names.

DIMENSION FIELDS:
- 日期 (timestamp millis) — filter with: FROM_UNIXTIME(日期/1000, 'yyyy-MM-dd') >= '2025-09-15'
- 品类分层 — data level: '门店'(store daily, customer_count IS deduped), '大分类','中分类','小分类','sku'
- 品类名称 — category name at current level
- 门店汇总 — region or store name, e.g. '广州滨江宏岸店'
- 门店汇总维度 — aggregation type: '管理区域','大区','门店'

SALES METRICS: 销售额, 销售重量, 全天来客数, 客单价, 平均售价, 原价, 在售sku
PRE-7PM METRICS: 19点前销售额, 19点前来客数, 19点前客单价, 19点前pi
PROFIT METRICS: 全链路毛利额, 全链路毛利率, 门店毛利额, 门店毛利率, 供应链毛利额, 供应链毛利率, 供应链预期毛利率, 门店定价毛利率
INVENTORY METRICS: 进货金额, 进货重量, 门店进货价, 采购价
LOSS METRICS: 门店损耗额, 门店损耗率
DISCOUNT METRICS: 促销折扣额, 促销折扣率, 时段折扣额, 时段折扣率
OTHER: 营业店日数, 营业门店数

IMPORTANT for operation_center_wide_daily:
- Percentages are STRINGS like '19.77%'. To calculate: CAST(REPLACE(门店损耗率,'%','') AS DOUBLE)/100
- Store-level: WHERE 门店汇总维度='门店' AND 品类分层='门店'
- Category: WHERE 品类分层='中分类' AND 品类名称='蔬菜类'
- Date: WHERE FROM_UNIXTIME(日期/1000, 'yyyy-MM-dd') >= '2025-09-15'
- Region: WHERE 门店汇总维度='管理区域' AND 门店汇总='华南区'
- There are MULTIPLE stores (not just one). Use 门店汇总 to filter by store name.

USER-LEVEL TABLE — store_transaction_details (default_catalog.ads_business_analysis.store_transaction_details):
- order_id, pay_at (datetime), sales_amt, channel (线上/线下),
  thirdparty_user_identity (user ID), customer_phone,
  abi_article_id, article_name, category_level1/2/3_description
- For user/repurchase analysis: COUNT(DISTINCT thirdparty_user_identity), COUNT(DISTINCT order_id)

SQL RULES:
1. Return ONLY the SQL query, no markdown, no backticks, no explanations
2. Default to operation_center_wide_daily unless the question is about users/orders
3. For store-level: 品类分层='门店' AND 门店汇总维度='门店'
4. Date filtering: FROM_UNIXTIME(日期/1000, 'yyyy-MM-dd')
5. ORDER BY date/group appropriately
6. Round decimal results to 2-4 places
7. Do NOT use LIMIT unless question asks for "top N"

Question: {question['question']}
Hint tables: {question.get('tables_hint', '')}
Hint fields: {question.get('fields_hint', '')}
Expected output: {question.get('expected_output_type', '')}"""

    try:
        sql = llm_chat(
            system_prompt="You are a SQL expert. Reply with ONLY the SQL query, no markdown, no backticks, no explanations.",
            user_message=prompt,
            temperature=0.1,
        ).strip()
        sql = re.sub(r'^```(?:sql)?\s*', '', sql)
        sql = re.sub(r'\s*```$', '', sql)
        sql = sql.strip().rstrip(";")
        return sql
    except Exception as e:
        raise RuntimeError(f"SQL generation failed: {e}")


def execute_question(question: dict) -> dict:
    """
    Execute a data retrieval question.

    Returns: {
        "question_id": str,
        "status": "success" | "error",
        "sql": str,
        "columns": [str],
        "rows": [[...]],
        "row_count": int,
        "error": str | None,
    }
    """
    result = {
        "question_id": question["id"],
        "status": "error",
        "sql": "",
        "columns": [],
        "rows": [],
        "row_count": 0,
        "error": None,
    }

    try:
        sql = _build_sql(question)
        result["sql"] = sql

        db = create_connector_from_config()
        data = db.execute_query(sql)

        if not data:
            result["status"] = "success"
            result["error"] = "Query returned 0 rows"
            return result

        # Truncate if too many rows
        if len(data) > MAX_RESULT_ROWS:
            data = data[:MAX_RESULT_ROWS]

        columns = list(data[0].keys())
        rows = [[row.get(c) for c in columns] for row in data]

        result["status"] = "success"
        result["columns"] = columns
        result["rows"] = rows
        result["row_count"] = len(rows)

    except DBConnectorError as e:
        result["error"] = f"DB Error: {e}"
    except Exception as e:
        result["error"] = f"Error: {e}"

    return result
