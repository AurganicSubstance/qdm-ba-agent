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
    prompt = f"""You are a SQL expert for a fresh-food supermarket database. Write a SINGLE SQL query for this data retrieval question.

Database tables available:

TABLE strategy_fm_levels_result (full path: default_catalog.ads_business_analysis.strategy_fm_levels_result):
- Store-level (level_description='门店'): business_date, store_no, store_name, store_flag,
  total_sale_amount, total_customer_count, total_per_customer_transaction,
  full_link_profit_amount, full_link_profit_rate, store_profit_amount, store_profit_rate,
  store_pricing_profit_rate, store_expected_profit_rate,
  supply_chain_profit_rate, supply_chain_expected_profit_rate,
  loss_amount, loss_rate, loss_rate_qty,
  discount_rate, promotional_discount_rate, time_period_discount_rate,
  inbound_amount, inbound_price, purchase_price,
  average_selling_price, average_sales_original_price,
  soldout_rate_16, soldout_rate_20, turnover_rate,
  operating_store_days, operating_store_count
- SKU-level (level_description='sku'): same fields + sku_id, category_name, category_level1/2/3_description
- Sub-category (level_description='小分类'): grouped by category_level3_description
- Mid-category (level_description='中分类'): grouped by category_level2_description
- Large-category (level_description='大分类'): grouped by category_level1_description
- ALWAYS include: WHERE day_clear = '1'
- For store-level traffic/ticket: MUST use level_description='门店' (otherwise customer_count is NOT deduplicated!)
- Date range: data available from 2025-09-15 to 2026-05-10
- Only one store: store_no = 'food mart' (广州滨江宏岸店)

TABLE store_transaction_details (full path: default_catalog.ads_business_analysis.store_transaction_details):
- order_id, pay_at (datetime), sales_amt, channel (线上/线下),
  thirdparty_user_identity (user ID), customer_phone,
  abi_article_id, article_name,
  category_level1/2/3_description
- One row per product per order (order_id can repeat)
- For user counting: COUNT(DISTINCT thirdparty_user_identity)
- For order counting: COUNT(DISTINCT order_id)

SQL rules:
1. Return a clean SELECT query, NO markdown fences, NO explanations
2. Always include WHERE conditions for date range
3. Use level_description='门店' for store-level aggregates
4. Use DATE_FORMAT for month grouping, DATE() for day grouping
5. ORDER BY date/group appropriately
6. Round decimal results to 2-4 places
7. Do NOT use LIMIT unless the question specifically asks for "top N"
8. Only output the SQL, nothing else

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
