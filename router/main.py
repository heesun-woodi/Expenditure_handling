"""
Slack Router Service

Slack App의 Request URL을 단일 진입점으로 받아
callback_id / action_id prefix에 따라 각 백엔드 서비스로 포워딩한다.

라우팅 규칙:
  - url_verification  → 라우터가 직접 challenge 반환
  - block_actions     → action_id prefix 기준
      expense_*       → EXPENSE_AGENT_URL
      simpson_*, calendar_* → SIMPSON_SERVICE_URL
  - event_callback    → event.type 기준
      app_mention, reaction_added → EXPENSE_AGENT_URL
      기타             → SIMPSON_SERVICE_URL
  - view_submission/view_closed → view.callback_id prefix 기준
  - shortcut/message_action     → callback_id prefix 기준
  - 기타              → SIMPSON_SERVICE_URL (fallback)
"""
from __future__ import annotations

import json
import logging
import os
import urllib.parse

import requests
from flask import Flask, request, jsonify
from slack_sdk.signature import SignatureVerifier

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

app = Flask(__name__)

SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET", "")
EXPENSE_AGENT_URL = os.environ.get("EXPENSE_AGENT_URL", "http://localhost:3000/slack/events")
SIMPSON_SERVICE_URL = os.environ.get("SIMPSON_SERVICE_URL", "")

verifier = SignatureVerifier(SLACK_SIGNING_SECRET)

# expense agent로 보낼 event.type 목록
EXPENSE_EVENT_TYPES = {"app_mention", "reaction_added"}

# expense agent 라우팅 prefix
EXPENSE_PREFIX = "expense_"

# 기존 서비스 라우팅 prefix
SIMPSON_PREFIXES = ("simpson_", "calendar_")


def _parse_payload(raw_body: bytes, content_type: str) -> dict:
    """JSON 또는 URL-encoded form 형식의 Slack payload 파싱"""
    if "application/json" in content_type:
        return json.loads(raw_body)

    # block_actions, view_submission 등은 payload= 형식으로 전달됨
    decoded = raw_body.decode("utf-8")
    parsed = urllib.parse.parse_qs(decoded)
    payload_str = parsed.get("payload", ["{}"])[0]
    return json.loads(payload_str)


def _get_target_url(payload: dict) -> str | None:
    """payload를 분석해 포워딩 대상 URL 반환. None이면 라우터가 직접 처리."""
    payload_type = payload.get("type", "")

    if payload_type == "url_verification":
        return None

    if payload_type == "event_callback":
        event = payload.get("event", {})
        event_type = event.get("type", "")
        if event_type == "reaction_added":
            reaction = event.get("reaction", "")
            if reaction == "email":
                return SIMPSON_SERVICE_URL
            return EXPENSE_AGENT_URL
        if event_type in EXPENSE_EVENT_TYPES:
            return EXPENSE_AGENT_URL
        return SIMPSON_SERVICE_URL

    if payload_type == "block_actions":
        actions = payload.get("actions", [])
        action_id = actions[0].get("action_id", "") if actions else ""
        if action_id.startswith(EXPENSE_PREFIX):
            return EXPENSE_AGENT_URL
        if action_id.startswith(SIMPSON_PREFIXES):
            return SIMPSON_SERVICE_URL
        return SIMPSON_SERVICE_URL

    if payload_type in ("view_submission", "view_closed"):
        callback_id = payload.get("view", {}).get("callback_id", "")
        if callback_id.startswith(EXPENSE_PREFIX):
            return EXPENSE_AGENT_URL
        return SIMPSON_SERVICE_URL

    if payload_type in ("shortcut", "message_action"):
        callback_id = payload.get("callback_id", "")
        if callback_id.startswith(EXPENSE_PREFIX):
            return EXPENSE_AGENT_URL
        return SIMPSON_SERVICE_URL

    # fallback
    return SIMPSON_SERVICE_URL


@app.route("/slack/events", methods=["POST"])
def slack_events():
    raw_body = request.get_data()

    # Slack 서명 검증
    if not verifier.is_valid_request(raw_body, dict(request.headers)):
        logger.warning("Invalid Slack signature")
        return jsonify({"error": "Invalid signature"}), 403

    content_type = request.content_type or ""
    try:
        payload = _parse_payload(raw_body, content_type)
    except Exception as e:
        logger.error(f"Payload 파싱 실패: {e}")
        return jsonify({"error": "Invalid payload"}), 400

    # url_verification은 라우터가 직접 처리
    if payload.get("type") == "url_verification":
        logger.info("url_verification challenge 처리")
        return jsonify({"challenge": payload["challenge"]})

    target_url = _get_target_url(payload)
    if not target_url:
        logger.warning("포워딩 대상 URL 없음, 무시")
        return "", 200

    logger.info(f"라우팅: type={payload.get('type')} → {target_url}")

    # 원본 헤더 그대로 포워딩 (백엔드 서명 검증용)
    forward_headers = {
        k: v for k, v in request.headers
        if k not in ("Host", "Content-Length")
    }

    try:
        resp = requests.post(
            target_url,
            data=raw_body,
            headers=forward_headers,
            timeout=10,
        )
        return resp.content, resp.status_code, {"Content-Type": resp.headers.get("Content-Type", "application/json")}
    except Exception as e:
        logger.error(f"포워딩 실패 ({target_url}): {e}")
        # 포워딩 실패 시 200 반환해 Slack 재시도 방지
        return "", 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "3001"))
    logger.info(f"Slack Router 시작 (port={port})")
    logger.info(f"  EXPENSE_AGENT_URL={EXPENSE_AGENT_URL}")
    logger.info(f"  SIMPSON_SERVICE_URL={SIMPSON_SERVICE_URL}")
    app.run(host="0.0.0.0", port=port)
