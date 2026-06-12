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
