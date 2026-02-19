# Expense Agent

Slack에서 영수증 사진을 올리면 AI가 자동으로 지출결의서를 작성해주는 봇입니다.

## 주요 기능

- **영수증 자동 분석**: JPG, PNG, HEIC, PDF 파일을 Claude Vision AI로 분석
- **지출결의서 자동 생성**: Google Sheets 템플릿을 복사하여 분석 데이터 자동 입력
- **프로젝트명 자동 조회**: Slack 채널 기반으로 프로젝트명 자동 매핑
- **자동 공유**: 생성된 문서를 재무팀(Paul, Eunmi)에게 자동으로 공유
- **영수증 이미지 첨부**: 원본 영수증 이미지를 시트의 별도 탭에 자동 첨부
- **AI 학습 피드백**: 사용자가 수정한 내용을 학습하여 다음 분석에 반영

## 동작 흐름

```
사용자가 Slack에서 봇 멘션 + 영수증 첨부
        ↓
Phase 1: 영수증 이미지/PDF 다운로드 및 전처리
        ↓
Phase 2: Claude Vision API로 병렬 분석 (상호명, 금액, 품목, 항목분류 등)
        ↓
Phase 3: 지출결의서 데이터 생성 (합계, 부가세 계산 등)
        ↓
Phase 4: Google Sheets 템플릿 복사 → 데이터 입력 → 영수증 이미지 첨부 → 권한 공유
        ↓
Phase 5: Slack에 검토 요청 메시지 전송 (시트 링크 + 제출 버튼)
        ↓
사용자가 시트 내용 확인 후 수정 → Slack에서 "제출" 클릭
        ↓
AI 교정 데이터 저장 + 재무팀 채널로 최종 전달
```

## 아키텍처

```
expense-agent/
├── main.py                     # 진입점 (Slack Bolt Socket Mode)
├── config.py                   # 환경변수 및 상수
├── models.py                   # 데이터 모델 (ReceiptData, ExpenseReport 등)
│
├── handlers/
│   ├── slack_handler.py        # Slack 이벤트 오케스트레이션
│   ├── ai_handler.py           # Claude Vision API 호출
│   ├── sheets_handler.py       # Google Sheets/Drive API
│   ├── dungeon_api.py          # 프로젝트명 조회 API
│   └── feedback.py             # AI 교정 데이터 수집/저장
│
├── prompts/
│   └── receipt_analysis.py     # 스킬 파일 로더
│
├── skills/
│   └── receipt_analysis.md     # 영수증 분석 AI 스킬 (비개발자도 수정 가능)
│
├── utils/
│   ├── image_processor.py      # 이미지 리사이즈, PDF 변환
│   ├── validators.py           # 영수증 데이터 검증
│   └── logger.py               # 로깅 설정
│
├── credentials/                # Google 인증 파일 (Git 제외)
├── Dockerfile                  # Docker 이미지 정의
└── .env                        # 환경변수 (Git 제외)
```

## 환경 설정

### 1. 환경변수 (.env)

```env
# Slack
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...

# Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# Google
GOOGLE_APPLICATION_CREDENTIALS=./credentials/service-account-key.json
TEMPLATE_SPREADSHEET_ID=...      # 지출결의서 템플릿 시트 ID
PARENT_FOLDER_ID=...             # 생성된 시트를 저장할 Google Drive 폴더 ID

# Slack 사용자/채널
FINANCE_MANAGER_USER_ID=...      # 재무담당자 Slack User ID (@Eunmi Wi)
CFO_USER_ID=...                  # CFO Slack User ID (@Sungyoung Jung)
EXPENSE_SUBMIT_CHANNEL_ID=...    # 지출결의서 제출 채널 ID

# 던전 API (프로젝트명 조회, 선택)
DUNGEON_API_BASE_URL=...
DUNGEON_API_EMAIL=...
DUNGEON_API_PASSWORD=...
```

### 2. 필요 파일

```
credentials/
├── service-account-key.json     # Google Cloud 서비스 계정 키
├── oauth_client.json            # OAuth 클라이언트 설정
└── token.json                   # OAuth 토큰 (최초 실행 시 자동 생성)
```

> **주의**: credentials/ 디렉토리와 .env 파일은 Git에 포함되지 않습니다.

## 실행 방법

### 로컬 실행

```bash
cd expense-agent
pip install -r requirements.txt
python main.py
```

### GCP 서버 (운영 환경)

봇은 GCP Compute Engine VM에서 Docker + systemd로 24/7 운영됩니다.

- **VM**: `expense-agent` (asia-northeast3-a, e2-small)
- **프로젝트**: `mfl-expenditurehandling`

```bash
# 봇 상태 확인
gcloud compute ssh expense-agent --project=mfl-expenditurehandling --zone=asia-northeast3-a \
  --command="sudo systemctl status expense-agent --no-pager"

# 실시간 로그 확인
gcloud compute ssh expense-agent --project=mfl-expenditurehandling --zone=asia-northeast3-a \
  --command="sudo docker logs expense-agent-container -f --tail 50"
```

## 코드 업데이트 배포

로컬에서 코드 수정 후 GitHub에 push, 이후 VM에서 아래 명령 실행:

```bash
gcloud compute ssh expense-agent --project=mfl-expenditurehandling --zone=asia-northeast3-a

# VM에서
cd /home/joseph/expense-agent
git pull
sudo docker build -t expense-agent .
sudo systemctl restart expense-agent
```

## AI 스킬 수정

영수증 분석 로직은 `skills/receipt_analysis.md` 파일에 정의되어 있습니다.
Python 코드 수정 없이 이 파일만 수정하면 AI 분석 동작을 변경할 수 있습니다.

```
skills/receipt_analysis.md  ← 여기서 분류 기준, 프롬프트 내용 수정
```

수정 후 봇을 재시작하면 변경 내용이 반영됩니다.

## AI 학습 피드백

사용자가 생성된 지출결의서의 **항목 분류** 또는 **지출 목적**을 수정하면,
Slack에서 "제출" 버튼 클릭 시 수정 내용이 자동으로 학습 데이터로 저장됩니다.

- **저장 위치**: `PROJECT_COST_SPREADSHEET_ID` 시트의 `AI교정데이터` 탭
- **활용**: 다음 영수증 분석 시 최근 10건의 교정 사례를 AI 프롬프트에 자동 포함

## 지원 파일 형식

| 형식 | 분석 | Sheets 첨부 |
|------|------|-------------|
| JPG / PNG / GIF / WebP | ✅ | ✅ |
| HEIC / HEIF (iPhone) | ✅ | ✅ (JPG 변환) |
| PDF | ✅ | ✅ (페이지별 JPG 변환) |

한 번에 최대 **15장** 처리 가능.
