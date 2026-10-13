"""Market-neutral symbol schema, KIS source adapters and versioned storage.

Source layouts stop here: downstream code only sees SymbolRecord fields.
"""

import csv
import json
from pathlib import Path
from tempfile import NamedTemporaryFile

from pydantic import BaseModel, model_validator

from core.instruments import EXCHANGE_NAMES, US_EXCHANGES, parse_instrument


class SymbolRecord(BaseModel):
    id: str
    ticker: str
    market: str
    exchange: str
    currency: str
    name: str
    english_name: str = ""
    exchange_name: str
    # Compatibility with the pre-global API; new clients should use id.
    code: str

    @model_validator(mode="after")
    def validate_identity(self):
        instrument = parse_instrument(self.id)
        if self.id != instrument.id or self.code != (instrument.id if instrument.is_overseas else instrument.ticker):
            raise ValueError("정규화된 종목 ID가 필요합니다")
        if (instrument.ticker, instrument.exchange, instrument.currency, instrument.market) != (
            self.ticker, self.exchange, self.currency, self.market
        ):
            raise ValueError("종목 ID와 시장 메타데이터가 일치하지 않습니다")
        return self


def make_symbol(ticker: str, exchange: str, name: str, english_name: str = "") -> dict:
    instrument = parse_instrument(f"{exchange}:{ticker}")
    return SymbolRecord(
        id=instrument.id, ticker=instrument.ticker, market=instrument.market,
        exchange=exchange, currency=instrument.currency, name=name,
        english_name=english_name, exchange_name=EXCHANGE_NAMES[exchange],
        code=instrument.id if instrument.is_overseas else instrument.ticker,
    ).model_dump()


def parse_kis_domestic(content: bytes, exchange: str) -> list[dict]:
    """KIS domestic source uses fixed byte offsets and EUC-KR names."""
    symbols = []
    for line in content.splitlines():
        if len(line) < 61:
            continue
        ticker = line[:9].decode("euc-kr").strip()
        name = line[21:61].decode("euc-kr").strip()
        if len(ticker) > 6:
            ticker = ticker[-6:]
        try:
            if ticker and name:
                symbols.append(make_symbol(ticker, exchange, name))
        except ValueError:
            continue
    return symbols


def parse_kis_us(content: bytes, exchange: str) -> list[dict]:
    """KIS US source uses tab-separated CP949 fields; retain stocks and ETPs."""
    symbols = {}
    for fields in csv.reader(content.decode("cp949").splitlines(), delimiter="\t", quoting=csv.QUOTE_NONE):
        if len(fields) < 10 or fields[0].strip() != "US":
            continue
        if fields[2].strip() != US_EXCHANGES[exchange] or fields[8].strip() not in ("2", "3") or fields[9].strip() != "USD":
            continue
        ticker = fields[4].strip().upper()
        try:
            symbol = make_symbol(ticker, exchange, fields[6].strip() or fields[7].strip() or ticker, fields[7].strip())
        except ValueError:
            continue
        symbols[symbol["id"]] = symbol
    return list(symbols.values())


def load_master(directory: Path, exchange: str) -> list[dict]:
    path = directory / f"{exchange}.json"
    if path.exists():
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema_version") != 1:
            raise ValueError("지원하지 않는 종목 마스터 버전입니다")
        symbols = [SymbolRecord.model_validate(row).model_dump() for row in document["symbols"]]
        if any(row["exchange"] != exchange for row in symbols):
            raise ValueError("마스터 거래소가 일치하지 않습니다")
        return symbols
    # Read old CSV files without modifying the user's existing domestic master.
    legacy = directory / f"{exchange}.csv"
    if not legacy.exists():
        return []
    symbols = []
    with legacy.open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            if row.get("exchange") == exchange and row.get("code") and row.get("name"):
                try:
                    symbols.append(make_symbol(row.get("ticker") or row["code"].split(":")[-1], exchange, row["name"], row.get("english_name") or ""))
                except ValueError:
                    continue
    return symbols


def save_master(directory: Path, exchange: str, symbols: list[dict]) -> None:
    records = [SymbolRecord.model_validate(row).model_dump() for row in symbols]
    if not records or any(row["exchange"] != exchange for row in records):
        raise ValueError("유효한 거래소 마스터가 필요합니다")
    directory.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory, delete=False) as target:
            temporary = Path(target.name)
            json.dump({"schema_version": 1, "symbols": records}, target, ensure_ascii=False)
        temporary.replace(directory / f"{exchange}.json")
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
