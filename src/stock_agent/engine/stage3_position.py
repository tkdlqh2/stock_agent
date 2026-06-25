"""단계3 — 차트 포지션 분류 (자동).

현재가를 4개 국면 중 하나로 분류한다.
  3-1 저점권   장기 이평/추세선 지지 테스트 + 하락멈춤 + 매도 거래량 위축
  3-2 박스권   지지~저항 사이 횡보, 변동성 수축
  3-3 고점권   강력 저항 매물대 테스트, 거래량 증가 주시
  3-4 신고가   역사적 신고가 돌파 + 대량 거래량 + 상단 매물 없음

분류는 결정론적 규칙이되, 임계값(근접도 등)은 운영하며 조정 대상.
"""
from __future__ import annotations

import pandas as pd

from ..models import ChartPosition
from ..indicators.trend import sma
from ..indicators.volume import nearest_support_resistance


def classify_position(
    df: pd.DataFrame,
    *,
    proximity: float = 0.03,
    new_high_lookback: int | None = None,
) -> ChartPosition:
    """OHLCV DataFrame -> ChartPosition.

    proximity: 지지/저항 '근처' 판정 비율(기본 3%).
    new_high_lookback: 신고가 비교 구간(None = 전체 기간 = 역사적 신고가).
    """
    close = df["close"]
    price = float(close.iloc[-1])

    # 3-4 신고가: 역사적 고점 돌파(전체 또는 최근 구간 최고가 갱신)
    hist = close if new_high_lookback is None else close.iloc[-new_high_lookback:]
    prior_max = float(hist.iloc[:-1].max()) if len(hist) > 1 else price
    if price >= prior_max:
        return ChartPosition.NEW_HIGH

    support, resistance = nearest_support_resistance(df)

    # 3-3 고점권: 저항 매물대 근접
    if resistance is not None and price >= resistance * (1 - proximity):
        return ChartPosition.HIGH

    # 3-1 저점권: 지지(또는 120일선) 근접
    sma120 = sma(close, 120)
    long_support = sma120.iloc[-1] if pd.notna(sma120.iloc[-1]) else None
    near_box_support = support is not None and price <= support * (1 + proximity)
    near_long_ma = long_support is not None and price <= long_support * (1 + proximity)
    if near_box_support or near_long_ma:
        return ChartPosition.LOW

    # 그 외: 지지~저항 사이 = 3-2 박스권
    return ChartPosition.BOX
