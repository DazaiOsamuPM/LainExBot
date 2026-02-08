"""
Unit tests for utility functions.
"""


from utils import (
    find_first_url, strip_tracking_params, is_supported_url,
    detect_platform, sanitize_filename, format_file_size,
    format_duration, validate_url_input
)
from models import Platform


class TestURLProcessing:
    """Test URL processing functions."""

    def test_find_first_url_valid(self):
        """Test finding first URL in text."""
        text = "Check this video: https://youtube.com/watch?v=123 and this https://tiktok.com/@user/video/456"
        result = find_first_url(text)
        assert result == "https://youtube.com/watch?v=123"

    def test_find_first_url_none(self):
        """Test no URL found."""
        text = "This is just plain text without any URLs."
        result = find_first_url(text)
        assert result is None

    def test_strip_tracking_params(self):
        """Test removing tracking parameters."""
        url = "https://example.com/video?v=123&utm_source=test&utm_campaign=promo"
        result = strip_tracking_params(url)
        assert "utm_source" not in result
        assert "utm_campaign" not in result
        assert "v=123" in result

    def test_is_supported_url_youtube(self):
        """Test supported YouTube URL."""
        url = "https://youtube.com/watch?v=dQw4w9WgXcQ"
        assert is_supported_url(url)

    def test_is_supported_url_tiktok(self):
        """Test supported TikTok URL."""
        url = "https://tiktok.com/@user/video/123456789"
        assert is_supported_url(url)

    def test_is_supported_url_unsupported(self):
        """Test unsupported URL."""
        url = "https://unsupported-site.com/video"
        assert not is_supported_url(url)

    def test_detect_platform_youtube(self):
        """Test platform detection for YouTube."""
        url = "https://youtube.com/watch?v=test"
        assert detect_platform(url) == Platform.YOUTUBE

    def test_detect_platform_tiktok(self):
        """Test platform detection for TikTok."""
        url = "https://tiktok.com/@user/video/123"
        assert detect_platform(url) == Platform.TIKTOK

    def test_detect_platform_unknown(self):
        """Test platform detection for unknown."""
        url = "https://unknown-site.com/video"
        assert detect_platform(url) == Platform.UNKNOWN


class TestFileOperations:
    """Test file operation utilities."""

    def test_sanitize_filename(self):
        """Test filename sanitization."""
        filename = 'file<>:"/\\|?*with"bad:chars.mp4'
        result = sanitize_filename(filename)
        assert "<>" not in result
        assert ":\"|?*" not in result
        assert result.endswith(".mp4")

    def test_format_file_size_bytes(self):
        """Test file size formatting for bytes."""
        assert format_file_size(512) == "512.0 B"

    def test_format_file_size_kb(self):
        """Test file size formatting for KB."""
        assert format_file_size(1536) == "1.5 KB"

    def test_format_file_size_mb(self):
        """Test file size formatting for MB."""
        assert format_file_size(1048576) == "1.0 MB"

    def test_format_duration_seconds(self):
        """Test duration formatting for seconds."""
        assert format_duration(65) == "01:05"

    def test_format_duration_minutes(self):
        """Test duration formatting for minutes."""
        assert format_duration(3665) == "1:01:05"


class TestValidation:
    """Test validation functions."""

    def test_validate_url_input_valid(self):
        """Test valid URL validation."""
        is_valid, error = validate_url_input("https://example.com/video")
        assert is_valid
        assert error == ""

    def test_validate_url_input_invalid_scheme(self):
        """Test invalid scheme validation."""
        is_valid, error = validate_url_input("ftp://example.com/video")
        assert not is_valid
        assert "url" in error.lower()

    def test_validate_url_input_too_long(self):
        """Test URL too long validation."""
        long_url = "https://example.com/" + "a" * 2000
        is_valid, error = validate_url_input(long_url)
        assert not is_valid
        assert "url" in error.lower()

    def test_validate_url_input_empty(self):
        """Test empty URL validation."""
        is_valid, error = validate_url_input("")
        assert not is_valid
        assert "url" in error.lower()
