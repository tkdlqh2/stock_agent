"""pykrx 어댑터 — 종목코드 -> OHLCV(일/주/월봉)·외국인/기관/개인 순매수.

명세서 방향: 증권 API를 MCP 서버로 감싸 도구화. 여기서는 KRX 공개 데이터(pykrx)를
표준 DataFrame 스키마로 정규화해 엔진에 공급한다. 계좌(미래에셋 등)와 무관.

pykrx 는 선택 의존성(`pip install -e ".[data]"`)이며 이 모듈에서 **지연 import** 한다.
따라서 합성 데이터 기반 테스트는 pykrx 없이도 동작한다.
"""
from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Literal, Protocol

import pandas as pd

# 엔진이 가정하는 표준 컬럼 스키마 (소문자 영문).
OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]
SUPPLY_COLUMNS = ["foreign", "institution", "individual"]  # 순매수(매수-매도)

Freq = Literal["day", "week", "month"]

# pykrx get_market_ohlcv 의 freq 는 'd'/'m'/'y' 만 지원(주봉 'w' 없음).
# 따라서 일봉을 받아 주/월봉은 로컬에서 리샘플한다.
_RESAMPLE_RULE = {"week": "W", "month": "ME"}


def resample_ohlcv(daily: pd.DataFrame, rule: str) -> pd.DataFrame:
    """일봉 -> 주/월봉. open=시초, high=최고, low=최저, close=종가, volume=합."""
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    out = daily.resample(rule).agg(agg).dropna(how="any")
    return out


class MarketDataProvider(Protocol):
    """엔진이 의존하는 데이터 인터페이스. 테스트는 가짜 구현으로 대체한다."""

    def ohlcv(self, ticker: str, start: str, end: str, freq: Freq = "day") -> pd.DataFrame: ...

    def supply(self, ticker: str, start: str, end: str) -> pd.DataFrame: ...


class PykrxProvider:
    """pykrx 기반 실데이터 공급자."""

    def __init__(self) -> None:
        try:
            from pykrx import stock  # noqa: F401  (지연 import)
        except ImportError as exc:  # pragma: no cover - 환경 의존
            raise ImportError(
                "pykrx 가 필요합니다. `pip install -e \".[data]\"` 로 설치하세요."
            ) from exc
        from pykrx import stock

        self._stock = stock

    @staticmethod
    def _fmt(d: str) -> str:
        """'YYYY-MM-DD' 또는 'YYYYMMDD' -> pykrx 형식 'YYYYMMDD'."""
        return d.replace("-", "")

    def ohlcv(self, ticker: str, start: str, end: str, freq: Freq = "day") -> pd.DataFrame:
        # 항상 일봉을 받아 표준화하고, 주/월봉은 로컬 리샘플(pykrx 'w' 미지원 회피).
        df = self._stock.get_market_ohlcv(self._fmt(start), self._fmt(end), ticker, freq="d")
        df = df.rename(
            columns={
                "시가": "open",
                "고가": "high",
                "저가": "low",
                "종가": "close",
                "거래량": "volume",
            }
        )
        daily = df[OHLCV_COLUMNS].astype(float)
        if freq == "day":
            return daily
        return resample_ohlcv(daily, _RESAMPLE_RULE[freq])

    def supply(self, ticker: str, start: str, end: str) -> pd.DataFrame:
        """외국인/기관/개인 순매수(거래대금 기준).

        ⚠️ KRX 가 투자자별 거래실적을 인증 뒤로 옮겨, 이 데이터는 KRX 계정이 필요하다.
           무료 계정(data.krx.co.kr) 후 환경변수 KRX_ID / KRX_PW 를 설정하면 pykrx 가
           자동 로그인한다. 미설정 시 빈 DataFrame 을 반환하고 엔진은 '수급 미확증(보류)'
           으로 안전 강등한다.
        """
        # KRX 자격증명이 없으면 (시끄러운 실패 경로를 피해) 호출 자체를 건너뛴다.
        if not (os.getenv("KRX_ID") and os.getenv("KRX_PW")):
            return pd.DataFrame(columns=SUPPLY_COLUMNS)
        # ETF 는 개별주 경로(get_market_trading_value_by_date)가 ISIN 조회에서 실패하며
        # 시끄러운 로그를 남긴다 -> ETF 면 곧장 ETF 경로로 라우팅.
        if self._is_etf(ticker):
            return self._supply_etf(ticker, end)
        # 1) 개별주 경로 (일자별 시계열).
        try:
            df = self._stock.get_market_trading_value_by_date(
                self._fmt(start), self._fmt(end), ticker
            )
        except Exception:
            df = None
        if df is not None and not df.empty:
            alias = {
                "외국인합계": "foreign", "외국인": "foreign",
                "기관합계": "institution", "기관": "institution",
                "개인": "individual",
            }
            df = df.rename(columns=alias)
            df = df.loc[:, ~df.columns.duplicated()]  # 합계+세부 중복 시 첫 컬럼만
            cols = [c for c in SUPPLY_COLUMNS if c in df.columns]
            if cols:
                return df[cols].astype(float)
        # 2) 개별주 경로가 비면 ETF 경로(기간합계 단일행)로 폴백.
        return self._supply_etf(ticker, end)

    def _is_etf(self, ticker: str) -> bool:
        """ETF 티커 여부(한 번 조회 후 캐시). 실패 시 보수적으로 False."""
        if not hasattr(self, "_etf_set"):
            try:
                self._etf_set = set(self._stock.get_etf_ticker_list())
            except Exception:
                self._etf_set = set()
        return ticker in self._etf_set

    def _supply_etf(self, ticker: str, end: str, lookback_days: int = 35) -> pd.DataFrame:
        """ETF 투자자별 순매수(거래대금). pykrx 의 ETF 함수는 일자별 시계열이 아니라
        '투자자별 기간합계'라, 최근 lookback_days 구간을 합산해 **단일행**으로 반환한다.
        엔진의 classify_supply/confirms_breakout 은 tail(window).sum() 이라 단일행도 동작."""
        try:
            edt = date.fromisoformat(end)
        except ValueError:
            edt = date.today()
        sdt = edt - timedelta(days=lookback_days)
        try:
            df = self._stock.get_etf_trading_volume_and_value(
                self._fmt(sdt.isoformat()), self._fmt(edt.isoformat()), ticker
            )
        except Exception:
            return pd.DataFrame(columns=SUPPLY_COLUMNS)
        if df is None or df.empty or ("거래대금", "순매수") not in df.columns:
            return pd.DataFrame(columns=SUPPLY_COLUMNS)
        net = df[("거래대금", "순매수")]
        row = {
            "foreign": float(net.get("외국인", 0.0)),
            "institution": float(net.get("기관합계", 0.0)),
            "individual": float(net.get("개인", 0.0)),
        }
        return pd.DataFrame([row], columns=SUPPLY_COLUMNS)


class YFinanceProvider:
    """yfinance 기반 미국(해외) 주식 OHLCV 공급자.

    ⚠️ 미국 시장에는 KRX식 투자자별 순매수(외국인/기관/개인) 공개 피드가 없다.
       따라서 supply() 는 항상 빈 DF -> 엔진의 6장 수급 확증 레이어는 N/A.
       단계3(차트 포지션)·단계4(다이버전스·돌파·반등·저점)는 시장 무관하게 유효.
    """

    def __init__(self) -> None:
        try:
            import yfinance  # noqa: F401
        except ImportError as exc:  # pragma: no cover
            raise ImportError("yfinance 가 필요합니다. `pip install yfinance`.") from exc
        import yfinance

        self._yf = yfinance

    def ohlcv(self, ticker: str, start: str, end: str, freq: Freq = "day") -> pd.DataFrame:
        interval = {"day": "1d", "week": "1wk", "month": "1mo"}[freq]
        df = self._yf.download(
            ticker, start=start, end=end, interval=interval,
            auto_adjust=True, progress=False,
        )
        if df is None or df.empty:
            return pd.DataFrame(columns=OHLCV_COLUMNS)
        if isinstance(df.columns, pd.MultiIndex):  # 단일 티커도 멀티인덱스로 올 때가 있음
            df.columns = df.columns.get_level_values(0)
        df = df.rename(
            columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"}
        )
        return df[OHLCV_COLUMNS].astype(float)

    def supply(self, ticker: str, start: str, end: str) -> pd.DataFrame:
        return pd.DataFrame(columns=SUPPLY_COLUMNS)  # 미국 시장: 수급 데이터 N/A


def default_window(days: int = 400) -> tuple[str, str]:
    """오늘 기준 조회 구간. 120일선·주봉 다이버전스를 위해 넉넉히 약 400 거래일."""
    end = date.today()
    start = end - timedelta(days=int(days * 1.6))  # 휴장일 보정
    return start.isoformat(), end.isoformat()
