"""단계4 — 실행 신호 (자동).

포지션별 신호의 O/X 를 계산하고, '근거(신호 중첩)'를 함께 모은다.
수급 확증·매도 오버라이드는 상위(decide.py)에서 결합한다.

  4-1 RSI 하락 다이버전스   O -> 일부매도30% / X -> 홀딩
  4-2 저항 돌파+거래량 폭발  O -> 추격매수(확증 필요) / X -> 대기
  4-3 지지 반등             O -> 추격매수(확증 필요) / X -> 대기
  4-4 저점 방어 실패        O -> 대기 / X -> 4-3 으로
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from ..models import ChartPosition, SignalCode
from ..indicators.candles import classify_last, CandleType
from ..indicators.rsi import bearish_divergence
from ..indicators.trend import swing_points, has_higher_low
from ..indicators.volume import volume_spike, nearest_support_resistance


@dataclass
class SignalResult:
    code: SignalCode
    triggered: bool                       # 신호 조건 충족(O) 여부
    needs_supply_confirm: bool = False    # 4-2/4-3: 수급 확증 필요
    reasons: list[str] = field(default_factory=list)


def _signal_4_1(df: pd.DataFrame) -> SignalResult:
    div = bearish_divergence(df["close"])
    reasons = ["RSI 하락 다이버전스(가격↑·RSI↓)"] if div else []
    return SignalResult(SignalCode.S4_1, triggered=div, reasons=reasons)


def _signal_4_2(df: pd.DataFrame) -> SignalResult:
    _, resistance = nearest_support_resistance(df)
    price = float(df["close"].iloc[-1])
    broke = resistance is not None and price > resistance
    spike = volume_spike(df["volume"])
    reasons = []
    if broke:
        reasons.append("저항 매물대 돌파")
    if spike:
        reasons.append("거래량 폭발(평소 5~10배)")
    return SignalResult(
        SignalCode.S4_2,
        triggered=broke and spike,
        needs_supply_confirm=True,
        reasons=reasons,
    )


def _signal_4_3(df: pd.DataFrame) -> SignalResult:
    support, _ = nearest_support_resistance(df)
    price = float(df["close"].iloc[-1])
    at_support = support is not None and price <= support * 1.03
    candle = classify_last(df)
    rebound_candle = candle == CandleType.HAMMER
    spike = volume_spike(df["volume"], mult=2.0)  # 반등은 폭발까진 아님
    reasons = []
    if at_support:
        reasons.append("지지 도달")
    if rebound_candle:
        reasons.append("망치형 반등 캔들")
    if spike:
        reasons.append("반등 거래량 동반")
    return SignalResult(
        SignalCode.S4_3,
        triggered=at_support and rebound_candle,
        needs_supply_confirm=True,
        reasons=reasons,
    )


def _signal_4_4(df: pd.DataFrame) -> SignalResult:
    """저점 방어 실패 = 저점 하향 갱신(최근 스윙 저점이 직전보다 낮음)."""
    close = df["close"]
    _, low_idx = swing_points(close)
    failed = False
    reasons = []
    if len(low_idx) >= 2:
        lows = close.loc[low_idx]
        failed = bool(lows.iloc[-1] < lows.iloc[-2])
    if failed:
        reasons.append("저점 하향 갱신(방어 실패)")
    elif has_higher_low(close):
        reasons.append("Higher Low 유지(상승 구조)")
    return SignalResult(SignalCode.S4_4, triggered=failed, reasons=reasons)


_DISPATCH = {
    SignalCode.S4_1: _signal_4_1,
    SignalCode.S4_2: _signal_4_2,
    SignalCode.S4_3: _signal_4_3,
    SignalCode.S4_4: _signal_4_4,
}


def evaluate_signal(df: pd.DataFrame, position: ChartPosition) -> SignalResult:
    """포지션에 매핑된 단계4 신호를 평가."""
    return _DISPATCH[position.signal_code](df)
