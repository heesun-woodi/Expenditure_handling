# 데이터 매핑 및 로직 명세서 (Data Spec)

**중요:** `푸드케어 CRO PJ_11월 12월_개인카드 지출품의서_우디` 샘플 파일의 작성 규칙을 따릅니다.

---

## 1. Google Sheets 구조

### 1.1 시트 구성
- **지출결의서_템플릿**: 메인 데이터 입력 시트
- **영수증 첨부**: 영수증 이미지 첨부 시트

---

## 2. 지출결의서_템플릿 시트 입력 규칙

### 2.1 헤더 정보 매핑

| 필드명 | 셀 위치 (추정) | 데이터 출처 및 로직 | 예시 데이터 |
|--------|---------------|---------------------|-------------|
| **작성일자** | 문서 상단 | 지출품의서 생성 시점 (Today)<br>형식: `YY.MM.DD` | `26.02.07` |
| **프로젝트 명** | 문서 상단 | 요청이 발생한 Slack 채널명<br>(또는 채널명 매핑 테이블 참조) | `푸드케어 CRO PJ` |
| **사용자** | 문서 상단 | Slack 요청자의 Display Name<br>(실명 매핑 필요) | `우디` |
| **지출금액** | 문서 상단 | 영수증 총 합계 금액 (모든 항목 합산) | `22,400` |
| **사용목적** | 문서 상단 | 자동 생성 형식:<br>`{프로젝트명} {월}월 개인카드 지출` | `푸드케어 CRO PJ 2월 개인카드 지출` |

### 2.2 상세 내역 매핑 (반복 가능)

| 필드명 | 셀 위치 | 데이터 출처 및 로직 | 예시 데이터 |
|--------|---------|---------------------|-------------|
| **적요** | 리스트 영역 | **포맷:**<br>`{영수증품목/목적} ({YY.MM.DD} / {사용자})`<br><br>- 영수증품목: AI가 추출한 대표 품목명<br>- 날짜: 영수증의 거래일자<br>- 사용자: 요청자명 | `대면세션 커피 및 간식 (25.11.25 / 우디)` |
| **수량** | 리스트 영역 | 기본값 `1`<br>(항목별로 별도 처리하지 않음) | `1` |
| **공급가액** | 리스트 영역 | **계산식:**<br>`공급가액 = ROUND(합계금액 / 1.1, 0)`<br>(소수점 반올림) | `8,001` |
| **세액** | 리스트 영역 | **계산식:**<br>`세액 = 합계금액 - 공급가액` | `799` |
| **소계** | 리스트 영역 | 영수증의 합계 금액 (Total Amount) | `8,800` |

---

## 3. 금액 계산 로직

### 3.1 부가세 포함 금액 분리

한국 부가가치세는 10%이므로, 다음 공식을 사용합니다:

```python
# 입력: total_amount (부가세 포함 총액)
supply_value = round(total_amount / 1.1)  # 공급가액 (반올림)
tax_amount = total_amount - supply_value   # 세액
```

### 3.2 예시

| 합계금액 | 공급가액 계산 | 세액 계산 | 검증 |
|---------|--------------|----------|------|
| 8,800원 | 8,800 / 1.1 = 8,000 (반올림) | 8,800 - 8,000 = 800 | ✓ |
| 22,400원 | 22,400 / 1.1 = 20,364 (반올림) | 22,400 - 20,364 = 2,036 | ✓ |

**주의사항:**
- 반올림 오차로 인해 `공급가액 × 1.1 ≠ 합계금액`일 수 있음
- 항상 `합계금액 = 공급가액 + 세액`이 성립해야 함

---

## 4. 영수증 첨부 시트 처리 규칙

### 4.1 이미지 삽입 위치
- **시트명:** `영수증 첨부`
- **삽입 위치:** B2 셀 근처 (또는 지정된 영역)
- **정렬:** 세로로 순차 배치 (여러 영수증 시)

### 4.2 이미지 처리 규칙
- **파일 형식:** JPG, PNG 권장 (HEIC는 변환 필요)
- **크기 조정:**
  - 최대 너비: 600px
  - 최대 높이: 800px
  - 비율 유지하면서 리사이징
- **품질:** 원본 유지 (손실 최소화)

### 4.3 구현 방법 (Google Sheets API)
```python
# 1. 이미지를 Google Drive에 업로드
# 2. Drive 파일 ID를 사용하여 Sheets에 IMAGE 함수 삽입
# 또는
# 3. spreadsheets.batchUpdate API의 InsertImageRequest 사용
```

---

## 5. Slack 채널명 → 프로젝트명 매핑 테이블

| Slack 채널명 | Google Sheets 프로젝트명 |
|-------------|------------------------|
| `#pj-foodcare` | `푸드케어 CRO PJ` |
| `#pj-alpha` | `알파 프로젝트` |
| `#pj-beta` | `베타 서비스 런칭` |

**설정 방법:**
- 코드 내 딕셔너리로 관리
- 또는 별도 설정 파일 (config.yaml) 사용

```python
CHANNEL_PROJECT_MAP = {
    "C01234ABC": "푸드케어 CRO PJ",  # 채널 ID를 키로 사용
    "C56789DEF": "알파 프로젝트",
}
```

---

## 6. Slack User ID → 실명 매핑

| Slack User ID | Display Name | 실명 |
|--------------|--------------|------|
| U01ABC123 | woodi | 우디 |
| U02DEF456 | paul | Paul |
| U03GHI789 | eunmi.wi | Eunmi Wi |

**구현 방법:**
```python
# Slack API를 통한 실시간 조회
from slack_sdk import WebClient

client = WebClient(token=SLACK_BOT_TOKEN)
user_info = client.users_info(user=user_id)
real_name = user_info['user']['profile']['real_name']
```

---

## 7. 알림 메시지 템플릿

### 7.1 검토 요청 메시지 (Step 3)

```
우디님, 지출품의서 초안이 작성되었습니다.
내용을 확인하고 수정이 필요 없으면 '완료'라고 답글을 달아주세요.

📄 {google_sheets_url}

---
📌 확인 사항:
- 날짜가 정확한가요?
- 금액이 맞나요?
- 품목 설명이 적절한가요?
```

### 7.2 최종 제출 메시지 (Step 5)

```
@Eunmi Wi 은미님!
{project_name} {year}년 {month}월 개인카드사용 지출결의서 전달드립니다.
cc @Paul / @Sungyoung Jung

📄 {google_sheets_url}

---
작성자: {user_name}
총 지출액: {total_amount:,}원
작성일: {created_date}
```

**동적 변수:**
- `{project_name}`: 푸드케어 CRO PJ
- `{year}`: 2026
- `{month}`: 2
- `{user_name}`: 우디
- `{total_amount}`: 22400
- `{created_date}`: 2026-02-07
- `{google_sheets_url}`: https://docs.google.com/spreadsheets/d/...

---

## 8. 데이터 유효성 검사

### 8.1 필수 필드 검증
```python
required_fields = {
    'transaction_date': '거래일자',
    'total_amount': '총 금액',
    'merchant_name': '상호명',
}

for field, label in required_fields.items():
    if not data.get(field):
        raise ValueError(f"{label}을(를) 찾을 수 없습니다.")
```

### 8.2 금액 유효성 검사
```python
# 1. 음수 체크
if total_amount <= 0:
    raise ValueError("금액은 0보다 커야 합니다.")

# 2. 상식적인 범위 체크 (예: 10,000,000원 초과 시 경고)
if total_amount > 10_000_000:
    # Slack으로 경고 메시지 발송
    send_warning(f"⚠️ 고액 지출 감지: {total_amount:,}원")

# 3. 공급가액 + 세액 = 합계 검증
if supply_value + tax_amount != total_amount:
    raise ValueError("금액 계산 오류")
```

### 8.3 날짜 유효성 검사
```python
from datetime import datetime, timedelta

# 1. 미래 날짜 체크
if transaction_date > datetime.now():
    raise ValueError("미래 날짜의 영수증은 처리할 수 없습니다.")

# 2. 너무 오래된 영수증 체크 (예: 6개월 이전)
if transaction_date < datetime.now() - timedelta(days=180):
    send_warning("⚠️ 6개월 이전 영수증입니다. 확인이 필요합니다.")
```

---

## 9. 에러 처리 시나리오

| 상황 | 처리 방법 |
|------|----------|
| 영수증 이미지가 흐릿함 | 사용자에게 재업로드 요청 메시지 발송 |
| 상호명을 찾을 수 없음 | "알 수 없음"으로 기록 후 사용자에게 수동 입력 요청 |
| 날짜를 찾을 수 없음 | 현재 날짜로 임시 설정 후 검토 요청 시 강조 표시 |
| 금액 추출 실패 | 처리 중단 후 에러 메시지 발송 (필수 항목) |
| Google Sheets API 오류 | 3회 재시도 후 실패 시 관리자에게 알림 |
| Slack API 오류 | 로그 기록 후 재시도 큐에 추가 |

---

## 10. 로그 및 모니터링

### 10.1 기록할 정보
```python
log_entry = {
    'timestamp': datetime.now().isoformat(),
    'user_id': user_id,
    'channel_id': channel_id,
    'file_id': file_id,
    'processing_time': elapsed_seconds,
    'status': 'success' | 'failed',
    'error_message': error_msg if failed,
    'sheets_url': sheets_url,
}
```

### 10.2 모니터링 지표
- 시간당 처리 건수
- 평균 처리 시간
- 성공률 / 실패율
- 사용자별 사용 빈도
