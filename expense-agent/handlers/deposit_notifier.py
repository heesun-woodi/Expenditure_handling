from __future__ import annotations

import logging
import threading
import time
from datetime import datetime

from slack_sdk import WebClient

from config import PROJECT_COST_SPREADSHEET_ID

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 300  # 5분


def _get_sheets_service():
    from handlers.sheets_handler import get_google_services
    sheets_svc, _ = get_google_services()
    return sheets_svc


def _format_deposit_date(raw: str) -> str:
    """입금일자 텍스트를 'MM월DD일' 형식으로 변환 (파싱 실패 시 원본 반환)"""
    raw = raw.strip()
    for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d", "%m/%d/%Y", "%m-%d"):
        try:
            dt = datetime.strptime(raw, fmt)
            return f"{dt.month}월{dt.day}일"
        except ValueError:
            continue
    return raw


def check_and_notify_deposits(client: WebClient) -> None:
    """PROJECT_COST 시트에서 입금일자(K) 기입 + 알림 미발송(O) 행을 찾아 Slack 알림 전송"""
    try:
        sheets_svc = _get_sheets_service()

        result = sheets_svc.spreadsheets().values().get(
            spreadsheetId=PROJECT_COST_SPREADSHEET_ID,
            range="A2:O",
        ).execute()
        rows = result.get("values", [])

        for row_index, row in enumerate(rows):
            # K열(index 10): 입금일자, L열(11): channel_id, M열(12): thread_ts,
            # N열(13): user_id, O열(14): 알림발송
            if len(row) < 14:
                continue

            deposit_date = row[10].strip() if len(row) > 10 else ""
            channel_id = row[11].strip() if len(row) > 11 else ""
            thread_ts = row[12].strip() if len(row) > 12 else ""
            user_id = row[13].strip() if len(row) > 13 else ""
            notified = row[14].strip() if len(row) > 14 else ""

            # 조건: 입금일자 있음 + Slack 컨텍스트 있음 + 알림 미발송
            if not deposit_date or not channel_id or not thread_ts or not user_id:
                continue
            if notified:
                continue

            # 알림 발송
            formatted_date = _format_deposit_date(deposit_date)
            message = f"<@{user_id}> {formatted_date}에 입금이 완료되었습니다."

            try:
                client.chat_postMessage(
                    channel=channel_id,
                    thread_ts=thread_ts,
                    text=message,
                )
                logger.info(f"입금 완료 알림 발송: {user_id} / {formatted_date}")
            except Exception as e:
                logger.error(f"입금 완료 알림 발송 실패: {e}")
                continue

            # O열에 발송 타임스탬프 기록 (2행부터 시작이므로 row_index+2)
            sheet_row = row_index + 2
            try:
                sheets_svc.spreadsheets().values().update(
                    spreadsheetId=PROJECT_COST_SPREADSHEET_ID,
                    range=f"O{sheet_row}",
                    valueInputOption="RAW",
                    body={"values": [[datetime.now().isoformat()]]},
                ).execute()
            except Exception as e:
                logger.error(f"알림 발송 기록 실패 (행 {sheet_row}): {e}")

    except Exception as e:
        logger.error(f"입금 완료 알림 확인 실패: {e}")


def start_deposit_polling(client: WebClient) -> None:
    """백그라운드 스레드로 주기적으로 입금 완료 알림 확인"""

    def _poll():
        logger.info(f"입금 완료 알림 폴링 시작 (간격: {POLL_INTERVAL_SECONDS}초)")
        while True:
            time.sleep(POLL_INTERVAL_SECONDS)
            check_and_notify_deposits(client)

    thread = threading.Thread(target=_poll, daemon=True)
    thread.start()
