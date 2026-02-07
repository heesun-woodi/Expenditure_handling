from __future__ import annotations

import logging
import os
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from config import TEMPLATE_SPREADSHEET_ID
from models import ExpenseReport

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# 템플릿 시트 이름
TEMPLATE_SHEET_NAME = "지출결의서_템플릿"
RECEIPT_SHEET_NAME = "영수증 첨부"

# 하드코딩된 기본 셀 매핑 (동적 탐색 실패 시 폴백)
DEFAULT_CELL_MAPPING = {
    "project_name_cell": "F1",
    "user_name_cell": "L1",
    "created_date_cell": "N1",
    "total_amount_cell": "F2",
    "purpose_cell": "F3",
    "data_start_row": 5,
    "description_col": 5,  # F (0-indexed)
    "quantity_col": 11,     # L
    "subtotal_col": 14,     # O (소계는 중간에 공급가액+세액 뒤)
    "supply_col": 17,       # R (공급가액)
    "tax_col": 18,          # S (세액)
}


TOKEN_FILE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "credentials", "token.json"
)


def get_google_services():
    """Google Sheets 및 Drive 서비스 객체 생성 (OAuth2 토큰 사용)"""
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    sheets_service = build("sheets", "v4", credentials=creds)
    drive_service = build("drive", "v3", credentials=creds)
    return sheets_service, drive_service


def copy_template(
    drive_service,
    new_title: str,
    template_id: str = TEMPLATE_SPREADSHEET_ID,
    parent_folder_id: Optional[str] = None,
) -> str:
    """
    템플릿 스프레드시트를 복사하여 새 파일 생성

    Returns:
        새로 생성된 스프레드시트 ID
    """
    body = {"name": new_title}
    if parent_folder_id:
        body["parents"] = [parent_folder_id]

    copied = drive_service.files().copy(
        fileId=template_id,
        body=body,
    ).execute()

    spreadsheet_id = copied["id"]
    logger.info(f"템플릿 복사 완료: {new_title} (ID: {spreadsheet_id})")
    return spreadsheet_id


def discover_cell_mapping(sheets_service, spreadsheet_id: str) -> dict:
    """
    시트 데이터를 읽어 키워드 기반으로 셀 위치를 동적 탐색

    전체 시트를 읽고 키워드를 찾아 입력 셀 위치를 결정합니다.
    실패 시 DEFAULT_CELL_MAPPING을 반환합니다.
    """
    try:
        result = sheets_service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"{TEMPLATE_SHEET_NAME}!A1:Z50",
        ).execute()
        rows = result.get("values", [])

        if not rows:
            logger.warning("시트 데이터가 비어있습니다. 기본 매핑 사용.")
            return DEFAULT_CELL_MAPPING.copy()

        mapping = {}

        for row_idx, row in enumerate(rows):
            for col_idx, cell in enumerate(row):
                text = str(cell).strip().replace(" ", "")

                if "프로젝트" in text and "명" in text:
                    # 같은 행에서 값이 있는 다음 셀 또는 빈 셀을 찾음
                    input_col = _find_input_col(row, col_idx)
                    mapping["project_name_cell"] = _cell_ref(row_idx, input_col)

                elif "작성일자" in text:
                    input_col = _find_input_col(row, col_idx)
                    mapping["created_date_cell"] = _cell_ref(row_idx, input_col)

                elif "사용자" == text or "사용자" in text and len(text) <= 4:
                    input_col = _find_input_col(row, col_idx)
                    mapping["user_name_cell"] = _cell_ref(row_idx, input_col)

                elif "지출금액" in text:
                    input_col = _find_input_col(row, col_idx)
                    mapping["total_amount_cell"] = _cell_ref(row_idx, input_col)

                elif "사용목적" in text:
                    input_col = _find_input_col(row, col_idx)
                    mapping["purpose_cell"] = _cell_ref(row_idx, input_col)

                elif "적" in text and "요" in text and len(text) <= 4:
                    mapping["data_start_row"] = row_idx + 2  # 헤더 다음 행 (1-indexed)
                    mapping.update(_identify_data_columns(row_idx, row))

                elif "합계금액" in text:
                    mapping["total_row"] = row_idx + 1  # 1-indexed

                elif "작성자" in text or "신청자" in text:
                    input_col = _find_input_col(row, col_idx)
                    mapping["bottom_author_cell"] = _cell_ref(row_idx, input_col)

                elif "년" in text and "월" in text and "일" in text:
                    # 하단 날짜: "2024 년  5 월  27 일" 형태의 단일 셀
                    mapping["bottom_date_cell"] = _cell_ref(row_idx, col_idx)

        # 필수 키가 모두 있는지 확인
        required_keys = ["data_start_row", "description_col"]
        if all(k in mapping for k in required_keys):
            logger.info(f"동적 셀 매핑 성공: {mapping}")
            return mapping
        else:
            missing = [k for k in required_keys if k not in mapping]
            logger.warning(f"동적 매핑 불완전 (누락: {missing}). 기본 매핑 사용.")
            return DEFAULT_CELL_MAPPING.copy()

    except Exception as e:
        logger.error(f"셀 매핑 탐색 실패: {e}. 기본 매핑 사용.")
        return DEFAULT_CELL_MAPPING.copy()


def fill_expense_data(
    sheets_service,
    spreadsheet_id: str,
    expense_report: ExpenseReport,
    cell_mapping: dict,
) -> None:
    """지출결의서 데이터 입력"""
    data = []

    # 헤더 정보 입력
    header_fields = {
        "project_name_cell": expense_report.project_name,
        "user_name_cell": expense_report.user_name,
        "created_date_cell": expense_report.created_date,
        "total_amount_cell": expense_report.total_amount,
        "purpose_cell": expense_report.purpose,
    }

    for key, value in header_fields.items():
        cell = cell_mapping.get(key)
        if cell:
            data.append({
                "range": f"{TEMPLATE_SHEET_NAME}!{cell}",
                "values": [[value]],
            })

    # 상세 내역 입력
    start_row = cell_mapping.get("data_start_row", 5)
    desc_col = cell_mapping.get("description_col", 5)

    for idx, item in enumerate(expense_report.line_items):
        row = start_row + idx

        # 적요
        data.append({
            "range": f"{TEMPLATE_SHEET_NAME}!{_col_letter(desc_col)}{row}",
            "values": [[item.description]],
        })

        # 수량
        qty_col = cell_mapping.get("quantity_col")
        if qty_col is not None:
            data.append({
                "range": f"{TEMPLATE_SHEET_NAME}!{_col_letter(qty_col)}{row}",
                "values": [[item.quantity]],
            })

        # 소계 (합계금액)
        subtotal_col = cell_mapping.get("subtotal_col")
        if subtotal_col is not None:
            data.append({
                "range": f"{TEMPLATE_SHEET_NAME}!{_col_letter(subtotal_col)}{row}",
                "values": [[item.subtotal]],
            })

        # 공급가액
        supply_col = cell_mapping.get("supply_col")
        if supply_col is not None:
            data.append({
                "range": f"{TEMPLATE_SHEET_NAME}!{_col_letter(supply_col)}{row}",
                "values": [[item.supply_value]],
            })

        # 세액
        tax_col = cell_mapping.get("tax_col")
        if tax_col is not None:
            data.append({
                "range": f"{TEMPLATE_SHEET_NAME}!{_col_letter(tax_col)}{row}",
                "values": [[item.tax_amount]],
            })

    # 합계 행
    total_row = cell_mapping.get("total_row")
    if total_row and subtotal_col is not None:
        data.append({
            "range": f"{TEMPLATE_SHEET_NAME}!{_col_letter(subtotal_col)}{total_row}",
            "values": [[expense_report.total_amount]],
        })

    # 하단 날짜 입력 ("2026 년   2  월   7  일" 형태)
    from datetime import datetime
    now = datetime.now()
    if cell_mapping.get("bottom_date_cell"):
        date_str = f"{now.year} 년   {now.month}  월   {now.day}  일"
        data.append({
            "range": f"{TEMPLATE_SHEET_NAME}!{cell_mapping['bottom_date_cell']}",
            "values": [[date_str]],
        })

    # 하단 작성자 입력
    if cell_mapping.get("bottom_author_cell"):
        data.append({
            "range": f"{TEMPLATE_SHEET_NAME}!{cell_mapping['bottom_author_cell']}",
            "values": [[expense_report.user_name]],
        })

    # batchUpdate로 한 번에 입력
    if data:
        sheets_service.spreadsheets().values().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "valueInputOption": "USER_ENTERED",
                "data": data,
            },
        ).execute()
        logger.info(f"데이터 입력 완료: {len(data)}개 셀 업데이트")

        # 입력한 셀의 글씨 색상을 검정색으로 설정
        sheet_id = _get_sheet_id(sheets_service, spreadsheet_id, TEMPLATE_SHEET_NAME)
        if sheet_id is not None:
            format_requests = []
            for entry in data:
                cell_ref = entry["range"].split("!")[-1]
                row_idx, col_idx = _parse_cell_ref(cell_ref)
                format_requests.append({
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": row_idx,
                            "endRowIndex": row_idx + 1,
                            "startColumnIndex": col_idx,
                            "endColumnIndex": col_idx + 1,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "textFormat": {
                                    "foregroundColor": {
                                        "red": 0, "green": 0, "blue": 0,
                                    }
                                }
                            }
                        },
                        "fields": "userEnteredFormat.textFormat.foregroundColor",
                    }
                })
            sheets_service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": format_requests},
            ).execute()
            logger.info("글씨 색상 검정색으로 설정 완료")


def attach_receipt_images(
    sheets_service,
    drive_service,
    spreadsheet_id: str,
    image_paths: list[str],
) -> None:
    """
    영수증 이미지를 '영수증 첨부' 시트에 IMAGE() 함수로 삽입

    Google Drive에 이미지 업로드 후 IMAGE() 함수로 셀에 표시
    """
    if not image_paths:
        return

    data = []

    for idx, image_path in enumerate(image_paths):
        if not os.path.exists(image_path):
            logger.warning(f"이미지 파일 없음: {image_path}")
            continue

        # Google Drive에 업로드
        file_metadata = {
            "name": f"receipt_{idx+1}.jpg",
        }
        media = MediaFileUpload(
            image_path,
            mimetype="image/jpeg",
            resumable=True,
        )
        uploaded = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id",
        ).execute()
        file_id = uploaded["id"]

        # 누구나 읽을 수 있도록 공개 권한
        drive_service.permissions().create(
            fileId=file_id,
            body={"type": "anyone", "role": "reader"},
        ).execute()

        image_url = f"https://drive.google.com/uc?id={file_id}"
        logger.info(f"이미지 업로드 완료: {file_id}")

        # 연속 행에 배치 (B2, B3, B4, ...)
        row = 2 + idx
        data.append({
            "range": f"{RECEIPT_SHEET_NAME}!B{row}",
            "values": [[f'=IMAGE("{image_url}")']],
        })

    if data:
        sheets_service.spreadsheets().values().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "valueInputOption": "USER_ENTERED",
                "data": data,
            },
        ).execute()

        # 셀 크기 조정: B열 너비 364px, 이미지 행 높이 350px
        sheet_id = _get_sheet_id(sheets_service, spreadsheet_id, RECEIPT_SHEET_NAME)
        if sheet_id is not None:
            size_requests = [
                {
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "COLUMNS",
                            "startIndex": 1,
                            "endIndex": 2,
                        },
                        "properties": {"pixelSize": 364},
                        "fields": "pixelSize",
                    }
                },
                {
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "ROWS",
                            "startIndex": 1,
                            "endIndex": 1 + len(data),
                        },
                        "properties": {"pixelSize": 350},
                        "fields": "pixelSize",
                    }
                },
            ]
            sheets_service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": size_requests},
            ).execute()

        logger.info(f"영수증 이미지 {len(data)}장 IMAGE() 함수로 삽입 완료")


def share_spreadsheet(
    drive_service,
    spreadsheet_id: str,
    email_addresses: list[str],
    role: str = "writer",
) -> None:
    """생성된 스프레드시트에 편집 권한 부여"""
    for email in email_addresses:
        try:
            drive_service.permissions().create(
                fileId=spreadsheet_id,
                body={
                    "type": "user",
                    "role": role,
                    "emailAddress": email,
                },
                sendNotificationEmail=False,
            ).execute()
            logger.info(f"공유 권한 부여: {email} ({role})")
        except Exception as e:
            logger.error(f"공유 권한 부여 실패 ({email}): {e}")


def calculate_tax(total_amount: int) -> tuple[int, int]:
    """
    부가세 포함 금액을 공급가액과 세액으로 분리

    Returns:
        (supply_value, tax_amount)
    """
    supply_value = round(total_amount / 1.1)
    tax_amount = total_amount - supply_value
    return supply_value, tax_amount


# --- 헬퍼 함수 ---

def _find_input_col(row: list, label_col: int) -> int:
    """레이블 셀 이후의 입력 가능 셀 위치 결정"""
    # 레이블 바로 다음의 비어있지 않은 셀, 또는 다음 셀을 반환
    for col in range(label_col + 1, len(row)):
        if row[col].strip():
            return col
    # 행 끝까지 비어있으면 레이블 다음 셀
    return label_col + 1


def _identify_data_columns(header_row_idx: int, row: list) -> dict:
    """헤더 행에서 데이터 컬럼 위치 식별"""
    cols = {}
    for col_idx, cell in enumerate(row):
        text = str(cell).strip().replace(" ", "")
        if "적요" in text:
            cols["description_col"] = col_idx
        elif "수량" in text:
            cols["quantity_col"] = col_idx
        elif "공급가액" in text:
            cols["supply_col"] = col_idx
        elif "세액" in text:
            cols["tax_col"] = col_idx
        elif "소계" in text:
            cols["subtotal_col"] = col_idx
    return cols


def _parse_cell_ref(cell_ref: str) -> tuple:
    """A1 형식 셀 참조를 (row_index, col_index) 0-indexed로 변환"""
    col_str = ""
    row_str = ""
    for ch in cell_ref:
        if ch.isalpha():
            col_str += ch
        else:
            row_str += ch
    col_idx = 0
    for ch in col_str.upper():
        col_idx = col_idx * 26 + (ord(ch) - ord("A") + 1)
    col_idx -= 1
    row_idx = int(row_str) - 1
    return row_idx, col_idx


def _cell_ref(row_idx: int, col_idx: int) -> str:
    """0-indexed row, col을 A1 형식 셀 참조로 변환"""
    return f"{_col_letter(col_idx)}{row_idx + 1}"


def _col_letter(col_idx: int) -> str:
    """0-indexed 컬럼 인덱스를 A, B, ..., Z, AA, AB, ... 형식으로 변환"""
    result = ""
    while col_idx >= 0:
        result = chr(col_idx % 26 + ord("A")) + result
        col_idx = col_idx // 26 - 1
    return result


def _get_sheet_id(sheets_service, spreadsheet_id: str, sheet_name: str) -> Optional[int]:
    """시트 이름으로 시트 ID 조회"""
    try:
        metadata = sheets_service.spreadsheets().get(
            spreadsheetId=spreadsheet_id,
        ).execute()
        for sheet in metadata.get("sheets", []):
            if sheet["properties"]["title"] == sheet_name:
                return sheet["properties"]["sheetId"]
    except Exception as e:
        logger.error(f"시트 ID 조회 실패: {e}")
    return None
