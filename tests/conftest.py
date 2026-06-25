"""테스트용 합성 데이터 헬퍼 — 네트워크/ pykrx 불필요."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def make_ohlcv(close: list[float], volume: list[float] | None = None) -> pd.DataFrame:
    """종가 리스트로 단순 OHLCV 생성 (시/고/저는 종가에서 파생)."""
    close_arr = np.array(close, dtype=float)
    n = len(close_arr)
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    open_ = np.concatenate([[close_arr[0]], close_arr[:-1]])
    high = np.maximum(open_, close_arr) * 1.01
    low = np.minimum(open_, close_arr) * 0.99
    vol = np.array(volume, dtype=float) if volume is not None else np.full(n, 1000.0)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close_arr, "volume": vol},
        index=idx,
    )


@pytest.fixture
def uptrend_df() -> pd.DataFrame:
    # 톱니형 상승: 분명한 Higher High / Higher Low 구조
    base = np.linspace(100, 200, 160)
    wave = 5 * np.sin(np.linspace(0, 12 * np.pi, 160))
    return make_ohlcv(list(base + wave))


@pytest.fixture
def supply_rocket() -> pd.DataFrame:
    n = 30
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    return pd.DataFrame(
        {"foreign": np.full(n, 1e8), "institution": np.full(n, 5e7), "individual": np.full(n, -1.5e8)},
        index=idx,
    )
