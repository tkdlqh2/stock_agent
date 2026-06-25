"""거래량 — 거래량 폭발, 매물대(지지·저항).

계산 기준 (명세서 고정):
- 거래량 폭발: 평소(이동평균) 대비 5~10배 (돌파 확증 조건)
- 매물대: 거래량 집중 가격대 = 지지/저항
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def volume_spike(volume: pd.Series, lookback: int = 20, mult: float = 5.0) -> bool:
    """마지막 봉 거래량이 직전 lookback 평균의 mult 배 이상인가."""
    if len(volume) < lookback + 1:
        return False
    baseline = volume.iloc[-(lookback + 1) : -1].mean()
    if baseline <= 0:
        return False
    return bool(volume.iloc[-1] >= baseline * mult)


def volume_profile(df: pd.DataFrame, bins: int = 20) -> pd.DataFrame:
    """가격 구간별 누적 거래량(매물대). 컬럼: price_low, price_high, volume.

    각 봉의 거래량을 대표가(종가)가 속한 가격 구간에 적재한다(근사).
    """
    price = df["close"].to_numpy()
    vol = df["volume"].to_numpy()
    lo, hi = price.min(), price.max()
    if hi <= lo:
        return pd.DataFrame(columns=["price_low", "price_high", "volume"])
    edges = np.linspace(lo, hi, bins + 1)
    idx = np.clip(np.digitize(price, edges) - 1, 0, bins - 1)
    agg = np.zeros(bins)
    for b, v in zip(idx, vol):
        agg[b] += v
    return pd.DataFrame(
        {"price_low": edges[:-1], "price_high": edges[1:], "volume": agg}
    )


def nearest_support_resistance(
    df: pd.DataFrame, bins: int = 20, top: int = 3
) -> tuple[float | None, float | None]:
    """현재가 기준 가장 가까운 지지(아래)·저항(위) 매물대 중심가.

    거래량 상위 `top` 매물대 중에서 현재가 아래 최댓값=지지, 위 최솟값=저항.
    """
    prof = volume_profile(df, bins)
    if prof.empty:
        return None, None
    prof = prof.sort_values("volume", ascending=False).head(top)
    centers = ((prof["price_low"] + prof["price_high"]) / 2).to_numpy()
    price = float(df["close"].iloc[-1])
    below = [c for c in centers if c <= price]
    above = [c for c in centers if c >= price]
    support = max(below) if below else None
    resistance = min(above) if above else None
    return support, resistance
