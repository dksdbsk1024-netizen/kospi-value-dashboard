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


def get_video_metadata(url: str) -> dict:
    """yt-dlp로 영상 메타데이터 추출. 접근 불가 시 Exception 발생."""
    ydl_opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return {
        "title": info.get("title", ""),
        "channel": info.get("uploader", ""),
        "duration": info.get("duration", 0),
        "video_id": info.get("id", ""),
    }


def get_transcript_from_captions(video_id: str) -> list[dict]:
    """
    youtube-transcript-api로 자막 추출.
    한국어 우선, 없으면 영어 시도.
    반환: [{"text": str, "start": float, "duration": float}, ...]
    자막 없으면 Exception 발생.
    """
    return YouTubeTranscriptApi.get_transcript(video_id, languages=["ko", "en"])


def get_transcript_from_whisper(url: str, openai_api_key: str) -> list[dict]:
    """
    yt-dlp로 오디오(.mp3) 추출 후 OpenAI Whisper API로 전사.
    반환: [{"text": str, "start": float, "duration": float}, ...]
    임시 파일은 처리 완료 즉시 삭제.
    """
    client = OpenAI(api_key=openai_api_key)
    with tempfile.TemporaryDirectory() as tmpdir:
        output_base = os.path.join(tmpdir, "audio")
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": output_base,
            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}],
            "quiet": True,
            "no_warnings": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        audio_path = output_base + ".mp3"
        with open(audio_path, "rb") as f:
            response = client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                response_format="verbose_json",
                timestamp_granularities=["segment"],
            )
    segments = []
    for seg in response.segments:
        segments.append({
            "text": seg.text,
            "start": seg.start,
            "duration": seg.end - seg.start,
        })
    return segments


def get_transcript(url: str, video_id: str, openai_api_key: str) -> tuple[list[dict], str]:
    """
    자막 추출 시도 후 실패하면 Whisper로 폴백.
    반환: (segments, source) — source는 "captions" 또는 "whisper"
    """
    try:
        segments = get_transcript_from_captions(video_id)
        return segments, "captions"
    except Exception:
        segments = get_transcript_from_whisper(url, openai_api_key)
        return segments, "whisper"
