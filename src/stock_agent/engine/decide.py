"""오케스트레이션 — 종목 1개에 대한 최종 Verdict 산출.

처리 순서 (명세서 7절 우선순위):
  0) 전량매도 오버라이드 (사람 입력 게이트, 최우선)
  1) 단계3 차트 포지션 분류
  2) 단계4 실행 신호
  3) 수급 확증 (4-2/4-3)
  4) 포지션별 액션 결정 + 근거/경보 수집
"""
from __future__ import annotations

import pandas as pd

from ..models import Action, ChartPosition, SignalCode, Verdict
from .stage3_position import classify_position
from .stage4_signal import evaluate_signal
from .supply_demand import classify_supply, confirms_breakout
from .sell_rules import Fundamentals, full_exit_override


def _action_for(
    position: ChartPosition,
    triggered: bool,
    confirmed: bool,
) -> Action:
    """포지션·신호 O/X·확증 -> 권장 액션 (명세서 단계4 표)."""
    code = position.signal_code
    if code == SignalCode.S4_1:
        # 신고가/고점: 하락 다이버전스 O -> 일부매도30% / X -> 홀딩
        return Action.SELL_PARTIAL if triggered else Action.HOLD
    if code == SignalCode.S4_2:
        # 고점권: 저항 돌파+거래량 O & 수급 확증 -> 추격매수 / 아니면 대기
        return Action.CHASE_BUY if (triggered and confirmed) else Action.WAIT
    if code == SignalCode.S4_3:
        # 박스권: 지지 반등 O & 수급 확증 -> 추격매수 / 아니면 대기
        return Action.CHASE_BUY if (triggered and confirmed) else Action.WAIT
    if code == SignalCode.S4_4:
        # 저점권: 방어 실패 O -> 대기 / X(Higher Low 유지) -> 매수 관점
        return Action.WAIT if triggered else Action.BUY
    return Action.WAIT


def decide(
    ticker: str,
    ohlcv: pd.DataFrame,
    supply: pd.DataFrame | None = None,
    fundamentals: Fundamentals | None = None,
    *,
    weekly_ohlcv: pd.DataFrame | None = None,
    monthly_ohlcv: pd.DataFrame | None = None,
) -> Verdict:
    """종목 1개에 대한 의사결정.

    ohlcv: 일봉(필수). supply: 순매수(선택, 없으면 확증 불가). fundamentals: 사람 입력.
    weekly_ohlcv/monthly_ohlcv: 주봉·월봉(선택). 명세서상 다이버전스는 **큰 프레임 우선**이라,
      4-1 에서 주/월봉 하락 다이버전스가 있으면 일봉이 아니어도 신호를 '발효'로 본다
      (→ 일부매도 30%). 월봉 > 주봉 > 일봉 순으로 강한 신호로 취급한다.
    """
    fund = fundamentals or Fundamentals()

    # 0) 전량매도 오버라이드 (최우선)
    override, reason = full_exit_override(fund)
    if override:
        v = Verdict(
            ticker=ticker,
            position=classify_position(ohlcv),
            signal=SignalCode.S4_1,
            action=Action.SELL_ALL,
            overshadowed_by_override=True,
        )
        v.reasons.append(f"전량매도 오버라이드: {reason}")
        v.alerts.extend(fund.quant_alerts())
        return v

    # 1) 단계3 분류
    position = classify_position(ohlcv)

    # 2) 단계4 신호
    sig = evaluate_signal(ohlcv, position)

    # 3) 수급 확증
    #    supply 상태 구분: None=해당 시장에 수급 개념 없음(미국 등, N/A) /
    #                      empty=수급 가능 시장인데 데이터 미수신(예: KRX 로그인 없음) / 데이터 있음
    if supply is None:
        supply_status = "na"
    elif supply.empty:
        supply_status = "missing"
    else:
        supply_status = "present"

    pattern = classify_supply(supply) if supply_status == "present" else classify_supply(pd.DataFrame())
    if sig.needs_supply_confirm:
        confirmed = confirms_breakout(supply) if supply_status == "present" else False
    else:
        confirmed = True  # 확증 불필요 신호(4-1/4-4)

    # 4) 큰 프레임 우선: 4-1 은 주/월봉 다이버전스가 있으면 신호 '발효'로 격상.
    effective_triggered = sig.triggered
    timeframe_reasons: list[str] = []
    if sig.code == SignalCode.S4_1:
        from ..indicators.rsi import bearish_divergence

        if weekly_ohlcv is not None and len(weekly_ohlcv) and bearish_divergence(weekly_ohlcv["close"]):
            effective_triggered = True
            timeframe_reasons.append("주봉 RSI 하락 다이버전스(강한 신호)")
        if monthly_ohlcv is not None and len(monthly_ohlcv) and bearish_divergence(monthly_ohlcv["close"]):
            effective_triggered = True
            timeframe_reasons.append("월봉 RSI 하락 다이버전스(가장 강한 신호)")

    # 5) 액션 + 근거/경보
    action = _action_for(position, effective_triggered, confirmed)

    v = Verdict(
        ticker=ticker,
        position=position,
        signal=sig.code,
        action=action,
        supply_pattern=pattern,
        confirmed=confirmed,
    )
    v.reasons.extend(sig.reasons)
    v.reasons.extend(timeframe_reasons)
    if sig.needs_supply_confirm:
        if supply_status == "present" and confirmed:
            v.reasons.append(f"수급 확증({pattern.value})")
        elif supply_status == "present":
            v.reasons.append("⚠ 수급 미확증 — 거래량 없는 돌파/반등(보류)")
        elif supply_status == "na":
            v.reasons.append("수급 N/A(해당 시장 미적용) — 확증 생략, 차트 기준 보류")
        else:  # missing
            v.reasons.append("수급 미수신(데이터 없음) — 확증 불가, 보류")

    # 경보: 정량 펀더멘털 훼손 감시
    v.alerts.extend(fund.quant_alerts())
    if sig.code == SignalCode.S4_4 and sig.triggered:
        v.alerts.append("저점 하향 갱신 — 추세 훼손 주의")

    return v
