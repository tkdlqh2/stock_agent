"""RSI(Wilder) + 하락 다이버전스.

명세서: 다이버전스는 일봉보다 주봉·월봉이 강한 신호. 큰 프레임 우선.
하락 다이버전스 = 가격 고점은 높아지는데 RSI 고점은 낮아짐 (4-1 트리거).
"""
from __future__ import annotations

import pandas as pd

from .trend import swing_points


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder RSI."""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss
    out = 100 - (100 / (1 + rs))
    out[avg_loss == 0] = 100.0
    return out


def bearish_divergence(
    close: pd.Series, period: int = 14, order: int = 5
) -> bool:
    """하락 다이버전스 여부.

    최근 두 가격 스윙 고점에서 가격은 Higher High, RSI 는 Lower High 면 True.
    """
    r = rsi(close, period)
    high_idx, _ = swing_points(close, order)
    # RSI 가 유효한(=NaN 아님) 가격 스윙 고점만 사용
    valid = [i for i in high_idx if i in r.index and pd.notna(r.loc[i])]
    if len(valid) < 2:
        return False
    p_prev, p_last = close.loc[valid[-2]], close.loc[valid[-1]]
    r_prev, r_last = r.loc[valid[-2]], r.loc[valid[-1]]
    price_higher_high = p_last > p_prev
    rsi_lower_high = r_last < r_prev
    return bool(price_higher_high and rsi_lower_high)
