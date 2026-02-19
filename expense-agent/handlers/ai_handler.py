from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import anthropic

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from prompts.receipt_analysis import get_system_prompt

logger = logging.getLogger(__name__)

_client = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


def analyze_receipt(image_base64: str, media_type: str) -> dict:
    """
    단일 영수증 이미지 분석

    Returns:
        {
            "merchant_name": str,
            "transaction_date": str | None,
            "total_amount": int,
            "items": [...],
            "payment_method": str | None,
            "summary_inference": str | None,
        }
    """
    client = _get_client()

    if media_type == "application/pdf":
        content_block = {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": image_base64,
            },
        }
        prompt_text = "위 PDF 영수증을 분석하여 JSON 형식으로 데이터를 추출해주세요."
    else:
        content_block = {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": image_base64,
            },
        }
        prompt_text = "위 영수증 이미지를 분석하여 JSON 형식으로 데이터를 추출해주세요."

    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        system=get_system_prompt(),
        messages=[
            {
                "role": "user",
                "content": [
                    content_block,
                    {"type": "text", "text": prompt_text},
                ],
            }
        ],
    )

    response_text = message.content[0].text
    receipt_data = _parse_ai_response(response_text)
    return receipt_data


def analyze_receipts_batch(
    images: list[tuple[str, str]],
) -> list[dict]:
    """
    여러 영수증 병렬 분석

    Args:
        images: (base64_data, media_type) 튜플 리스트

    Returns:
        분석 결과 리스트 (실패한 건은 {"error": "..."} 포함)
    """
    results = [None] * len(images)

    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_index = {
            executor.submit(analyze_receipt, img_b64, media_type): idx
            for idx, (img_b64, media_type) in enumerate(images)
        }

        for future in as_completed(future_to_index):
            idx = future_to_index[future]
            try:
                results[idx] = future.result()
                logger.info(f"영수증 #{idx+1} 분석 완료")
            except Exception as e:
                logger.error(f"영수증 #{idx+1} 분석 실패: {e}")
                results[idx] = {"error": str(e), "index": idx}

    return results


def _parse_ai_response(response_text: str) -> dict:
    """Claude 응답에서 JSON 추출 및 파싱"""
    text = response_text.strip()

    # ```json ... ``` 블록 추출
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.error(f"JSON 파싱 오류: {e}\n원본: {response_text[:500]}")
        raise ValueError(f"영수증 데이터를 파싱할 수 없습니다: {e}")
