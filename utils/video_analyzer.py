import re
import os
import tempfile
import json

import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi
from openai import OpenAI
import anthropic


def extract_video_id(url: str) -> str | None:
    """YouTube URL에서 11자리 video ID 추출. 유효하지 않으면 None 반환."""
    pattern = r'(?:v=|youtu\.be/)([a-zA-Z0-9_-]{11})'
    match = re.search(pattern, url)
    return match.group(1) if match else None


def format_transcript_for_claude(segments: list[dict]) -> str:
    """
    트랜스크립트 세그먼트 리스트를 '[HH:MM:SS] text' 형식 문자열로 변환.
    segments: [{"text": str, "start": float, "duration": float}, ...]
    """
    if not segments:
        return ""
    lines = []
    for seg in segments:
        start = seg["start"]
        h = int(start // 3600)
        m = int((start % 3600) // 60)
        s = int(start % 60)
        lines.append(f"[{h:02d}:{m:02d}:{s:02d}] {seg['text'].strip()}")
    return "\n".join(lines)
