# -*- coding: utf-8 -*-
"""
数据库连接器模块
通过 REST API 执行 SQL 查询
"""

import hashlib
import json
import random
import re
import string
import time
import requests
from typing import Dict, List, Optional
from datetime import datetime


def _validate_date(date_str: str) -> str:
    """
    验证日期格式，防止 SQL 注入

    Args:
        date_str: 日期字符串，应为 YYYY-MM-DD 格式

    Returns:
        验证后的日期字符串

    Raises:
        ValueError: 如果日期格式无效
    """
    if not date_str:
        raise ValueError("日期不能为空")
    # 只允许 YYYY-MM-DD 格式
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
        raise ValueError(f"无效的日期格式: {date_str}，应为 YYYY-MM-DD")
    # 尝试解析验证
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError as e:
        raise ValueError(f"无效的日期: {date_str}") from e
    return date_str


class DBConnectorError(Exception):
    """数据库连接器异常"""
    pass


class UserDBConnector:
    """
    用户数据库连接器

    通过 REST API 访问业务数据库，执行 SQL 查询。

    使用示例:
        db = UserDBConnector(
            api_host="https://bdapp.qdama.cn",
            api_id="xxx",
            access_key="xxx",
            secret_key="xxx"
        )
        data = db.execute_query("SELECT * FROM users LIMIT 10")
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

    def execute_query(
        self,
        sql: str,
        params: Optional[Dict] = None
    ) -> List[Dict]:
        """
        执行 SQL 查询

        Args:
            sql: SQL 查询语句
            params: 查询参数（暂未使用）

        Returns:
            查询结果列表
        """
        # 构建请求体
        param_map = {
            "apiId": self.api_id,
            "sql": sql
        }
        body_dict = {
            "apiId": self.api_id,
            "paramMap": param_map
        }
        body_str = json.dumps(body_dict, ensure_ascii=False)

        # 生成签名参数
        nonce = ''.join(random.choices(string.ascii_letters + string.digits, k=6))
        timestamp = int(time.time() * 1000)
        sign = self._generate_sign(timestamp, nonce, body_str)

        # 构建请求 URL
        query_params = {
            "AccessKey": self.access_key,
            "timestamp": timestamp,
            "nonce": nonce,
            "encrypt": self.encrypt,
            "version": self.api_version,
            "sign": sign
        }
        query_str = '&'.join([f"{k}={v}" for k, v in query_params.items()])
        url = f"{self.api_host}/api/v1/executeApi/{self.api_id}?{query_str}"

        # 发送请求
        headers = {"Content-Type": "application/json"}
        try:
            response = requests.post(
                url,
                data=body_str.encode('utf-8'),
                headers=headers,
                timeout=self.timeout
            )
            response.raise_for_status()
        except requests.exceptions.Timeout:
            raise DBConnectorError(f"请求超时 ({self.timeout}s)")
        except requests.exceptions.RequestException as e:
            raise DBConnectorError(f"请求失败: {e}")

        # 解析响应
        try:
            data = response.json()
        except (json.JSONDecodeError, ValueError) as e:
            raise DBConnectorError(f"响应解析失败: {response.text[:200]}") from e

        if data.get("code") != 0:
            raise DBConnectorError(f"API 错误: {data.get('msg', data)}")

        # 提取数据
        result = data.get("data", [])
        if isinstance(result, dict):
            return result.get("pageData", [])
        return result if isinstance(result, list) else []

    def get_user_order_data(
        self,
        start_date: str,
        end_date: str,
        invalid_days: Optional[List[str]] = None,
        store_id: Optional[str] = None,
    ) -> List[Dict]:
        """
        获取用户订单数据

        Args:
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            invalid_days: 无效日期列表（节假日），这些日期会被过滤
            store_id: 门店ID (可选)

        Returns:
            订单明细列表
        """
        # 验证日期格式，防止 SQL 注入
        start_date = _validate_date(start_date)
        end_date = _validate_date(end_date)

        if invalid_days:
            invalid_days = [_validate_date(d) for d in invalid_days]

        # 字段名在 SQL 中用下划线格式，返回结果自动转为驼峰
        # 品类映射：按翠花标准重新分类
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

        # 过滤无效日期
        if invalid_days:
            invalid_str = ", ".join([f"'{d}'" for d in invalid_days])
            sql += f" AND DATE(pay_at) NOT IN ({invalid_str})"

        # store_id 只允许字母数字和下划线
        if store_id:
            if not re.match(r'^[\w\-]+$', store_id):
                raise ValueError(f"无效的 store_id: {store_id}")
            sql += f" AND store_id = '{store_id}'"

        sql += " ORDER BY pay_at DESC"

        return self.execute_query(sql)

    def get_category_sales_data(
        self,
        start_date: str,
        end_date: str,
    ) -> List[Dict]:
        """
        获取品类销售数据（用于品类分析）

        从 strategy_fm_levels_result 表获取品类级别的汇总数据

        Args:
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)

        Returns:
            品类销售数据列表
        """
        # 验证日期格式
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

    def _generate_sign(
        self,
        timestamp: int,
        nonce: str,
        body_str: str
    ) -> str:
        """生成 API 签名"""
        sign_params = {
            "AccessKey": self.access_key,
            "encrypt": self.encrypt,
            "nonce": nonce,
            "timestamp": timestamp,
            "version": self.api_version
        }

        if body_str:
            sign_params["bodyStr"] = body_str

        # 过滤空值并按字母顺序排序
        filtered = {k: v for k, v in sign_params.items() if v not in (None, "")}
        keys = sorted(filtered.keys())

        # 拼接参数字符串
        param_str = '&'.join([f"{k}={filtered[k]}" for k in keys])
        param_str += f"&SecretKey={self.secret_key}"

        # MD5 加密并转大写
        md5 = hashlib.md5()
        md5.update(param_str.encode('utf-8'))
        return md5.hexdigest().upper()


def create_connector_from_config() -> UserDBConnector:
    """从环境变量创建连接器"""
    import os

    # 验证必要的环境变量
    missing_vars = []
    api_id = os.getenv("API_ID")
    access_key = os.getenv("ACCESS_KEY")
    secret_key = os.getenv("SECRET_KEY")

    if not api_id:
        missing_vars.append("API_ID")
    if not access_key:
        missing_vars.append("ACCESS_KEY")
    if not secret_key:
        missing_vars.append("SECRET_KEY")

    if missing_vars:
        raise DBConnectorError(
            f"缺少必要的环境变量: {', '.join(missing_vars)}。"
            f"请在 GitHub Secrets 或 .env 文件中配置这些变量。"
        )

    return UserDBConnector(
        api_host=os.getenv("API_HOST", "https://bdapp.qdama.cn"),
        api_id=api_id,
        access_key=access_key,
        secret_key=secret_key,
        api_version=os.getenv("API_VERSION", "1.0"),
        encrypt=int(os.getenv("ENCRYPT", "0")),
    )
