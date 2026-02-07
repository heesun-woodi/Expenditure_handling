from __future__ import annotations

import os
import json
from dotenv import load_dotenv

load_dotenv()

# --- Slack ---
SLACK_BOT_TOKEN: str = os.environ.get("SLACK_BOT_TOKEN", "")
SLACK_APP_TOKEN: str = os.environ.get("SLACK_APP_TOKEN", "")

# --- Anthropic ---
ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL: str = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5-20250929")

# --- Google ---
GOOGLE_APPLICATION_CREDENTIALS: str = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
TEMPLATE_SPREADSHEET_ID: str = os.environ.get("TEMPLATE_SPREADSHEET_ID", "")
PARENT_FOLDER_ID: str = os.environ.get("PARENT_FOLDER_ID", "")

# --- Slack User IDs ---
FINANCE_MANAGER_USER_ID: str = os.environ.get("FINANCE_MANAGER_USER_ID", "")  # @Eunmi Wi
CEO_USER_ID: str = os.environ.get("CEO_USER_ID", "")  # @Paul
CFO_USER_ID: str = os.environ.get("CFO_USER_ID", "")  # @Sungyoung Jung

# --- Channels ---
EXPENSE_SUBMIT_CHANNEL_ID: str = os.environ.get("EXPENSE_SUBMIT_CHANNEL_ID", "")

# --- Channel → Project Name Mapping ---
# JSON format: {"C01234ABC": "푸드케어 CRO PJ", "C56789DEF": "알파 프로젝트"}
CHANNEL_PROJECT_MAP: dict = json.loads(os.getenv("CHANNEL_PROJECT_MAP", "{}"))

# --- Constants ---
MAX_RECEIPT_COUNT: int = 15
SUPPORTED_IMAGE_TYPES: set = {"image/jpeg", "image/png", "image/heic", "image/heif", "image/gif", "image/webp"}
TEMP_DIR: str = os.getenv("TEMP_DIR", "/tmp/expense-agent")
MAX_IMAGE_DIMENSION: int = 1024
HIGH_AMOUNT_THRESHOLD: int = 10_000_000
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
