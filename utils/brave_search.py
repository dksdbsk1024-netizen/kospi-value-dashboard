"""Brave Search API 유틸리티.

news_search(): 뉴스 전용 엔드포인트 (/v1/news/search) — 최신성 보장
web_search(): 일반 웹 검색 (/v1/web/search)
"""

import os
import requests

# st.secrets → 환경변수 순으로 fallback
try:
    import streamlit as st
    BRAVE_API_KEY = st.secrets.get("BRAVE_API_KEY", "") or os.environ.get("BRAVE_API_KEY", "")
except Exception:
    BRAVE_API_KEY = os.environ.get("BRAVE_API_KEY", "")
_BASE = "https://api.search.brave.com/res/v1"
_HEADERS = {
    "Accept": "application/json",
    "Accept-Encoding": "gzip",
    "X-Subscription-Token": BRAVE_API_KEY,
}


def news_search(
    query: str,
    count: int = 5,
    freshness: str = "pw",   # pd=하루, pw=1주, pm=1개월
) -> list[dict]:
    """뉴스 전용 엔드포인트로 최신 기사 반환.

    Returns:
        list of {title, url, description, age, source}
    """
    params = {
        "q": query,
        "count": count,
        "country": "KR",
        "search_lang": "ko",
        "freshness": freshness,
    }
    if not BRAVE_API_KEY:
        return []
    try:
        resp = requests.get(
            f"{_BASE}/news/search",
            headers=_HEADERS,
            params=params,
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "description": r.get("description", ""),
                "age": r.get("age", ""),
                "source": r.get("meta_url", {}).get("hostname", ""),
            }
            for r in results
        ]
    except Exception:
        return []


def web_search(
    query: str,
    count: int = 5,
    freshness: str | None = None,
) -> list[dict]:
    """일반 웹 검색 결과 반환.

    Returns:
        list of {title, url, description, age}
    """
    params: dict = {
        "q": query,
        "count": count,
        "country": "KR",
        "search_lang": "ko",
    }
    if freshness:
        params["freshness"] = freshness
    if not BRAVE_API_KEY:
        return []
    try:
        resp = requests.get(
            f"{_BASE}/web/search",
            headers=_HEADERS,
            params=params,
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json().get("web", {}).get("results", [])
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "description": r.get("description", ""),
                "age": r.get("age", ""),
            }
            for r in results
        ]
    except Exception:
        return []


# 하위 호환 — 기존 코드에서 search() 호출 시 뉴스 엔드포인트로 라우팅
def search(query: str, count: int = 5) -> list[dict]:
    return news_search(query, count=count, freshness="pm")
