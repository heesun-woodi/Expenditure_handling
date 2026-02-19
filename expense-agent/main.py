import logging

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from config import SLACK_BOT_TOKEN, SLACK_APP_TOKEN, LOG_LEVEL
from handlers.deposit_notifier import start_deposit_polling
from handlers.slack_handler import register_handlers
from utils.logger import setup_logger


def create_app() -> App:
    """Slack Bolt 앱 생성 및 핸들러 등록"""
    app = App(token=SLACK_BOT_TOKEN)
    register_handlers(app)
    return app


def main():
    setup_logger(LOG_LEVEL)
    logger = logging.getLogger(__name__)
    logger.info("Expense Agent 시작 중...")

    app = create_app()
    start_deposit_polling(app.client)
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)

    logger.info("Socket Mode 연결 시작...")
    handler.start()


if __name__ == "__main__":
    main()
