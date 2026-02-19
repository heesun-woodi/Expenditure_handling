from __future__ import annotations

from pathlib import Path

from config import EXPENSE_CATEGORIES
from handlers.feedback import get_correction_examples

SKILL_FILE = Path(__file__).parent.parent / "skills" / "receipt_analysis.md"


def get_system_prompt() -> str:
    """스킬 파일을 읽고 동적 값(카테고리, 교정 사례)을 주입하여 시스템 프롬프트 반환"""
    prompt = SKILL_FILE.read_text(encoding="utf-8")
    prompt = prompt.replace("{categories}", ", ".join(EXPENSE_CATEGORIES))

    corrections = get_correction_examples()
    if corrections:
        prompt += corrections

    return prompt
