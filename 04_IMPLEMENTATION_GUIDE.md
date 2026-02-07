# Claude Code 실행 가이드 (Implementation Guide)

이 문서는 Claude Code에 직접 입력하여 지출품의서 자동화 에이전트를 구현할 수 있는 상세 가이드입니다.

---

## 1. Claude Code 프롬프트

다음 내용을 Claude Code에 복사하여 붙여넣으세요:

```markdown
@CLAUDE 당신은 Google Sheets API와 Slack API를 활용한 업무 자동화 에이전트를 구축해야 합니다.
다음은 사용자가 요청한 '지출품의서 자동화 Agent'의 PRD와 기술 명세서입니다. 이 내용을 바탕으로 Python 코드를 작성해 주세요.

## [목표]
Slack에서 영수증 이미지를 받으면 Google Sheets 템플릿에 내용을 채우고, 결재 요청 메시지를 보내는 봇 생성.

## [기술 스택]
- **언어:** Python 3.9+
- **프레임워크:** Slack Bolt (Socket Mode 권장)
- **Google Cloud:** Google Sheets API, Google Drive API (이미지 업로드 및 시트 복사)
- **AI 모델:** Claude 3.5 Sonnet (영수증 이미지 분석용 - base64 인코딩 전송)
- **데이터베이스:** SQLite (처리 이력 저장, 선택사항)

## [구현 단계]

### Step 1: 환경 설정
1. 필요한 패키지 설치
   - slack-bolt
   - slack-sdk
   - google-api-python-client
   - google-auth-httplib2
   - google-auth-oauthlib
   - anthropic
   - python-dotenv
   - Pillow (이미지 처리)

2. 환경 변수 설정 (.env 파일)
   - SLACK_BOT_TOKEN
   - SLACK_APP_TOKEN (Socket Mode)
   - ANTHROPIC_API_KEY
   - GOOGLE_APPLICATION_CREDENTIALS (서비스 계정 JSON 파일 경로)
   - TEMPLATE_SPREADSHEET_ID (템플릿 Google Sheets ID)
   - FINANCE_MANAGER_USER_ID (재무 담당자 Slack User ID)
   - CEO_USER_ID (대표님 Slack User ID)

### Step 2: Slack 리스너 설정
- 앱 멘션(@Bot) 및 파일 공유 이벤트를 감지
- 이벤트 타입: `app_mention` + 파일 첨부
- 이미지 파일만 처리 (MIME type 확인)

```python
@app.event("app_mention")
def handle_mention(event, say, client):
    # 이미지 첨부 확인
    # 처리 시작 메시지 발송
    # 백그라운드 작업 시작
    pass
```

### Step 3: 이미지 처리 및 AI 분석
1. Slack에서 이미지 다운로드
2. 필요시 이미지 최적화 (크기 조정, HEIC → JPG 변환)
3. Base64 인코딩
4. Claude API에 전송하여 JSON 데이터 추출

**Claude API 프롬프트 요구사항:**
- docs/03_AI_PROMPT_GUIDE.md 참조
- 출력 형식: JSON
- 필수 필드: merchant_name, transaction_date, total_amount, items

### Step 4: Google Sheets 조작
1. **시트 복사:**
   - 템플릿 파일을 복사하여 새로운 스프레드시트 생성
   - 파일명: `{프로젝트명}_{월}월_개인카드_지출품의서_{사용자명}`

2. **데이터 입력 (`지출결의서_템플릿` 시트):**
   - docs/02_DATA_SPEC.md의 매핑 테이블 참조
   - 작성일자, 프로젝트명, 사용자, 지출금액, 사용목적
   - 내역: 적요, 수량, 공급가액, 세액, 소계

3. **금액 계산 로직:**
   ```python
   supply_value = round(total_amount / 1.1)  # 공급가액
   tax_amount = total_amount - supply_value   # 세액
   ```

4. **영수증 이미지 첨부 (`영수증 첨부` 시트):**
   - 방법 1: Google Drive에 이미지 업로드 후 IMAGE() 함수 사용
   - 방법 2: Sheets API의 InsertImageRequest 사용
   - 삽입 위치: B2 셀 근처

5. **권한 설정:**
   - 생성된 시트에 요청자 및 재무 담당자 편집 권한 부여

### Step 5: Slack 인터랙션 흐름
1. **처리 중 메시지:**
   ```
   "지출품의서를 작성 중입니다... ⏳"
   ```

2. **검토 요청 메시지 (스레드 답글):**
   ```
   {사용자명}님, 지출품의서 초안이 작성되었습니다.
   내용을 확인하고 수정이 필요 없으면 '완료'라고 답글을 달아주세요.

   📄 {Google Sheets URL}
   ```

3. **사용자 응답 리스너:**
   - 메시지 이벤트 감지 (스레드 내 "완료" 키워드)
   - 또는 Slack Interactive Components (버튼) 사용

4. **최종 제출 메시지:**
   ```
   @Eunmi Wi 은미님!
   {프로젝트명} {년}년 {월}월 개인카드사용 지출결의서 전달드립니다.
   cc @Paul / @Sungyoung Jung

   📄 {Google Sheets URL}
   ```

### Step 6: 에러 처리 및 로깅
- 각 단계별 try-except 처리
- 실패 시 사용자에게 친절한 에러 메시지 발송
- 처리 이력을 SQLite DB에 저장 (선택사항)
- 로그 파일 생성 (INFO, ERROR 레벨 구분)

### Step 7: 추가 기능 (선택사항)
- Slack 채널명 → 프로젝트명 매핑 테이블
- Slack User ID → 실명 매핑
- 고액 지출 경고 (예: 100만원 초과 시)
- 중복 처리 방지 (이미지 해시 체크)

## [프로젝트 구조]
```
expense-agent/
├── main.py                 # 메인 실행 파일
├── .env                    # 환경 변수
├── requirements.txt        # 패키지 의존성
├── config.py              # 설정 파일
├── handlers/
│   ├── slack_handler.py   # Slack 이벤트 처리
│   ├── sheets_handler.py  # Google Sheets 처리
│   └── ai_handler.py      # Claude API 호출
├── utils/
│   ├── image_processor.py # 이미지 처리 유틸리티
│   ├── validators.py      # 데이터 검증
│   └── logger.py          # 로깅 유틸리티
├── prompts/
│   └── receipt_analysis.py # AI 프롬프트 템플릿
└── tests/
    └── test_handlers.py   # 단위 테스트
```

## [구현 요청 사항]
1. 위 구조에 맞춰 모듈화된 Python 코드 작성
2. requirements.txt 생성
3. .env.example 파일 생성 (환경 변수 템플릿)
4. README.md 작성 (설정 및 실행 방법 포함)
5. 주요 함수에 docstring 추가
6. 에러 처리 및 로깅 구현

## [참조 문서]
- docs/01_PRD.md: 제품 요구사항 정의서
- docs/02_DATA_SPEC.md: 데이터 매핑 및 로직 명세서
- docs/03_AI_PROMPT_GUIDE.md: AI 프롬프트 가이드

위 요구사항에 맞춰 구현을 시작해주세요!
```

---

## 2. 단계별 실행 가이드

### 2.1 사전 준비

#### A. Slack App 설정
1. https://api.slack.com/apps 에서 새 앱 생성
2. **OAuth & Permissions**에서 다음 스코프 추가:
   - `app_mentions:read`
   - `chat:write`
   - `files:read`
   - `users:read`
   - `channels:history`
3. **Event Subscriptions** 활성화:
   - `app_mention`
   - `message.channels` (스레드 응답 감지용)
4. **Socket Mode** 활성화 (또는 ngrok 사용)
5. 토큰 복사:
   - Bot User OAuth Token → `SLACK_BOT_TOKEN`
   - App-Level Token → `SLACK_APP_TOKEN`

#### B. Google Cloud 설정
1. Google Cloud Console에서 프로젝트 생성
2. 다음 API 활성화:
   - Google Sheets API
   - Google Drive API
3. 서비스 계정 생성:
   - IAM & Admin → Service Accounts → Create
   - JSON 키 다운로드
4. 템플릿 Google Sheets에 서비스 계정 이메일 공유 (편집 권한)

#### C. Claude API 설정
1. https://console.anthropic.com/ 에서 API 키 발급
2. 크레딧 확인 및 충전

### 2.2 로컬 개발 환경 설정

```bash
# 1. 프로젝트 디렉토리 생성
mkdir expense-agent
cd expense-agent

# 2. 가상 환경 생성
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. (Claude Code가 생성한 requirements.txt 설치)
pip install -r requirements.txt

# 4. 환경 변수 설정
cp .env.example .env
# .env 파일을 편집하여 실제 값 입력

# 5. Google 서비스 계정 JSON 파일 배치
mv ~/Downloads/service-account-key.json ./credentials/

# 6. 실행
python main.py
```

### 2.3 환경 변수 (.env) 예시

```bash
# Slack
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-token

# Anthropic Claude
ANTHROPIC_API_KEY=sk-ant-your-api-key

# Google Cloud
GOOGLE_APPLICATION_CREDENTIALS=./credentials/service-account-key.json

# Google Sheets
TEMPLATE_SPREADSHEET_ID=1AbCdEfGhIjKlMnOpQrStUvWxYz

# Slack User IDs
FINANCE_MANAGER_USER_ID=U01ABC123  # @Eunmi Wi
CEO_USER_ID=U02DEF456              # @Paul
CFO_USER_ID=U03GHI789              # @Sungyoung Jung

# Channel → Project Mapping (JSON 형식)
CHANNEL_PROJECT_MAP='{"C01234ABC": "푸드케어 CRO PJ", "C56789DEF": "알파 프로젝트"}'

# Optional
LOG_LEVEL=INFO
DATABASE_PATH=./data/expense_tracking.db
```

---

## 3. 테스트 시나리오

### 3.1 End-to-End 테스트

1. **Step 1: 영수증 업로드**
   - Slack 테스트 채널에서 `@ExpenseBot`를 태그하며 영수증 이미지 업로드
   - 예상 결과: "지출품의서를 작성 중입니다..." 메시지 수신

2. **Step 2: AI 분석 확인**
   - 로그에서 Claude API 응답 확인
   - 추출된 JSON 데이터 검증

3. **Step 3: Google Sheets 확인**
   - 새로 생성된 시트 URL 수신
   - 데이터가 올바르게 입력되었는지 확인
   - 영수증 이미지가 첨부되었는지 확인

4. **Step 4: 검토 프로세스**
   - 스레드에 "완료" 입력
   - 재무 담당자에게 알림 메시지 발송 확인

### 3.2 단위 테스트 예시

```python
# tests/test_handlers.py
import pytest
from handlers.ai_handler import analyze_receipt
from handlers.sheets_handler import calculate_tax

def test_analyze_receipt():
    """영수증 분석 테스트"""
    result = analyze_receipt("test_data/sample_receipt.jpg")
    assert result["total_amount"] > 0
    assert result["merchant_name"] is not None

def test_calculate_tax():
    """세액 계산 테스트"""
    supply_value, tax = calculate_tax(11000)
    assert supply_value == 10000
    assert tax == 1000
    assert supply_value + tax == 11000

def test_date_validation():
    """날짜 검증 테스트"""
    from utils.validators import validate_date

    assert validate_date("2025-11-25") == True
    assert validate_date("2025-13-01") == False
    assert validate_date("invalid") == False
```

---

## 4. 배포 가이드

### 4.1 로컬 실행 (개발용)

```bash
python main.py
```

### 4.2 서버 배포 (운영용)

#### Option 1: Docker 배포

```dockerfile
# Dockerfile
FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
```

```bash
# 빌드 및 실행
docker build -t expense-agent .
docker run -d --env-file .env --name expense-bot expense-agent
```

#### Option 2: systemd 서비스 (Linux)

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
sudo systemctl status expense-agent
```

#### Option 3: AWS EC2 / Google Compute Engine

1. VM 인스턴스 생성 (최소 스펙: 1GB RAM)
2. 코드 배포 및 환경 설정
3. systemd 또는 Docker로 실행
4. 보안 그룹 / 방화벽 설정 (Socket Mode 사용 시 아웃바운드만 필요)

---

## 5. 모니터링 및 유지보수

### 5.1 로그 확인

```bash
# 실시간 로그 확인
tail -f logs/expense_agent.log

# 에러 로그만 필터링
grep ERROR logs/expense_agent.log
```

### 5.2 성능 모니터링

```python
# utils/metrics.py
import time
from functools import wraps

def track_time(func):
    """함수 실행 시간 측정 데코레이터"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        elapsed = time.time() - start
        print(f"{func.__name__} 실행 시간: {elapsed:.2f}초")
        return result
    return wrapper

@track_time
def analyze_receipt(image_path):
    # ...
    pass
```

### 5.3 주기적 점검 사항

- [ ] Claude API 크레딧 잔액 확인 (주 1회)
- [ ] Google Sheets API 할당량 확인 (월 1회)
- [ ] 에러 로그 검토 (주 1회)
- [ ] 처리 성공률 확인 (월 1회)
- [ ] 디스크 용량 확인 (월 1회)

---

## 6. 트러블슈팅

### 6.1 자주 발생하는 문제

#### 문제 1: Slack 이벤트를 받지 못함
**원인:**
- Socket Mode가 제대로 연결되지 않음
- 토큰이 잘못됨
- 이벤트 구독 설정 누락

**해결:**
```bash
# 토큰 확인
echo $SLACK_APP_TOKEN
echo $SLACK_BOT_TOKEN

# 연결 테스트
python -c "from slack_bolt import App; app = App(token='...'); print('OK')"
```

#### 문제 2: Google Sheets API 권한 오류
**원인:**
- 서비스 계정에 시트 접근 권한 없음
- API가 활성화되지 않음

**해결:**
1. 템플릿 시트에 서비스 계정 이메일 공유 (편집 권한)
2. Google Cloud Console에서 API 활성화 확인

#### 문제 3: Claude API 오류
**원인:**
- API 키가 만료됨
- 크레딧 부족
- 이미지 크기 초과

**해결:**
```python
# 이미지 크기 확인 및 최적화
from PIL import Image
img = Image.open(receipt_path)
if img.size[0] > 1024 or img.size[1] > 1024:
    img.thumbnail((1024, 1024))
    img.save(receipt_path, quality=85)
```

#### 문제 4: 영수증 인식 정확도 낮음
**원인:**
- 이미지 화질 불량
- 조명 불량
- 프롬프트가 최적화되지 않음

**해결:**
1. 이미지 전처리 (밝기 조정, 샤프닝)
2. 프롬프트 개선 (Few-shot Examples 추가)
3. 사용자에게 재촬영 요청

---

## 7. FAQ

### Q1: 여러 장의 영수증을 한 번에 처리할 수 있나요?
A: 현재 버전은 1개의 이미지만 처리합니다. 향후 업데이트에서 일괄 처리 기능을 추가할 예정입니다.

### Q2: 손글씨 영수증도 인식하나요?
A: Claude Vision 모델은 손글씨도 어느 정도 인식하지만, 인쇄된 영수증보다 정확도가 낮을 수 있습니다.

### Q3: 비용은 얼마나 드나요?
A: 영수증 1건당 약 $0.01-0.02 (Claude API 비용)입니다. Google Sheets API와 Slack API는 무료 할당량 내에서 사용 가능합니다.

### Q4: 보안은 어떻게 보장하나요?
A:
- 모든 API 키는 환경 변수로 관리
- 영수증 이미지는 처리 후 즉시 삭제
- Google Sheets 권한은 최소 권한 원칙 적용
- HTTPS 통신 사용

### Q5: 다른 회사에서도 사용할 수 있나요?
A: 네, 설정 파일(채널 매핑, 템플릿 ID 등)만 수정하면 어떤 조직에서도 사용 가능합니다.

---

## 8. 다음 단계

구현이 완료되면:

1. **테스트 실행:** 샘플 영수증으로 전체 워크플로우 테스트
2. **팀원 교육:** 사용 방법 안내 문서 작성 및 공유
3. **피드백 수집:** 초기 사용자 의견 수렴
4. **개선:** 정확도 향상 및 추가 기능 구현
5. **문서화:** 운영 매뉴얼 작성

---

## 9. 지원 및 문의

- **기술 문서:** docs/ 폴더 참조
- **이슈 트래킹:** GitHub Issues 사용
- **문의:** 프로젝트 관리자에게 Slack DM

---

**작성일:** 2026-02-07
**버전:** 1.0
**작성자:** Claude Code
**문서 유형:** 구현 가이드
