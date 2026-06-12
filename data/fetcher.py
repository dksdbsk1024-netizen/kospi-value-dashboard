"""
KRX/Naver 데이터 수집 모듈.

데이터 소스:
  1. Naver Finance sise_market_sum — PBR, PER, ROE, EPS, 시가총액 (전종목)
  2. Naver Finance main.naver — 재무제표 시계열 (개별 종목)
  3. pykrx — OHLCV
"""

import re
import time
import requests
import pandas as pd
from bs4 import BeautifulSoup
from pykrx import stock

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://finance.naver.com/",
    "Accept-Language": "ko-KR,ko;q=0.9",
}

_CRAWL_DELAY = 0.5  # 네이버 크롤링 최소 간격(초)

# Naver sise_market_sum: sosok 코드
_MARKET_SOSOK = {"KOSPI": "0", "KOSDAQ": "1"}

# ETF/ETN 브랜드 첫 단어 (대문자 기준)
_ETF_BRANDS: frozenset[str] = frozenset({
    "KODEX", "TIGER", "RISE", "ACE", "SOL", "PLUS", "HANARO", "KIWOOM",
    "1Q", "TIME", "KOACT", "WON", "HK", "FOCUS", "TREX", "VITA",
    "DAISHIN343", "BNK", "MIDAS", "UNICORN", "KCGI", "IBK",
    "에셋플러스", "파워", "마이티",
})


def is_etf_etn(name: str) -> bool:
    """종목명 기반 ETF/ETN 여부 판별."""
    if not isinstance(name, str) or not name.strip():
        return False
    if "ETN" in name.upper():
        return True
    first_word = name.strip().split()[0].upper()
    return first_word in _ETF_BRANDS


def _get_sise_session() -> requests.Session:
    """PBR 컬럼이 활성화된 Naver sise 세션 반환."""
    sess = requests.Session()
    sess.headers.update(_HEADERS)
    # field_submit POST: pbr 컬럼 추가
    fields = ["market_sum", "frgn_rate", "listed_stock_cnt", "per", "roe", "pbr", "eps", "quant"]
    data = {"menu": "market_sum",
            "returnUrl": "http://finance.naver.com/sise/sise_market_sum.naver?sosok=0"}
    for f in fields:
        data.setdefault("fieldIds", [])
        if isinstance(data["fieldIds"], list):
            data["fieldIds"].append(f)
    resp = sess.post(
        "https://finance.naver.com/sise/field_submit.naver",
        data=data,
        timeout=10,
    )
    resp.raise_for_status()
    return sess


def _parse_sise_page(soup: BeautifulSoup, market: str) -> list[dict]:
    """sise_market_sum 페이지에서 종목 데이터 파싱."""
    table = soup.find("table", class_="type_2")
    if table is None:
        return []

    headers = [th.get_text(strip=True) for th in table.find_all("th")]
    # 컬럼 인덱스 매핑
    col_map: dict[str, int] = {}
    for i, h in enumerate(headers):
        col_map[h] = i

    records = []
    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 5:
            continue
        link = cells[1].find("a") if len(cells) > 1 else None
        if link is None:
            continue
        href = link.get("href", "")
        m = re.search(r"code=(\d+)", href)
        if not m:
            continue
        ticker = m.group(1).zfill(6)
        name = link.get_text(strip=True)

        def _cell(col_name: str) -> float | None:
            idx = col_map.get(col_name)
            if idx is None or idx >= len(cells):
                return None
            raw = cells[idx].get_text(strip=True).replace(",", "").replace("%", "")
            try:
                return float(raw)
            except ValueError:
                return None

        records.append({
            "ticker": ticker,
            "name": name,
            "market": market,
            "pbr": _cell("PBR"),
            "per": _cell("PER"),
            "roe": _cell("ROE"),
            "eps": _cell("주당순이익"),
            "marcap": _cell("시가총액"),  # 단위: 억원
        })
    return records


def _scrape_sise_market(sess: requests.Session, market: str) -> list[dict]:
    """sise_market_sum 전 페이지 스크랩."""
    sosok = _MARKET_SOSOK.get(market, "0")
    base_url = f"https://finance.naver.com/sise/sise_market_sum.naver?sosok={sosok}"

    # 1페이지에서 총 페이지 수 파악
    resp = sess.get(f"{base_url}&page=1", timeout=10)
    html = resp.content.decode("euc-kr", errors="replace")
    soup = BeautifulSoup(html, "lxml")

    pgrr = soup.find("td", class_="pgRR")
    last_page = 1
    if pgrr:
        a = pgrr.find("a")
        if a:
            pm = re.search(r"page=(\d+)", a.get("href", ""))
            if pm:
                last_page = int(pm.group(1))

    all_records = _parse_sise_page(soup, market)

    for page in range(2, last_page + 1):
        time.sleep(_CRAWL_DELAY)
        try:
            resp = sess.get(f"{base_url}&page={page}", timeout=10)
            html = resp.content.decode("euc-kr", errors="replace")
            soup = BeautifulSoup(html, "lxml")
            all_records.extend(_parse_sise_page(soup, market))
        except Exception:
            continue

    return all_records


# ──────────────────────────────────────────────
# 공개 API
# ──────────────────────────────────────────────

def get_all_stocks_valuation(market: str = "ALL") -> pd.DataFrame:
    """KOSPI+KOSDAQ 전종목 PBR/PER/ROE/EPS/시가총액 수집.

    Args:
        market: "KOSPI" | "KOSDAQ" | "ALL"

    Returns:
        DataFrame 컬럼: ticker, name, market, pbr, per, roe, eps, marcap
    """
    sess = _get_sise_session()
    markets = ["KOSPI", "KOSDAQ"] if market == "ALL" else [market]

    all_records = []
    for mkt in markets:
        all_records.extend(_scrape_sise_market(sess, mkt))

    if not all_records:
        return pd.DataFrame(columns=["ticker", "name", "market", "pbr", "per", "roe", "eps", "marcap"])

    df = pd.DataFrame(all_records)
    df = df[["ticker", "name", "market", "pbr", "per", "roe", "eps", "marcap"]]
    df = df.drop_duplicates(subset=["ticker"]).reset_index(drop=True)
    df["is_etf"] = df["name"].apply(is_etf_etn)
    return df


def get_industry_map() -> dict[str, str]:
    """네이버 업종(upjong) 그룹 전체를 순회하여 종목코드 → 업종명 매핑 반환.

    79개 그룹 × 크롤링 = 최초 약 30~60초, 이후 24시간 캐시 권장.
    """
    url_groups = "https://finance.naver.com/sise/sise_group.naver?type=upjong"
    resp = requests.get(url_groups, headers=_HEADERS, timeout=10)
    html = resp.content.decode("euc-kr", errors="replace")
    soup = BeautifulSoup(html, "lxml")

    groups: list[tuple[str, str]] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        m = re.search(r"no=(\d+)", a["href"])
        if m and "upjong" in a["href"] and m.group(1) not in seen:
            seen.add(m.group(1))
            groups.append((m.group(1), a.get_text(strip=True)))

    ticker_to_industry: dict[str, str] = {}
    for no, name in groups:
        time.sleep(_CRAWL_DELAY)
        try:
            url_detail = (
                f"https://finance.naver.com/sise/sise_group_detail.naver"
                f"?type=upjong&no={no}"
            )
            r = requests.get(url_detail, headers=_HEADERS, timeout=10)
            codes = re.findall(r"code=(\d{6})", r.content.decode("euc-kr", errors="replace"))
            for code in set(codes):
                ticker_to_industry[code] = name
        except Exception:
            continue

    return ticker_to_industry


def get_realtime_price(ticker: str) -> int | None:
    """네이버 금융 현재가 실시간 수집 (캐싱 없음).

    Returns:
        현재가 (원) or None (장 마감 / 수집 실패 시)
    """
    ticker = str(ticker).zfill(6)
    url = f"https://finance.naver.com/item/main.naver?code={ticker}"
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=8)
        soup = BeautifulSoup(resp.content, "lxml")
        for sel in ["#_nowVal", "p.no_today strong", ".no_today .blind"]:
            el = soup.select_one(sel)
            if el:
                text = re.sub(r"[^\d]", "", el.get_text())
                if text:
                    return int(text)
    except Exception:
        pass
    return None


def get_ohlcv(ticker: str, start: str, end: str) -> pd.DataFrame:
    """주가 OHLCV 수집 (pykrx).

    Args:
        ticker: 6자리 종목코드
        start / end: "YYYYMMDD" 형식

    Returns:
        DataFrame 컬럼: date, open, high, low, close, volume
    """
    ticker = str(ticker).zfill(6)
    df = stock.get_market_ohlcv(start, end, ticker)
    if df.empty:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
    df = df.reset_index()
    df.columns = ["date", "open", "high", "low", "close", "volume"] + list(df.columns[6:])
    return df[["date", "open", "high", "low", "close", "volume"]]


# ──────────────────────────────────────────────
# 네이버 금융 크롤링 함수
# ──────────────────────────────────────────────

def _fetch_naver_main(ticker: str) -> BeautifulSoup:
    """finance.naver.com/item/main.naver 파싱."""
    ticker = str(ticker).zfill(6)
    url = f"https://finance.naver.com/item/main.naver?code={ticker}"
    resp = requests.get(url, headers=_HEADERS, timeout=10)
    resp.raise_for_status()
    # bytes 직접 전달 → lxml이 meta charset(euc-kr) 기반으로 자동 디코딩
    return BeautifulSoup(resp.content, "lxml")


def _parse_main_table(soup: BeautifulSoup) -> tuple[list[str], dict[str, list]]:
    """main.naver의 주요재무정보 테이블에서 연간 연도 헤더와 행 데이터 추출.

    Returns:
        (years, rows)
        years: ["2022.12", "2023.12", "2024.12"] 형태의 연간 컬럼 목록
        rows: {"ROE(지배주주)": [4.15, 9.03, ...], "매출액": [...], ...}
    """
    # class에 tb_type1_ifrs 또는 tb_type1 + tb_num 포함 테이블
    table = soup.find(
        "table",
        class_=lambda c: c and "tb_type1" in c and "tb_num" in c,
    )
    if table is None:
        return [], {}

    all_rows = table.find_all("tr")
    if len(all_rows) < 2:
        return [], {}

    # 헤더 행: 연도 파싱 (분기 컬럼 제외 → "XXXX.12" 형태이고 "(E)" 없는 것만)
    header_cells = all_rows[1].find_all(["th", "td"])
    all_headers = [c.get_text(strip=True) for c in header_cells]

    # 연간 컬럼 인덱스 결정 (분기는 month != 12 이거나 "(E)" 포함)
    annual_indices = []
    annual_years = []
    for i, h in enumerate(all_headers):
        if not h:
            continue
        # "(E)" 제거 후 연도.월 형태 확인
        h_clean = h.replace("(E)", "").strip()
        if "." in h_clean:
            parts = h_clean.split(".")
            if len(parts) == 2 and parts[1].zfill(2) == "12" and "(E)" not in h:
                annual_indices.append(i)
                annual_years.append(h_clean)

    if not annual_indices:
        return [], {}

    # 데이터 행 파싱
    rows: dict[str, list] = {}
    for row in all_rows[3:]:  # 처음 3행(헤더) 스킵
        cells = row.find_all(["th", "td"])
        if not cells:
            continue
        label = cells[0].get_text(strip=True)
        if not label:
            continue
        values = []
        for i in annual_indices:
            if i < len(cells):
                raw = cells[i].get_text(strip=True).replace(",", "")
                try:
                    values.append(float(raw))
                except ValueError:
                    values.append(None)
            else:
                values.append(None)
        rows[label] = values

    return annual_years, rows


def get_stock_roe(ticker: str, years: int = 5) -> pd.DataFrame:
    """네이버 금융 크롤링으로 ROE 시계열 수집.

    Args:
        ticker: 6자리 종목코드
        years: 최대 반환 연수 (최신 기준 소급)

    Returns:
        DataFrame 컬럼: year, roe
    """
    try:
        time.sleep(_CRAWL_DELAY)
        soup = _fetch_naver_main(ticker)
        annual_years, rows = _parse_main_table(soup)
    except Exception:
        return pd.DataFrame(columns=["year", "roe"])

    # ROE 행 찾기 (레이블이 "ROE" 포함)
    roe_values = None
    for label, vals in rows.items():
        if "ROE" in label:
            roe_values = vals
            break

    if roe_values is None or not annual_years:
        return pd.DataFrame(columns=["year", "roe"])

    df = pd.DataFrame({"year": annual_years, "roe": roe_values})
    df["year"] = df["year"].str[:4].astype(int)  # "2023.12" → 2023
    df = df.dropna(subset=["roe"])
    df = df.sort_values("year", ascending=True).tail(years).reset_index(drop=True)
    return df


def get_stock_financials(ticker: str) -> dict:
    """재무제표 시계열 수집 (네이버 main.naver).

    Returns:
        {
          "years": [2022, 2023, 2024],
          "revenue": [2589355, ...],    # 억원
          "op_income": [65670, ...],
          "net_income": [154871, ...],
          "roe": [4.15, ...],
          "eps": [2131, ...],
          "bps": [52002, ...],
          "pbr": [1.51, ...],
          "per": [36.84, ...],
        }
    """
    try:
        time.sleep(_CRAWL_DELAY)
        soup = _fetch_naver_main(ticker)
        annual_years, rows = _parse_main_table(soup)
    except Exception:
        return {}

    if not annual_years:
        return {}

    year_ints = [int(y[:4]) for y in annual_years]

    def _get(key_fragment: str) -> list:
        for label, vals in rows.items():
            if key_fragment in label:
                return vals
        return [None] * len(annual_years)

    return {
        "years": year_ints,
        "revenue": _get("매출액"),
        "op_income": _get("영업이익"),
        "net_income": _get("당기순이익"),
        "roe": _get("ROE"),
        "eps": _get("EPS"),
        "bps": _get("BPS"),
        "pbr": _get("PBR"),
        "per": _get("PER"),
    }
