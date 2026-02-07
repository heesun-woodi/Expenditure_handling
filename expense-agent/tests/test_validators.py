import pytest
from utils.validators import validate_receipt_data, validate_date


class TestValidateReceiptData:
    def test_valid_data(self):
        data = {
            "merchant_name": "스타벅스",
            "transaction_date": "2025-11-25",
            "total_amount": 8800,
        }
        is_valid, errors, warnings = validate_receipt_data(data)
        assert is_valid
        assert not errors

    def test_missing_amount(self):
        data = {"merchant_name": "스타벅스", "transaction_date": "2025-11-25"}
        is_valid, errors, warnings = validate_receipt_data(data)
        assert not is_valid
        assert any("금액" in e for e in errors)

    def test_negative_amount(self):
        data = {
            "merchant_name": "스타벅스",
            "transaction_date": "2025-11-25",
            "total_amount": -1000,
        }
        is_valid, errors, warnings = validate_receipt_data(data)
        assert not is_valid

    def test_missing_merchant_fills_default(self):
        data = {"transaction_date": "2025-11-25", "total_amount": 8800}
        is_valid, errors, warnings = validate_receipt_data(data)
        assert is_valid
        assert data["merchant_name"] == "알 수 없음"
        assert any("상호명" in w for w in warnings)

    def test_missing_date_warns(self):
        data = {"merchant_name": "스타벅스", "total_amount": 8800}
        is_valid, errors, warnings = validate_receipt_data(data)
        assert is_valid
        assert any("거래일자" in w for w in warnings)

    def test_high_amount_warns(self):
        data = {
            "merchant_name": "비싼곳",
            "transaction_date": "2025-11-25",
            "total_amount": 15_000_000,
        }
        is_valid, errors, warnings = validate_receipt_data(data)
        assert is_valid
        assert any("고액" in w for w in warnings)


class TestValidateDate:
    def test_valid_date(self):
        is_valid, warnings = validate_date("2025-11-25")
        assert is_valid

    def test_invalid_format(self):
        is_valid, warnings = validate_date("2025/11/25")
        assert not is_valid

    def test_invalid_string(self):
        is_valid, warnings = validate_date("not-a-date")
        assert not is_valid

    def test_future_date(self):
        is_valid, warnings = validate_date("2099-12-31")
        assert not is_valid

    def test_old_date_warns(self):
        is_valid, warnings = validate_date("2020-01-01")
        assert is_valid
        assert any("6개월" in w for w in warnings)
