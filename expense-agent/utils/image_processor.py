from __future__ import annotations

import os
import base64
import logging
from pathlib import Path

from PIL import Image

from config import MAX_IMAGE_DIMENSION, TEMP_DIR

logger = logging.getLogger(__name__)

# 디컴프레션 폭탄 방어: 60MP 초과 이미지는 디코딩 거부 (48MP 폰 카메라는 허용).
# 가로 20000px PNG 한 장이면 raw RGB 1.2GB → OOM 으로 호스트가 멈출 수 있어 상한을 둔다.
Image.MAX_IMAGE_PIXELS = 60_000_000


def process_image(file_path: str) -> tuple[str, str]:
    """
    이미지 전처리 파이프라인: 형식 변환 → 리사이즈 → base64 인코딩

    Returns:
        (base64_data, media_type)
    """
    os.makedirs(TEMP_DIR, exist_ok=True)

    ext = Path(file_path).suffix.lower()

    # HEIC/HEIF → JPG 변환
    if ext in (".heic", ".heif"):
        file_path = convert_heic_to_jpg(file_path)

    # 리사이즈
    file_path = resize_image(file_path)

    # base64 인코딩
    return encode_image_base64(file_path)


def convert_heic_to_jpg(heic_path: str) -> str:
    """HEIC/HEIF 이미지를 JPG로 변환"""
    import pillow_heif
    pillow_heif.register_heif_opener()

    jpg_path = os.path.join(TEMP_DIR, Path(heic_path).stem + ".jpg")
    with Image.open(heic_path) as img:
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGB")
        img.save(jpg_path, "JPEG", quality=90)
    logger.info(f"HEIC → JPG 변환 완료: {jpg_path}")
    return jpg_path


def resize_image(image_path: str, max_dim: int = MAX_IMAGE_DIMENSION) -> str:
    """이미지를 최대 크기 이내로 리사이즈 (비율 유지)"""
    resized_path = os.path.join(TEMP_DIR, "resized_" + Path(image_path).name)
    with Image.open(image_path) as img:
        # 헤더만 읽어 크기 확인 (전체 디코딩 전). 이미 작으면 재인코딩 없이 원본 사용.
        if img.width <= max_dim and img.height <= max_dim:
            return image_path

        # JPEG draft 모드: libjpeg가 1/2·1/4·1/8 축소 디코딩 → 대용량 사진의 피크 메모리 급감.
        # (JPEG 이외 포맷에는 no-op)
        img.draft("RGB", (max_dim, max_dim))
        img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGB")
        img.save(resized_path, "JPEG", quality=85)
        logger.info(f"리사이즈 완료: {img.width}x{img.height} → {resized_path}")
    return resized_path


def encode_image_base64(image_path: str) -> tuple[str, str]:
    """
    이미지를 base64 인코딩

    Returns:
        (base64_data, media_type)
    """
    # 확장자가 아닌 실제 파일 포맷으로 media_type 결정
    # (Slack이 JPEG를 .png 확장자로 전송하는 경우 대응)
    format_to_media_type = {
        "JPEG": "image/jpeg",
        "PNG": "image/png",
        "GIF": "image/gif",
        "WEBP": "image/webp",
    }
    with Image.open(image_path) as img:
        media_type = format_to_media_type.get(img.format, "image/jpeg")

    with open(image_path, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode("utf-8")

    return data, media_type


def process_pdf(file_path: str) -> tuple[str, str]:
    """PDF를 base64로 인코딩하여 Claude API용 데이터 반환 (document 타입)"""
    with open(file_path, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode("utf-8")
    return data, "application/pdf"


def convert_pdf_pages_to_jpg(pdf_path: str) -> list[str]:
    """PDF의 각 페이지를 JPG 이미지로 변환하여 경로 목록 반환 (Sheets 첨부용)"""
    import fitz  # PyMuPDF

    os.makedirs(TEMP_DIR, exist_ok=True)
    jpg_paths = []
    doc = fitz.open(pdf_path)

    for page_num in range(len(doc)):
        page = doc[page_num]
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        jpg_path = os.path.join(TEMP_DIR, f"{Path(pdf_path).stem}_page{page_num + 1}.jpg")
        pix.save(jpg_path)
        jpg_paths.append(jpg_path)
        logger.info(f"PDF 페이지 {page_num + 1} → JPG 변환 완료: {jpg_path}")
        # 페이지별 비압축 픽스맵을 즉시 해제 (다중 페이지 PDF의 메모리 누적 방지)
        pix = None

    doc.close()
    return jpg_paths


def get_jpg_path_for_sheets(file_path: str) -> str:
    """Google Sheets 첨부용 JPG 경로 반환 (HEIC면 변환, 아니면 원본)"""
    ext = Path(file_path).suffix.lower()
    if ext in (".heic", ".heif"):
        return convert_heic_to_jpg(file_path)
    return file_path


def cleanup_temp_files(file_paths: list[str]) -> None:
    """임시 파일 정리"""
    for path in file_paths:
        try:
            if os.path.exists(path) and path.startswith(TEMP_DIR):
                os.remove(path)
                logger.debug(f"임시 파일 삭제: {path}")
        except OSError as e:
            logger.warning(f"임시 파일 삭제 실패: {path} - {e}")
