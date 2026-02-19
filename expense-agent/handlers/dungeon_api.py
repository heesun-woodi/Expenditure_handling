from __future__ import annotations

import logging
import time

import requests

from config import DUNGEON_API_BASE_URL, DUNGEON_API_EMAIL, DUNGEON_API_PASSWORD

logger = logging.getLogger(__name__)

# 토큰 캐시 (모듈 레벨)
_token_cache = {
    "access_token": "",
    "expires_at": 0.0,
}


def _login() -> str:
    """던전검색 API 로그인 → accessToken 반환"""
    url = f"{DUNGEON_API_BASE_URL}/auth/login"
    resp = requests.post(
        url,
        json={"email": DUNGEON_API_EMAIL, "password": DUNGEON_API_PASSWORD},
        headers={"Content-Type": "application/json"},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()

    if data.get("resultType") != "SUCCESS":
        raise RuntimeError(f"던전 API 로그인 실패: {data}")

    token = data["result"]["accessToken"]
    # JWT 만료 1시간 기준, 여유 5분 전에 갱신
    _token_cache["access_token"] = token
    _token_cache["expires_at"] = time.time() + 3500
    logger.info("던전 API 로그인 성공")
    return token


def _get_token() -> str:
    """캐시된 토큰 반환, 만료 시 재로그인"""
    if _token_cache["access_token"] and time.time() < _token_cache["expires_at"]:
        return _token_cache["access_token"]
    return _login()


def get_project_name(channel_id: str) -> str:
    """Slack 채널 ID로 프로젝트명(던전명) 조회"""
    try:
        token = _get_token()
    except Exception as e:
        logger.error(f"던전 API 로그인 실패: {e}")
        return "프로젝트"

    url = f"{DUNGEON_API_BASE_URL}/dungeons"
    params = {
        "slackChannelId": channel_id,
        "searchOnly": "false",
        "criteria": "0.6",
        "exactSearch": "false",
    }

    try:
        resp = requests.get(
            url,
            params=params,
            headers={
                "Authorization": f"Bearer {token}",
                "accept": "application/json",
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("resultType") == "SUCCESS":
            results = data.get("result", [])
            if results:
                name = results[0].get("name", "")
                if name:
                    logger.info(f"프로젝트명 조회 성공: {channel_id} → {name}")
                    return name

        logger.warning(f"프로젝트명 조회 결과 없음: {channel_id}")
        return "프로젝트"

    except Exception as e:
        logger.error(f"프로젝트명 조회 실패: {e}")
        return "프로젝트"
