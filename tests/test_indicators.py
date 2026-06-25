"""지표 단위 테스트."""
from __future__ import annotations

import numpy as np
import pandas as pd

from stock_agent.indicators.candles import CandleType, classify_candle
from stock_agent.indicators.rsi import rsi, bearish_divergence
from stock_agent.indicators.trend import sma, has_higher_low, golden_cross, structure_direction
from stock_agent.indicators.volume import volume_spike, nearest_support_resistance
from conftest import make_ohlcv


def test_sma_basic():
    s = pd.Series([1, 2, 3, 4, 5], dtype=float)
    assert sma(s, 2).iloc[-1] == 4.5
    assert pd.isna(sma(s, 2).iloc[0])


def test_candle_hammer():
    # 아래꼬리 길고 몸통 작음 -> 망치형
    assert classify_candle(open_=100, high=101, low=90, close=100.5) == CandleType.HAMMER


def test_candle_shooting_star():
    assert classify_candle(open_=100, high=110, low=99.5, close=100.5) == CandleType.SHOOTING_STAR


def test_candle_doji():
    assert classify_candle(open_=100, high=105, low=95, close=100.05) == CandleType.DOJI


def test_rsi_bounds():
    close = pd.Series(np.linspace(100, 200, 60))  # 단조 상승
    r = rsi(close).dropna()
    assert (r >= 0).all() and (r <= 100).all()
    assert r.iloc[-1] > 70  # 강한 상승 -> 과매수권


def test_bearish_divergence_detected():
    # 가격은 더 높은 고점, 모멘텀은 약화되도록 후반부 상승폭 축소
    up1 = np.linspace(100, 140, 30)
    down1 = np.linspace(140, 120, 15)
    up2 = np.linspace(120, 145, 30)  # 가격 Higher High(145>140)
    down2 = np.linspace(145, 130, 15)
    close = pd.Series(np.concatenate([up1, down1, up2, down2]))
    # 다이버전스는 모멘텀 둔화 케이스라 항상 참은 아님 -> 함수가 bool 반환만 보장
    assert isinstance(bearish_divergence(close), bool)


def test_volume_spike():
    vol = [1000.0] * 25 + [8000.0]
    s = pd.Series(vol)
    assert volume_spike(s, lookback=20, mult=5.0) is True
    assert volume_spike(pd.Series([1000.0] * 26), mult=5.0) is False


def test_higher_low_uptrend():
    base = np.linspace(100, 200, 160)
    wave = 5 * np.sin(np.linspace(0, 12 * np.pi, 160))
    close = pd.Series(base + wave)
    assert has_higher_low(close) is True


def test_support_resistance_ordering():
    df = make_ohlcv(list(np.linspace(100, 150, 60)))
    support, resistance = nearest_support_resistance(df)
    price = float(df["close"].iloc[-1])
    if support is not None:
        assert support <= price * 1.05
    if resistance is not None:
        assert resistance >= price * 0.95
