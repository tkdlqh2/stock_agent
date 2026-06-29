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


def classify_position(
    df: pd.DataFrame,
    *,
    new_high_lookback: int | None = None,
    range_lookback: int = 60,
) -> ChartPosition:
    """OHLCV DataFrame -> ChartPosition.

    new_high_lookback: 신고가 비교 구간(None = 전체 기간 = 역사적 신고가).
    range_lookback: 레인지 내 위치(저점/고점) 계산 구간.

    핵심: **최근 레인지 내 위치를 단일 기준**으로 분류한다(상단=고점권/하단=저점권/중앙=박스권).
    거래량 매물대(지지/저항) 근접을 1차 기준으로 쓰면, 추세 바닥에서 위에 매물이 있다고
    '고점권', 추세 상단에서 아래에 지지가 있다고 '저점권'으로 오판하는 문제가 생긴다
    (금·IGF 실측 버그). 레인지 위치는 그런 오판이 없고 명세서 정의에 직접 대응한다.
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

    if pct >= 0.70:
        return ChartPosition.HIGH   # 3-3 고점권: 레인지 상단부(저항 테스트)
    if pct <= 0.30:
        return ChartPosition.LOW    # 3-1 저점권: 레인지 하단부(지지 테스트)
    return ChartPosition.BOX        # 3-2 박스권: 중앙부 횡보
