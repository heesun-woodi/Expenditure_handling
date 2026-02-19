from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ReceiptItem:
    name: str
    quantity: int
    price: int
    amount: int


@dataclass
class ReceiptData:
    merchant_name: str
    transaction_date: Optional[str]  # "YYYY-MM-DD"
    total_amount: int
    items: list[ReceiptItem] = field(default_factory=list)
    payment_method: Optional[str] = None
    summary_inference: Optional[str] = None
    expense_category: Optional[str] = None
    transaction_time: Optional[str] = None


@dataclass
class ExpenseLineItem:
    date: str               # "YY.MM.DD"
    category: str           # 항목 (회의비, 점심식비 등)
    purpose: str            # "설명\n(닉네임)"
    quantity: int            # 기본 1
    unit_price: int          # 단가 (= subtotal when quantity is 1)
    supply_value: int        # 공급가액 = round(subtotal / 1.1)
    tax_amount: int          # 세액 = subtotal - supply_value
    subtotal: int            # 소계 (total_amount)


@dataclass
class ExpenseReport:
    project_name: str
    user_name: str
    created_date: str          # "YY.MM.DD"
    purpose: str               # AI가 요약한 사용목적
    doc_number: str            # "연-닉네임-순번"
    line_items: list[ExpenseLineItem]
    total_amount: int
    expense_months: list[int]  # 영수증에 포함된 월 목록
    expense_year: int
    image_paths: list[str] = field(default_factory=list)


@dataclass
class ProcessingContext:
    channel_id: str
    user_id: str
    thread_ts: str
    file_ids: list[str]
    project_name: str
    user_display_name: str
    user_real_name: Optional[str] = None
    sheets_url: Optional[str] = None
    expense_report: Optional[ExpenseReport] = None
