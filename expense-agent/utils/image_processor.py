from __future__ import annotations

import os
import base64
import logging
from pathlib import Path

from PIL import Image

from config import MAX_IMAGE_DIMENSION, TEMP_DIR

logger = logging.getLogger(__name__)


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

    img = Image.open(heic_path)
    jpg_path = os.path.join(TEMP_DIR, Path(heic_path).stem + ".jpg")
    img.save(jpg_path, "JPEG", quality=90)
    logger.info(f"HEIC → JPG 변환 완료: {jpg_path}")
    return jpg_path


def resize_image(image_path: str, max_dim: int = MAX_IMAGE_DIMENSION) -> str:
    """이미지를 최대 크기 이내로 리사이즈 (비율 유지)"""
    img = Image.open(image_path)
    if img.width <= max_dim and img.height <= max_dim:
        return image_path

    img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
    resized_path = os.path.join(TEMP_DIR, "resized_" + Path(image_path).name)
    img.save(resized_path, "JPEG", quality=85)
    logger.info(f"리사이즈 완료: {img.width}x{img.height} → {resized_path}")
    return resized_path


def encode_image_base64(image_path: str) -> tuple[str, str]:
    """
    이미지를 base64 인코딩

    Returns:
        (base64_data, media_type)
    """
    ext = Path(image_path).suffix.lower()
    media_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    media_type = media_types.get(ext, "image/jpeg")

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
