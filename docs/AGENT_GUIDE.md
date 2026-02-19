# 지출품의서 자동화 Agent 가이드

Slack에서 영수증 사진을 올리면 AI가 분석하여 Google Sheets 지출품의서를 자동 생성하는 에이전트입니다.

---

## 목차

1. [사용자 가이드 (How to Use)](#1-사용자-가이드)
2. [시스템 아키텍처](#2-시스템-아키텍처)
3. [프로젝트 구조](#3-프로젝트-구조)
4. [환경 설정 및 설치](#4-환경-설정-및-설치)
5. [핵심 모듈 상세 설명](#5-핵심-모듈-상세-설명)
6. [데이터 흐름](#6-데이터-흐름)
7. [테스트](#7-테스트)
8. [배포](#8-배포)
9. [트러블슈팅](#9-트러블슈팅)
10. [설정 커스터마이징](#10-설정-커스터마이징)

---

## 1. 사용자 가이드

### 1.1 기본 사용법

Slack 채널에서 봇을 멘션하며 영수증 사진을 첨부합니다.

```
@ExpenseBot (영수증 이미지 첨부)
```

### 1.2 전체 워크플로우

```
[Step 1] 사용자: Slack 채널에서 @Agent 멘션 + 영수증 이미지 업로드
    ↓
[Step 2] Agent: "지출품의서를 작성 중입니다..." 즉시 응답
    ↓
[Step 3] Agent: 백그라운드에서 처리
    - 이미지 다운로드 및 전처리
    - Claude Vision AI로 영수증 분석
    - Google Sheets 템플릿 복사 + 데이터 입력
    - 영수증 이미지 첨부
    ↓
[Step 4] Agent: 스레드에 검토 요청 메시지 + Google Sheets 링크 전송
    ↓
[Step 5] 사용자: 시트 내용 확인 후 스레드에 "완료" 입력
    ↓
[Step 6] Agent: 지출품의서 처리 채널에 최종 제출 메시지 발송
    - 수신: @Eunmi Wi (재무담당)
    - 참조: @Paul (CEO) / @Sungyoung Jung (CFO)
```

### 1.3 지원 이미지 형식

- JPG / JPEG
- PNG
- HEIC / HEIF (iPhone 사진)
- GIF, WebP

### 1.4 한 번에 처리 가능한 영수증

- 최대 **15장**까지 동시 업로드 가능
- 여러 장을 첨부하면 각각 분석하여 하나의 지출품의서에 합산

### 1.5 생성되는 Google Sheets

- 파일명: `{프로젝트명}_{월}월_개인카드 지출품의서_{사용자명}`
- 시트 구성:
  - **지출결의서_템플릿**: 프로젝트명, 작성일자, 금액, 적요 등 입력
  - **영수증 첨부**: 영수증 원본 이미지 삽입

### 1.6 자동 입력 항목

| 항목 | 내용 | 예시 |
|------|------|------|
| 작성일자 | 지출품의서 생성일 (YY.MM.DD) | `26.02.10` |
| 프로젝트명 | Slack 채널에 매핑된 프로젝트명 | `푸드케어 CRO PJ` |
| 사용자 | Slack Display Name | `우디` |
| 지출금액 | 모든 영수증 합산 금액 | `22,400` |
| 사용목적 | 자동 생성 | `푸드케어 CRO PJ 2월 개인카드 지출` |
| 적요 | `{지출내용} ({YY.MM.DD} / {사용자})` | `커피/음료 (26.02.10 / 우디)` |
| 공급가액 | `round(합계 / 1.1)` | `8,000` |
| 세액 | `합계 - 공급가액` | `800` |
| 소계 | 영수증 합계 금액 | `8,800` |

---

## 2. 시스템 아키텍처

```
┌─────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   Slack      │────▶│  slack_handler   │────▶│   ai_handler     │
│  (Socket     │     │  (오케스트레이션)  │     │  (Claude Vision) │
│   Mode)      │◀────│                  │◀────│                  │
└─────────────┘     └──────────────────┘     └──────────────────┘
                            │    ▲
                            ▼    │
                    ┌──────────────────┐
                    │  sheets_handler  │
                    │  (Google Sheets  │
                    │   + Drive API)   │
                    └──────────────────┘
```

### 기술 스택

| 구성요소 | 기술 |
|---------|------|
| 런타임 | Python 3.9+ |
| Slack 연동 | Slack Bolt SDK (Socket Mode) |
| AI 분석 | Claude Sonnet 4.5 (Vision API) |
| 시트 생성 | Google Sheets API v4 |
| 파일 관리 | Google Drive API v3 |
| 이미지 처리 | Pillow + pillow-heif |
| 인증 | Google OAuth2 (사용자 계정 토큰) |

---

## 3. 프로젝트 구조

```
expense-agent/
├── main.py                      # 앱 진입점 (Slack Bolt + Socket Mode 시작)
├── config.py                    # 환경변수 로드 및 상수 정의
├── models.py                    # 데이터 모델 (dataclass)
├── auth_setup.py                # Google OAuth2 최초 인증 스크립트
├── .env                         # 환경변수 (비공개)
├── .env.example                 # 환경변수 템플릿
├── requirements.txt             # Python 패키지 의존성
├── Dockerfile                   # Docker 배포용
│
├── handlers/
│   ├── __init__.py
│   ├── slack_handler.py         # Slack 이벤트 처리 + 전체 파이프라인 오케스트레이션
│   ├── ai_handler.py            # Claude Vision API 호출 (영수증 분석)
│   └── sheets_handler.py        # Google Sheets/Drive 조작
│
├── prompts/
│   ├── __init__.py
│   └── receipt_analysis.py      # AI 시스템 프롬프트 정의
│
├── utils/
│   ├── __init__.py
│   ├── image_processor.py       # 이미지 전처리 (HEIC 변환, 리사이즈, base64)
│   ├── validators.py            # 데이터 유효성 검증
│   └── logger.py                # 로깅 설정 (콘솔 + 파일 + 에러 전용)
│
├── tests/
│   ├── __init__.py
│   ├── test_image_processor.py  # 이미지 처리 테스트
│   ├── test_tax_calculation.py  # 세액 계산 테스트
│   └── test_validators.py       # 데이터 검증 테스트
│
├── credentials/                 # Google 인증 파일 (비공개)
│   ├── oauth_client.json        # OAuth 클라이언트 설정
│   └── token.json               # 발급된 액세스/리프레시 토큰
│
└── logs/                        # 로그 파일
    ├── expense_agent.log        # 전체 로그 (10MB 로테이션)
    └── errors.log               # 에러 전용 로그
```

---

## 4. 환경 설정 및 설치

### 4.1 사전 요구사항

- Python 3.9 이상
- Slack Workspace 관리자 권한 (앱 설치)
- Google Cloud 프로젝트 (Sheets API, Drive API 활성화)
- Anthropic API 키

### 4.2 설치

```bash
cd expense-agent

# 가상 환경 생성 및 활성화
python3 -m venv venv
source venv/bin/activate

# 패키지 설치
pip install -r requirements.txt
```

### 4.3 Slack App 설정

1. [Slack API](https://api.slack.com/apps)에서 새 앱 생성
2. **OAuth & Permissions** - Bot Token Scopes 추가:
   - `app_mentions:read` - 봇 멘션 감지
   - `chat:write` - 메시지 발송
   - `files:read` - 파일 다운로드
   - `users:read` - 사용자 정보 조회
   - `channels:history` - 채널 메시지 읽기
3. **Event Subscriptions** 활성화:
   - `app_mention` - 봇 멘션 이벤트
   - `message.channels` - 스레드 "완료" 응답 감지
4. **Socket Mode** 활성화
5. 토큰 복사:
   - Bot User OAuth Token → `SLACK_BOT_TOKEN`
   - App-Level Token (connections:write scope) → `SLACK_APP_TOKEN`

### 4.4 Google Cloud 설정

1. [Google Cloud Console](https://console.cloud.google.com/)에서 프로젝트 생성
2. **API 활성화**:
   - Google Sheets API
   - Google Drive API
3. **OAuth2 클라이언트 생성**:
   - API & Services → Credentials → Create OAuth Client ID
   - Application type: Desktop app
   - JSON 다운로드 → `credentials/oauth_client.json`으로 저장
4. **최초 인증 실행**:
   ```bash
   python auth_setup.py
   ```
   - 브라우저가 열리면 Google 계정으로 로그인
   - 성공 시 `credentials/token.json` 자동 생성
   - 이후 토큰은 자동 갱신됨

### 4.5 환경변수 설정

```bash
cp .env.example .env
```

`.env` 파일을 편집하여 실제 값 입력:

```bash
# --- Slack ---
SLACK_BOT_TOKEN=xoxb-xxxx-xxxx-xxxx      # Bot User OAuth Token
SLACK_APP_TOKEN=xapp-xxxx-xxxx            # Socket Mode App Token

# --- Claude API ---
ANTHROPIC_API_KEY=sk-ant-xxxx             # Anthropic API Key
CLAUDE_MODEL=claude-sonnet-4-5-20250929   # 사용할 모델 (기본값)

# --- Google ---
TEMPLATE_SPREADSHEET_ID=1yjnhrlD8T...    # 마스터 템플릿 시트 ID
PARENT_FOLDER_ID=                         # 생성된 시트가 저장될 Drive 폴더 ID (선택)

# --- Slack 사용자 ID ---
FINANCE_MANAGER_USER_ID=U0XXXXX           # @Eunmi Wi
CEO_USER_ID=U0XXXXX                       # @Paul
CFO_USER_ID=U0XXXXX                       # @Sungyoung Jung

# --- 지출품의서 제출 채널 ---
EXPENSE_SUBMIT_CHANNEL_ID=C0XXXXX         # 최종 제출 메시지가 발송될 채널

# --- 채널-프로젝트 매핑 (JSON) ---
CHANNEL_PROJECT_MAP={"C01234ABC":"푸드케어 CRO PJ"}

# --- 선택 ---
LOG_LEVEL=INFO
TEMP_DIR=/tmp/expense-agent
```

### 4.6 실행

```bash
python main.py
```

정상 실행 시 로그:
```
Expense Agent 시작 중...
Socket Mode 연결 시작...
```

---

## 5. 핵심 모듈 상세 설명

### 5.1 `main.py` - 앱 진입점

Slack Bolt 앱을 생성하고 Socket Mode로 연결합니다.

```python
app = App(token=SLACK_BOT_TOKEN)        # Slack Bolt 앱 생성
register_handlers(app)                   # 이벤트 핸들러 등록
SocketModeHandler(app, SLACK_APP_TOKEN)  # Socket Mode 시작
```

### 5.2 `models.py` - 데이터 모델

4개의 dataclass로 데이터를 구조화합니다:

| 모델 | 용도 |
|------|------|
| `ReceiptItem` | 영수증 개별 품목 (이름, 수량, 단가, 금액) |
| `ReceiptData` | AI가 분석한 영수증 전체 데이터 |
| `ExpenseLineItem` | 지출결의서 1행 (적요, 수량, 공급가액, 세액, 소계) |
| `ExpenseReport` | 지출결의서 전체 (프로젝트명, 사용자, 내역 리스트 등) |
| `ProcessingContext` | 처리 중인 요청의 컨텍스트 (채널, 사용자, 스레드 정보) |

### 5.3 `handlers/slack_handler.py` - Slack 이벤트 처리

전체 파이프라인을 오케스트레이션하는 핵심 모듈입니다.

**등록되는 이벤트 핸들러:**

| 이벤트 | 함수 | 설명 |
|--------|------|------|
| `app_mention` | `_on_app_mention()` | 봇 멘션 시 영수증 처리 시작 |
| `message` | `_on_thread_message()` | 스레드에서 "완료" 감지 |

**처리 파이프라인 (`_process_receipts_background`):**

```
Phase 1: 이미지 수집 및 전처리
  - Slack에서 이미지 다운로드 (_download_slack_file)
  - HEIC 변환 + 리사이즈 + base64 인코딩 (process_image)
      ↓
Phase 2: AI 분석
  - Claude Vision API로 영수증 병렬 분석 (analyze_receipts_batch)
  - 결과 유효성 검증 (validate_receipt_data)
      ↓
Phase 3: ExpenseReport 생성
  - 세액 계산 (calculate_tax)
  - 적요 문자열 생성
  - 대상 월 추출
      ↓
Phase 4: Google Sheets 생성
  - 템플릿 복사 (copy_template)
  - 셀 위치 동적 탐색 (discover_cell_mapping)
  - 데이터 입력 (fill_expense_data)
  - 영수증 이미지 첨부 (attach_receipt_images)
      ↓
Phase 5: 검토 요청 메시지 전송
```

- 처리는 **별도 스레드**(`threading.Thread`)에서 실행되어 Slack 응답이 블로킹되지 않음
- `_active_threads` 딕셔너리로 진행 중인 요청을 추적 (thread_ts 기반)

### 5.4 `handlers/ai_handler.py` - Claude Vision AI

영수증 이미지를 Claude API로 분석합니다.

- **단일 분석**: `analyze_receipt(image_base64, media_type)` → JSON dict 반환
- **병렬 분석**: `analyze_receipts_batch(images)` → `ThreadPoolExecutor`로 최대 5개 동시 처리
- **응답 파싱**: `_parse_ai_response()` → JSON 블록 추출 및 파싱

AI 분석 결과 JSON 필드:

```json
{
  "merchant_name": "스타벅스 강남점",
  "transaction_date": "2026-02-10",
  "total_amount": 8800,
  "items": [{"name": "아메리카노", "quantity": 2, "price": 4400, "amount": 8800}],
  "payment_method": "카드",
  "expense_category": "식비(점심)/간식비",
  "summary_inference": "커피/음료"
}
```

### 5.5 `handlers/sheets_handler.py` - Google Sheets 처리

**핵심 함수:**

| 함수 | 설명 |
|------|------|
| `get_google_services()` | OAuth2 토큰으로 Sheets/Drive 서비스 객체 생성 |
| `copy_template()` | 마스터 템플릿을 Drive에 복사 |
| `discover_cell_mapping()` | 시트 내 키워드를 검색해 입력 셀 위치를 동적 탐색 |
| `fill_expense_data()` | 헤더 + 상세 내역 + 하단 정보 일괄 입력 (batchUpdate) |
| `attach_receipt_images()` | Drive에 이미지 업로드 후 `=IMAGE()` 함수로 삽입 |
| `share_spreadsheet()` | 이메일 기반 편집 권한 부여 |
| `calculate_tax()` | 부가세 포함 금액 → 공급가액/세액 분리 |

**동적 셀 매핑 (`discover_cell_mapping`):**

시트를 A1:Z50 범위로 읽어 키워드를 검색합니다:

| 검색 키워드 | 매핑되는 필드 |
|------------|-------------|
| "프로젝트" + "명" | `project_name_cell` |
| "작성일자" | `created_date_cell` |
| "사용자" | `user_name_cell` |
| "지출금액" | `total_amount_cell` |
| "사용목적" | `purpose_cell` |
| "적요" | `data_start_row`, `description_col` |
| "수량", "공급가액", "세액", "소계" | 각 데이터 컬럼 위치 |

동적 탐색 실패 시 `DEFAULT_CELL_MAPPING`(하드코딩 값)으로 폴백합니다.

### 5.6 `prompts/receipt_analysis.py` - AI 프롬프트

영수증 분석용 시스템 프롬프트를 정의합니다. 주요 규칙:

- **날짜**: 불명확하면 `null` (추측 금지), 형식 `YYYY-MM-DD`
- **금액**: 정수만, 합계/총액 우선
- **품목**: 5개 이상이면 대표 3개 + "외 N건"
- **부가세**: total_amount에 포함된 것으로 간주
- **카테고리**: 교통비, 접대비, 회식비, 식비, 솔루션비, 물품구매비, 기타
- **출력**: 순수 JSON만 반환 (마크다운 블록 없이)

### 5.7 `utils/image_processor.py` - 이미지 처리

| 함수 | 설명 |
|------|------|
| `process_image()` | 전체 파이프라인: HEIC 변환 → 리사이즈 → base64 |
| `convert_heic_to_jpg()` | `pillow-heif`로 HEIC/HEIF → JPG 변환 |
| `resize_image()` | 최대 1024px 이내로 리사이즈 (비율 유지) |
| `encode_image_base64()` | 파일 → base64 문자열 + media_type |
| `cleanup_temp_files()` | 처리 완료 후 임시 파일 삭제 |

### 5.8 `utils/validators.py` - 데이터 검증

| 함수 | 검증 내용 |
|------|----------|
| `validate_receipt_data()` | 금액 필수/양수, 상호명 기본값, 날짜 형식 |
| `validate_date()` | 날짜 형식, 미래 날짜 거부, 6개월 이전 경고 |
| `validate_expense_report()` | 합계 정합성, 공급가액+세액=소계 검증 |

### 5.9 `utils/logger.py` - 로깅

3개 핸들러로 로그를 분리합니다:

| 핸들러 | 출력 | 크기 제한 |
|--------|------|----------|
| Console | 터미널 출력 | - |
| File (`expense_agent.log`) | 전체 로그 | 10MB x 5 백업 |
| Error (`errors.log`) | ERROR 이상만 | 5MB x 3 백업 |

---

## 6. 데이터 흐름

### 6.1 금액 계산

한국 부가가치세(10%) 기준:

```
총액 (영수증 합계) = 8,800원
공급가액 = round(8,800 / 1.1) = 8,000원
세액 = 8,800 - 8,000 = 800원
```

항상 `공급가액 + 세액 = 총액`이 성립합니다.

### 6.2 적요 생성 형식

```
{summary_inference} ({YY.MM.DD} / {사용자명})
```

예시: `커피/음료 (26.02.10 / 우디)`

- `summary_inference`: AI가 추론한 지출 요약 (없으면 상호명 사용)
- 날짜: 영수증 거래일자 (없으면 "날짜불명")

### 6.3 최종 제출 메시지

사용자가 "완료"라고 답하면, 설정된 지출처리 채널(`EXPENSE_SUBMIT_CHANNEL_ID`)에 발송:

```
@Eunmi Wi 은미님!

푸드케어 CRO PJ 26년 2월 개인카드사용 지출결의서 전달드립니다.

cc @Paul / @Sungyoung Jung

📄 https://docs.google.com/spreadsheets/d/xxxxx
```

---

## 7. 테스트

### 7.1 테스트 실행

```bash
cd expense-agent
pytest tests/ -v
```

### 7.2 테스트 커버리지

| 테스트 파일 | 대상 | 검증 내용 |
|------------|------|----------|
| `test_tax_calculation.py` | `calculate_tax()` | 공급가액+세액=총액 (100~100,000원 범위) |
| `test_validators.py` | `validate_receipt_data()` | 필수 필드, 금액 범위, 날짜 형식 |
| `test_image_processor.py` | `encode_image_base64()` | base64 인코딩, media_type 판별 |

---

## 8. 배포

### 8.1 Docker 배포

```bash
cd expense-agent

# 이미지 빌드
docker build -t expense-agent .

# 실행 (.env 파일과 credentials 마운트)
docker run -d \
  --name expense-bot \
  --env-file .env \
  -v $(pwd)/credentials:/app/credentials:ro \
  expense-agent
```

Dockerfile 특이사항:
- `python:3.11-slim` 기반
- `libheif-dev` 포함 (HEIC 이미지 지원)
- 비루트 사용자(`appuser`)로 실행

### 8.2 systemd 서비스 (Linux)

```ini
# /etc/systemd/system/expense-agent.service
[Unit]
Description=Expense Report Agent
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/expense-agent
EnvironmentFile=/home/ubuntu/expense-agent/.env
ExecStart=/home/ubuntu/expense-agent/venv/bin/python main.py
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable expense-agent
sudo systemctl start expense-agent
```

### 8.3 로그 확인

```bash
# 실시간 전체 로그
tail -f logs/expense_agent.log

# 에러만 확인
tail -f logs/errors.log
```

---

## 9. 트러블슈팅

### Slack 이벤트를 받지 못할 때

- **Socket Mode 확인**: Slack App 설정에서 Socket Mode가 활성화되어 있는지 확인
- **토큰 확인**: `SLACK_BOT_TOKEN`과 `SLACK_APP_TOKEN`이 올바른지 확인
- **이벤트 구독 확인**: `app_mention`과 `message.channels` 이벤트가 등록되어 있는지 확인
- **채널 초대**: 봇이 해당 채널에 초대되어 있는지 확인

### Google Sheets 권한 오류

- OAuth 토큰 만료: `python auth_setup.py`로 재인증
- `token.json`에 refresh_token이 있으면 자동 갱신됨
- 템플릿 시트에 대한 접근 권한이 있는지 확인

### Claude API 오류

- API 키 유효성 확인
- 크레딧 잔액 확인
- 이미지 크기가 너무 크면 자동 리사이즈 (1024px 제한)

### 영수증 인식이 부정확할 때

- 고화질 이미지 사용 권장
- 영수증 전체가 프레임에 들어오게 촬영
- 조명이 균일한 환경에서 촬영
- `prompts/receipt_analysis.py`에서 프롬프트 개선 가능

### "완료" 응답이 감지되지 않을 때

- 반드시 **스레드 답글**로 입력 (채널 메시지 아님)
- 원래 요청한 사용자만 "완료" 입력 가능
- 메시지에 "완료"라는 텍스트가 포함되어야 함

---

## 10. 설정 커스터마이징

### 10.1 채널-프로젝트 매핑 추가

`.env`에서 JSON 형식으로 관리:

```bash
CHANNEL_PROJECT_MAP={"C01234ABC":"푸드케어 CRO PJ","CNEWCHANNEL":"새 프로젝트명"}
```

매핑이 없는 채널은 Slack 채널명을 프로젝트명으로 사용합니다.

### 10.2 AI 모델 변경

```bash
CLAUDE_MODEL=claude-sonnet-4-5-20250929   # 기본값 (정확도/비용 균형)
```

### 10.3 이미지 처리 설정

`config.py`에서 조정:

```python
MAX_RECEIPT_COUNT = 15        # 1회 최대 영수증 수
MAX_IMAGE_DIMENSION = 1024    # 리사이즈 최대 픽셀
HIGH_AMOUNT_THRESHOLD = 10_000_000  # 고액 경고 기준 (원)
```

### 10.4 알림 수신자 변경

`.env`에서 Slack User ID 수정:

```bash
FINANCE_MANAGER_USER_ID=U0XXXXX   # 재무 담당자
CEO_USER_ID=U0XXXXX               # CEO
CFO_USER_ID=U0XXXXX               # CFO
```

### 10.5 Google Sheets 템플릿 변경

1. 새 템플릿 시트를 Google Drive에 준비
2. 시트 ID를 `.env`의 `TEMPLATE_SPREADSHEET_ID`에 설정
3. 시트에 "프로젝트명", "작성일자", "적요", "수량", "공급가액", "세액", "소계" 등의 키워드가 있으면 동적 매핑이 자동으로 동작
4. 키워드가 없거나 매핑 실패 시 `sheets_handler.py`의 `DEFAULT_CELL_MAPPING` 수정

---

## 부록: 주기적 점검 사항

| 항목 | 주기 | 확인 방법 |
|------|------|----------|
| Claude API 크레딧 | 주 1회 | [Anthropic Console](https://console.anthropic.com/) |
| Google Sheets API 할당량 | 월 1회 | [Google Cloud Console](https://console.cloud.google.com/) |
| 에러 로그 | 주 1회 | `logs/errors.log` 확인 |
| 디스크 용량 | 월 1회 | 임시 파일 정리 (`/tmp/expense-agent`) |
| OAuth 토큰 상태 | 필요 시 | `python auth_setup.py` |
