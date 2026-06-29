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
from ..indicators.trend import breakout_sustained
from ..indicators.volume import volume_spike
from .stage3_position import classify_position
from .stage4_signal import evaluate_signal
from .supply_demand import classify_supply, confirms_breakout, foreign_buying
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
    asset_kind: str = "stock",
) -> Verdict:
    """종목 1개에 대한 의사결정.

    ohlcv: 일봉(필수). supply: 순매수(선택, 없으면 확증 불가). fundamentals: 사람 입력.
    weekly_ohlcv/monthly_ohlcv: 주봉·월봉(선택). 명세서상 다이버전스는 **큰 프레임 우선**이라,
      4-1 에서 주/월봉 하락 다이버전스가 있으면 일봉이 아니어도 신호를 '발효'로 본다
      (→ 일부매도 30%). 월봉 > 주봉 > 일봉 순으로 강한 신호로 취급한다.
    asset_kind: stock/etf/commodity. 수급 N/A(미국) 시장의 4-2/4-3 확증 방식이 갈린다 —
      단일주는 '거래량 폭발', ETF/원자재는 '지속 돌파'(ETF 자체 거래량은 노이즈가 커서).
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
    etf_like = asset_kind in ("etf", "commodity")
    sustained = breakout_sustained(ohlcv["close"], days=3)
    confirm_note: str | None = None

    # 자산·시장별로 가장 깨끗한 확증 수단을 고른다 (가짜 돌파/반등 거르기).
    if not sig.needs_supply_confirm:
        confirmed = True  # 확증 불필요 신호(4-1/4-4)
    elif supply_status == "present":
        if etf_like:
            # 한국 ETF: '기관' 라인엔 LP(유동성공급자) 잡음 → 외국인 순매수 중심 +
            # 지속 돌파 크로스체크. (기관 단독 신호가 LP 잡음인지 가격으로 교차검증)
            fb = foreign_buying(supply)
            confirmed = fb or sustained
            if fb:
                confirm_note = f"수급 확증(외국인 순매수, {pattern.value})"
            elif sustained:
                confirm_note = "지속 돌파 확증(ETF — 외국인 약하나 가격 유지)"
            else:
                confirm_note = "보류 — 외국인 약함+지속 돌파 미확인(ETF 기관은 LP 잡음 가능)"
        else:  # 한국 단일주: 수급(외인/기관) 그대로
            confirmed = confirms_breakout(supply)
            confirm_note = (f"수급 확증({pattern.value})" if confirmed
                            else "⚠ 수급 미확증 — 거래량 없는 돌파/반등(보류)")
    elif supply_status == "na":
        # 미국 등 수급 N/A: 단일주=거래량 폭발 / ETF·원자재=지속 돌파(자체 거래량 노이즈).
        if etf_like:
            confirmed = sustained
            confirm_note = ("지속 돌파 확증(ETF — 최근 종가 유지)" if confirmed
                            else "지속 돌파 미확인 — 보류(ETF 거래량은 노이즈)")
        else:
            confirmed = volume_spike(ohlcv["volume"], lookback=20, mult=2.0)
            confirm_note = ("거래량 확증(수급 N/A 시장 — 거래량 폭발로 대체)" if confirmed
                            else "수급 N/A + 거래량 부족 — 확증 불가(보류)")
    else:  # missing — 수급 가능 시장인데 데이터 못 받음
        confirmed = False
        confirm_note = "수급 미수신(데이터 없음) — 확증 불가, 보류"

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
    if sig.needs_supply_confirm and confirm_note:
        v.reasons.append(confirm_note)

    # 경보: 정량 펀더멘털 훼손 감시
    v.alerts.extend(fund.quant_alerts())
    if sig.code == SignalCode.S4_4 and sig.triggered:
        v.alerts.append("저점 하향 갱신 — 추세 훼손 주의")

    return v
