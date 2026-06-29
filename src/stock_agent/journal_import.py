"""미래에셋 거래내역(체결) CSV → 매매 일지 임포트.

미래에셋 HTS/MTS 에서 내보낸 '거래내역' CSV(국내/해외)를 파싱해 TradeEntry 로 변환한다.
- 인코딩: 한국 증권사 CSV는 보통 cp949(euc-kr). utf-8-sig 도 시도.
- 컬럼은 한글 헤더로 매칭(공백 제거). 종목번호 = 티커(미국=심볼, 한국=6자리).
- **자동으로 채우는 것**: 날짜·종목·수량·체결단가·수수료·세금·원화손익.
- **수동으로 남는 것**: tag(쉼표/마침표) + rationale(왜) — 시나리오 판단=사람.
  (임포트 후 enrich_entry() 또는 직접 보정으로 채운다.)
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

from .journal import TradeEntry


def _read_text(path: Path) -> str:
    data = path.read_bytes()
    for enc in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _norm_row(row: dict) -> dict:
    """헤더보다 값이 많아 생기는 None 키/리스트 값을 안전하게 거른다."""
    return {
        k.strip(): (v.strip() if isinstance(v, str) else "")
        for k, v in row.items()
        if isinstance(k, str)
    }


def _num(s: str | None) -> float:
    if not s:
        return 0.0
    try:
        return float(str(s).replace(",", "").strip())
    except ValueError:
        return 0.0


def import_miraeasset_csv(path: str | Path) -> list[TradeEntry]:
    """미래에셋 거래내역 CSV → 체결 기반 TradeEntry 목록(tag/rationale 미설정)."""
    text = _read_text(Path(path))
    reader = csv.DictReader(io.StringIO(text))
    out: list[TradeEntry] = []
    for row in reader:
        r = {k.replace(" ", ""): v for k, v in _norm_row(row).items()}
        date = r.get("매매일")
        ticker = r.get("종목번호")
        if not date or not ticker:  # 빈 줄/꼬리 스킵
            continue
        name = r.get("종목명") or ticker
        buy, sell, bal = _num(r.get("매수수량")), _num(r.get("매도수량")), _num(r.get("잔고수량"))
        if sell > 0:
            action = "전량매도" if bal == 0 else "일부매도"
            shares, price = sell, _num(r.get("매도단가"))
        elif buy > 0:
            action, shares, price = "매수", buy, _num(r.get("매수단가"))
        else:
            continue
        pnl = r.get("총평가손익") or r.get("원화매매손익") or ""
        ret = r.get("환산손익률") or r.get("손익률") or ""
        note = f"수수료 {r.get('수수료','-')}·세금 {r.get('세금','-')}"
        if pnl:
            note += f" / 원화손익 {pnl}원" + (f"({ret}%)" if ret else "")
        out.append(TradeEntry(
            date=date.replace("/", "-"), ticker=ticker, name=name,
            action=action, shares=shares, price=price, note=note,
        ))
    return out


def import_miraeasset_chegyul_csv(
    path: str | Path, name_map: dict[str, str], date: str
) -> list[TradeEntry]:
    """미래에셋 '체결내역' CSV → TradeEntry. 이 양식은 종목명만 있어 name_map 필요,
    날짜 컬럼이 없어 date(파일 기준일)를 인자로 받는다. tag/rationale 미설정."""
    text = _read_text(Path(path))
    reader = csv.DictReader(io.StringIO(text))
    out: list[TradeEntry] = []
    for row in reader:
        r = _norm_row(row)
        gubun, nm = r.get("매매구분"), r.get("종목명")
        qty = _num(r.get("체결량"))
        if not gubun or not nm or qty <= 0:
            continue
        action = "매도" if "매도" in gubun else "매수"
        out.append(TradeEntry(
            date=date, ticker=name_map.get(nm, nm), name=nm,
            action=action, shares=qty, price=_num(r.get("체결가")),
            note=f"체결금액 {r.get('체결금액','-')} ({gubun}, {r.get('주문시각','')})",
        ))
    return out


def import_miraeasset_balance_csv(
    path: str | Path, name_map: dict[str, str]
) -> tuple[list[dict], float]:
    """미래에셋 '잔고' CSV → (holdings, usd_cash). holdings=[{ticker,market,shares,avg_price}].
    유형: 주식→kr / 해외주식→us / 외화(미국달러)→usd_cash."""
    text = _read_text(Path(path))
    reader = csv.DictReader(io.StringIO(text))
    holdings: list[dict] = []
    usd_cash = 0.0
    for row in reader:
        r = _norm_row(row)
        typ, nm = r.get("유형"), r.get("종목명")
        if not typ or not nm:
            continue
        if typ == "외화":  # 미국달러 등 외화 예수금
            usd_cash = _num(r.get("보유량"))
            continue
        holdings.append({
            "ticker": name_map.get(nm, nm),
            "market": "kr" if typ == "주식" else "us",
            "shares": _num(r.get("보유량")),
            "avg_price": _num(r.get("평균단가")),
        })
    return holdings, usd_cash


def enrich_entry(entry: TradeEntry, *, tag: str, rationale: str,
                 position: str | None = None, signal: str | None = None,
                 name: str | None = None) -> TradeEntry:
    """임포트한 체결에 사람 판단(tag·근거·당시 국면)을 덧붙인다."""
    entry.tag = tag
    entry.rationale = rationale
    if position:
        entry.position = position
    if signal:
        entry.signal = signal
    if name:
        entry.name = name
    return entry
