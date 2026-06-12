"""
PBR-ROE 기반 투자 판단 핵심 로직.

  PBR = PER × ROE  (항등식)
  저PBR + 고ROE → 저평가 우량주 (목표)
  저PBR + 저ROE → 가치함정 (주의)
"""

from __future__ import annotations

# 4사분면 분류 임계값 기본값
_PBR_THRESHOLD = 1.0
_ROE_THRESHOLD = 15.0  # %


def get_quadrant(
    pbr: float,
    roe: float,
    pbr_threshold: float = _PBR_THRESHOLD,
    roe_threshold: float = _ROE_THRESHOLD,
) -> str:
    """PBR-ROE 4사분면 분류.

    Returns:
        "low_pbr_high_roe" | "high_pbr_high_roe" |
        "low_pbr_low_roe"  | "high_pbr_low_roe"
    """
    low_pbr = pbr <= pbr_threshold
    high_roe = roe >= roe_threshold
    if low_pbr and high_roe:
        return "low_pbr_high_roe"
    if not low_pbr and high_roe:
        return "high_pbr_high_roe"
    if low_pbr and not high_roe:
        return "low_pbr_low_roe"
    return "high_pbr_low_roe"


def get_investment_signal(
    pbr: float,
    roe: float,
    pbr_threshold: float = 1.0,
    roe_threshold: float = 15.0,
) -> dict:
    """PBR-ROE 4사분면 기반 투자 판단 신호 반환.

    4사분면 해석표:
      저PBR + 고ROE → 저평가 우량  (#2F64E3)  전략: 적극 매수 검토
      고PBR + 고ROE → 고평가 우량  (#6b7280)  전략: 진입 시점 주의
      저PBR + 저ROE → 가치함정     (#f59e0b)  전략: 실적 개선 확인 필수
      고PBR + 저ROE → 고평가 위험  (#ef4444)  전략: 회피

    Returns:
        {label, color, description, strategy, quadrant}
    """
    q = get_quadrant(pbr, roe, pbr_threshold=pbr_threshold, roe_threshold=roe_threshold)

    if pbr <= pbr_threshold:
        if roe >= roe_threshold:
            return {
                "label": "저평가 우량",
                "color": "#2F64E3",
                "description": "저PBR + 고ROE — 핵심 목표 영역. 적극 검토 대상.",
                "strategy": "적극 매수 검토",
                "quadrant": q,
            }
        return {
            "label": "가치함정",
            "color": "#f59e0b",
            "description": "저PBR이지만 수익성 낮음 — 싸 보이지만 ROE 부진. 실적 개선 확인 필수.",
            "strategy": "실적 개선 확인 필수",
            "quadrant": q,
        }
    else:
        if roe >= roe_threshold:
            return {
                "label": "고평가 우량",
                "color": "#6b7280",
                "description": "ROE 우수하지만 이미 시장에 반영된 가격. 진입 시점 주의.",
                "strategy": "진입 시점 주의",
                "quadrant": q,
            }
        return {
            "label": "고평가 위험",
            "color": "#ef4444",
            "description": "고PBR + 저ROE — 최악의 조합. 회피 권고.",
            "strategy": "회피",
            "quadrant": q,
        }


def get_badge_label(pbr: float, roe: float) -> str:
    """뱃지 레이블 문자열만 반환 (테이블 표시용)."""
    return get_investment_signal(pbr, roe)["label"]


def decompose_pbr(pbr: float, per: float, roe: float) -> dict:
    """PBR = PER × ROE 항등식 분해 및 일관성 검증.

    Returns:
        {pbr_actual, pbr_calc, per, roe_pct, is_consistent, diff_pct}
    """
    roe_decimal = roe / 100.0 if roe > 1 else roe  # % → 소수
    pbr_calc = per * roe_decimal
    diff = abs(pbr - pbr_calc) / max(abs(pbr), 1e-9)
    return {
        "pbr_actual": pbr,
        "pbr_calc": round(pbr_calc, 3),
        "per": per,
        "roe_pct": roe if roe > 1 else roe * 100,
        "is_consistent": diff < 0.15,  # 15% 이내면 일관적
        "diff_pct": round(diff * 100, 1),
    }


def dupont_analysis(
    net_margin: float,
    asset_turnover: float,
    leverage: float,
) -> float:
    """듀퐁 분석: ROE = 순이익률 × 자산회전율 × 재무레버리지.

    Args:
        net_margin: 순이익률 (예: 0.05 = 5%)
        asset_turnover: 자산회전율 (예: 0.8)
        leverage: 재무레버리지 = 총자산/자기자본

    Returns:
        ROE (소수, 예: 0.064 = 6.4%)
    """
    return net_margin * asset_turnover * leverage


def dupont_decompose(revenue: float, net_income: float,
                     total_assets: float, equity: float) -> dict:
    """재무제표 수치로 듀퐁 3요소 분해.

    Args:
        revenue: 매출액
        net_income: 당기순이익
        total_assets: 총자산
        equity: 자기자본

    Returns:
        {net_margin, asset_turnover, leverage, roe}
    """
    net_margin = net_income / revenue if revenue else 0.0
    asset_turnover = revenue / total_assets if total_assets else 0.0
    leverage = total_assets / equity if equity else 0.0
    roe = net_margin * asset_turnover * leverage
    return {
        "net_margin": round(net_margin * 100, 2),       # %
        "asset_turnover": round(asset_turnover, 4),
        "leverage": round(leverage, 2),
        "roe": round(roe * 100, 2),                     # %
    }


def get_phase_label(rate_direction: str, eps_direction: str) -> dict:
    """금리 방향 + EPS 방향으로 경기 국면 판단.

    금리/EPS 방향 기반 국면 분류:
      금리↓ + EPS↑ → 금융장세  (초기 상승, 저PBR 반등)
      금리↑ + EPS↑ → 실적장세  (주도주 매수 유지)
      금리↑ + EPS↓ → 역금융장세 (방어주·현금 비중 확대)
      금리↓ + EPS↓ → 역실적장세 (추가 하락 위험, 현금 보유)

    Args:
        rate_direction: "up" | "down" | "flat"
        eps_direction:  "up" | "down" | "flat"

    Returns:
        {phase, label, strategy, favorable_sectors}
    """
    key = (rate_direction, eps_direction)
    phases = {
        ("down", "up"): {
            "phase": "금융장세",
            "label": "📈 금융장세",
            "strategy": "저PBR 주식 반등 포착, 주식 비중 확대",
            "favorable_sectors": ["건설", "금융", "유통", "저PBR 가치주"],
        },
        ("up", "up"): {
            "phase": "실적장세",
            "label": "🚀 실적장세",
            "strategy": "실적 주도주 매수 유지, 고ROE 성장주 집중",
            "favorable_sectors": ["IT", "반도체", "자동차", "방산", "조선"],
        },
        ("up", "down"): {
            "phase": "역금융장세",
            "label": "⚠️ 역금융장세",
            "strategy": "방어주 비중 확대, 고배당·유틸리티·헬스케어 선호",
            "favorable_sectors": ["유틸리티", "헬스케어", "필수소비재", "통신"],
        },
        ("down", "down"): {
            "phase": "역실적장세",
            "label": "🔴 역실적장세",
            "strategy": "현금 비중 최대화, 추가 하락 위험 대비",
            "favorable_sectors": ["현금", "채권", "금"],
        },
    }
    result = phases.get(key)
    if result is None:
        return {
            "phase": "판단 불가",
            "label": "❓ 방향 불명확",
            "strategy": "금리·EPS 방향 명확해질 때까지 관망",
            "favorable_sectors": [],
        }
    return result
