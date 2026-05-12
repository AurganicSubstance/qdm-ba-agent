"""
Agent system configuration.
"""
import os
from pathlib import Path

# ── Paths ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
STATE_FILE = DATA_DIR / "agent_state.json"
EVOLUTION_LOG = DATA_DIR / "evolution_log.json"
QUESTION_HISTORY_DIR = DATA_DIR / "question_history"

# KB path (ECS: ~/BAKnowledgeBase3.1, local: adjacent project)
KB_PATH = os.getenv("KB_PATH", str(PROJECT_ROOT.parent / "BAKnowledgeBase3.1"))
KB_2026_PATH = os.path.join(KB_PATH, "2026年")
KB_2025_PATH = os.path.join(KB_PATH, "2025年")

# ── Email (Tencent Enterprise) ──
MAIL_CONFIG = {
    "imap_host": "imap.exmail.qq.com",
    "imap_port": 993,
    "smtp_host": "smtp.exmail.qq.com",
    "smtp_port": 465,
    "username": os.getenv("MAIL_USERNAME", "liangsheng1@qdama.cn"),
    "password": os.getenv("MAIL_PASSWORD", "Yn5u63VjLfSDpDQa"),
    "sender_name": "取数验证Agent",
}

# ── Experts routing (domain → expert) ──
EXPERT_ROUTING = {
    "商品": {"name": "刘阗", "email": "liutian1@qdama.cn"},
    "运营": {"name": "刘舒颖", "email": "liushuying1@qdama.cn"},
    "物流": {"name": "周晶晶", "email": "zhoujingjing@qdama.cn"},
    "用户": {"name": "刘舒颖", "email": "liushuying1@qdama.cn"},
}

# ── Daily report recipient (user himself) ──
USER_EMAIL = "liangsheng1@qdama.cn"
USER_NAME = "梁晟"

# ── Number of questions per day ──
QUESTIONS_PER_DAY = 5

# ── Max rows per query result in email ──
MAX_RESULT_ROWS = 500
