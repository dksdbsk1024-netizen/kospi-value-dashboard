import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from utils.video_analyzer import extract_video_id, format_transcript_for_claude


def test_extract_video_id_standard_url():
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert extract_video_id(url) == "dQw4w9WgXcQ"


def test_extract_video_id_short_url():
    url = "https://youtu.be/dQw4w9WgXcQ"
    assert extract_video_id(url) == "dQw4w9WgXcQ"


def test_extract_video_id_invalid_url():
    assert extract_video_id("https://example.com/video") is None


def test_format_transcript_for_claude_formats_timestamp():
    segments = [
        {"text": "안녕하세요", "start": 0.0, "duration": 2.0},
        {"text": "금리 인상 분석", "start": 125.5, "duration": 3.0},
    ]
    result = format_transcript_for_claude(segments)
    assert "[00:00:00] 안녕하세요" in result
    assert "[00:02:05] 금리 인상 분석" in result


def test_format_transcript_for_claude_empty():
    assert format_transcript_for_claude([]) == ""


from unittest.mock import patch, MagicMock
from utils.video_analyzer import get_video_metadata, get_transcript


def test_get_video_metadata_returns_expected_keys():
    fake_info = {
        "title": "테스트 영상",
        "uploader": "테스트 채널",
        "duration": 300,
        "id": "abc123def45",
    }
    with patch("yt_dlp.YoutubeDL") as MockYDL:
        instance = MockYDL.return_value.__enter__.return_value
        instance.extract_info.return_value = fake_info
        result = get_video_metadata("https://www.youtube.com/watch?v=abc123def45")
    assert result == {
        "title": "테스트 영상",
        "channel": "테스트 채널",
        "duration": 300,
        "video_id": "abc123def45",
    }


def test_get_transcript_uses_captions_when_available():
    fake_segments = [{"text": "hello", "start": 0.0, "duration": 1.0}]
    with patch("utils.video_analyzer.get_transcript_from_captions", return_value=fake_segments):
        segments, source = get_transcript(
            url="https://youtu.be/abc123def45",
            video_id="abc123def45",
            openai_api_key="test-key",
        )
    assert source == "captions"
    assert segments == fake_segments


def test_get_transcript_falls_back_to_whisper():
    fake_segments = [{"text": "whisper text", "start": 0.0, "duration": 1.0}]
    with patch("utils.video_analyzer.get_transcript_from_captions", side_effect=Exception("no captions")):
        with patch("utils.video_analyzer.get_transcript_from_whisper", return_value=fake_segments):
            segments, source = get_transcript(
                url="https://youtu.be/abc123def45",
                video_id="abc123def45",
                openai_api_key="test-key",
            )
    assert source == "whisper"
    assert segments == fake_segments
