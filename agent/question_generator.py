"""
Question Generator Agent.
Reads KnowledgeBase docs → uses LLM to generate low-complexity data retrieval questions.
"""
import random
import json
import re
import os
from pathlib import Path
from datetime import datetime
from typing import Optional

from agent.config import KB_2026_PATH, KB_2025_PATH, QUESTIONS_PER_DAY
from agent.llm_client import chat as llm_chat


def _find_md_files(base_path: str, limit: int = 5) -> list[dict]:
    """Find markdown files in the KB, preferring 专项类 (analysis) documents."""
    results = []
    for root, dirs, files in os.walk(base_path):
        # Skip non-analysis directories
        rel = os.path.relpath(root, base_path)
        parts = rel.split(os.sep)
        if any(skip in parts for skip in ["会议纪要类", "images", ".git"]):
            continue
        for f in files:
            if f.endswith(".md") and not f.startswith("."):
                full_path = os.path.join(root, f)
                results.append(full_path)
    if len(results) <= limit:
        # Also try 2025年 if not enough in 2026年
        for root, dirs, files in os.walk(KB_2025_PATH):
            for f in files:
                if f.endswith(".md"):
                    results.append(os.path.join(root, f))
    random.shuffle(results)
    return results[:limit]


def _parse_front_matter(content: str) -> dict:
    """Extract YAML front matter from markdown."""
    if not content.startswith("---"):
        return {}
    end = content.find("---", 3)
    if end == -1:
        return {}
    fm_text = content[3:end].strip()
    fm = {}
    current_key = None
    for line in fm_text.split("\n"):
        if line.startswith("- ") and current_key:
            existing = fm.get(current_key, [])
            if isinstance(existing, str):
                existing = [existing]
            existing.append(line[2:].strip())
            fm[current_key] = existing
        elif ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if val:
                fm[key] = val
            else:
                fm[key] = []
            current_key = key
    return fm


def _read_doc_sample(filepath: str, max_lines: int = 150) -> dict:
    """Read a KB document and extract front matter + first few paragraphs."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return {}
    fm = _parse_front_matter(content)
    # Get first N non-empty lines of body
    body_start = content.find("---", 3)
    if body_start == -1:
        body_start = 0
    else:
        body_start = content.find("\n", body_start + 3) + 1
    body_lines = [l for l in content[body_start:].split("\n") if l.strip() and not l.startswith("!")]
    body_sample = "\n".join(body_lines[:max_lines])
    return {
        "file": os.path.basename(filepath),
        "metrics": fm.get("metrics", []),
        "tags": fm.get("tags", []),
        "title": fm.get("title", ""),
        "group": fm.get("group", ""),
        "body_sample": body_sample,
    }


def _call_llm(prompt: str) -> str:
    """Call LLM via Anthropic SDK (DeepSeek V4 Pro backend)."""
    return llm_chat(
        system_prompt="You are a data analyst for a fresh-food supermarket chain. You understand retail KPIs and SQL. Respond in Chinese. Output ONLY valid JSON — no other text, no markdown fences.",
        user_message=prompt,
        temperature=0.8,
    )


def _classify_domain_fast(question: str) -> str:
    """Fast keyword-based domain classification (no LLM needed)."""
    q = question.lower()
    if any(kw in q for kw in ["会员", "用户", "复购", "留存", "频次", "r", "f", "m", "rfm"]):
        return "用户"
    if any(kw in q for kw in ["供应链", "物流", "损耗", "库存", "加工", "周转", "进价"]):
        return "物流"
    if any(kw in q for kw in ["品类", "sku", "商品", "采购", "定价", "竞价", "毛利"]):
        return "商品"
    return "运营"


def _classify_domain(question: str) -> str:
    """Classify a question into one of the four expert domains (LLM-based)."""
    try:
        result = _call_llm(f"""Classify this data retrieval question into exactly one domain:
- 商品: about products, SKUs, categories, procurement, pricing, bidding
- 运营: about stores, sales, traffic, ticket size, promotions, operations
- 物流: about supply chain, processing, inventory, loss/waste
- 用户: about members, RFM, repurchase, retention, user behavior

Question: {question}

Reply with just one word: 商品, 运营, 物流, or 用户.""").strip()
        for domain in ["商品", "运营", "物流", "用户"]:
            if domain in result:
                return domain
    except Exception:
        pass
    return _classify_domain_fast(question)


def generate_questions(dry_run: bool = False) -> list[dict]:
    """
    Generate N data retrieval questions based on KnowledgeBase documents.
    """
    today = datetime.now().strftime("%Y%m%d")

    if dry_run:
        print("[DRY RUN] Using fallback questions (skipping LLM + KB scan)")
        questions = _generate_fallback_questions(today)
    else:
        questions = _generate_via_llm(today)

    # Classify domain and assign expert for all questions
    for i, q in enumerate(questions):
        q.setdefault("id", f"{today}_{i+1:02d}")
        domain = _classify_domain(q["question"])
        q["domain"] = domain
        expert = _get_expert_for_domain(domain)
        q["expert_name"] = expert["name"]
        q["expert_email"] = expert["email"]

    return questions[:QUESTIONS_PER_DAY]


def _generate_via_llm(today: str) -> list[dict]:
    """Generate questions using LLM + KnowledgeBase context."""
    md_files = _find_md_files(KB_2026_PATH, limit=5)
    doc_samples = [_read_doc_sample(f) for f in md_files]
    doc_samples = [d for d in doc_samples if d.get("body_sample")]

    if not doc_samples:
        print("[WARN] No KB docs found, using fallback questions")
        return _generate_fallback_questions(today)

    # Step 2: Build LLM prompt with doc context
    docs_context = ""
    for i, doc in enumerate(doc_samples, 1):
        docs_context += f"""
--- Document {i} ---
Title: {doc.get('title', 'Unknown')}
Group: {doc.get('group', 'Unknown')}
Metrics referenced: {', '.join(doc.get('metrics', []))}
Tags: {', '.join(doc.get('tags', []))}
Body excerpt:
{doc['body_sample'][:800]}
"""

    prompt = f"""You are a data retrieval specialist for a fresh-food supermarket (翠花 brand). Write questions for the 大妈 database.

PRIMARY TABLE: `default_catalog.ads_business_analysis.operation_center_wide_daily` (运营宽表)
- ALL Chinese field names. One row = one aggregation level × one day.
- Dimension: 日期(timestamp ms), 品类分层(门店/大分类/中分类/小分类/sku), 品类名称, 门店汇总(store/region), 门店汇总维度(管理区域/大区/门店)
- Sales: 销售额, 销售重量, 全天来客数, 客单价, 平均售价
- Profit: 全链路毛利额, 全链路毛利率, 门店毛利额, 门店毛利率, 供应链毛利率, 供应链预期毛利率, 门店定价毛利率
- Loss: 门店损耗额, 门店损耗率
- Discount: 促销折扣额, 促销折扣率, 时段折扣额, 时段折扣率
- Inventory: 进货金额, 门店进货价, 采购价
- Store-level: WHERE 门店汇总维度='门店' AND 品类分层='门店'
- Category: WHERE 品类分层='中分类' AND 品类名称='蔬菜类'
- Percentages are STRINGS '19.77%' — need CAST/REPLACE for computation
- Date: FROM_UNIXTIME(日期/1000, 'yyyy-MM-dd') >= '2025-09-15'
- Multiple stores exist — filter with 门店汇总='xxx店'

SECONDARY TABLE: `default_catalog.ads_business_analysis.store_transaction_details`
- order_id, pay_at, sales_amt, channel, thirdparty_user_identity, customer_phone, article_name, category_level1/2/3_description
- For user/member/repurchase analysis only

Below are excerpts from the company's business analysis knowledge base. Study the metrics, categories, and analysis patterns used:

{docs_context}

Generate {QUESTIONS_PER_DAY} NEW data retrieval questions. Rules:
1. Questions MUST be simple data retrieval (NOT analysis)
2. Default to operation_center_wide_daily for store/sales/profit/loss/discount/category questions
3. Use store_transaction_details ONLY for user/member/order-level questions
4. Vary the domains: mix of 商品(product), 运营(operations), 物流(supply chain), 用户(user/member)
5. Vary time ranges: some week, some month, some multi-month
6. Questions should be answerable with a single SQL query

Output valid JSON array (no markdown fences):
[
  {{
    "question": "华南区2026年3月的店日均门店毛利额是多少？",
    "tables_hint": "operation_center_wide_daily",
    "fields_hint": "门店毛利额, 品类分层='门店'",
    "expected_output_type": "monthly daily average"
  }},
  ...
]"""

    try:
        raw = _call_llm(prompt)
        # Parse JSON from LLM response
        questions = _parse_json_response(raw)
        if not questions or len(questions) < 3:
            raise ValueError("Too few questions generated")
    except Exception as e:
        print(f"[WARN] LLM question generation failed: {e}, using fallback")
        questions = _generate_fallback_questions(today)

    return questions[:QUESTIONS_PER_DAY]


def _get_expert_for_domain(domain: str) -> dict:
    """Map domain to expert."""
    from agent.config import EXPERT_ROUTING
    return EXPERT_ROUTING.get(domain, EXPERT_ROUTING["运营"])


def _generate_fallback_questions(today: str) -> list[dict]:
    """Generate fallback questions when LLM is unavailable."""
    templates = [
        {
            "question": "2026年3月每天店日均销售额是多少？",
            "tables_hint": "operation_center_wide_daily",
            "fields_hint": "销售额, 品类分层='门店', 门店汇总维度='门店'",
            "expected_output_type": "daily table",
        },
        {
            "question": "2026年4月各一级品类的销售额占比和毛利率？",
            "tables_hint": "operation_center_wide_daily",
            "fields_hint": "品类分层='大分类', 品类名称, 销售额, 全链路毛利率",
            "expected_output_type": "category breakdown",
        },
        {
            "question": "2026年1-3月每月会员人均购买频次？",
            "tables_hint": "store_transaction_details",
            "fields_hint": "thirdparty_user_identity, order_id, COUNT DISTINCT",
            "expected_output_type": "monthly time series",
        },
        {
            "question": "最近3个月门店促销折扣率变化趋势（按周）？",
            "tables_hint": "operation_center_wide_daily",
            "fields_hint": "促销折扣率, 品类分层='门店', 门店汇总维度='门店'",
            "expected_output_type": "weekly trend",
        },
        {
            "question": "2026年4月门店损耗率最高的5个三级品类？",
            "tables_hint": "operation_center_wide_daily",
            "fields_hint": "品类分层='小分类', 品类名称, 门店损耗率",
            "expected_output_type": "top 5 list",
        },
        {
            "question": "2026年春节（2月）和3月的店日均客单价对比？",
            "tables_hint": "operation_center_wide_daily",
            "fields_hint": "客单价, 品类分层='门店', 门店汇总维度='门店'",
            "expected_output_type": "comparison",
        },
        {
            "question": "2026年4月每天19点前销售额渗透率？",
            "tables_hint": "operation_center_wide_daily",
            "fields_hint": "19点前销售额, 销售额, 品类分层='门店'",
            "expected_output_type": "daily trend",
        },
        {
            "question": "最近4周蔬菜类和水果类的每周店日均销售额对比？",
            "tables_hint": "operation_center_wide_daily",
            "fields_hint": "品类分层='中分类', 品类名称, 销售额",
            "expected_output_type": "weekly category comparison",
        },
        {
            "question": "2026年Q1每月供应链预期毛利率和门店定价毛利率的变化？",
            "tables_hint": "operation_center_wide_daily",
            "fields_hint": "供应链预期毛利率, 门店定价毛利率, 品类分层='门店'",
            "expected_output_type": "monthly trend",
        },
        {
            "question": "2026年4月线上和线下渠道的订单数占比和客单价对比？",
            "tables_hint": "store_transaction_details",
            "fields_hint": "channel, order_id, sales_amt",
            "expected_output_type": "channel breakdown",
        },
    ]
    for i, q in enumerate(templates):
        q["id"] = f"{today}_{i+1:02d}"
    return templates


def _parse_json_response(raw: str) -> list:
    """Extract JSON array from LLM response, handling markdown fences."""
    # Remove markdown fences
    raw = raw.strip()
    if raw.startswith("```"):
        # Find first newline after opening fence
        nl = raw.find("\n")
        if nl != -1:
            raw = raw[nl + 1:]
        if raw.endswith("```"):
            raw = raw[:-3]
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Try to find JSON array in the text
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return []
