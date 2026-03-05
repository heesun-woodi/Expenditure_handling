import logging

from flask import Flask, request
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler

from config import SLACK_BOT_TOKEN, SLACK_SIGNING_SECRET, PORT, LOG_LEVEL
from handlers.deposit_notifier import start_deposit_polling
from handlers.slack_handler import register_handlers
from utils.logger import setup_logger


def create_app() -> App:
    """Slack Bolt 앱 생성 및 핸들러 등록"""
    app = App(token=SLACK_BOT_TOKEN, signing_secret=SLACK_SIGNING_SECRET)
    register_handlers(app)
    return app


def main():
    setup_logger(LOG_LEVEL)
    logger = logging.getLogger(__name__)
    logger.info("Expense Agent 시작 중...")

    bolt_app = create_app()
    start_deposit_polling(bolt_app.client)

    flask_app = Flask(__name__)
    handler = SlackRequestHandler(bolt_app)

    @flask_app.route("/slack/events", methods=["POST"])
    def slack_events():
        return handler.handle(request)

    logger.info(f"HTTP 모드로 시작 (port={PORT})...")
    flask_app.run(host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
