from __future__ import annotations

import logging
import os
import threading
from collections import Counter
from datetime import datetime

import requests
from slack_bolt import App
from slack_sdk import WebClient

from config import (
    EXPENSE_SUBMIT_CHANNEL_ID,
    FINANCE_MANAGER_USER_ID,
    CFO_USER_ID,
    MAX_RECEIPT_COUNT,
    PARENT_FOLDER_ID,
    PROJECT_COST_SPREADSHEET_ID,
    SUPPORTED_IMAGE_TYPES,
    SUPPORTED_PDF_TYPES,
    TEMP_DIR,
)
from models import (
    ExpenseLineItem,
    ExpenseReport,
    ProcessingContext,
)
from handlers.ai_handler import analyze_receipts_batch
from handlers.dungeon_api import get_project_name
from handlers.feedback import collect_feedback
from handlers.sheets_handler import (
    append_to_project_cost_sheet,
    attach_receipt_images,
    calculate_tax,
    copy_template,
    discover_cell_mapping,
    fill_expense_data,
    get_google_services,
    get_next_doc_number,
    lookup_real_name,
    read_expense_data,
    setup_spreadsheet_permissions,
    share_spreadsheet,
    update_confirmation_date,
    update_deposit_date,
)
from utils.image_processor import (
    cleanup_temp_files,
    convert_pdf_pages_to_jpg,
    get_jpg_path_for_sheets,
    process_image,
    process_pdf,
)
from utils.validators import validate_receipt_data

logger = logging.getLogger(__name__)

# 진행 중인 처리 요청 추적 (thread_ts -> ProcessingContext)
_active_threads: dict[str, ProcessingContext] = {}

# 제출된 메시지 추적 (submit_channel_message_ts -> (origin_channel_id, origin_thread_ts))
_submitted_messages: dict[str, tuple[str, str]] = {}


def register_handlers(app: App) -> None:
    """모든 Slack 이벤트 핸들러를 앱에 등록"""

    @app.event("app_mention")
    def handle_app_mention(event, say, client):
        _on_app_mention(event, say, client)

    @app.event("message")
    def handle_message(event, client):
        _on_thread_message(event, client)

    @app.action("expense_submit")
    def handle_submit_action(ack, body, client):
        ack()
        _on_submit_button(body, client)

    @app.action("expense_deposit_complete")
    def handle_deposit_complete(ack, body, client):
        ack()
        _on_deposit_complete(body, client)

    @app.view("expense_deposit_date_modal")
    def handle_deposit_date_submit(ack, body, client, view):
        ack()
        threading.Thread(
            target=_on_deposit_date_submit,
            args=(body, client, view),
            daemon=True,
        ).start()

    @app.event("reaction_added")
    def handle_reaction(event, client):
        _on_reaction_added(event, client)


def _on_app_mention(event: dict, say, client: WebClient) -> None:
    """앱 멘션 이벤트 처리"""
    channel_id = event["channel"]
    user_id = event["user"]
    thread_ts = event.get("ts", "")

    # 이미지 파일 추출
    files = event.get("files", [])
    image_files = [
        f for f in files
        if f.get("mimetype", "") in SUPPORTED_IMAGE_TYPES | SUPPORTED_PDF_TYPES
    ]

    if not image_files:
        say(
            text="영수증 이미지를 함께 첨부해주세요. (JPG, PNG, HEIC 지원)",
            thread_ts=thread_ts,
        )
        return

    if len(image_files) > MAX_RECEIPT_COUNT:
        say(
            text=f"한 번에 최대 {MAX_RECEIPT_COUNT}장까지 처리 가능합니다. ({len(image_files)}장 첨부됨)",
            thread_ts=thread_ts,
        )
        return

    # "처리 중" 즉시 응답
    say(
        text=f"지출결의서를 작성 중입니다... ({len(image_files)}장의 영수증 처리 중)",
        thread_ts=thread_ts,
    )

    # 사용자 정보 조회
    user_name = _get_user_display_name(client, user_id)

    # 던전검색 API로 프로젝트명 조회
    project_name = get_project_name(channel_id)

    context = ProcessingContext(
        channel_id=channel_id,
        user_id=user_id,
        thread_ts=thread_ts,
        file_ids=[f["id"] for f in image_files],
        project_name=project_name,
        user_display_name=user_name,
    )

    # 활성 스레드 등록
    _active_threads[thread_ts] = context

    # 백그라운드 처리 시작
    thread = threading.Thread(
        target=_process_receipts_background,
        args=(client, context, image_files),
        daemon=True,
    )
    thread.start()


def _process_receipts_background(
    client: WebClient,
    context: ProcessingContext,
    image_files: list[dict],
) -> None:
    """백그라운드에서 영수증 처리 파이프라인 실행"""
    temp_files = []
    os.makedirs(TEMP_DIR, exist_ok=True)

    try:
        # === Phase 1: 이미지 수집 및 전처리 ===
        logger.info(f"Phase 1: {len(image_files)}장 이미지 처리 시작")
        images_for_analysis = []
        sheets_image_paths = []

        for idx, file_info in enumerate(image_files):
            local_path = _download_slack_file(client, file_info, idx)
            temp_files.append(local_path)

            if file_info.get("mimetype") == "application/pdf":
                # PDF: Claude에 document 타입으로 직접 전달
                b64_data, media_type = process_pdf(local_path)
                images_for_analysis.append((b64_data, media_type))
                # Sheets용: 페이지별 JPG 변환
                jpg_pages = convert_pdf_pages_to_jpg(local_path)
                temp_files.extend(jpg_pages)
                sheets_image_paths.extend(jpg_pages)
            else:
                b64_data, media_type = process_image(local_path)
                images_for_analysis.append((b64_data, media_type))
                jpg_path = get_jpg_path_for_sheets(local_path)
                if jpg_path != local_path:
                    temp_files.append(jpg_path)
                sheets_image_paths.append(jpg_path)

        # === Phase 2: AI 분석 (병렬) ===
        logger.info("Phase 2: AI 영수증 분석 시작")
        analysis_results = analyze_receipts_batch(images_for_analysis)

        # 결과 필터링
        failed_indices = []
        successful_results = []
        warnings_all = []

        for idx, result in enumerate(analysis_results):
            if result is None or "error" in result:
                failed_indices.append(idx + 1)
                continue

            is_valid, errors, warnings = validate_receipt_data(result)
            warnings_all.extend(warnings)

            if is_valid:
                successful_results.append(result)
            else:
                failed_indices.append(idx + 1)
                logger.error(f"영수증 #{idx+1} 검증 실패: {errors}")

        if not successful_results:
            client.chat_postMessage(
                channel=context.channel_id,
                thread_ts=context.thread_ts,
                text="모든 영수증 분석에 실패했습니다. 이미지를 확인하고 다시 시도해주세요.",
            )
            return

        # === Phase 3: ExpenseReport 생성 ===
        logger.info("Phase 3: 지출결의서 데이터 생성")
        line_items = []
        all_dates = []
        purpose_summaries = []

        for result in successful_results:
            supply, tax = calculate_tax(result["total_amount"])
            summary = result.get("summary_inference") or result.get("merchant_name", "지출")
            category = result.get("expense_category", "기타비용")
            date_str = result.get("transaction_date")

            if date_str:
                try:
                    dt = datetime.strptime(date_str, "%Y-%m-%d")
                    yy_mm_dd = dt.strftime("%y.%m.%d")
                    all_dates.append(dt)
                except ValueError:
                    yy_mm_dd = "날짜불명"
            else:
                yy_mm_dd = "날짜불명"

            purpose_text = summary
            purpose_summaries.append(summary)

            line_items.append(ExpenseLineItem(
                date=yy_mm_dd,
                category=category,
                purpose=purpose_text,
                quantity=1,
                unit_price=result["total_amount"],
                supply_value=supply,
                tax_amount=tax,
                subtotal=result["total_amount"],
            ))

        total = sum(item.subtotal for item in line_items)

        # 대상 월 추출
        if all_dates:
            month_counts = Counter((d.year, d.month) for d in all_dates)
            months_sorted = sorted(month_counts.keys())
            expense_year = months_sorted[0][0]
            expense_months = sorted(set(m for _, m in months_sorted))
        else:
            now = datetime.now()
            expense_year = now.year
            expense_months = [now.month]

        year_short = expense_year % 100
        months_str = " ".join(f"{m}월" for m in expense_months)

        # 사용목적: AI 분석 결과 요약
        purpose = f"{year_short}년 {months_str} " + ", ".join(
            dict.fromkeys(purpose_summaries)  # 중복 제거, 순서 유지
        )

        # 문서번호 생성 및 실명 조회
        sheets_svc, drive_svc = get_google_services()
        doc_number = get_next_doc_number(drive_svc, context.user_display_name)
        real_name = lookup_real_name(sheets_svc, context.user_display_name)
        context.user_real_name = real_name

        expense_report = ExpenseReport(
            project_name=context.project_name,
            user_name=real_name,
            user_display_name=context.user_display_name,
            created_date=datetime.now().strftime("%y.%m.%d"),
            purpose=purpose,
            doc_number=doc_number,
            line_items=line_items,
            total_amount=total,
            expense_months=expense_months,
            expense_year=expense_year,
            image_paths=sheets_image_paths,
        )
        context.expense_report = expense_report

        # === Phase 4: Google Sheets 생성 ===
        logger.info("Phase 4: Google Sheets 생성")

        # 파일 제목: "PJ명_제출연월_개인카드지출결의서_이름"
        submit_months = " ".join(f"{m}월" for m in expense_months)
        new_title = (
            f"{context.project_name}_{year_short}년 {submit_months}"
            f"_개인카드지출결의서_{context.user_display_name}"
        )

        spreadsheet_id = copy_template(
            drive_svc, new_title,
            parent_folder_id=PARENT_FOLDER_ID or None,
        )
        setup_spreadsheet_permissions(drive_svc, spreadsheet_id)
        cell_mapping = discover_cell_mapping(sheets_svc, spreadsheet_id)
        fill_expense_data(sheets_svc, spreadsheet_id, expense_report, cell_mapping)
        attach_receipt_images(sheets_svc, drive_svc, spreadsheet_id, sheets_image_paths)

        sheets_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
        context.sheets_url = sheets_url

        # === Phase 5: 검토 요청 메시지 ===
        logger.info("Phase 5: 검토 요청 메시지 전송")
        warning_text = ""
        if failed_indices:
            nums = ", ".join(f"#{n}" for n in failed_indices)
            warning_text = f"\n\n:warning: 영수증 {nums} 분석에 실패하여 누락되었습니다."

        if warnings_all:
            warning_text += "\n:pushpin: 주의사항:\n" + "\n".join(
                f"- {w}" for w in warnings_all
            )

        review_message = (
            f"{context.user_display_name}님, 지출결의서가 작성되었습니다.\n"
            f"내용을 검토하고 수정이 필요하면 수정을 하신후에 '제출' 버튼을 눌러주세요.\n\n"
            f":page_facing_up: {sheets_url}\n\n"
            f"---\n"
            f":pushpin: 확인 사항:\n"
            f"- 날짜가 정확한가요?\n"
            f"- 금액이 맞나요?\n"
            f"- 항목 분류가 적절한가요?\n"
            f"- 목적 설명이 적절한가요?"
            f"{warning_text}"
        )

        client.chat_postMessage(
            channel=context.channel_id,
            thread_ts=context.thread_ts,
            text=review_message,
            blocks=[
                {"type": "section", "text": {"type": "mrkdwn", "text": review_message}},
                {"type": "actions", "elements": [{
                    "type": "button",
                    "text": {"type": "plain_text", "text": "제출"},
                    "style": "primary",
                    "action_id": "expense_submit",
                    "value": context.thread_ts,
                }]},
            ],
        )

    except Exception as e:
        logger.exception(f"처리 중 오류 발생: {e}")
        client.chat_postMessage(
            channel=context.channel_id,
            thread_ts=context.thread_ts,
            text=f"처리 중 오류가 발생했습니다: {str(e)}\n다시 시도해주세요.",
        )

    finally:
        cleanup_temp_files(temp_files)


def _on_thread_message(event: dict, client: WebClient) -> None:
    """스레드 메시지 이벤트 처리"""
    # 버튼으로 제출 처리하므로 텍스트 감지는 제거
    pass


def _on_submit_button(body: dict, client: WebClient) -> None:
    """'제출' 버튼 클릭 처리"""
    thread_ts = body["actions"][0]["value"]
    user_id = body["user"]["id"]
    channel_id = body["channel"]["id"]

    context = _active_threads.get(thread_ts)
    if not context:
        client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text="처리 정보를 찾을 수 없습니다. 다시 시도해주세요.",
        )
        return

    if user_id != context.user_id:
        client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text="지출결의서를 요청한 본인만 제출할 수 있습니다.",
        )
        return

    # 피드백 수집 및 프로젝트 비용 내역서 기록
    current_items = []
    try:
        if context.expense_report and context.sheets_url:
            spreadsheet_id = context.sheets_url.split("/d/")[1].split("/")[0]
            sheets_svc, _ = get_google_services()
            cell_mapping = discover_cell_mapping(sheets_svc, spreadsheet_id)
            current_items = read_expense_data(
                sheets_svc, spreadsheet_id, cell_mapping,
                len(context.expense_report.line_items),
            )
            changes = collect_feedback(context.expense_report, current_items)
            if changes:
                logger.info(f"사용자 교정 {len(changes)}건 감지됨")
    except Exception as e:
        logger.error(f"피드백 수집 실패: {e}")

    # 프로젝트 비용 내역서에 기록
    try:
        if context.expense_report and current_items:
            append_to_project_cost_sheet(
                sheets_svc, context.expense_report,
                context.user_display_name, current_items,
                channel_id=context.channel_id,
                thread_ts=context.thread_ts,
                user_id=context.user_id,
            )
    except Exception as e:
        logger.error(f"프로젝트 비용 내역서 기록 실패: {e}")

    # 최종 제출
    finance_url = _send_final_notification(client, context)

    confirm_text = "지출결의서가 최종 제출되었습니다. 감사합니다!"
    if finance_url:
        confirm_text += f"\n\n재무팀 채널에 전달된 메시지: {finance_url}"

    client.chat_postMessage(
        channel=channel_id,
        thread_ts=thread_ts,
        text=confirm_text,
    )

    del _active_threads[thread_ts]
    logger.info(f"지출결의서 최종 제출 완료: {context.project_name}")


def _on_reaction_added(event: dict, client: WebClient) -> None:
    """이모지 리액션 이벤트 처리 - 은미님 ✅ 확인"""
    user_id = event.get("user", "")
    reaction = event.get("reaction", "")
    item = event.get("item", {})
    message_ts = item.get("ts", "")
    channel_id = item.get("channel", "")

    logger.info(f"reaction_added 수신: user={user_id}, reaction={reaction}, channel={channel_id}, ts={message_ts}")
    logger.info(f"추적 중인 메시지 목록: {list(_submitted_messages.keys())}")

    # 조건: 은미님 + ✅ + 제출 채널 + 추적 중인 메시지
    if user_id not in (FINANCE_MANAGER_USER_ID, "U05DG0KGDRU"):
        logger.info(f"조건 미충족 - user_id 불일치: {user_id}")
        return
    if reaction != "white_check_mark":
        logger.info(f"조건 미충족 - reaction 불일치: {reaction}")
        return
    if channel_id != EXPENSE_SUBMIT_CHANNEL_ID:
        logger.info(f"조건 미충족 - channel 불일치: {channel_id} != {EXPENSE_SUBMIT_CHANNEL_ID}")
        return
    if message_ts not in _submitted_messages:
        logger.info(f"조건 미충족 - message_ts 미추적: {message_ts}")
        return

    origin_channel, origin_thread_ts = _submitted_messages[message_ts]

    client.chat_postMessage(
        channel=origin_channel,
        thread_ts=origin_thread_ts,
        text="제출된 지출결의서를 은미님께서 확인하셨습니다",
    )

    # project_cost 시트 J열(확인일자) 자동 기록
    try:
        sheets_svc, _ = get_google_services()
        update_confirmation_date(sheets_svc, origin_channel, origin_thread_ts)
    except Exception as e:
        logger.error(f"확인일자 기록 실패: {e}")

    # 입금완료 버튼 메시지 전송 (✅ 이모지를 찍은 제출 채널 알림 스레드에)
    client.chat_postMessage(
        channel=EXPENSE_SUBMIT_CHANNEL_ID,
        thread_ts=message_ts,
        blocks=[
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"<@{FINANCE_MANAGER_USER_ID}> 해당비용이 입금되면 입금완료 버튼을 클릭해주세요.",
                },
            },
            {
                "type": "actions",
                "elements": [{
                    "type": "button",
                    "text": {"type": "plain_text", "text": "입금완료"},
                    "style": "primary",
                    "action_id": "expense_deposit_complete",
                    "value": f"{origin_channel}|{origin_thread_ts}",
                }],
            },
        ],
        text=f"<@{FINANCE_MANAGER_USER_ID}> 해당비용이 입금되면 입금완료 버튼을 클릭해주세요.",
    )

    del _submitted_messages[message_ts]
    logger.info(f"은미님 확인 완료 알림 전송: {origin_channel}/{origin_thread_ts}")


def _send_final_notification(client: WebClient, context: ProcessingContext) -> "str | None":
    """지출결의서 처리요청 채널에 최종 메시지 발송. 발송된 메시지 permalink 반환."""
    report = context.expense_report
    if not report:
        logger.error("ExpenseReport가 없습니다.")
        return None

    year_short = report.expense_year % 100
    months_str = " ".join(f"{m}월" for m in report.expense_months)

    message = (
        f"<@{FINANCE_MANAGER_USER_ID}> 은미님! "
        f"<@{context.user_id}>가 {context.project_name} {year_short}년 {months_str} "
        f"개인카드사용 지출결의서를 제출했습니다.\n\n"
        f"cc <@{CFO_USER_ID}>\n\n"
        f":page_facing_up: {context.sheets_url}"
    )

    response = client.chat_postMessage(
        channel=EXPENSE_SUBMIT_CHANNEL_ID,
        text=message,
    )
    notification_ts = response["ts"]
    _submitted_messages[notification_ts] = (context.channel_id, context.thread_ts)
    logger.info(f"최종 알림 발송 완료: {EXPENSE_SUBMIT_CHANNEL_ID}")

    try:
        permalink_response = client.chat_getPermalink(
            channel=EXPENSE_SUBMIT_CHANNEL_ID,
            message_ts=notification_ts,
        )
        return permalink_response["permalink"]
    except Exception as e:
        logger.error(f"permalink 조회 실패: {e}")
        return None


# --- 헬퍼 함수 ---

def _get_user_display_name(client: WebClient, user_id: str) -> str:
    """Slack User ID로 display name 조회"""
    try:
        user_info = client.users_info(user=user_id)
        profile = user_info["user"]["profile"]
        raw_name = (
            profile.get("display_name")
            or profile.get("real_name")
            or "사용자"
        )
        # "Woodi / Heesun Woo" → "Woodi"
        if "/" in raw_name:
            raw_name = raw_name.split("/")[0].strip()
        return raw_name
    except Exception as e:
        logger.error(f"사용자 정보 조회 실패: {e}")
        return "사용자"


def _is_deposit_already_processed(sheets_svc, channel_id: str, thread_ts: str) -> bool:
    """K열(입금일자)에 이미 값이 있으면 True 반환 (중복 처리 방지)"""
    try:
        result = sheets_svc.spreadsheets().values().get(
            spreadsheetId=PROJECT_COST_SPREADSHEET_ID,
            range="A2:O",
        ).execute()
        rows = result.get("values", [])
        ts_int = thread_ts.split('.')[0]
        for row in rows:
            row_channel_id = row[11].strip() if len(row) > 11 else ""
            row_thread_ts = row[12].strip() if len(row) > 12 else ""
            if row_channel_id == channel_id and (row_thread_ts == thread_ts or row_thread_ts == ts_int):
                return bool(row[10].strip() if len(row) > 10 else "")
    except Exception as e:
        logger.error(f"중복 처리 확인 실패: {e}")
    return False


def _on_deposit_complete(body: dict, client: WebClient) -> None:
    """'입금완료' 버튼 클릭 → 날짜 선택 모달 팝업"""
    value = body["actions"][0]["value"]
    origin_channel, origin_thread_ts = value.split("|", 1)
    button_channel = body["channel"]["id"]
    button_message_ts = body["message"]["ts"]
    trigger_id = body["trigger_id"]

    # 중복 클릭 방지: 이미 처리된 건이면 모달 열지 않음
    try:
        sheets_svc, _ = get_google_services()
        if _is_deposit_already_processed(sheets_svc, origin_channel, origin_thread_ts):
            logger.info("입금완료 중복 클릭 무시")
            return
    except Exception as e:
        logger.error(f"중복 클릭 확인 실패: {e}")

    today = datetime.now().strftime("%Y-%m-%d")
    private_metadata = f"{origin_channel}|{origin_thread_ts}|{button_channel}|{button_message_ts}"

    client.views_open(
        trigger_id=trigger_id,
        view={
            "type": "modal",
            "callback_id": "expense_deposit_date_modal",
            "title": {"type": "plain_text", "text": "입금 날짜 입력"},
            "submit": {"type": "plain_text", "text": "확인"},
            "close": {"type": "plain_text", "text": "취소"},
            "private_metadata": private_metadata,
            "blocks": [{
                "type": "input",
                "block_id": "deposit_date_block",
                "label": {"type": "plain_text", "text": "실제 입금 날짜를 선택해주세요"},
                "element": {
                    "type": "datepicker",
                    "action_id": "deposit_date_picker",
                    "initial_date": today,
                    "placeholder": {"type": "plain_text", "text": "날짜 선택"},
                },
            }],
        },
    )
    logger.info(f"입금 날짜 선택 모달 오픈: {origin_channel}/{origin_thread_ts}")


def _on_deposit_date_submit(body: dict, client: WebClient, view: dict) -> None:
    """입금 날짜 선택 모달 제출 처리"""
    meta = view["private_metadata"]
    origin_channel, origin_thread_ts, button_channel, button_message_ts = meta.split("|", 3)

    deposit_date = view["state"]["values"]["deposit_date_block"]["deposit_date_picker"]["selected_date"]

    try:
        sheets_svc, _ = get_google_services()
        user_id = update_deposit_date(sheets_svc, origin_channel, origin_thread_ts, deposit_date)
    except Exception as e:
        logger.error(f"입금일자 기록 실패: {e}")
        return

    if user_id is None:
        logger.info("입금완료 중복 처리 무시")
        return

    # 버튼 메시지를 "처리됨" 텍스트로 교체
    try:
        client.chat_update(
            channel=button_channel,
            ts=button_message_ts,
            blocks=[{
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"✅ 입금완료 처리됨 ({deposit_date})"},
            }],
            text=f"✅ 입금완료 처리됨 ({deposit_date})",
        )
    except Exception as e:
        logger.error(f"버튼 메시지 업데이트 실패: {e}")

    # 제출자에게 알림
    client.chat_postMessage(
        channel=origin_channel,
        thread_ts=origin_thread_ts,
        text=f"<@{user_id}> 비용이 입금되었습니다.",
    )
    logger.info(f"입금 완료 알림 전송: {user_id}")


def _download_slack_file(
    client: WebClient, file_info: dict, index: int
) -> str:
    """Slack 파일을 로컬 임시 경로에 다운로드"""
    url = file_info.get("url_private_download") or file_info.get("url_private")
    filename = file_info.get("name", f"receipt_{index}.jpg")

    local_path = os.path.join(TEMP_DIR, f"{index}_{filename}")

    response = requests.get(
        url,
        headers={"Authorization": f"Bearer {client.token}"},
        timeout=30,
    )
    response.raise_for_status()

    with open(local_path, "wb") as f:
        f.write(response.content)

    logger.info(f"이미지 다운로드 완료: {local_path} ({len(response.content)} bytes)")
    return local_path
