# -*- coding: utf-8 -*-
"""
数据库查询脚本 — dataqueryplus skill 专用

用法：
    python -m skills.dataqueryplus.db_query "SELECT * FROM ... LIMIT 10"

或作为模块导入：
    from skills.dataqueryplus.db_query import create_db, query

    db = create_db()
    rows = db.execute_query("SELECT ...")
"""

import hashlib
import json
import os
import random
import re
import string
import sys
import time
from typing import Dict, List, Optional
from datetime import datetime

import requests


def _validate_date(date_str: str) -> str:
    if not date_str:
        raise ValueError("日期不能为空")
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
        raise ValueError(f"无效的日期格式: {date_str}，应为 YYYY-MM-DD")
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError as e:
        raise ValueError(f"无效的日期: {date_str}") from e
    return date_str


class DBConnectorError(Exception):
    pass


class DBConnector:
    """
    通用数据库连接器（通过 REST API 执行 SQL）

    大妈表和翠花表共用同一个连接，区别只在 SQL 中的表名和字段名。

    用法：
        db = DBConnector(
            api_host="https://bdapp.qdama.cn",
            api_id="xxx",
            access_key="xxx",
            secret_key="xxx"
        )
        rows = db.execute_query("SELECT * FROM ... LIMIT 10")
    """

    def __init__(
        self,
        api_host: str,
        api_id: str,
        access_key: str,
        secret_key: str,
        api_version: str = "1.0",
        encrypt: int = 0,
        timeout: int = 300,
    ):
        self.api_host = api_host.rstrip("/")
        self.api_id = api_id
        self.access_key = access_key
        self.secret_key = secret_key
        self.api_version = api_version
        self.encrypt = encrypt
        self.timeout = timeout

    def execute_query(self, sql: str, params: Optional[Dict] = None) -> List[Dict]:
        """执行 SQL 查询，返回 list[dict]"""
        param_map = {"apiId": self.api_id, "sql": sql}
        if params:
            param_map["params"] = params

        body_str = json.dumps({"apiId": self.api_id, "paramMap": param_map}, ensure_ascii=False)

        nonce = ''.join(random.choices(string.ascii_letters + string.digits, k=6))
        timestamp = int(time.time() * 1000)
        sign = self._generate_sign(timestamp, nonce, body_str)

        query_params = {
            "AccessKey": self.access_key,
            "timestamp": timestamp,
            "nonce": nonce,
            "encrypt": self.encrypt,
            "version": self.api_version,
            "sign": sign,
        }
        query_str = '&'.join([f"{k}={v}" for k, v in query_params.items()])
        url = f"{self.api_host}/api/v1/executeApi/{self.api_id}?{query_str}"

        try:
            response = requests.post(
                url,
                data=body_str.encode('utf-8'),
                headers={"Content-Type": "application/json"},
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.exceptions.Timeout:
            raise DBConnectorError(f"请求超时 ({self.timeout}s)")
        except requests.exceptions.RequestException as e:
            raise DBConnectorError(f"请求失败: {e}")

        try:
            data = response.json()
        except (json.JSONDecodeError, ValueError) as e:
            raise DBConnectorError(f"响应解析失败: {response.text[:200]}") from e

        if data.get("code") != 0:
            raise DBConnectorError(f"API 错误: {data.get('msg', data)}")

        result = data.get("data", [])
        if isinstance(result, dict):
            return result.get("pageData", [])
        return result if isinstance(result, list) else []

    def query_dama(self, sql: str) -> List[Dict]:
        """执行大妈表查询（语义别名）"""
        return self.execute_query(sql)

    def query_cuihua(self, sql: str) -> List[Dict]:
        """执行翠花表查询（语义别名）"""
        return self.execute_query(sql)

    # ── 翠花封装方法 ──────────────────────────────────────

    def get_cuihua_user_order_data(
        self,
        start_date: str,
        end_date: str,
        invalid_days: Optional[List[str]] = None,
        store_id: Optional[str] = None,
    ) -> List[Dict]:
        """翠花：获取用户订单明细（含品类重分类）"""
        start_date = _validate_date(start_date)
        end_date = _validate_date(end_date)
        if invalid_days:
            invalid_days = [_validate_date(d) for d in invalid_days]

        sql = f"""
        SELECT
            thirdparty_user_identity,
            customer_phone,
            order_id,
            pay_at,
            sales_amt,
            channel,
            abi_article_id,
            article_name,
            category_level2_description,
            category_level3_description,
            CASE
                WHEN category_level2_description IN ('蛋类','烘焙类') THEN category_level2_description
                WHEN category_level2_description IN ('冷藏奶制品类','饮料类') THEN '乳制品及水饮类'
                WHEN category_level1_description = '肉禽蛋类' AND category_level2_description <> '蛋类' THEN '肉禽类'
                WHEN RIGHT(category_level3_description, 2) = '熟食' THEN '熟食类'
                WHEN category_level1_description IN ('冷藏及加工类','预制菜') THEN '冷藏加工及预制菜类'
                ELSE category_level1_description
            END AS category_level1_description
        FROM default_catalog.ads_business_analysis.store_transaction_details
        WHERE DATE(pay_at) >= '{start_date}'
          AND DATE(pay_at) <= '{end_date}'
        """

        if invalid_days:
            invalid_str = ", ".join([f"'{d}'" for d in invalid_days])
            sql += f" AND DATE(pay_at) NOT IN ({invalid_str})"
        if store_id:
            if not re.match(r'^[\w\-]+$', store_id):
                raise ValueError(f"无效的 store_id: {store_id}")
            sql += f" AND store_id = '{store_id}'"
        sql += " ORDER BY pay_at DESC"

        return self.execute_query(sql)

    def get_cuihua_category_sales_data(
        self,
        start_date: str,
        end_date: str,
    ) -> List[Dict]:
        """翠花：获取品类销售汇总"""
        start_date = _validate_date(start_date)
        end_date = _validate_date(end_date)

        sql = f"""
        SELECT
            business_date,
            category_level1_description AS category,
            category_level2_description AS sub_category,
            sku_id,
            category_name AS sku_name,
            SUM(total_sale_amount) AS sales,
            SUM(total_sale_qty) AS qty,
            SUM(total_customer_count) AS customers
        FROM default_catalog.ads_business_analysis.strategy_fm_levels_result
        WHERE business_date >= '{start_date}'
          AND business_date <= '{end_date}'
          AND level_description = 'sku'
          AND category_level1_description IS NOT NULL
          AND category_level1_description != ''
        GROUP BY business_date, category_level1_description, category_level2_description, sku_id, category_name
        """

        return self.execute_query(sql)

    def _generate_sign(self, timestamp: int, nonce: str, body_str: str) -> str:
        sign_params = {
            "AccessKey": self.access_key,
            "encrypt": self.encrypt,
            "nonce": nonce,
            "timestamp": timestamp,
            "version": self.api_version,
        }
        if body_str:
            sign_params["bodyStr"] = body_str

        filtered = {k: v for k, v in sign_params.items() if v not in (None, "")}
        keys = sorted(filtered.keys())
        param_str = '&'.join([f"{k}={filtered[k]}" for k in keys])
        param_str += f"&SecretKey={self.secret_key}"

        md5 = hashlib.md5()
        md5.update(param_str.encode('utf-8'))
        return md5.hexdigest().upper()


def create_db() -> DBConnector:
    """从 .env 环境变量创建连接器"""
    from dotenv import load_dotenv
    load_dotenv()

    missing = []
    for var in ("API_ID", "ACCESS_KEY", "SECRET_KEY"):
        if not os.getenv(var):
            missing.append(var)
    if missing:
        raise DBConnectorError(f"缺少环境变量: {', '.join(missing)}")

    return DBConnector(
        api_host=os.getenv("API_HOST", "https://bdapp.qdama.cn"),
        api_id=os.getenv("API_ID"),
        access_key=os.getenv("ACCESS_KEY"),
        secret_key=os.getenv("SECRET_KEY"),
        api_version=os.getenv("API_VERSION", "1.0"),
        encrypt=int(os.getenv("ENCRYPT", "0")),
    )


# ── CLI 入口 ──────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python db_query.py \"SELECT ...\"")
        sys.exit(1)

    sql = sys.argv[1]
    db = create_db()

    try:
        rows = db.execute_query(sql)
        print(json.dumps(rows, ensure_ascii=False, indent=2, default=str))
    except DBConnectorError as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)
