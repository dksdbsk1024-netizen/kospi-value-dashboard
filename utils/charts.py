import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from utils.styles import COLOR

BASE_LAYOUT = dict(
    font=dict(family="Noto Sans KR, sans-serif", size=12, color="#111827"),
    plot_bgcolor="white",
    paper_bgcolor="white",
    xaxis=dict(gridcolor="#f3f4f6", gridwidth=0.5, linecolor="#e5e7eb"),
    yaxis=dict(gridcolor="#f3f4f6", gridwidth=0.5, linecolor="#e5e7eb"),
    margin=dict(l=40, r=20, t=40, b=40),
    hoverlabel=dict(font_family="Noto Sans KR, sans-serif"),
)


def apply_layout(fig: go.Figure, title: str = "") -> go.Figure:
    """fig에 BASE_LAYOUT을 적용하고 제목을 설정한다."""
    fig.update_layout(**BASE_LAYOUT)
    if title:
        fig.update_layout(title=dict(text=title, font=dict(size=15, color="#111827")))
    return fig


def line_chart(
    df: pd.DataFrame,
    x: str,
    y: str | list,
    title: str = "",
    colors: list | None = None,
    y_suffix: str = "",
) -> go.Figure:
    """단일 또는 다중 라인 차트. 매크로 추이, 재무 시계열에 사용."""
    fig = go.Figure()
    ys = [y] if isinstance(y, str) else y
    default_colors = [COLOR["primary"], COLOR["positive"], COLOR["warning"], COLOR["negative"]]
    palette = colors or default_colors

    for i, col in enumerate(ys):
        fig.add_trace(
            go.Scatter(
                x=df[x],
                y=df[col],
                name=col,
                mode="lines",
                line=dict(color=palette[i % len(palette)], width=2),
                hovertemplate=f"%{{x}}<br>{col}: %{{y}}{y_suffix}<extra></extra>",
            )
        )

    apply_layout(fig, title)
    return fig


def bar_chart(
    df: pd.DataFrame,
    x: str,
    y: str | list,
    title: str = "",
    colors: list | None = None,
    barmode: str = "group",
    y_suffix: str = "",
) -> go.Figure:
    """단일 또는 그룹 바차트. 듀퐁 분석, 섹터 비교, 연도별 재무에 사용."""
    fig = go.Figure()
    ys = [y] if isinstance(y, str) else y
    default_colors = [COLOR["primary"], COLOR["positive"], COLOR["warning"], COLOR["negative"]]
    palette = colors or default_colors

    for i, col in enumerate(ys):
        fig.add_trace(
            go.Bar(
                x=df[x],
                y=df[col],
                name=col,
                marker_color=palette[i % len(palette)],
                hovertemplate=f"%{{x}}<br>{col}: %{{y}}{y_suffix}<extra></extra>",
            )
        )

    apply_layout(fig, title)
    fig.update_layout(barmode=barmode)
    return fig


def bubble_chart(
    df: pd.DataFrame,
    x: str,
    y: str,
    size: str,
    color: str,
    title: str = "",
    hover_name: str = "",
    pbr_threshold: float = 1.0,
    roe_threshold: float = 8.0,
) -> go.Figure:
    """PBR×ROE 4사분면 버블차트.

    색상 규칙 (01_design.md):
      저PBR+고ROE → primary (#2F64E3)
      고PBR+고ROE → text_muted (#6b7280)
      저PBR+저ROE → warning (#f59e0b)
      고PBR+저ROE → negative (#ef4444)
    """
    def _quad_color(row):
        low_pbr = row[y] <= pbr_threshold
        high_roe = row[x] >= roe_threshold
        if low_pbr and high_roe:
            return COLOR["primary"]
        elif not low_pbr and high_roe:
            return COLOR["text_muted"]
        elif low_pbr and not high_roe:
            return COLOR["warning"]
        else:
            return COLOR["negative"]

    marker_colors = df.apply(_quad_color, axis=1).tolist()

    max_size = df[size].max() if df[size].max() > 0 else 1
    bubble_sizes = (df[size] / max_size * 40 + 5).tolist()

    hover_col = hover_name if hover_name and hover_name in df.columns else None
    hover_text = df[hover_col].tolist() if hover_col else df.index.tolist()

    fig = go.Figure(
        go.Scatter(
            x=df[x],
            y=df[y],
            mode="markers",
            marker=dict(
                size=bubble_sizes,
                color=marker_colors,
                opacity=0.75,
                line=dict(width=0.5, color="white"),
            ),
            text=hover_text,
            hovertemplate=(
                "<b>%{text}</b><br>"
                f"ROE: %{{x:.1f}}%<br>"
                f"PBR: %{{y:.2f}}x<extra></extra>"
            ),
        )
    )

    # 사분면 기준선
    fig.add_hline(y=pbr_threshold, line_dash="dash", line_color="#d1d5db", line_width=1)
    fig.add_vline(x=roe_threshold, line_dash="dash", line_color="#d1d5db", line_width=1)

    apply_layout(fig, title)
    fig.update_layout(
        xaxis_title=f"ROE (%)",
        yaxis_title="PBR (배)",
    )
    return fig


def candlestick_chart(df: pd.DataFrame, title: str = "") -> go.Figure:
    """기술적 분석용 캔들스틱 + 거래량 바차트.

    df 필수 컬럼: date(또는 index), open, high, low, close, volume
    """
    date_col = "date" if "date" in df.columns else df.index

    volume_colors = [
        COLOR["negative"] if c >= o else COLOR["primary"]
        for c, o in zip(df["close"], df["open"])
    ]

    fig = go.Figure()
    fig.add_trace(
        go.Candlestick(
            x=date_col if isinstance(date_col, str) else df.index,
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name="가격",
            increasing_line_color=COLOR["negative"],
            decreasing_line_color=COLOR["primary"],
        )
    )

    apply_layout(fig, title)
    fig.update_layout(xaxis_rangeslider_visible=False)
    return fig


def volume_chart(df: pd.DataFrame, title: str = "") -> go.Figure:
    """거래량 바차트 (캔들스틱과 함께 사용)."""
    date_col = df["date"] if "date" in df.columns else df.index
    colors = [
        COLOR["negative"] if c >= o else COLOR["primary"]
        for c, o in zip(df["close"], df["open"])
    ]
    fig = go.Figure(
        go.Bar(
            x=date_col,
            y=df["volume"],
            marker_color=colors,
            name="거래량",
            hovertemplate="%{x}<br>거래량: %{y:,}<extra></extra>",
        )
    )
    apply_layout(fig, title)
    return fig


def heatmap_chart(
    df: pd.DataFrame,
    title: str = "",
    x_label: str = "",
    y_label: str = "",
    colorscale: str = "Blues",
) -> go.Figure:
    """섹터별 PBR×ROE 히트맵.

    df: pivot 형태 (index=섹터, columns=지표, values=수치)
    """
    fig = go.Figure(
        go.Heatmap(
            z=df.values,
            x=df.columns.tolist(),
            y=df.index.tolist(),
            colorscale=colorscale,
            hovertemplate="%{y} / %{x}<br>값: %{z:.2f}<extra></extra>",
        )
    )
    apply_layout(fig, title)
    if x_label:
        fig.update_layout(xaxis_title=x_label)
    if y_label:
        fig.update_layout(yaxis_title=y_label)
    return fig
