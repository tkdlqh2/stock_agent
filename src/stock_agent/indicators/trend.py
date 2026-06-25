"""추세·구조 — 고점·저점 동시 방향, Higher Low, 이평선/골든크로스.

계산 기준 (명세서 고정):
- 이평선: 20/60/120일 SMA
- 진짜 골든크로스 = 120일선이 '상승 중'인 교차
- Higher Low = 상승 구조 핵심
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def sma(close: pd.Series, window: int) -> pd.Series:
    return close.rolling(window, min_periods=window).mean()


def swing_points(series: pd.Series, order: int = 5) -> tuple[pd.Index, pd.Index]:
    """국소 고점/저점(스윙) 인덱스. order = 좌우 비교 폭.

    한 점이 좌우 `order`개보다 모두 높으면 스윙 고점, 모두 낮으면 스윙 저점.
    """
    values = series.to_numpy()
    n = len(values)
    highs, lows = [], []
    for i in range(order, n - order):
        window = values[i - order : i + order + 1]
        center = values[i]
        if center == window.max() and (window.argmax() == order):
            highs.append(series.index[i])
        if center == window.min() and (window.argmin() == order):
            lows.append(series.index[i])
    return pd.Index(highs), pd.Index(lows)


def structure_direction(close: pd.Series, order: int = 5) -> str:
    """고점·저점 동시 방향으로 추세 판정 -> '상승'/'하락'/'횡보'."""
    high_idx, low_idx = swing_points(close, order)
    if len(high_idx) < 2 or len(low_idx) < 2:
        return "횡보"
    highs = close.loc[high_idx]
    lows = close.loc[low_idx]
    higher_high = highs.iloc[-1] > highs.iloc[-2]
    higher_low = lows.iloc[-1] > lows.iloc[-2]
    lower_high = highs.iloc[-1] < highs.iloc[-2]
    lower_low = lows.iloc[-1] < lows.iloc[-2]
    if higher_high and higher_low:
        return "상승"
    if lower_high and lower_low:
        return "하락"
    return "횡보"


def has_higher_low(close: pd.Series, order: int = 5) -> bool:
    """최근 두 스윙 저점이 Higher Low 인가 (상승 구조 핵심)."""
    _, low_idx = swing_points(close, order)
    if len(low_idx) < 2:
        return False
    lows = close.loc[low_idx]
    return bool(lows.iloc[-1] > lows.iloc[-2])


def golden_cross(
    close: pd.Series, short: int = 20, long: int = 60, anchor: int = 120
) -> bool:
    """진짜 골든크로스 = 단기선이 장기선을 상향 교차 + anchor(120일)선이 상승 중.

    마지막 봉에서 막 교차가 일어났고, 120일선 기울기가 양(+)일 때만 True.
    """
    s = sma(close, short)
    l = sma(close, long)
    a = sma(close, anchor)
    if s.isna().iloc[-1] or l.isna().iloc[-1] or a.isna().iloc[-2:].any():
        return False
    crossed_up = (s.iloc[-2] <= l.iloc[-2]) and (s.iloc[-1] > l.iloc[-1])
    anchor_rising = a.iloc[-1] > a.iloc[-2]
    return bool(crossed_up and anchor_rising)


def ma_stack(close: pd.Series) -> dict[str, float]:
    """현재 20/60/120 SMA 값 (NaN 가능)."""
    return {
        "sma20": float(sma(close, 20).iloc[-1]),
        "sma60": float(sma(close, 60).iloc[-1]),
        "sma120": float(sma(close, 120).iloc[-1]),
    }
