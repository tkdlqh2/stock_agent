"""매도·포지션 운영 (8장) + 전량매도 오버라이드.

- 부분 매도(약 30%) = 기본 '쉼표', 코어 70% 보호.
- 전량 매도 = '마침표', ①시나리오 달성 ②펀더멘털 훼손 두 경우만.
- 오버라이드는 단계4 신호 흐름보다 '우선'하는 별도 게이트.

⚠️ 펀더멘털 판단(시나리오 달성·내재가치)은 사람 입력 영역. 여기서는 사람이 넣은
   값(목표 도달 여부 플래그, 정량 지표 훼손 여부)을 받아 판정만 한다 — 환각 금지.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Fundamentals:
    """단계1·2 게이트 입력(사람). 정량 지표는 자동 보조이나 최종 해석은 사람.

    target_reached: 목표 내재가치(시나리오) 실현 — 사람 판단.
    roic_gt_wacc / fcf_positive / revenue_trend_up: 정량 훼손 감시 보조 지표.
    thesis_broken: 펀더멘털/시나리오 훼손 — 사람 확정.
    """

    target_reached: bool = False
    thesis_broken: bool = False
    roic_gt_wacc: bool | None = None
    fcf_positive: bool | None = None
    revenue_trend_up: bool | None = None

    def quant_alerts(self) -> list[str]:
        """정량 지표 훼손 경보(보조). None 은 데이터 없음으로 보고 건너뛴다."""
        alerts = []
        if self.roic_gt_wacc is False:
            alerts.append("ROIC < WACC (가치창출 훼손)")
        if self.fcf_positive is False:
            alerts.append("FCF 적자 전환")
        if self.revenue_trend_up is False:
            alerts.append("매출 추세 둔화/역성장")
        return alerts


def full_exit_override(fund: Fundamentals) -> tuple[bool, str | None]:
    """전량매도 오버라이드 판정. (발동여부, 사유)."""
    if fund.target_reached:
        return True, "목표 내재가치 실현(시나리오 달성)"
    if fund.thesis_broken:
        return True, "펀더멘털/시나리오 훼손"
    return False, None
