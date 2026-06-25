"""펀더멘털·섹터 리서치 레이어 (단계1·2 보조).

명세서 원칙 준수:
- 이 레이어는 **자동 매매 트리거가 아니다.** 사람의 단계1·2 게이트 판단을 돕는 '브리핑'.
- 섹터 전망·주도주 여부·시나리오 훼손은 LLM/사람 보조 해석 + **출처 필수 + 단정 금지**.
- 정량 지표(ROIC>WACC·FCF·매출추세)만 자동 보조/훼손 감시 대상.
- 주기(cadence)는 차트(일 단위)와 분리: 분기 실적 + 주요 이벤트 트리거.
"""

from .brief import FundamentalBrief, Outlook, render_brief

__all__ = ["FundamentalBrief", "Outlook", "render_brief"]
