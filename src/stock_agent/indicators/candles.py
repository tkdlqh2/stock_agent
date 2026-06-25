"""캔들 판정 — 망치형/유성형/도지.

계산 기준 (명세서 고정):
- 망치형: 아래꼬리 >= 몸통 × 2~3 (반등 캔들, 4-3)
- 유성형: 위꼬리 >= 몸통 × 2~3 (고점 경고)
- 도지: 몸통 ≈ 0
"""
from __future__ import annotations

from enum import Enum

import pandas as pd


class CandleType(str, Enum):
    HAMMER = "망치형"
    SHOOTING_STAR = "유성형"
    DOJI = "도지"
    NEUTRAL = "중립"


def classify_candle(
    open_: float,
    high: float,
    low: float,
    close: float,
    *,
    tail_ratio: float = 2.0,
    doji_ratio: float = 0.1,
) -> CandleType:
    """단일 캔들 분류.

    tail_ratio: 꼬리/몸통 배수 임계(기본 2배). doji_ratio: 몸통/전체범위 임계.
    """
    rng = high - low
    if rng <= 0:
        return CandleType.DOJI
    body = abs(close - open_)
    upper = high - max(open_, close)
    lower = min(open_, close) - low

    # 방향성 꼬리 우선 판정 — 망치형/유성형은 몸통이 작아도 한쪽 꼬리가 지배적.
    if lower >= body * tail_ratio and upper <= body:
        return CandleType.HAMMER
    if upper >= body * tail_ratio and lower <= body:
        return CandleType.SHOOTING_STAR
    # 지배적 꼬리가 없고 몸통이 거의 0 -> 도지
    if body <= rng * doji_ratio:
        return CandleType.DOJI
    return CandleType.NEUTRAL


def classify_last(df: pd.DataFrame, **kwargs) -> CandleType:
    """DataFrame 마지막 봉 분류 (컬럼: open/high/low/close)."""
    row = df.iloc[-1]
    return classify_candle(
        float(row["open"]),
        float(row["high"]),
        float(row["low"]),
        float(row["close"]),
        **kwargs,
    )
