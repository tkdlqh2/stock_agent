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
from ..indicators.volume import nearest_support_resistance


def classify_position(
    df: pd.DataFrame,
    *,
    proximity: float = 0.03,
    new_high_lookback: int | None = None,
    range_lookback: int = 60,
) -> ChartPosition:
    """OHLCV DataFrame -> ChartPosition.

    proximity: 지지/저항 '근처' 판정 비율(기본 3%).
    new_high_lookback: 신고가 비교 구간(None = 전체 기간 = 역사적 신고가).
    range_lookback: 레인지 내 위치(저점/고점) 계산 구간.

    핵심: **레인지 내 위치를 1차 기준**으로 삼는다. 거래량 매물대(지지/저항)는 보조.
    이렇게 해야 하락추세 '바닥'에서 위에 국소 매물대가 있다는 이유로 '고점권'으로
    오판하지 않는다(역의 경우도 마찬가지). 명세서의 '고점권=상단부 저항 테스트',
    '저점권=하단부 지지 테스트' 정의에 맞춘다.
    """
    close = df["close"]
    price = float(close.iloc[-1])

    # 3-4 신고가: 역사적 고점 돌파(전체 또는 최근 구간 최고가 갱신)
    hist = close if new_high_lookback is None else close.iloc[-new_high_lookback:]
    prior_max = float(hist.iloc[:-1].max()) if len(hist) > 1 else price
    if price >= prior_max:
        return ChartPosition.NEW_HIGH

    # 최근 레인지 내 위치 (0=저점, 1=고점)
    window = close.iloc[-range_lookback:]
    lo, hi = float(window.min()), float(window.max())
    pct = (price - lo) / (hi - lo) if hi > lo else 0.5

    support, resistance = nearest_support_resistance(df)
    near_res = resistance is not None and price >= resistance * (1 - proximity)
    near_sup = support is not None and price <= support * (1 + proximity)

    # 3-1 저점권: 레인지 하단부 또는 지지 근접 (매물대가 위에 있어도 바닥이면 저점권)
    if pct <= 0.30 or near_sup:
        return ChartPosition.LOW
    # 3-3 고점권: 레인지 상단부에서 저항 테스트(또는 상단부 강세)
    if (pct >= 0.70 and near_res) or pct >= 0.85:
        return ChartPosition.HIGH
    # 그 외: 3-2 박스권
    return ChartPosition.BOX
