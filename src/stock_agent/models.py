"""도메인 모델 — 명세서 7장(단계3·4)·6장(수급)·8장(매도) 용어를 코드 타입으로 고정.

여기 정의된 enum 값은 산출물 사양(현재 포지션 / 권장 액션 / 근거 / 경보)의 어휘다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ChartPosition(str, Enum):
    """단계3 — 차트 포지션 4분류."""

    LOW = "3-1 저점권"        # 장기 이평/추세선 지지 테스트 -> 신호 4-4
    BOX = "3-2 박스권"        # 지지~저항 사이 횡보 -> 신호 4-3
    HIGH = "3-3 고점권"       # 강력 저항 매물대 테스트 -> 신호 4-2
    NEW_HIGH = "3-4 신고가"   # 역사적 신고가 돌파 -> 신호 4-1

    @property
    def signal_code(self) -> "SignalCode":
        return _POSITION_TO_SIGNAL[self]


class SignalCode(str, Enum):
    """단계4 — 실행 신호."""

    S4_1 = "4-1 하락 다이버전스"      # 가격 고점↑ & RSI 고점↓
    S4_2 = "4-2 저항 돌파+거래량 폭발"  # 평소 5~10배 + 수급 동반
    S4_3 = "4-3 지지 반등"            # 망치형 등 반등 캔들 + 거래량
    S4_4 = "4-4 저점 방어 실패"        # 저점 하향 갱신


_POSITION_TO_SIGNAL: dict[ChartPosition, SignalCode] = {
    ChartPosition.LOW: SignalCode.S4_4,
    ChartPosition.BOX: SignalCode.S4_3,
    ChartPosition.HIGH: SignalCode.S4_2,
    ChartPosition.NEW_HIGH: SignalCode.S4_1,
}


class Action(str, Enum):
    """권장 액션. 전량매도만 '마침표', 나머지 매도는 '쉼표(부분 매도)'."""

    BUY = "매수"
    CHASE_BUY = "추격매수"
    HOLD = "홀딩"
    SELL_PARTIAL = "일부매도(30%)"   # 8장 기본 = 쉼표, 코어 70% 보호
    WAIT = "대기"
    SELL_ALL = "전량매도"            # 오버라이드: ①시나리오 달성 ②펀더멘털 훼손만


class SupplyPattern(str, Enum):
    """6장 — 외국인/기관/개인 누적 순매수 조합 5패턴."""

    GAP = "기회의 틈"        # 외인 매수 + 개인 매도 -> 매수 우호
    ROCKET = "로켓 점화"     # 외인+기관 매수 -> 홀딩 강화
    GREED_END = "탐욕의 끝"  # 외인 매도 + 개인 매수 -> 일부 익절
    DEAD_CAT = "데드캣"      # 외인 매도 + 개인/기관 매수 -> 반등 신뢰↓
    REGIME = "구조 전환"     # 외인 이탈 후 기관 주도 -> 턴어라운드 관찰
    NEUTRAL = "중립"         # 뚜렷한 조합 없음


@dataclass
class Verdict:
    """종목별 산출물 (명세서 6절 출력 사양)."""

    ticker: str
    position: ChartPosition
    signal: SignalCode
    action: Action
    supply_pattern: SupplyPattern = SupplyPattern.NEUTRAL
    confirmed: bool = False           # 수급 확증 여부 (4-2/4-3 돌파·반등)
    reasons: list[str] = field(default_factory=list)   # 근거: 신호 중첩
    alerts: list[str] = field(default_factory=list)     # 경보: 펀더멘털 훼손·저점 갱신
    overshadowed_by_override: bool = False  # 전량매도 오버라이드가 발동했는가

    @property
    def conviction(self) -> int:
        """근거 중첩 정도 = 신호 강도. 많이 겹칠수록 강하다."""
        return len(self.reasons)

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "position": self.position.value,
            "signal": self.signal.value,
            "action": self.action.value,
            "supply_pattern": self.supply_pattern.value,
            "confirmed": self.confirmed,
            "conviction": self.conviction,
            "reasons": self.reasons,
            "alerts": self.alerts,
        }
