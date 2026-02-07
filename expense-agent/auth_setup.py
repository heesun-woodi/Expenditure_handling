"""
OAuth2 최초 인증 스크립트

1회만 실행하면 credentials/token.json이 생성되며,
이후 봇이 자동으로 토큰을 갱신하여 사용합니다.
"""
from __future__ import annotations

import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

CREDENTIALS_DIR = os.path.join(os.path.dirname(__file__), "credentials")
CLIENT_SECRET_FILE = os.path.join(CREDENTIALS_DIR, "oauth_client.json")
TOKEN_FILE = os.path.join(CREDENTIALS_DIR, "token.json")


def main():
    creds = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("토큰 갱신 중...")
            creds.refresh(Request())
        else:
            print("브라우저에서 Google 계정 로그인을 진행합니다...")
            flow = InstalledAppFlow.from_client_secrets_file(
                CLIENT_SECRET_FILE, SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
        print(f"토큰 저장 완료: {TOKEN_FILE}")

    print("인증 성공!")


if __name__ == "__main__":
    main()
