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


_ANALYSIS_PROMPT = """\
아래는 YouTube 영상의 타임스탬프별 트랜스크립트입니다.
다음 3가지를 반드시 유효한 JSON 형식으로만 반환하세요. JSON 외 다른 텍스트는 절대 포함하지 마세요.

{{
  "summary": "전체 내용 요약 (3~5문단, 한국어)",
  "key_moments": [
    {{"timestamp": "HH:MM:SS", "description": "한 줄 설명 (한국어)"}}
  ],
  "keywords": [
    {{
      "keyword": "키워드명",
      "summary": "해당 키워드 관련 내용 요약 2~3문장 (한국어)",
      "timestamps": ["HH:MM:SS"]
    }}
  ]
}}

key_moments는 5~10개, keywords는 3~7개를 추출하세요.

트랜스크립트:
{transcript}"""


def analyze_transcript(transcript_text: str, anthropic_api_key: str) -> dict:
    """
    Claude API로 트랜스크립트 분석.
    반환: {"summary": str, "key_moments": [...], "keywords": [...]}
    JSON 파싱 실패 시 ValueError 발생.
    """
    client = anthropic.Anthropic(api_key=anthropic_api_key)
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": _ANALYSIS_PROMPT.format(transcript=transcript_text),
        }],
    )
    raw = message.content[0].text.strip()
    return json.loads(raw)


def analyze_video(url: str, anthropic_api_key: str, openai_api_key: str) -> dict:
    """
    전체 분석 파이프라인.
    반환: {"summary", "key_moments", "keywords", "meta", "source"}
    """
    meta = get_video_metadata(url)
    video_id = meta["video_id"]
    segments, source = get_transcript(url, video_id, openai_api_key)
    transcript_text = format_transcript_for_claude(segments)
    result = analyze_transcript(transcript_text, anthropic_api_key)
    result["meta"] = meta
    result["source"] = source
    return result
