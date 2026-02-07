from __future__ import annotations

import logging
from datetime import datetime, timedelta

from config import HIGH_AMOUNT_THRESHOLD

logger = logging.getLogger(__name__)


def validate_receipt_data(data: dict) -> tuple[bool, list[str], list[str]]:
    """
    영수증 데이터 종합 검증

    Returns:
        (is_valid, errors, warnings)
    """
    errors = []
    warnings = []

    # 필수: 금액
    total = data.get("total_amount")
    if not total:
        errors.append("총 금액을 찾을 수 없습니다.")
    elif not isinstance(total, (int, float)):
        errors.append(f"금액 형식 오류: {total}")
    elif total <= 0:
        errors.append(f"금액은 양수여야 합니다: {total}")
    elif total > HIGH_AMOUNT_THRESHOLD:
        warnings.append(f"고액 지출 감지: {total:,}원")

    # 상호명: 없으면 기본값
    if not data.get("merchant_name"):
        warnings.append("상호명을 찾을 수 없어 '알 수 없음'으로 기록합니다.")
        data["merchant_name"] = "알 수 없음"

    # 날짜 검증
    date_str = data.get("transaction_date")
    if not date_str:
        warnings.append("거래일자를 찾을 수 없어 수동 확인이 필요합니다.")
    else:
        is_valid_date, date_warnings = validate_date(date_str)
        if not is_valid_date:
            errors.append(f"날짜 형식 오류: {date_str}")
        warnings.extend(date_warnings)

    return len(errors) == 0, errors, warnings


def validate_date(date_str: str) -> tuple[bool, list[str]]:
    """날짜 문자열 검증"""
    warnings = []
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return False, []

    if dt > datetime.now():
        return False, ["미래 날짜의 영수증입니다."]

    if dt < datetime.now() - timedelta(days=180):
        warnings.append(f"6개월 이전 영수증입니다: {date_str}")

    return True, warnings


def validate_expense_report(line_items, total_amount: int) -> tuple[bool, list[str]]:
    """
    지출결의서 데이터 정합성 검증
    """
    errors = []

    if not line_items:
        errors.append("지출 내역이 없습니다.")
        return False, errors

    calculated_total = sum(item.subtotal for item in line_items)
    if calculated_total != total_amount:
        errors.append(
            f"합계 불일치: 계산값={calculated_total:,}, 기록값={total_amount:,}"
        )

    for idx, item in enumerate(line_items):
        if item.supply_value + item.tax_amount != item.subtotal:
            errors.append(f"항목 #{idx+1} 세액 계산 오류")

    return len(errors) == 0, errors
