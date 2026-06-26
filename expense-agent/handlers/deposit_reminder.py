from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta

from slack_sdk import WebClient

from config import (
    EXPENSE_SUBMIT_CHANNEL_ID,
    FINANCE_MANAGER_USER_ID,
    SLACK_BOT_TOKEN,
)
from handlers.sheets_handler import (
    get_google_services,
    get_pending_deposits,
    update_reminder_dates,
)

logger = logging.getLogger(__name__)

REMINDER_INTERVAL_DAYS = 7
CHECK_INTERVAL_SECONDS = 3 * 24 * 60 * 60  # 3일


def start_deposit_reminder_loop() -> None:
    """입금 리마인더 데몬 스레드 시작"""
    thread = threading.Thread(target=_reminder_loop, daemon=True)
    thread.start()
    logger.info("입금 리마인더 루프 시작됨 (간격: %d시간)", CHECK_INTERVAL_SECONDS // 3600)


def _reminder_loop() -> None:
    """주기적으로 입금 대기 건을 체크하고 리마인더 발송"""
    client = WebClient(token=SLACK_BOT_TOKEN)
    time.sleep(60)  # 앱 시작 후 60초 대기
    while True:
        try:
            check_and_send_reminders(client)
        except Exception:
            logger.exception("리마인더 체크 실패")
        time.sleep(CHECK_INTERVAL_SECONDS)


def check_and_send_reminders(client: WebClient) -> None:
    """입금 대기 건을 조회하여 7일 경과 시 리마인더 발송"""
    sheets_svc, _ = get_google_services()
    pending = get_pending_deposits(sheets_svc)

    if not pending:
        logger.debug("입금 대기 건 없음")
        return

    today = datetime.now().date()

    for item in pending:
        # 기준 날짜: 마지막 리마인더 > 확인일자
        ref_date_str = item["last_reminder_date"] or item["confirmation_date"]
        try:
            ref_date = datetime.strptime(ref_date_str, "%Y-%m-%d").date()
        except ValueError:
            logger.warning("날짜 파싱 실패: %s", ref_date_str)
            continue

        if (today - ref_date).days < REMINDER_INTERVAL_DAYS:
            continue

        # 리마인더 메시지 발송
        submit_ts = item.get("submit_message_ts")
        try:
            if submit_ts:
                # 제출 채널의 알림 스레드에 댓글
                client.chat_postMessage(
                    channel=EXPENSE_SUBMIT_CHANNEL_ID,
                    thread_ts=submit_ts,
                    text=(
                        f"<@{FINANCE_MANAGER_USER_ID}> 은미님 해당 비용 입금 되셨을까요? "
                        f"입금되셨으면 입금완료 버튼을 눌러주세요."
                    ),
                )
            else:
                # Q열 없는 과거 데이터: 원본 스레드에 fallback
                client.chat_postMessage(
                    channel=item["channel_id"],
                    thread_ts=item["thread_ts"],
                    text=(
                        f"<@{FINANCE_MANAGER_USER_ID}> 은미님 해당 비용 입금 되셨을까요? "
                        f"입금되셨으면 입금완료 버튼을 눌러주세요."
                    ),
                )
        except Exception:
            logger.exception(
                "리마인더 발송 실패: channel=%s, thread=%s",
                item["channel_id"],
                item["thread_ts"],
            )
            continue

        # P열 업데이트
        try:
            update_reminder_dates(sheets_svc, item["row_indices"])
        except Exception:
            logger.exception("리마인더 발송일 기록 실패")

        logger.info(
            "입금 리마인더 발송 완료: channel=%s, thread=%s",
            item["channel_id"],
            item["thread_ts"],
        )
