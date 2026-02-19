from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from config import PROJECT_COST_SPREADSHEET_ID
from models import ExpenseReport

logger = logging.getLogger(__name__)

CORRECTIONS_SHEET_NAME = "AI교정데이터"
MAX_CORRECTIONS = 50

# 메모리 캐시 (봇 세션 동안 유지)
_corrections_cache: Optional[list] = None


def _get_sheets_service():
    from handlers.sheets_handler import get_google_services
    sheets_svc, _ = get_google_services()
    return sheets_svc


def _ensure_sheet_exists(sheets_service) -> None:
    """AI교정데이터 탭이 없으면 생성하고 헤더 입력"""
    try:
        metadata = sheets_service.spreadsheets().get(
            spreadsheetId=PROJECT_COST_SPREADSHEET_ID,
            fields="sheets.properties.title",
        ).execute()
        titles = [s["properties"]["title"] for s in metadata.get("sheets", [])]

        if CORRECTIONS_SHEET_NAME not in titles:
            sheets_service.spreadsheets().batchUpdate(
                spreadsheetId=PROJECT_COST_SPREADSHEET_ID,
                body={"requests": [{"addSheet": {"properties": {"title": CORRECTIONS_SHEET_NAME}}}]},
            ).execute()
            sheets_service.spreadsheets().values().update(
                spreadsheetId=PROJECT_COST_SPREADSHEET_ID,
                range=f"{CORRECTIONS_SHEET_NAME}!A1:E1",
                valueInputOption="RAW",
                body={"values": [["timestamp", "원본_항목", "교정_항목", "원본_목적", "교정_목적"]]},
            ).execute()
            logger.info(f"'{CORRECTIONS_SHEET_NAME}' 탭 생성 완료")
    except Exception as e:
        logger.error(f"시트 생성 확인 실패: {e}")


def _load_corrections() -> list:
    """Google Sheets에서 교정 데이터 로드 (캐시 우선)"""
    global _corrections_cache
    if _corrections_cache is not None:
        return _corrections_cache

    try:
        sheets_svc = _get_sheets_service()
        _ensure_sheet_exists(sheets_svc)

        result = sheets_svc.spreadsheets().values().get(
            spreadsheetId=PROJECT_COST_SPREADSHEET_ID,
            range=f"{CORRECTIONS_SHEET_NAME}!A2:E",
        ).execute()
        rows = result.get("values", [])

        corrections = []
        for row in rows:
            if len(row) < 5:
                continue
            corrections.append({
                "timestamp": row[0],
                "original": {"category": row[1], "purpose": row[3]},
                "corrected": {"category": row[2], "purpose": row[4]},
            })

        _corrections_cache = corrections[-MAX_CORRECTIONS:]
        logger.info(f"교정 데이터 {len(_corrections_cache)}건 로드 완료")
    except Exception as e:
        logger.error(f"교정 데이터 로드 실패: {e}")
        _corrections_cache = []

    return _corrections_cache


def _append_correction(change: dict) -> None:
    """Google Sheets에 교정 1건 append"""
    try:
        sheets_svc = _get_sheets_service()
        orig = change.get("original", {})
        corr = change.get("corrected", {})
        row = [
            change.get("timestamp", ""),
            orig.get("category", ""),
            corr.get("category", ""),
            orig.get("purpose", ""),
            corr.get("purpose", ""),
        ]
        sheets_svc.spreadsheets().values().append(
            spreadsheetId=PROJECT_COST_SPREADSHEET_ID,
            range=f"{CORRECTIONS_SHEET_NAME}!A:E",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]},
        ).execute()
    except Exception as e:
        logger.error(f"교정 데이터 Sheets 저장 실패: {e}")


def collect_feedback(
    original_report: ExpenseReport,
    current_sheet_items: list[dict],
) -> list[dict]:
    """
    원본 ExpenseReport와 현재 시트 데이터를 비교하여 변경 사항 수집 및 저장

    Returns:
        변경 사항 리스트
    """
    global _corrections_cache
    changes = []

    for idx, item in enumerate(original_report.line_items):
        if idx >= len(current_sheet_items):
            break

        current = current_sheet_items[idx]
        original_category = item.category
        original_purpose = item.purpose.split("\n")[0]  # "(닉네임)" 제거

        current_category = current.get("category", "")
        current_purpose = current.get("purpose", "").split("\n")[0]

        if not current_category and not current_purpose:
            continue

        category_changed = current_category and current_category != original_category
        purpose_changed = current_purpose and current_purpose != original_purpose

        if category_changed or purpose_changed:
            change = {
                "timestamp": datetime.now().isoformat(),
                "item_index": idx,
                "original": {
                    "category": original_category,
                    "purpose": original_purpose,
                },
                "corrected": {
                    "category": current_category if category_changed else original_category,
                    "purpose": current_purpose if purpose_changed else original_purpose,
                },
            }
            changes.append(change)
            logger.info(
                f"교정 감지 #{idx+1}: "
                f"항목 {original_category}→{change['corrected']['category']}, "
                f"목적 {original_purpose}→{change['corrected']['purpose']}"
            )

    if changes:
        # Sheets에 저장 + 캐시 업데이트
        for change in changes:
            _append_correction(change)

        if _corrections_cache is None:
            _corrections_cache = []
        _corrections_cache.extend(changes)
        if len(_corrections_cache) > MAX_CORRECTIONS:
            _corrections_cache = _corrections_cache[-MAX_CORRECTIONS:]

        logger.info(f"교정 사례 {len(changes)}건 저장 완료")

    return changes


def get_correction_examples() -> str:
    """프롬프트에 포함할 최근 교정 사례 텍스트 반환"""
    corrections = _load_corrections()
    if not corrections:
        return ""

    recent = corrections[-10:]

    lines = []
    for c in recent:
        orig = c.get("original", {})
        corr = c.get("corrected", {})

        orig_cat = orig.get("category", "")
        corr_cat = corr.get("category", "")
        orig_pur = orig.get("purpose", "")
        corr_pur = corr.get("purpose", "")

        parts = []
        if orig_cat != corr_cat:
            parts.append(f'항목: "{orig_cat}" → "{corr_cat}"')
        if orig_pur != corr_pur:
            parts.append(f'목적: "{orig_pur}" → "{corr_pur}"')

        if parts:
            lines.append("- " + ", ".join(parts))

    if not lines:
        return ""

    return (
        "\n\n# 과거 교정 사례 (이 패턴을 참고하여 분류하십시오)\n"
        + "\n".join(lines)
    )
