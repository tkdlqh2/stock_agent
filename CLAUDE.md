# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 현재 상태

설계 명세서 `에이전트. 통합 매매 전략 (1~8장).md`(박두환 『실전 매매 마스터 클라스』 1~8장 방법론을 의사결정 엔진으로 통합)가 **단일 진실 공급원(source of truth)**이다. 코드를 추가/수정할 때 이 명세서를 기준으로 한다.

초기 Python 스캐폴드가 구현되어 있다(아래 "기술 스택"·"구현 메모" 참조). 지표·엔진은 합성 데이터 단위 테스트로 검증된다.

문서는 한국어로 작성되어 있고, 사용자도 한국어로 소통한다. 응답과 산출물은 한국어를 기본으로 한다.

## 빌드 / 테스트 명령

Windows + Microsoft Store Python 환경. `python`은 Store 스텁이라 막힐 수 있어 **`py` 런처**로 venv를 만든다.

```bash
py -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"   # 또는: pip install numpy pandas pytest
.venv/Scripts/python -m pytest -q                  # 전체 테스트 (네트워크 불필요)
.venv/Scripts/python -m pytest tests/test_engine.py::test_decide_override_takes_precedence  # 단일 테스트
```

- 테스트는 `tests/conftest.py`의 **합성 OHLCV/수급**을 쓴다 — pykrx·네트워크 불필요.
- 지표는 순수 pandas/numpy. `pykrx`(실데이터)·`mcp`(서버)는 **선택 의존성**이며 각 모듈에서 **지연 import** 한다.
- 한글 출력이 깨지면 `PYTHONUTF8=1` 설정. native exe에 멀티라인 스크립트를 `-c`로 넘기지 말고 임시 `.py` 파일로 실행할 것(PowerShell이 따옴표를 먹는다).

## 코드 구조 (명세서 흐름 = 모듈 흐름)

`src/stock_agent/` 아래, 처리 순서 **게이트 → 단계3 분류 → 단계4 신호 → 수급 확증 → 매도 운영**을 그대로 모듈화:

- `models.py` — 도메인 어휘(enum): `ChartPosition`(3-1~3-4)·`SignalCode`(4-1~4-4)·`Action`·`SupplyPattern`(6장 5패턴)·`Verdict`(산출물). `ChartPosition.signal_code`가 포지션→신호 매핑.
- `indicators/` — 순수 지표. `trend`(SMA 20/60/120·골든크로스·스윙 고저·Higher Low)·`candles`(망치/유성/도지)·`rsi`(Wilder+하락 다이버전스)·`volume`(거래량 폭발·매물대).
- `engine/` — `stage3_position`(분류) → `stage4_signal`(신호 O/X+근거) → `supply_demand`(확증) → `sell_rules`(전량매도 오버라이드+`Fundamentals` 사람입력) → `decide`(오케스트레이션, **오버라이드 최우선**).
- `data/provider.py` — `PykrxProvider`(한국, OHLCV+수급) / `YFinanceProvider`(미국 등 해외, OHLCV만 — **수급 N/A**). 둘 다 표준 스키마 `open/high/low/close/volume`(+`foreign/institution/individual`). pykrx `freq`는 `d/m/y`만이라 주봉은 일봉을 받아 로컬 리샘플. **개별주 수급**=`get_market_trading_value_by_date`(일자별 시계열), **ETF 수급**=`get_etf_trading_volume_and_value`(투자자별 기간합계 → 최근 ~35일 단일행, `_is_etf()`로 라우팅). 둘 다 KRX 로그인 필요.
- `fundamentals/brief.py` — `FundamentalBrief`(섹터/테마/매크로 전망·주도주·상위구성·시나리오 훼손 후보 + 정량). **단계1·2 보조 리서치**: 출처·확신도·기준일 필수, **자동 매매 트리거 아님**. `asset_kind`(stock/etf/commodity)별 렌더. `review_cadence_days`(stock·etf=90/commodity=30) + `is_stale()`로 전망 갱신주기 관리. 정량 지표만 `to_fundamentals_hint()`로 게이트에 연결, `thesis_broken`/`target_reached`는 사람이 설정.
- `fundamentals/store.py` — 브리핑 캐시(`briefs/<ticker>.json`) + 보유(`portfolio.json`) + 워치리스트(`watchlist.json`) 영속화. **차트=라이브/매일, 펀더멘털=캐시/분기·월**의 주기 분리를 구현.
- `report.py` — `build_report(base_dir)`: 보유(portfolio.json) 분석 + 워치리스트(watchlist.json) **매수 신호 감시**(액션이 매수/추격매수면 🟢진입검토) + briefs/ 캐시 + 라이브 차트 + 매매일지 최근내역 → 통합 마크다운. 브리핑 stale 시 '⏰갱신필요' 표시. CLI: `python -m stock_agent.report [base_dir]` → `reports/`에 저장.
- `journal.py` — 매매 일지. `TradeEntry`·`log_trade()`(journal.json 기록 + 매매일지.md 렌더)·`journal_summary()`(8장 복기 지표: 종목별 누적 수량=복리, 쉼표/마침표 횟수). 태그: 진입/쉼표(부분매도)/마침표(전량매도)/리밸런싱. journal.json·매매일지.md는 개인 데이터(gitignore).
- `journal_import.py` — 미래에셋 거래내역 CSV(cp949/utf-8 자동) → `TradeEntry` 임포트. **자동**: 날짜·종목(종목번호=티커)·수량·체결단가·수수료·세금·원화손익. **수동**(`enrich_entry`): 태그·근거·당시 국면(=사람 판단). 미래에셋은 API 없어 CSV가 현실적 경로(*.csv는 gitignore).
- `mcp_server.py` — FastMCP 스텁(`analyze_ticker`/`get_ohlcv`/`get_supply`/`analyze_portfolio`). 캐시 위치는 `STOCK_AGENT_HOME`(없으면 프로젝트 루트).

`decide()`의 수급 상태 3구분: `supply=None`→**N/A(미국 등)** / 빈 DataFrame→**미수신(예: KRX 로그인 없음)** / 데이터 있음→확증 판정. 셋 다 4-2/4-3은 보류로 강등하되 근거 메시지가 다르다.

핵심 불변식: `decide()`는 ①전량매도 오버라이드를 신호 흐름보다 먼저 확인, ②4-2/4-3 돌파·반등은 `confirms_breakout`(외인 매수 또는 외인+기관 누적 우상향) 없이는 추격매수로 가지 않음(보류), ③`Fundamentals`(시나리오·훼손)는 사람 입력 — 자동 판정 금지.

## 핵심 설계 원칙 (이 프로젝트의 모든 코드가 따라야 함)

> **계산·판정은 코드, 시나리오 판단은 사람.**

- **입력**: 워치리스트(사람이 선정한 종목) + 각 종목의 목표 내재가치·시나리오 가정
- **출력**: 종목별 `국면 판정 + 권장 액션 + 근거 + 경보`
- 이 도구는 **분석 보조**이지 투자 권유·자동매매가 아니다. 신호는 확률이지 보장이 아니다.

### 자동화 금지 영역 (환각 금지 — 반드시 사람 입력)
- 단계1: 산업 성장성(메가트렌드·정책·TAM)
- 단계2: 기업 독점력·내재가치 시나리오 (단, ROIC>WACC·FCF·매출추세 같은 **정량 지표는 자동 보조/훼손 감시**)
- 전량 매도(편출) 최종 실행
- 포지션 사이징·리밸런싱
- 패턴 인식(삼각수렴·쐐기 등)은 LLM 보조 해석만, **단정 금지**

### 자동화 영역
단계3(차트 포지션 분류), 단계4(실행 신호), 수급 확증(6장), 30% 분할익절 신호 — 모두 OHLCV·순매수 데이터로 계산.

## 의사결정 엔진 아키텍처 (7장 4단계)

처리 순서는 게이트 → 분류 → 신호 → 확증 → 운영이며, 코드 모듈은 이 흐름을 따라 구성하는 것을 권장한다.

1. **단계1·2 게이트 (사람)**: 워치리스트에 있다 = 펀더멘털 게이트 통과로 간주. 이후 정량 지표는 훼손 감시용으로 계속 모니터링.
2. **단계3 — 차트 포지션 분류 (자동)**: 현재가를 4개 국면 중 하나로 분류
   - `3-1 저점권` → 신호 4-4 로
   - `3-2 박스권` → 신호 4-3 으로
   - `3-3 고점권` → 신호 4-2 로
   - `3-4 신고가` → 신호 4-1 로
3. **단계4 — 실행 신호 (자동)**:
   - `4-1` RSI **하락 다이버전스**(가격 고점↑ & RSI 고점↓) → O: 일부 매도 30% / X: 물량 유지
   - `4-2` 저항 돌파 + 거래량 폭발(평소 5~10배) + 수급 동반 → O: 추격 매수→4-1 / X: 대기
   - `4-3` 지지 도달 + 반등 캔들(망치형 등) + 거래량 → O: 추격 매수→4-1 / X: 대기
   - `4-4` 저점 방어 실패(저점 하향 갱신) → O: 대기 / X: 4-3 으로
4. **수급 확증 레이어 (6장, 자동)**: 4-2/4-3 돌파·반등 신호는 **외국인 매수 또는 누적 순매수 우상향이 동반될 때만 '확증'**. 거래량 없는 돌파/반등은 가짜(보류).
5. **매도·포지션 운영 (8장)**: 부분 매도(약 30%)가 기본 = '쉼표', 코어 70% 보호. 전량 매도는 ①시나리오 달성 ②펀더멘털 훼손 **두 경우만** = '마침표'.

> **전량매도 오버라이드 (8장)**: 위 흐름과 무관하게 ①목표 내재가치 실현 또는 ②펀더멘털 훼손이면 전량 매도. 구현 시 단계4 신호 흐름보다 우선하는 별도 게이트로 둘 것.

### 계산 기준 (구현 시 정의 고정)
- **추세/구조**: 고점·저점 동시 방향. **Higher Low = 상승 구조 핵심**
- **이평선**: 20/60/120일 SMA. **진짜 골든크로스 = 120일선 상승 중인 교차**
- **캔들**: 망치형(아래꼬리 ≥ 몸통×2~3) / 유성형(위꼬리 ≥ 몸통×2~3) / 도지(몸통≈0)
- **매물대(지지·저항)**: 거래량 집중 가격대
- **다이버전스 시간프레임**: 일봉보다 **주봉·월봉 우선**(더 강한 신호)

### 수급 패턴 분류 (6장)
외국인/기관/개인 누적 순매수 조합으로 5패턴 — 기회의 틈(외인매수+개인매도, 매수 우호) / 로켓 점화(외인+기관 매수, 홀딩 강화) / 탐욕의 끝(외인매도+개인매수, 일부 익절) / 데드캣(외인매도+개인·기관매수, 반등 신뢰↓) / 구조 전환(외인 이탈 후 기관 주도, 턴어라운드 관찰).

## 기술 스택 (확정)

| 구성 | 선택 | 비고 |
|------|------|------|
| 언어 | **Python** | 한국 주식 데이터·지표·MCP 생태계 중심 |
| 시장 데이터 | **pykrx** | OHLCV(일/주/월)·거래량·외국인/기관/개인 순매수. KRX 공개 데이터라 **계좌 불필요** — 엔진 전부 커버 |
| 지표 계산 | **pandas + ta(또는 pandas-ta)** | RSI·SMA(20/60/120)·다이버전스·캔들 판정 |
| 도구화 | **MCP Python SDK (`mcp`)** | `종목코드 → OHLCV/수급` MCP 서버로 감싸 도구화 |

### 증권 계좌 연동 범위 (결정됨)
- **계좌 연동 안 함 (분석 전용)**. 입력 워치리스트·보유 현황은 사람이 직접 제공.
- 사용자 실계좌는 **미래에셋증권**이나, 미래에셋은 개인 개발자용 공개 API가 **없다**. 어차피 엔진이 쓰는 OHLCV·수급은 증권사와 무관한 KRX 공개 데이터라 pykrx로 충분.
- 향후 잔고·주문 자동 연동이 필요해지면 한국 리테일 표준인 **KIS(한국투자증권) Open API** 계좌를 별도 개설하는 것이 현실적 경로(미래에셋으로는 불가).

## 구현 메모

- **데이터 흐름**: `종목코드 → pykrx → OHLCV/수급 DataFrame → 지표 계산 → 단계3·4 판정 → MCP 도구 응답`.
- 분할 진입/청산 기본, 진입 전 손절 기준 사전 설정, 단일 종목 비중 한도 준수.

### pykrx 실데이터 제약 (실측 확인됨, 2026-06)
- **OHLCV는 로그인 불필요**. 단, `get_market_ohlcv`의 `freq`는 `d/m/y`만 지원(주봉 `w` 없음) → `data/provider.py`가 **일봉을 받아 주/월봉은 로컬 리샘플**(`resample_ohlcv`). 명세서가 중시하는 주봉 다이버전스는 이 경로로 공급.
- **투자자별 순매수(수급)는 KRX 로그인 필요**. KRX가 엔드포인트를 인증 뒤로 옮김. 무료 계정(data.krx.co.kr) 후 환경변수 `KRX_ID`/`KRX_PW` 설정 시 자동 활성화. 미설정이면 `provider.supply()`가 **빈 DF 반환(호출 자체 skip)** → 엔진은 4-2/4-3을 '수급 미확증(보류)'로 안전 강등. 즉 수급은 선택 레이어.

### MCP 서버 (Claude 도구 연결)
- 등록: 프로젝트 루트 `.mcp.json` (`stock-agent` → venv python `-m stock_agent.mcp_server`, stdio). Claude Code가 첫 사용 시 승인 요청.
- 도구: `analyze_ticker(ticker, target_reached, thesis_broken)` / `get_ohlcv` / `get_supply`. `target_reached`·`thesis_broken`은 사람 입력(단계1·2) — 기본 False.
- 검증: stdio 클라이언트로 핸드셰이크→`tools/list`→`analyze_ticker` 호출까지 실측 통과(삼성전자 005930).

## 산출물 사양 (종목별 출력)

1. **현재 포지션**: 3-1~3-4 중 분류
2. **권장 액션**: 매수/추격매수/홀딩/일부매도(30%)/대기/전량매도 + 이유
3. **근거**: 캔들·추세·거래량·RSI·수급 신호의 **중첩 정도** (많이 겹칠수록 강한 신호)
4. **경보**: 정량 펀더멘털(ROIC·FCF·매출) 훼손 또는 저점 하향 갱신 시 알림
