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
    CHANNEL_PROJECT_MAP,
    EXPENSE_SUBMIT_CHANNEL_ID,
    FINANCE_MANAGER_USER_ID,
    CEO_USER_ID,
    CFO_USER_ID,
    MAX_RECEIPT_COUNT,
    PARENT_FOLDER_ID,
    SUPPORTED_IMAGE_TYPES,
    TEMP_DIR,
)
from models import (
    ExpenseLineItem,
    ExpenseReport,
    ProcessingContext,
)
from handlers.ai_handler import analyze_receipts_batch
from handlers.sheets_handler import (
    attach_receipt_images,
    calculate_tax,
    copy_template,
    discover_cell_mapping,
    fill_expense_data,
    get_google_services,
    share_spreadsheet,
)
from utils.image_processor import (
    cleanup_temp_files,
    get_jpg_path_for_sheets,
    process_image,
)
from utils.validators import validate_receipt_data

logger = logging.getLogger(__name__)

# 진행 중인 처리 요청 추적 (thread_ts -> ProcessingContext)
_active_threads: dict[str, ProcessingContext] = {}


def register_handlers(app: App) -> None:
    """모든 Slack 이벤트 핸들러를 앱에 등록"""

    @app.event("app_mention")
    def handle_app_mention(event, say, client):
        _on_app_mention(event, say, client)

    @app.event("message")
    def handle_message(event, client):
        _on_thread_message(event, client)


def _on_app_mention(event: dict, say, client: WebClient) -> None:
    """앱 멘션 이벤트 처리"""
    channel_id = event["channel"]
    user_id = event["user"]
    thread_ts = event.get("ts", "")

    # 이미지 파일 추출
    files = event.get("files", [])
    image_files = [
        f for f in files
        if f.get("mimetype", "") in SUPPORTED_IMAGE_TYPES
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
        text=f"지출품의서를 작성 중입니다... ({len(image_files)}장의 영수증 처리 중)",
        thread_ts=thread_ts,
    )

    # 사용자 정보 및 프로젝트명 조회
    user_name = _get_user_display_name(client, user_id)
    project_name = _get_project_name(client, channel_id)

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
            # Slack에서 이미지 다운로드
            local_path = _download_slack_file(client, file_info, idx)
            temp_files.append(local_path)

            # AI 분석용 전처리 (HEIC 변환 + 리사이즈 + base64)
            b64_data, media_type = process_image(local_path)
            images_for_analysis.append((b64_data, media_type))

            # Sheets 첨부용 JPG 경로
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

        for result in successful_results:
            supply, tax = calculate_tax(result["total_amount"])
            summary = result.get("summary_inference") or result.get("merchant_name", "지출")
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

            description = f"{summary} ({yy_mm_dd} / {context.user_display_name})"

            line_items.append(ExpenseLineItem(
                description=description,
                quantity=1,
                subtotal=result["total_amount"],
                supply_value=supply,
                tax_amount=tax,
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

        months_str = " ".join(f"{m}월" for m in expense_months)
        purpose = f"{context.project_name} {months_str} 개인카드 지출"

        expense_report = ExpenseReport(
            project_name=context.project_name,
            user_name=context.user_display_name,
            created_date=datetime.now().strftime("%y.%m.%d"),
            purpose=purpose,
            line_items=line_items,
            total_amount=total,
            expense_months=expense_months,
            expense_year=expense_year,
            image_paths=sheets_image_paths,
        )
        context.expense_report = expense_report

        # === Phase 4: Google Sheets 생성 ===
        logger.info("Phase 4: Google Sheets 생성")
        sheets_svc, drive_svc = get_google_services()

        new_title = (
            f"{context.project_name}_{months_str}"
            f"_개인카드 지출품의서_{context.user_display_name}"
        )

        spreadsheet_id = copy_template(
            drive_svc, new_title,
            parent_folder_id=PARENT_FOLDER_ID or None,
        )
        cell_mapping = discover_cell_mapping(sheets_svc, spreadsheet_id)
        fill_expense_data(sheets_svc, spreadsheet_id, expense_report, cell_mapping)
        attach_receipt_images(sheets_svc, drive_svc, spreadsheet_id, sheets_image_paths)

        # 링크가 있는 사용자에게 공유 (선택사항 - 서비스 계정으로 공유)
        # share_spreadsheet(drive_svc, spreadsheet_id, [user_email])

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
            f"{context.user_display_name}님, 지출품의서 초안이 작성되었습니다.\n"
            f"내용을 확인하고 수정이 필요 없으면 '완료'라고 답글을 달아주세요.\n\n"
            f":page_facing_up: {sheets_url}\n\n"
            f"---\n"
            f":pushpin: 확인 사항:\n"
            f"- 날짜가 정확한가요?\n"
            f"- 금액이 맞나요?\n"
            f"- 품목 설명이 적절한가요?"
            f"{warning_text}"
        )

        client.chat_postMessage(
            channel=context.channel_id,
            thread_ts=context.thread_ts,
            text=review_message,
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
    """스레드 메시지 이벤트 처리 (사용자 "완료" 응답 감지)"""
    # 봇 자신의 메시지 무시
    if event.get("bot_id") or event.get("subtype"):
        return

    thread_ts = event.get("thread_ts")
    if not thread_ts:
        return

    context = _active_threads.get(thread_ts)
    if not context:
        return

    if event.get("user") != context.user_id:
        return

    text = event.get("text", "").strip()
    if "완료" in text:
        _send_final_notification(client, context)

        client.chat_postMessage(
            channel=context.channel_id,
            thread_ts=thread_ts,
            text="지출품의서가 최종 제출되었습니다. 감사합니다!",
        )

        del _active_threads[thread_ts]
        logger.info(f"지출품의서 최종 제출 완료: {context.project_name}")


def _send_final_notification(client: WebClient, context: ProcessingContext) -> None:
    """지출품의서 처리요청 채널에 최종 메시지 발송"""
    report = context.expense_report
    if not report:
        logger.error("ExpenseReport가 없습니다.")
        return

    year_short = report.expense_year % 100
    months_str = " ".join(f"{m}월" for m in report.expense_months)

    message = (
        f"<@{FINANCE_MANAGER_USER_ID}> 은미님!\n\n"
        f"{context.project_name} {year_short}년 {months_str} "
        f"개인카드사용 지출결의서 전달드립니다.\n\n"
        f"cc <@{CEO_USER_ID}> / <@{CFO_USER_ID}>\n\n"
        f":page_facing_up: {context.sheets_url}"
    )

    client.chat_postMessage(
        channel=EXPENSE_SUBMIT_CHANNEL_ID,
        text=message,
    )
    logger.info(f"최종 알림 발송 완료: {EXPENSE_SUBMIT_CHANNEL_ID}")


# --- 헬퍼 함수 ---

def _get_user_display_name(client: WebClient, user_id: str) -> str:
    """Slack User ID로 display name 조회"""
    try:
        user_info = client.users_info(user=user_id)
        profile = user_info["user"]["profile"]
        return (
            profile.get("display_name")
            or profile.get("real_name")
            or "사용자"
        )
    except Exception as e:
        logger.error(f"사용자 정보 조회 실패: {e}")
        return "사용자"


def _get_project_name(client: WebClient, channel_id: str) -> str:
    """채널 ID로 프로젝트명 조회"""
    # 매핑 테이블에서 먼저 확인
    if channel_id in CHANNEL_PROJECT_MAP:
        return CHANNEL_PROJECT_MAP[channel_id]

    # 없으면 채널명 조회
    try:
        channel_info = client.conversations_info(channel=channel_id)
        channel_name = channel_info["channel"]["name"]
        # #pj-foodcare → 푸드케어 CRO PJ 같은 자동 변환은 어려우므로 채널명 그대로 사용
        return channel_name
    except Exception as e:
        logger.error(f"채널 정보 조회 실패: {e}")
        return "프로젝트"


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
