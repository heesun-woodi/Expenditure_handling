from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from config import TEMPLATE_SPREADSHEET_ID, PARENT_FOLDER_ID, USER_LIST_SPREADSHEET_ID, PROJECT_COST_SPREADSHEET_ID, EXPENSE_CATEGORIES, PAUL_EMAIL, FINANCE_MANAGER_EMAIL, COMPANY_DOMAIN
from models import ExpenseReport

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# 템플릿 시트 이름
TEMPLATE_SHEET_NAME = "지출결의서_템플릿"
RECEIPT_SHEET_NAME = "영수증 첨부"

# 새 템플릿 기준 기본 셀 매핑 (동적 탐색 실패 시 폴백)
DEFAULT_CELL_MAPPING = {
    "doc_number_cell": "F4",
    "created_date_cell": "S4",
    "project_name_cell": "F5",
    "user_name_cell": "N5",
    "total_amount_cell": "F6",
    "purpose_cell": "F7",
    "data_start_row": 9,
    "date_col": 5,          # F (0-indexed)
    "category_col": 7,      # H
    "purpose_col": 9,        # J
    "quantity_col": 11,      # L
    "unit_price_col": 14,    # O
    "supply_col": 17,        # R
    "tax_col": 19,           # T
    "subtotal_col": 20,      # U
    "total_row": 18,
    "bottom_author_cell": "S24",
    "bottom_date_cell": "A22",
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
    """템플릿 스프레드시트를 복사하여 새 파일 생성"""
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


def get_next_doc_number(drive_service, user_display_name: str) -> str:
    """
    Google Drive 폴더에서 같은 사용자의 기존 지출결의서 수를 카운트하여 문서번호 생성

    형식: "연-닉네임-순번" (예: "26-woodi-1")
    """
    year_short = datetime.now().year % 100
    nickname = user_display_name.lower()

    count = 0
    if PARENT_FOLDER_ID:
        try:
            query = (
                f"'{PARENT_FOLDER_ID}' in parents and trashed = false "
                f"and name contains '개인카드지출결의서_{user_display_name}'"
            )
            result = drive_service.files().list(
                q=query,
                fields="files(id)",
                pageSize=1000,
            ).execute()
            count = len(result.get("files", []))
        except Exception as e:
            logger.error(f"Drive 파일 카운트 실패: {e}")

    seq = count + 1
    return f"{year_short}-{nickname}-{seq}"


def discover_cell_mapping(sheets_service, spreadsheet_id: str) -> dict:
    """시트 데이터를 읽어 키워드 기반으로 셀 위치를 동적 탐색

    헤더 필드(문서번호, 프로젝트명 등)는 기본 매핑을 사용하고,
    데이터 컬럼(일자, 항목, 목적 등)만 동적으로 탐색합니다.
    """
    # 헤더 필드는 고정 위치 사용 (입력 셀이 비어있으면 동적 탐색이 잘못된 셀을 찾음)
    mapping = DEFAULT_CELL_MAPPING.copy()

    try:
        result = sheets_service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"{TEMPLATE_SHEET_NAME}!A1:Z50",
        ).execute()
        rows = result.get("values", [])

        if not rows:
            logger.warning("시트 데이터가 비어있습니다. 기본 매핑 사용.")
            return mapping

        for row_idx, row in enumerate(rows):
            for col_idx, cell in enumerate(row):
                text = str(cell).strip().replace(" ", "")

                if "내" in text and "역" in text and len(text) <= 4:
                    # "내    역" 헤더 행 감지 → 데이터 컬럼 동적 탐색
                    mapping["data_start_row"] = row_idx + 2  # 헤더 다음 행 (1-indexed)
                    mapping.update(_identify_data_columns(row_idx, row))

                elif "합계금액" in text:
                    mapping["total_row"] = row_idx + 1  # 1-indexed

                elif "년" in text and "월" in text and "일" in text:
                    mapping["bottom_date_cell"] = _cell_ref(row_idx, col_idx)

        logger.info(f"셀 매핑 완료: {mapping}")
        return mapping

    except Exception as e:
        logger.error(f"셀 매핑 탐색 실패: {e}. 기본 매핑 사용.")
        return mapping


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
        "doc_number_cell": expense_report.doc_number,
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
    start_row = cell_mapping.get("data_start_row", 9)

    for idx, item in enumerate(expense_report.line_items):
        row = start_row + idx

        # 일자
        date_col = cell_mapping.get("date_col")
        if date_col is not None:
            data.append({
                "range": f"{TEMPLATE_SHEET_NAME}!{_col_letter(date_col)}{row}",
                "values": [[item.date]],
            })

        # 항목
        category_col = cell_mapping.get("category_col")
        if category_col is not None:
            data.append({
                "range": f"{TEMPLATE_SHEET_NAME}!{_col_letter(category_col)}{row}",
                "values": [[item.category]],
            })

        # 목적
        purpose_col = cell_mapping.get("purpose_col")
        if purpose_col is not None:
            data.append({
                "range": f"{TEMPLATE_SHEET_NAME}!{_col_letter(purpose_col)}{row}",
                "values": [[item.purpose]],
            })

        # 수량
        qty_col = cell_mapping.get("quantity_col")
        if qty_col is not None:
            data.append({
                "range": f"{TEMPLATE_SHEET_NAME}!{_col_letter(qty_col)}{row}",
                "values": [[item.quantity]],
            })

        # 단가
        unit_price_col = cell_mapping.get("unit_price_col")
        if unit_price_col is not None:
            data.append({
                "range": f"{TEMPLATE_SHEET_NAME}!{_col_letter(unit_price_col)}{row}",
                "values": [[item.unit_price]],
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

        # 소계
        subtotal_col = cell_mapping.get("subtotal_col")
        if subtotal_col is not None:
            data.append({
                "range": f"{TEMPLATE_SHEET_NAME}!{_col_letter(subtotal_col)}{row}",
                "values": [[item.subtotal]],
            })

    # 합계 행 (합계금액 값은 단가(O) 컬럼 위치에 입력)
    total_row = cell_mapping.get("total_row")
    if total_row:
        total_col = cell_mapping.get("unit_price_col")
        if total_col is not None:
            data.append({
                "range": f"{TEMPLATE_SHEET_NAME}!{_col_letter(total_col)}{total_row}",
                "values": [[expense_report.total_amount]],
            })

    # 하단 날짜 입력
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
        sheet_id = _get_sheet_id(sheets_service, spreadsheet_id, TEMPLATE_SHEET_NAME)

        # 기존 셀 병합 정보 저장 (데이터 입력 시 깨질 수 있음)
        original_merges = []
        if sheet_id is not None:
            original_merges = _get_sheet_merges(sheets_service, spreadsheet_id, sheet_id)

        sheets_service.spreadsheets().values().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "valueInputOption": "USER_ENTERED",
                "data": data,
            },
        ).execute()
        logger.info(f"데이터 입력 완료: {len(data)}개 셀 업데이트")

        # 입력한 셀의 글씨 색상을 검정색으로 설정
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

            # 데이터 입력으로 깨진 셀 병합 복원 및 숫자 셀 정렬 설정
            _restore_merges_and_alignment(
                sheets_service, spreadsheet_id, sheet_id,
                original_merges, data, cell_mapping,
            )

            # 항목(category) 셀에 드롭다운 데이터 유효성 검사 복원
            category_col = cell_mapping.get("category_col")
            if category_col is not None:
                start_row = cell_mapping.get("data_start_row", 9)
                num_items = len(expense_report.line_items)
                _restore_category_validation(
                    sheets_service, spreadsheet_id, sheet_id,
                    category_col, start_row, num_items,
                )


def attach_receipt_images(
    sheets_service,
    drive_service,
    spreadsheet_id: str,
    image_paths: list[str],
) -> None:
    """영수증 이미지를 '영수증 첨부' 시트에 IMAGE() 함수로 삽입"""
    if not image_paths:
        return

    data = []

    for idx, image_path in enumerate(image_paths):
        if not os.path.exists(image_path):
            logger.warning(f"이미지 파일 없음: {image_path}")
            continue

        file_metadata = {"name": f"receipt_{idx+1}.jpg"}
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

        drive_service.permissions().create(
            fileId=file_id,
            body={"type": "anyone", "role": "reader"},
        ).execute()

        image_url = f"https://drive.google.com/uc?id={file_id}"
        logger.info(f"이미지 업로드 완료: {file_id}")

        row = 2 + idx
        data.append({
            "range": f"{RECEIPT_SHEET_NAME}!B{row}",
            "values": [[f'=IMAGE("{image_url}")']],
        })

    if data:
        # 기존 템플릿 내용 클리어 후 삽입
        sheets_service.spreadsheets().values().clear(
            spreadsheetId=spreadsheet_id,
            range=f"{RECEIPT_SHEET_NAME}!B2:B100",
        ).execute()

        sheets_service.spreadsheets().values().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "valueInputOption": "USER_ENTERED",
                "data": data,
            },
        ).execute()

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


def share_with_domain(drive_service, spreadsheet_id: str) -> None:
    """회사 도메인(mfitlab.com) 전체에 뷰어 권한 부여"""
    try:
        drive_service.permissions().create(
            fileId=spreadsheet_id,
            body={
                "type": "domain",
                "role": "reader",
                "domain": COMPANY_DOMAIN,
            },
            sendNotificationEmail=False,
        ).execute()
        logger.info(f"도메인 뷰어 공유 완료: {COMPANY_DOMAIN}")
    except Exception as e:
        logger.error(f"도메인 공유 실패 ({COMPANY_DOMAIN}): {e}")


def setup_spreadsheet_permissions(drive_service, spreadsheet_id: str) -> None:
    """파일 생성 후 기본 권한 설정: 폴·은미님 편집자 + 도메인 뷰어"""
    editors = [email for email in [PAUL_EMAIL, FINANCE_MANAGER_EMAIL] if email]
    if editors:
        share_spreadsheet(drive_service, spreadsheet_id, editors, role="writer")
    share_with_domain(drive_service, spreadsheet_id)


def lookup_real_name(sheets_service, nickname: str) -> str:
    """슬랙 닉네임으로 실명 조회 (구글 스프레드시트 Summary 시트 E열→G열 매핑)"""
    try:
        # 시트 이름에 숨겨진 문자(\x08)가 포함되어 있어 동적으로 조회
        sheet_title = _find_sheet_title(sheets_service, USER_LIST_SPREADSHEET_ID, 1305441652)
        if not sheet_title:
            sheet_title = "Summary"

        result = sheets_service.spreadsheets().values().get(
            spreadsheetId=USER_LIST_SPREADSHEET_ID,
            range=f"'{sheet_title}'!E:G",
        ).execute()
        rows = result.get("values", [])

        for row in rows:
            if len(row) >= 3 and row[0].strip().lower() == nickname.lower():
                real_name = row[2].strip()
                if real_name:
                    logger.info(f"실명 조회 성공: {nickname} → {real_name}")
                    return real_name

        logger.warning(f"실명 조회 결과 없음: {nickname}")
    except Exception as e:
        logger.error(f"실명 조회 실패: {e}")

    return nickname


def read_expense_data(
    sheets_service,
    spreadsheet_id: str,
    cell_mapping: dict,
    num_items: int,
) -> list[dict]:
    """스프레드시트에서 현재 데이터 행을 읽어 반환 (사용자 수정 반영)"""
    start_row = cell_mapping.get("data_start_row", 9)
    end_row = start_row + num_items - 1

    try:
        result = sheets_service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"{TEMPLATE_SHEET_NAME}!A{start_row}:U{end_row}",
        ).execute()
        rows = result.get("values", [])

        items = []
        for row in rows:
            # 셀을 0-indexed 컬럼으로 읽기 (A=0)
            def cell(col_key):
                col = cell_mapping.get(col_key)
                if col is not None and col < len(row):
                    return str(row[col]).strip()
                return ""

            items.append({
                "category": cell("category_col"),
                "purpose": cell("purpose_col"),
                "date": cell("date_col"),
                "subtotal": cell("subtotal_col"),
            })
        return items

    except Exception as e:
        logger.error(f"스프레드시트 데이터 읽기 실패: {e}")
        return []


def append_to_project_cost_sheet(
    sheets_service,
    expense_report: ExpenseReport,
    user_display_name: str,
    current_items: list[dict],
    channel_id: str = "",
    thread_ts: str = "",
    user_id: str = "",
) -> None:
    """프로젝트 비용 내역서에 비용 항목 추가"""
    rows = []
    for item in current_items:
        purpose = item.get("purpose", "")
        # 목적에서 "(닉네임)" 제거
        if "\n(" in purpose:
            purpose = purpose.split("\n(")[0]
        rows.append([
            expense_report.created_date,      # A: 작성일자
            user_display_name,                 # B: 사용자
            expense_report.doc_number,         # C: 문서번호
            expense_report.project_name,       # D: 프로젝트명
            item.get("category", ""),          # E: 항목
            purpose,                           # F: 목적
            item.get("date", ""),              # G: 일자
            item.get("subtotal", ""),          # H: 소계
            "",                                # I: 비고
            "",                                # J: 입금일자
            channel_id,                        # K: slack_channel_id
            thread_ts,                         # L: slack_thread_ts
            user_id,                           # M: slack_user_id
            "",                                # N: 알림발송
        ])

    sheets_service.spreadsheets().values().append(
        spreadsheetId=PROJECT_COST_SPREADSHEET_ID,
        range="A1:N1",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": rows},
    ).execute()
    logger.info(f"프로젝트 비용 내역서에 {len(rows)}건 기록 완료")


def calculate_tax(total_amount: int) -> tuple:
    """부가세 포함 금액을 공급가액과 세액으로 분리"""
    supply_value = round(total_amount / 1.1)
    tax_amount = total_amount - supply_value
    return supply_value, tax_amount


# --- 헬퍼 함수 ---

def _find_sheet_title(sheets_service, spreadsheet_id: str, target_gid: int) -> Optional[str]:
    """sheetId(gid)로 시트 제목 조회"""
    try:
        metadata = sheets_service.spreadsheets().get(
            spreadsheetId=spreadsheet_id,
            fields="sheets.properties.title,sheets.properties.sheetId",
        ).execute()
        for sheet in metadata.get("sheets", []):
            if sheet["properties"]["sheetId"] == target_gid:
                return sheet["properties"]["title"]
    except Exception as e:
        logger.error(f"시트 제목 조회 실패: {e}")
    return None


def _find_input_col(row: list, label_col: int) -> int:
    """레이블 셀 이후의 입력 가능 셀 위치 결정"""
    for col in range(label_col + 1, len(row)):
        if row[col].strip():
            return col
    return label_col + 1


def _identify_data_columns(header_row_idx: int, row: list) -> dict:
    """헤더 행에서 데이터 컬럼 위치 식별"""
    cols = {}
    for col_idx, cell in enumerate(row):
        text = str(cell).strip().replace(" ", "")
        if "일자" in text:
            cols["date_col"] = col_idx
        elif "항목" in text:
            cols["category_col"] = col_idx
        elif "목적" in text:
            cols["purpose_col"] = col_idx
        elif "수량" in text:
            cols["quantity_col"] = col_idx
        elif "단가" in text:
            cols["unit_price_col"] = col_idx
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


def _get_sheet_merges(sheets_service, spreadsheet_id: str, sheet_id: int) -> list:
    """시트의 셀 병합 정보를 반환"""
    try:
        metadata = sheets_service.spreadsheets().get(
            spreadsheetId=spreadsheet_id,
            fields="sheets.merges,sheets.properties.sheetId",
        ).execute()
        for sheet in metadata.get("sheets", []):
            if sheet.get("properties", {}).get("sheetId") == sheet_id:
                return sheet.get("merges", [])
    except Exception as e:
        logger.error(f"병합 정보 조회 실패: {e}")
    return []


def _restore_merges_and_alignment(
    sheets_service,
    spreadsheet_id: str,
    sheet_id: int,
    original_merges: list,
    data: list,
    cell_mapping: dict,
) -> None:
    """데이터 입력으로 깨진 셀 병합 및 정렬을 복원"""
    restore_requests = []

    written_cells = set()
    for entry in data:
        cell_ref = entry["range"].split("!")[-1]
        row_idx, col_idx = _parse_cell_ref(cell_ref)
        written_cells.add((row_idx, col_idx))

    for merge in original_merges:
        for row_idx, col_idx in written_cells:
            if (merge["startRowIndex"] <= row_idx < merge["endRowIndex"]
                    and merge["startColumnIndex"] <= col_idx < merge["endColumnIndex"]):
                restore_requests.append({
                    "mergeCells": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": merge["startRowIndex"],
                            "endRowIndex": merge["endRowIndex"],
                            "startColumnIndex": merge["startColumnIndex"],
                            "endColumnIndex": merge["endColumnIndex"],
                        },
                        "mergeType": "MERGE_ALL",
                    }
                })
                break

    number_cols = set()
    for key in ("subtotal_col", "supply_col", "tax_col", "unit_price_col"):
        col = cell_mapping.get(key)
        if col is not None:
            number_cols.add(col)

    for row_idx, col_idx in written_cells:
        if col_idx in number_cols:
            restore_requests.append({
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
                            "horizontalAlignment": "RIGHT",
                        }
                    },
                    "fields": "userEnteredFormat.horizontalAlignment",
                }
            })

    if restore_requests:
        sheets_service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": restore_requests},
        ).execute()
        logger.info(f"셀 병합 및 정렬 복원 완료: {len(restore_requests)}개 요청")


def _restore_category_validation(
    sheets_service,
    spreadsheet_id: str,
    sheet_id: int,
    category_col: int,
    start_row: int,
    num_items: int,
) -> None:
    """항목(category) 셀에 드롭다운 데이터 유효성 검사를 설정"""
    try:
        validation_values = [{"userEnteredValue": cat} for cat in EXPENSE_CATEGORIES]
        requests = [{
            "setDataValidation": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": start_row - 1,  # 0-indexed
                    "endRowIndex": start_row - 1 + num_items,
                    "startColumnIndex": category_col,
                    "endColumnIndex": category_col + 1,
                },
                "rule": {
                    "condition": {
                        "type": "ONE_OF_LIST",
                        "values": validation_values,
                    },
                    "strict": True,
                    "showCustomUi": True,
                },
            }
        }]
        sheets_service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": requests},
        ).execute()
        logger.info("항목 드롭다운 데이터 유효성 검사 설정 완료")
    except Exception as e:
        logger.error(f"데이터 유효성 검사 설정 실패: {e}")


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
