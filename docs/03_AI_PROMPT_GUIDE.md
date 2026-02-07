# AI 프롬프트 가이드 (System Prompt)

이 문서는 Claude API를 사용하여 영수증 이미지를 분석할 때 사용할 프롬프트 템플릿을 제공합니다.

---

## 1. 영수증 분석용 System Prompt

### 1.1 기본 프롬프트

```markdown
# Role
당신은 꼼꼼한 회계 담당자 AI입니다. 사용자가 업로드한 영수증 이미지를 분석하여 JSON 형태로 데이터를 추출해야 합니다.

# Task
영수증 이미지에서 다음 정보를 정확하게 추출하십시오:
1. 상호명 (가게 이름, 업체명)
2. 거래 일시 (날짜 및 시간)
3. 총 금액 (합계)
4. 품목 리스트 (구매한 항목들)
5. 지출 성격 추론 (식대, 교통비, 비품 등)

# Output Format (JSON)
다음 형식의 JSON을 반환하십시오:

{
  "merchant_name": "상호명 (없으면 '알수없음')",
  "transaction_date": "YYYY-MM-DD",
  "transaction_time": "HH:MM:SS (선택사항)",
  "total_amount": 숫자 (콤마 제거, 정수만),
  "items": [
    {
      "name": "품목명",
      "quantity": 수량,
      "price": 단가,
      "amount": 금액
    }
  ],
  "payment_method": "결제수단 (카드/현금/알수없음)",
  "summary_inference": "지출 성격 추론 (예: 식대, 회식, 비품구입, 택시비, 커피/간식)"
}

# Rules
1. **날짜 처리:**
   - 날짜가 명확하게 보이지 않으면 `null`로 반환 (추정하지 말 것)
   - 형식은 반드시 YYYY-MM-DD (예: 2025-11-25)

2. **금액 처리:**
   - 콤마(,)를 제거하고 정수만 반환
   - 소수점이 있으면 반올림
   - 여러 금액이 있으면 "합계" 또는 "총액"을 우선으로 선택

3. **품목 처리:**
   - 품목이 많을 경우 (5개 이상), 대표 품목 3개 + "외 N건"으로 요약
   - 품목명이 불명확하면 "기타"로 표시

4. **부가세 처리:**
   - 부가세가 별도 표기되지 않은 경우, total_amount에 이미 포함된 것으로 간주
   - 부가세가 별도 표기된 경우, total_amount는 부가세 포함 금액

5. **확신도:**
   - 정보가 불명확하거나 읽기 어려운 경우, 해당 필드를 `null`로 설정
   - 절대 추측하거나 임의의 값을 넣지 말 것

# Examples

## Example 1: 카페 영수증
입력: [스타벅스 영수증 이미지]
출력:
{
  "merchant_name": "스타벅스 강남점",
  "transaction_date": "2025-11-25",
  "transaction_time": "14:30:22",
  "total_amount": 8800,
  "items": [
    {
      "name": "아메리카노(Tall)",
      "quantity": 2,
      "price": 4400,
      "amount": 8800
    }
  ],
  "payment_method": "카드",
  "summary_inference": "커피/간식"
}

## Example 2: 택시 영수증
입력: [택시 영수증 이미지]
출력:
{
  "merchant_name": "서울택시 1234",
  "transaction_date": "2025-12-01",
  "transaction_time": "09:15:00",
  "total_amount": 15000,
  "items": [
    {
      "name": "택시요금",
      "quantity": 1,
      "price": 15000,
      "amount": 15000
    }
  ],
  "payment_method": "카드",
  "summary_inference": "교통비"
}

## Example 3: 복잡한 식당 영수증
입력: [식당 영수증 이미지 - 품목 10개]
출력:
{
  "merchant_name": "맛있는집",
  "transaction_date": "2025-11-30",
  "transaction_time": "18:45:00",
  "total_amount": 65000,
  "items": [
    {
      "name": "삼겹살",
      "quantity": 2,
      "price": 15000,
      "amount": 30000
    },
    {
      "name": "냉면",
      "quantity": 2,
      "price": 9000,
      "amount": 18000
    },
    {
      "name": "소주 외 5건",
      "quantity": 1,
      "price": 17000,
      "amount": 17000
    }
  ],
  "payment_method": "카드",
  "summary_inference": "식대/회식"
}
```

---

## 2. API 호출 예시 (Python)

### 2.1 Claude API를 사용한 영수증 분석

```python
import anthropic
import base64
import json
from pathlib import Path

def analyze_receipt(image_path: str) -> dict:
    """
    영수증 이미지를 분석하여 JSON 데이터 반환

    Args:
        image_path: 영수증 이미지 파일 경로

    Returns:
        추출된 영수증 데이터 (dict)
    """
    # 1. 이미지를 base64로 인코딩
    with open(image_path, "rb") as image_file:
        image_data = base64.standard_b64encode(image_file.read()).decode("utf-8")

    # 2. 이미지 확장자 확인
    extension = Path(image_path).suffix.lower()
    media_type_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp"
    }
    media_type = media_type_map.get(extension, "image/jpeg")

    # 3. Claude API 클라이언트 생성
    client = anthropic.Anthropic(api_key="YOUR_API_KEY")

    # 4. System Prompt (위의 프롬프트 사용)
    system_prompt = """
    # Role
    당신은 꼼꼼한 회계 담당자 AI입니다. 사용자가 업로드한 영수증 이미지를 분석하여 JSON 형태로 데이터를 추출해야 합니다.

    [... 전체 프롬프트 생략 ...]
    """

    # 5. API 호출
    message = client.messages.create(
        model="claude-3-5-sonnet-20241022",  # 최신 Vision 모델
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_data,
                        },
                    },
                    {
                        "type": "text",
                        "text": "위 영수증 이미지를 분석하여 JSON 형식으로 데이터를 추출해주세요."
                    }
                ],
            }
        ],
    )

    # 6. 응답 파싱
    response_text = message.content[0].text

    # JSON 추출 (```json ``` 블록이 있을 수 있음)
    if "```json" in response_text:
        json_str = response_text.split("```json")[1].split("```")[0].strip()
    elif "```" in response_text:
        json_str = response_text.split("```")[1].split("```")[0].strip()
    else:
        json_str = response_text.strip()

    # 7. JSON 파싱
    try:
        receipt_data = json.loads(json_str)
        return receipt_data
    except json.JSONDecodeError as e:
        print(f"JSON 파싱 오류: {e}")
        print(f"원본 응답: {response_text}")
        raise

# 사용 예시
if __name__ == "__main__":
    result = analyze_receipt("receipt_sample.jpg")
    print(json.dumps(result, indent=2, ensure_ascii=False))
```

### 2.2 출력 예시

```json
{
  "merchant_name": "스타벅스 강남점",
  "transaction_date": "2025-11-25",
  "transaction_time": "14:30:22",
  "total_amount": 8800,
  "items": [
    {
      "name": "아메리카노(Tall)",
      "quantity": 2,
      "price": 4400,
      "amount": 8800
    }
  ],
  "payment_method": "카드",
  "summary_inference": "커피/간식"
}
```

---

## 3. 프롬프트 최적화 팁

### 3.1 정확도 향상을 위한 팁

1. **Few-shot Examples 추가:**
   - 실제 영수증 샘플과 기대 출력을 프롬프트에 포함
   - 다양한 유형 (카페, 식당, 택시, 편의점 등) 커버

2. **명확한 제약 조건:**
   - "추측하지 말고 확신이 없으면 null 반환"
   - "날짜 형식은 반드시 YYYY-MM-DD"
   - "금액은 정수만 (콤마 제거)"

3. **단계별 사고 유도 (Chain of Thought):**
   ```
   분석 과정:
   1. 먼저 이미지에서 텍스트를 모두 읽어주세요
   2. 상호명을 찾아주세요 (보통 상단에 크게 표시)
   3. 날짜와 시간을 찾아주세요
   4. 품목 리스트를 찾아주세요
   5. 합계 금액을 찾아주세요
   6. 최종적으로 JSON으로 정리해주세요
   ```

### 3.2 에러 처리

```python
def validate_receipt_data(data: dict) -> tuple[bool, list[str]]:
    """
    추출된 데이터 유효성 검증

    Returns:
        (is_valid, error_messages)
    """
    errors = []

    # 필수 필드 확인
    required_fields = ['merchant_name', 'transaction_date', 'total_amount']
    for field in required_fields:
        if not data.get(field):
            errors.append(f"필수 필드 누락: {field}")

    # 날짜 형식 확인
    if data.get('transaction_date'):
        try:
            from datetime import datetime
            datetime.strptime(data['transaction_date'], '%Y-%m-%d')
        except ValueError:
            errors.append(f"잘못된 날짜 형식: {data['transaction_date']}")

    # 금액 확인
    if data.get('total_amount'):
        if not isinstance(data['total_amount'], (int, float)):
            errors.append(f"잘못된 금액 타입: {type(data['total_amount'])}")
        elif data['total_amount'] <= 0:
            errors.append(f"금액은 0보다 커야 함: {data['total_amount']}")

    return len(errors) == 0, errors

# 사용 예시
is_valid, errors = validate_receipt_data(receipt_data)
if not is_valid:
    print("데이터 검증 실패:")
    for error in errors:
        print(f"  - {error}")
```

---

## 4. 비용 최적화

### 4.1 모델 선택

| 모델 | 성능 | 비용 | 권장 사용 |
|------|------|------|----------|
| Claude 3.5 Sonnet | 최고 | 높음 | 복잡한 영수증, 저화질 이미지 |
| Claude 3 Haiku | 빠름 | 낮음 | 단순한 영수증, 고화질 이미지 |

### 4.2 토큰 사용량 줄이기

```python
# 이미지 크기 최적화 (Vision API 전송 전)
from PIL import Image

def optimize_image(image_path: str, max_size: tuple = (1024, 1024)) -> str:
    """이미지 크기 최적화"""
    img = Image.open(image_path)
    img.thumbnail(max_size, Image.Resampling.LANCZOS)

    optimized_path = f"{image_path}_optimized.jpg"
    img.save(optimized_path, "JPEG", quality=85)
    return optimized_path
```

### 4.3 캐싱 활용

- 같은 영수증을 중복 처리하지 않도록 해시값 저장
- 처리 결과를 DB에 캐시하여 재사용

```python
import hashlib

def get_image_hash(image_path: str) -> str:
    """이미지 해시값 생성"""
    with open(image_path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()

# 캐시 확인
image_hash = get_image_hash(receipt_path)
if cached_result := cache.get(image_hash):
    return cached_result  # 캐시된 결과 사용
```

---

## 5. 프롬프트 버전 관리

프롬프트는 코드처럼 버전 관리가 필요합니다.

```python
# prompts.py
RECEIPT_ANALYSIS_PROMPT_V1 = """..."""
RECEIPT_ANALYSIS_PROMPT_V2 = """..."""  # 개선된 버전

# 설정에서 버전 선택
CURRENT_PROMPT_VERSION = "v2"

def get_system_prompt(version: str = CURRENT_PROMPT_VERSION) -> str:
    prompts = {
        "v1": RECEIPT_ANALYSIS_PROMPT_V1,
        "v2": RECEIPT_ANALYSIS_PROMPT_V2,
    }
    return prompts[version]
```

---

## 6. 테스트 및 평가

### 6.1 테스트 케이스 준비

```python
test_cases = [
    {
        "image": "receipts/cafe_clear.jpg",
        "expected": {
            "merchant_name": "스타벅스",
            "total_amount": 4400,
        }
    },
    {
        "image": "receipts/restaurant_blurry.jpg",
        "expected": {
            "merchant_name": "한식당",
            "total_amount": 35000,
        }
    },
]

def evaluate_accuracy():
    correct = 0
    total = len(test_cases)

    for case in test_cases:
        result = analyze_receipt(case["image"])
        if result["total_amount"] == case["expected"]["total_amount"]:
            correct += 1

    accuracy = correct / total * 100
    print(f"정확도: {accuracy:.2f}%")
```

### 6.2 정확도 목표

- 금액 추출 정확도: **99% 이상** (필수)
- 상호명 추출 정확도: **95% 이상**
- 날짜 추출 정확도: **98% 이상**
- 품목 추출 정확도: **90% 이상** (참고용)
