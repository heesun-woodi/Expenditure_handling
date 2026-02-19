from __future__ import annotations

import os
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
CFO_USER_ID: str = os.environ.get("CFO_USER_ID", "")  # @Sungyoung Jung

# --- Sharing: Google 계정 이메일 및 도메인 ---
PAUL_EMAIL: str = "paul@mfitlab.com"
FINANCE_MANAGER_EMAIL: str = "eunmi.wi@mfitlab.com"
COMPANY_DOMAIN: str = "mfitlab.com"

# --- Channels ---
EXPENSE_SUBMIT_CHANNEL_ID: str = os.environ.get("EXPENSE_SUBMIT_CHANNEL_ID", "")

# --- Dungeon API (프로젝트명 조회) ---
DUNGEON_API_BASE_URL: str = os.environ.get("DUNGEON_API_BASE_URL", "")
DUNGEON_API_EMAIL: str = os.environ.get("DUNGEON_API_EMAIL", "")
DUNGEON_API_PASSWORD: str = os.environ.get("DUNGEON_API_PASSWORD", "")

# --- Expense Categories ---
EXPENSE_CATEGORIES: list = [
    "회의비", "기타비용", "점심식비", "야근식비", "주말식비", "회식비", "기타식비",
    "업무교통비", "야근교통비", "국내출장비", "국외출장비", "접대비",
    "우편비", "수도비", "난방비", "전기비", "세금", "보험비", "유류비", "퀵사용료",
    "교육훈련비", "도서구입비", "정기구독료", "사무용품비", "소모품비", "IT솔루션",
    "서류발급비", "온라인 마케팅", "광고비", "판촉물제작비", "오사용",
]

# --- User List (닉네임 → 실명 조회) ---
USER_LIST_SPREADSHEET_ID: str = "1sCJsHzEBfhEdnvn-G-ehtTFJxMoEeGhLnsTsFgdJ7TI"

# --- Project Cost Sheet (프로젝트 비용 내역서) ---
PROJECT_COST_SPREADSHEET_ID: str = "1AYRT7Skv0eYm1IQqGOWBGpD89DnCoJLf1ROOFBGhTeQ"

# --- Constants ---
MAX_RECEIPT_COUNT: int = 15
SUPPORTED_IMAGE_TYPES: set = {"image/jpeg", "image/png", "image/heic", "image/heif", "image/gif", "image/webp"}
TEMP_DIR: str = os.getenv("TEMP_DIR", "/tmp/expense-agent")
MAX_IMAGE_DIMENSION: int = 1024
HIGH_AMOUNT_THRESHOLD: int = 10_000_000
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
