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
    transaction_time: Optional[str] = None


@dataclass
class ExpenseLineItem:
    description: str    # "{품목} ({YY.MM.DD} / {사용자})"
    quantity: int        # 기본 1
    subtotal: int        # 소계 (total_amount)
    supply_value: int    # 공급가액 = round(subtotal / 1.1)
    tax_amount: int      # 세액 = subtotal - supply_value


@dataclass
class ExpenseReport:
    project_name: str
    user_name: str
    created_date: str          # "YY.MM.DD"
    purpose: str
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
    sheets_url: Optional[str] = None
    expense_report: Optional[ExpenseReport] = None
