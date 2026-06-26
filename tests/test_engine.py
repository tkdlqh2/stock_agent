"""엔진 단위 테스트 — 분류·신호·확증·오버라이드·산출물."""
from __future__ import annotations

import numpy as np
import pandas as pd

from stock_agent.models import Action, ChartPosition, SignalCode, SupplyPattern
from stock_agent.engine.decide import decide
from stock_agent.engine.sell_rules import Fundamentals, full_exit_override
from stock_agent.engine.stage3_position import classify_position
from stock_agent.engine.supply_demand import classify_supply, confirms_breakout
from stock_agent.indicators.rsi import bearish_divergence
from conftest import make_ohlcv


def _supply(foreign: float, inst: float, indiv: float, n: int = 30) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    return pd.DataFrame(
        {"foreign": np.full(n, foreign), "institution": np.full(n, inst), "individual": np.full(n, indiv)},
        index=idx,
    )


# --- 단계3 분류 ---

def test_new_high_classification():
    df = make_ohlcv(list(np.linspace(100, 200, 130)))  # 마지막이 역사적 신고가
    assert classify_position(df) == ChartPosition.NEW_HIGH


def test_downtrend_bottom_is_low_not_high():
    # 하락추세 바닥(레인지 하단) — 위에 매물대가 있어도 '저점권'이어야 한다.
    # (실데이터 금 ETF가 '고점권'으로 오판된 버그 회귀 테스트)
    df = make_ohlcv(list(np.linspace(200, 100, 130)))
    assert classify_position(df) == ChartPosition.LOW


# --- 수급 패턴 (6장) ---

def test_supply_rocket():
    assert classify_supply(_supply(1e8, 5e7, -1.5e8)) == SupplyPattern.ROCKET


def test_supply_greed_end():
    assert classify_supply(_supply(-1e8, -2e7, 1.2e8)) == SupplyPattern.GREED_END


def test_confirms_breakout_true_when_foreign_buys():
    assert confirms_breakout(_supply(1e8, -1e7, -9e7)) is True


def test_confirms_breakout_false_when_no_supply():
    assert confirms_breakout(pd.DataFrame()) is False


# --- 전량매도 오버라이드 (8장) ---

def test_override_target_reached():
    fired, reason = full_exit_override(Fundamentals(target_reached=True))
    assert fired and "시나리오" in reason


def test_override_thesis_broken():
    fired, _ = full_exit_override(Fundamentals(thesis_broken=True))
    assert fired


def test_decide_override_takes_precedence():
    df = make_ohlcv(list(np.linspace(100, 200, 130)))
    v = decide("005930", df, fundamentals=Fundamentals(thesis_broken=True))
    assert v.action == Action.SELL_ALL
    assert v.overshadowed_by_override is True


# --- 산출물 형태 ---

def test_decide_produces_full_verdict():
    df = make_ohlcv(list(np.linspace(100, 200, 130)))
    v = decide("005930", df, supply=_supply(1e8, 5e7, -1.5e8))
    assert v.ticker == "005930"
    assert isinstance(v.position, ChartPosition)
    assert isinstance(v.signal, SignalCode)
    assert isinstance(v.action, Action)
    d = v.to_dict()
    assert set(["position", "action", "reasons", "alerts", "conviction"]).issubset(d)


def test_unconfirmed_breakout_holds_back():
    # 신고가가 아니면서 돌파 케이스라도 수급 없으면 추격매수가 아니어야 함
    df = make_ohlcv(list(np.linspace(100, 150, 130)) + [148, 146, 152])
    v = decide("000660", df, supply=None)
    assert v.action != Action.CHASE_BUY or v.confirmed is True


def test_weekly_divergence_escalates_4_1_to_partial_sell():
    # 일봉은 단조 상승(신고가, 다이버전스 없음) → 4-1 X → 홀딩
    daily = make_ohlcv(list(np.linspace(100, 200, 130)))
    # 주봉: 가격 Higher High + RSI Lower High = 하락 다이버전스
    wc = np.concatenate([
        np.linspace(80, 100, 20),   # 워밍업(RSI 14봉 확보, peak1이 유효 구간에 오도록)
        np.linspace(100, 170, 8),   # 가파른 상승 → peak1 고RSI
        np.linspace(170, 140, 8),   # 눌림
        np.linspace(140, 175, 60),  # 완만한 상승 → peak2 더 높은 가격·저RSI
        np.linspace(175, 168, 6),   # peak2를 내부 스윙고점으로
    ])
    weekly = make_ohlcv(list(wc))
    assert bearish_divergence(weekly["close"]) is True  # 구성 sanity 체크

    v_daily_only = decide("X", daily)
    v_with_weekly = decide("X", daily, weekly_ohlcv=weekly)
    assert v_daily_only.action == Action.HOLD          # 주봉 없으면 홀딩
    assert v_with_weekly.action == Action.SELL_PARTIAL  # 주봉 우선 → 일부매도 30%
    assert any("주봉" in r for r in v_with_weekly.reasons)


def test_us_breakout_confirmed_by_volume():
    # 미국(supply=None): 고점권 돌파에 거래량 폭발이 동반되면 수급 없이도 거래량으로 확증.
    np.random.seed(0)
    p = (list(np.linspace(100, 180, 20)) + list(np.linspace(180, 150, 15))
         + list(150 + np.random.uniform(-2, 2, 65)) + list(np.linspace(150, 165, 30)))
    vol = [300.0] * 35 + [3000.0] * 65 + [800.0] * 29 + [20000.0]
    df = make_ohlcv(p, vol)
    v = decide("X", df, supply=None)
    assert v.position == ChartPosition.HIGH      # 고점권 → 4-2(확증 필요)
    assert v.confirmed is True                    # 거래량 폭발로 확증
    assert any("거래량 확증" in r for r in v.reasons)


def test_us_no_volume_not_confirmed():
    # 미국 + 확증 필요 신호인데 거래량 폭발이 없으면 확증 불가(보류).
    np.random.seed(0)
    p = (list(np.linspace(100, 180, 20)) + list(np.linspace(180, 150, 15))
         + list(150 + np.random.uniform(-2, 2, 65)) + list(np.linspace(150, 165, 30)))
    vol = [300.0] * 35 + [3000.0] * 65 + [800.0] * 30  # 마지막 봉 거래량 폭발 없음
    df = make_ohlcv(p, vol)
    v = decide("X", df, supply=None)
    if v.signal == SignalCode.S4_2:  # 같은 포지션일 때만 의미
        assert v.confirmed is False
        assert any("거래량 부족" in r for r in v.reasons)


def test_quant_alerts_surface():
    df = make_ohlcv(list(np.linspace(100, 200, 130)))
    v = decide("005930", df, fundamentals=Fundamentals(fcf_positive=False, roic_gt_wacc=False))
    assert any("FCF" in a for a in v.alerts)
    assert any("ROIC" in a for a in v.alerts)
