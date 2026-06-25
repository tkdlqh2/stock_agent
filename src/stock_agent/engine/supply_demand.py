"""수급 확증 레이어 (6장, 자동).

외국인/기관/개인 누적 순매수 조합으로 5패턴 분류하고,
돌파·반등 신호(4-2/4-3)의 '확증' 여부를 판정한다.

  결합 규칙: 돌파·반등은 '외국인 매수 또는 누적 순매수 우상향' 동반 시에만 확증.
  거래량(수급) 없는 돌파/반등은 가짜로 간주(보류).
"""
from __future__ import annotations

import pandas as pd

from ..models import SupplyPattern


def _cumulative_trend(series: pd.Series) -> float:
    """순매수 누적합의 최종값 부호 크기(우상향이면 양수)."""
    return float(series.cumsum().iloc[-1]) if len(series) else 0.0


def classify_supply(supply: pd.DataFrame, window: int = 20) -> SupplyPattern:
    """최근 window 구간 순매수 합으로 5패턴 분류.

    supply 컬럼: foreign / institution / individual (순매수).
    """
    if supply is None or supply.empty:
        return SupplyPattern.NEUTRAL
    recent = supply.tail(window)
    f = recent.get("foreign", pd.Series(dtype=float)).sum()
    i = recent.get("institution", pd.Series(dtype=float)).sum()
    p = recent.get("individual", pd.Series(dtype=float)).sum()

    foreign_buy, foreign_sell = f > 0, f < 0
    inst_buy = i > 0
    indiv_buy, indiv_sell = p > 0, p < 0

    if foreign_buy and inst_buy:
        return SupplyPattern.ROCKET          # 외인+기관 매수 -> 홀딩 강화
    if foreign_buy and indiv_sell:
        return SupplyPattern.GAP             # 외인 매수+개인 매도 -> 매수 우호
    if foreign_sell and indiv_buy and inst_buy:
        return SupplyPattern.DEAD_CAT        # 외인 매도+개인/기관 매수 -> 반등 신뢰↓
    if foreign_sell and indiv_buy:
        return SupplyPattern.GREED_END       # 외인 매도+개인 매수 -> 일부 익절
    if foreign_sell and inst_buy:
        return SupplyPattern.REGIME          # 외인 이탈 후 기관 주도 -> 턴어라운드 관찰
    return SupplyPattern.NEUTRAL


def confirms_breakout(supply: pd.DataFrame, window: int = 20) -> bool:
    """4-2/4-3 확증 조건: 외국인 매수 또는 누적 순매수(외인+기관) 우상향."""
    if supply is None or supply.empty:
        return False
    recent = supply.tail(window)
    foreign_buy = recent.get("foreign", pd.Series(dtype=float)).sum() > 0
    smart_money = (
        recent.get("foreign", pd.Series(dtype=float)).sum()
        + recent.get("institution", pd.Series(dtype=float)).sum()
    )
    return bool(foreign_buy or smart_money > 0)
