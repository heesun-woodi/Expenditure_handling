import os
import pytest
from unittest.mock import patch
from utils.image_processor import encode_image_base64, cleanup_temp_files


class TestEncodeImageBase64:
    def test_returns_tuple(self, tmp_path):
        # 테스트용 간단한 이미지 파일 생성
        test_file = tmp_path / "test.jpg"
        test_file.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        b64, media_type = encode_image_base64(str(test_file))
        assert isinstance(b64, str)
        assert media_type == "image/jpeg"
        assert len(b64) > 0

    def test_png_media_type(self, tmp_path):
        test_file = tmp_path / "test.png"
        test_file.write_bytes(b"\x89PNG" + b"\x00" * 100)

        _, media_type = encode_image_base64(str(test_file))
        assert media_type == "image/png"

    def test_unknown_extension_defaults_to_jpeg(self, tmp_path):
        test_file = tmp_path / "test.bmp"
        test_file.write_bytes(b"\x00" * 100)

        _, media_type = encode_image_base64(str(test_file))
        assert media_type == "image/jpeg"


class TestCleanupTempFiles:
    def test_cleanup_removes_files(self, tmp_path):
        test_file = tmp_path / "test.jpg"
        test_file.write_bytes(b"test")

        with patch("utils.image_processor.TEMP_DIR", str(tmp_path)):
            cleanup_temp_files([str(test_file)])

        assert not test_file.exists()

    def test_cleanup_ignores_nonexistent(self, tmp_path):
        with patch("utils.image_processor.TEMP_DIR", str(tmp_path)):
            cleanup_temp_files([str(tmp_path / "nonexistent.jpg")])
