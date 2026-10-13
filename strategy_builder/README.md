# Strategy Builder — 전략 설계 + 시그널 생성 엔진

한국투자증권 Open API 기반 **비주얼 전략 빌더 + 실시간 주문 실행** 시스템입니다.

코딩 없이 기술적 지표를 조합하여 매매 전략을 설계하고,
설계한 전략을 `.kis.yaml` 파일로 내보내 **Backtester에서 과거 데이터 검증**을 거친 뒤,
검증된 전략을 다시 Strategy Builder에서 **실시간 시그널 생성 및 모의/실전 주문**으로 실행할 수 있습니다.

```
 Strategy Builder    .kis.yaml        Backtester        검증 완료?
┌───────────┐     ┌──────────┐     ┌───────────┐     ┌──────────┐
│ 전략 설계  │────▶│  Export   │────▶│ 백테스트   │────▶│ 결과 확인 │
│ (비주얼)   │     │          │     │ (과거 데이터)│     │ (수익률)  │
└───────────┘     └──────────┘     └───────────┘     └────┬─────┘
      ▲                                                    │
      │              Strategy Builder                      │ 좋으면
      │           ┌──────────────┐                         │
      └───────────│ 실전/모의 주문 │◀────────────────────────┘
                  └──────────────┘
```

---

## 빠른 시작

### 사전 요구사항

- Python 3.11+ / [uv](https://docs.astral.sh/uv/)
- Node.js 20.9+ / npm (Next.js 16 요구사항)
- KIS Open API 키 ([설정 방법](../README.md#35-kis_devlpyaml-설정))

### PC에서 모의투자 실행 (Linux / WSL)

KIS 서버에 접속 가능한 PC에서 실행하면 클라우드 VPN이 필요하지 않습니다.
아래 명령은 저장소 루트에서 시작합니다.

```bash
cd strategy_builder
uv sync
# 기존 .env는 덮어쓰지 않습니다.
test -e .env || (umask 077; cp .env.example .env)
```

로컬 편집기로 `.env`를 열어 `paper_app`, `paper_sec`, `my_paper_stock`,
`my_htsid`를 입력합니다. `my_paper_stock`은 모의투자 주식 계좌 앞 8자리이며
앞자리 0을 유지합니다. `my_prod=01`은 주식 계좌 상품코드입니다.
실전용 항목은 모의투자만 사용할 때 비워둡니다. `.env`는 Git에서 제외됩니다.
클라우드에 등록한 시크릿은 PC로 자동 전달되지 않으므로 PC에 별도로 설정해야 합니다.

설정 우선순위는 **프로세스 환경변수 > `strategy_builder/.env` >
`~/KIS/config/kis_devlp.yaml` > 기본값**입니다. 비어 있는 환경변수와 `.env` 항목은
기존 값을 덮어쓰지 않습니다. YAML 파일 없이도 빌더를 실행할 수 있습니다.
앱키·시크릿은 메모리에서 병합하며 YAML에 복사하지 않습니다.
발급된 접근토큰은 기존 방식대로 `~/KIS/config/`에 캐시됩니다.
`.env`/YAML 수정은 로그인 시 다시 읽고, 프로세스 환경변수 변경은 서버를 재시작해야 합니다.

```bash
# 터미널 1: strategy_builder 디렉터리
uv run uvicorn backend.main:app --host 127.0.0.1 --port 8000

# 터미널 2: strategy_builder/frontend 디렉터리
cd frontend
npm ci
npm run dev
```

로컬 브라우저에서 `http://127.0.0.1:3000`을 열고 설정에서 **모의투자**로 인증합니다.
주문 없이 연결만 확인하려면 다음 요청을 사용합니다.

```bash
curl --fail-with-body -sS http://127.0.0.1:8000/api/health
curl --fail-with-body -sS -X POST http://127.0.0.1:8000/api/auth/login \
  -H 'Content-Type: application/json' -d '{"mode":"vps"}'
curl --fail-with-body -sS http://127.0.0.1:8000/api/auth/status
curl --fail-with-body -sS 'http://127.0.0.1:8000/api/market/price/005930?env_dv=demo'
```

로그인 응답의 `authenticated: true`, 시세 응답의 `status: success`를 확인합니다.
헬스 체크 성공만으로 KIS 인증 성공을 판단하지 않습니다.

설정 로딩과 인증 실패 처리는 외부 API 호출 없이 검증할 수 있습니다.

```bash
# strategy_builder 디렉터리
uv run python -m unittest discover -s tests -v
```

### 서버 실행

```bash
cd strategy_builder
./start.sh
```

백엔드(8000)와 프론트엔드(3000)를 한 번에 시작합니다. `node_modules`가 없으면 `npm install`도 자동 실행됩니다.

브라우저에서 http://localhost:3000 으로 접속하면 전략 빌더 페이지가 표시됩니다.

**수동 실행이 필요할 때**

```bash
# Python 의존성 설치
uv sync

# Backend (터미널 1)
uv run uvicorn backend.main:app --host 127.0.0.1 --port 8000

# Frontend (터미널 2)
cd frontend
npm install
npm run dev
```

생성된 커스텀 Python 전략은 기본적으로 애플리케이션 소스와 분리된
`~/.kis_strategy_builder/strategies`에 저장됩니다. 다른 위치가 필요하면 서버 시작 전에
`KIS_STRATEGY_DIR` 환경변수로 전용 디렉터리를 지정할 수 있습니다.

기본 프론트엔드와 백엔드는 로컬 호스트에서만 접근할 수 있습니다. 외부 접속이 필요한
경우에는 인증과 접근통제가 적용된 역방향 프록시 뒤에서 운영하고 방화벽으로 직접 접근을
제한하십시오.

---


## 국내·미국 주식 공통 지원

전략 실행 화면에서 코스피·코스닥과 미국 나스닥·뉴욕·아멕스 종목을 함께 검색하고
시그널을 생성할 수 있습니다. 설정의 **마스터파일 수집**을 한 번 실행한 뒤
`AAPL`, `애플`, `APPLE` 등으로 검색하고 거래소가 표시된 결과를 선택하세요.
미국 시그널 카드를 클릭하면 USD 시세를 조회합니다.

**검색·현재가·일봉·시그널 생성**, 단일 미국 백테스트 및 미국 지정가 주문·취소·잔고를 지원합니다.
해외 ID는 국내 주문 경로로 전달하지 않습니다. 미국 주문은 설정의 전체 모드를 따르며 해외 호가는 지원하지 않습니다.
우측 계좌 영역은 국내 주식 잔고입니다. KIS 인증 모드와 계좌의 API 이용 권한이 필요하며,
시세의 실시간/지연 여부는 KIS 제공 조건을 따릅니다.

### 표시 통화와 USD/KRW 환율

설정의 **해외 시세 표시 통화**에서 USD 또는 KRW를 선택합니다. 선택은 브라우저에
저장되며, 원화 선택 시 미국 주식의 현재가와 전일 대비 금액을 같은 USD/KRW 환율로
환산합니다. 원 시세(USD)와 적용 환율도 함께 표시합니다. 전략 계산과 주문 값은 바뀌지 않습니다.

왼쪽 상단에는 `1달러 = ...원`, **마지막 조회 성공 시각**과 **KIS 제공 시각**을 표시합니다.
조회 시각은 브라우저의 시간대와 무관하게 `2026-10-14 01:23:45 KST` 형식으로
날짜와 초까지 표시합니다. KIS 제공 시각은 API 원문 기준이며 응답에 없으면 생략합니다.
조회 시각을 시세 발생 시각으로 사용하지 않습니다.

KIS 인증 후 활성 탭에서 30초마다 자동 갱신하고, 새로고침 버튼도 제공합니다.
서버는 모의/실전별로 30초간 응답을 캐시해 중복 호출을 줄입니다.
`/api/market/exchange-rate`는 KIS 해외지수 분봉 API의 `X / FX@KRW`를 조회합니다.
해당 모드에서 환율 시세 이용이 가능해야 하며, 장 마감·제공 지연 시 마지막 시세일 수 있습니다.

갱신에 실패하면 이전 환율과 마지막 성공 시각을 유지하고 **갱신 지연**을 표시합니다.
환율을 새로 확인할 수 없거나 마지막 조회가 90초를 넘으면 USD 표시로 돌아갑니다.
정상 조회가 복구되면 저장된 원화 설정을 다시 적용합니다. 환율 숫자나 갱신 시각을 임의로 만들지 않습니다.

### 공통 데이터 형식

앱 내부의 종목 형식은 원본 마스터파일 형식과 독립적입니다.
국내 고정폭/EUC-KR와 미국 탭 구분/CP949 원본을 어댑터에서 다음 공통 레코드로 변환합니다.

| 필드 | 국내 예 | 미국 예 |
|---|---|---|
| `id` | `KOSPI:005930` | `NASDAQ:AAPL` |
| `ticker` | `005930` | `AAPL` |
| `market` | `KR` | `US` |
| `exchange` | `kospi` | `nasdaq` |
| `currency` | `KRW` | `USD` |
| `name` | 삼성전자 | 애플 |
| `english_name` | 빈 문자열 | APPLE INC |
| `exchange_name` | 코스피 | 나스닥 |

`code`는 이전 클라이언트를 위한 호환 필드입니다. 새 코드는 `id`를 사용합니다.
`0000D0` 같은 국내 영숫자 코드, `NYSE:BRK/B` 같은 미국 클래스 티커도 보존합니다.
동일한 티커가 다른 거래소에 있으면 별개의 ID입니다.

저장 형식은 `.master/{exchange}.json`의
`{"schema_version": 1, "symbols": [...]}`입니다. 이전 국내 CSV는 읽을 때 공통 모델로
변환하며, 새 수집 결과는 JSON으로 저장합니다. 수집 실패 시 기존 파일을 유지합니다.

- `core/instruments.py`: 종목 ID·시장·통화 식별과 국내 전용 작업 검증
- `core/symbol_master.py`: 공통 스키마, 원본별 변환, 버전 저장·이전 CSV 호환
- `core/overseas_data.py`: 미국 시세를 공통 현재가/OHLCV로 변환
- `core/data_fetcher.py`: 종목 ID에 따라 조회 어댑터 선택

전략은 거래소별 응답 대신 `date/open/high/low/close/volume`을 받습니다.
일봉은 날짜 오름차순·날짜 중복 제거·소수점 보존을 적용하며 미국 일봉은 수정주가를 요청합니다.
미국 시세 요청 실패는 `ERROR` 시그널로 표시합니다. 매매 판단에 사용하는 가격 함수도
정수 절삭 없이 소수점을 유지합니다. 현재의 사용자 정의 전략에 별도 국내 API 호출이나
정수 변환이 있으면 해당 전략도 공통 조회 함수로 전환해야 합니다.

```bash
# 종목 수집·검색 (인증 불필요)
curl -sS -X POST http://127.0.0.1:8000/api/symbols/collect
curl -sS 'http://127.0.0.1:8000/api/symbols/search?q=AAPL&exchange=nasdaq'
# KIS 인증 후 시세 조회 (주문 아님)
curl -sS 'http://127.0.0.1:8000/api/market/price/NASDAQ:AAPL'
```

회귀 테스트는 `strategy_builder`에서 `uv run python -m unittest discover -s tests -v`로 실행합니다.
KIS 응답을 대체한 테스트로 공통 형식·기존 CSV·복합 티커·페이지 처리·소수점·혼합 시장 전략·해외 주문 차단을 검증합니다.
실제 KIS 인증 및 시세 연결의 성공 여부는 별도 확인이 필요합니다.

## 시스템 구성

```
┌──────────────────────────────────────────────────────────┐
│                    Frontend (Next.js)                     │
│                   http://localhost:3000                   │
│                                                          │
│   /builder                      /execute                 │
│   전략 설계 (빌더)               전략 실행 (시그널+주문)    │
│   YAML/Python Export            10종 전략 선택            │
│   로컬 저장                      종목 검색 + 시그널 생성   │
└────────────────────┬─────────────────────────────────────┘
                     │ Next.js Rewrite (/api/* → :8000)
                     ▼
┌──────────────────────────────────────────────────────────┐
│                    Backend (FastAPI)                      │
│                   http://localhost:8000                   │
│                                                          │
│   /api/strategies        10종 전략 (StrategyRegistry)    │
│   /api/strategies/execute    시그널 생성 (4가지 경로)     │
│   /api/orders/execute        주문 실행                   │
│   /api/auth/*                KIS API 인증                │
│   /api/market/*              시세/호가 조회              │
└────────────────────┬─────────────────────────────────────┘
                     │
                     ▼
          ┌─────────────────────┐
          │   KIS Open API      │
          │  (한국투자증권)       │
          │  모의투자 / 실전투자  │
          └─────────────────────┘
```

---

## 주요 기능

| 기능 | 설명 |
|------|------|
| 비주얼 빌더 (`/builder`) | 드래그 앤 드롭으로 지표/조건/리스크 설계 |
| 80개 기술지표 | RSI, MACD, 볼린저밴드, VWAP, 이치모쿠 등 |
| 57개 캔들스틱 패턴 | 도지, 잉걸핑, 해머 등 (Lean 미지원 9개 제외) |
| YAML Export/Import | `.kis.yaml` ↔ 빌더 양방향 변환 |
| Python 미리보기 | 빌더 상태 → 실행 가능한 Python 코드 실시간 생성 |
| 시그널 생성 (`/execute`) | 종목 입력 → BUY/SELL/HOLD + 강도(0~1) |
| 주문 실행 | 모의/실전 주문 (KIS Open API) |

---

## 전략 빌더

앱에 접속하면 전략 빌더 페이지가 표시됩니다.
좌측에 기본 전략 10종 + 내 전략 목록, 중앙에 5단계 빌더(지표→진입→청산→리스크→정보), 우측에 YAML/Python 미리보기가 배치됩니다.

![전략 빌더 메인](assets/01-builder-main.png)

**Step 1. 프리셋 전략 불러오기** — 좌측 목록에서 기본 전략을 클릭하면 지표, 조건, 리스크가 자동으로 채워집니다.

![프리셋 전략 로드](assets/02-preset-loaded.png)

**Step 2. 지표 추가** — `+ 지표 추가` 버튼으로 80개 기술지표 중 원하는 것을 선택합니다.

![지표 추가 패널](assets/03-add-indicator.png)

**Step 3. 진입/청산 조건 설정** — AND/OR 로직으로 조합합니다.
예: `SMA(5) cross_above SMA(20)`, `RSI > 70`

**Step 4. 리스크 관리** — 손절/익절/트레일링 스톱을 퍼센트 단위로 설정합니다.

**Step 5. 저장** — 전략 이름, 설명, 태그를 입력하고 로컬스토리지에 저장합니다.

![메타데이터 탭](assets/04-metadata-tab.png)

---

## YAML/Python Export

빌더 우측에 YAML과 Python 코드가 실시간으로 생성됩니다.

![YAML 미리보기](assets/05-yaml-preview.png)

![Python 미리보기](assets/06-python-preview.png)

| 버튼 | 동작 |
|------|------|
| **복사** | 클립보드에 YAML 또는 Python 코드 복사 |
| **Export** | `.kis.yaml` 파일로 다운로드 → **Backtester에서 백테스트 가능** |
| **Import** | 기존 YAML 파일을 드래그 앤 드롭으로 불러오기 |

---

## 전략 실행

상단 네비게이션에서 **전략 실행**을 클릭하면 실행 페이지로 이동합니다.

![전략 실행 페이지](assets/07-execute-page.png)

1. **전략 선택** — 10개 기본 전략이 카테고리별로 분류. 빌더에서 만든 로컬 전략도 선택 가능.

![전략 드롭다운](assets/08-strategy-dropdown.png)

> **종목 검색을 사용하려면 마스터파일 수집이 필요합니다.**
> 우측 상단 ⚙️ 설정 버튼 → 종목 마스터파일 섹션에서 **마스터파일 수집** 버튼을 클릭하여 종목 데이터를 먼저 다운로드하세요.
>
> ![마스터파일 수집](assets/10-collect-master.png)

2. **종목 선택** — 코드 직접 입력 또는 빠른 선택 버튼(삼성전자, SK하이닉스 등)

3. **시그널 생성** — BUY/SELL/HOLD 시그널 확인 후 주문 실행 가능 (KIS API 인증 필요)

---

## 인증 및 설정

우측 상단 톱니바퀴 → 설정 모달에서 인증 상태, 모의/실전 전환, 종목 마스터파일을 관리합니다.

![설정 모달](assets/09-settings-modal.png)

---

## 10개 프리셋 전략

| ID | 이름 | 카테고리 | 설명 |
|----|------|---------|------|
| `golden_cross` | 골든크로스 | 추세추종 | 단기 MA가 장기 MA를 상향 돌파 시 매수 |
| `momentum` | 모멘텀 | 추세추종 | N일 수익률 기준 매수/매도 |
| `trend_filter` | 추세 필터 | 추세추종 | MA 위/아래 추세 방향 매매 |
| `week52_high` | 52주 신고가 | 돌파매매 | 52주 최고가 돌파 시 매수 |
| `consecutive` | 연속 상승/하락 | 추세추종 | N일 연속 상승 시 매수 |
| `disparity` | 이격도 | 역추세 | MA 대비 이격 기준 매매 |
| `breakout_fail` | 돌파 실패 | 손절 | 전고점 돌파 실패 시 매도 |
| `strong_close` | 강한 종가 | 모멘텀 | 고가 대비 종가 위치로 매수 |
| `volatility` | 변동성 확장 | 돌파매매 | 변동성 최저에서 돌파 시 매수 |
| `mean_reversion` | 평균회귀 | 역추세 | N일 평균 대비 이탈 시 매매 |

---

## .kis.yaml 포맷

Strategy Builder와 Backtester가 공유하는 전략 정의 포맷입니다.
Strategy Builder에서 `.kis.yaml`로 내보낸 전략을 Backtester에서 불러와 백테스트를 수행하고,
검증이 완료된 전략을 다시 Strategy Builder에서 Import하여 실전 주문에 활용합니다.

```yaml
version: "1.0"

metadata:
  name: "골든크로스"
  description: "단기 MA가 장기 MA를 상향 돌파 시 매수"
  author: "KIS"
  tags: [ma, crossover, trend]

strategy:
  id: golden_cross
  category: trend

  indicators:
    - id: sma
      alias: sma_fast
      params:
        period: 5
    - id: sma
      alias: sma_slow
      params:
        period: 20

  entry:
    logic: AND
    conditions:
      - indicator: sma_fast
        operator: cross_above
        compare_to: sma_slow

  exit:
    logic: AND
    conditions:
      - indicator: sma_fast
        operator: cross_below
        compare_to: sma_slow

risk:
  stop_loss:
    enabled: true
    percent: 5.0
```

### 사용 가능한 연산자

| 연산자 | 의미 |
|--------|------|
| `cross_above` | 상향 돌파 |
| `cross_below` | 하향 돌파 |
| `greater_than` | 초과 |
| `less_than` | 미만 |
| `greater_equal` | 이상 |
| `less_equal` | 이하 |
| `equals` | 같음 |

---

## API 엔드포인트

### 인증

| Method | Path | 설명 |
|--------|------|------|
| `GET` | `/api/auth/status` | 인증 상태 확인 (모드, 인증 여부) |
| `POST` | `/api/auth/login` | 로그인 (mode: `vps` 모의투자 / `prod` 실전투자) |

### 전략

| Method | Path | 설명 |
|--------|------|------|
| `GET` | `/api/strategies` | 전략 목록 (10종, builder_state 포함) |
| `GET` | `/api/strategies/indicators` | 사용 가능한 지표 목록 |
| `POST` | `/api/strategies/execute` | 전략 실행 → 시그널 생성 |
| `POST` | `/api/strategies/preview` | Python 코드 미리보기 |
| `GET` | `/api/strategies/custom` | 커스텀 전략 목록 |

### 계좌 / 주문

| Method | Path | 설명 |
|--------|------|------|
| `GET` | `/api/account/holdings` | 보유 종목 |
| `GET` | `/api/account/balance` | 예수금 / 평가금액 |
| `POST` | `/api/orders/execute` | 주문 실행 (매수/매도) |

### 시장 / 파일

| Method | Path | 설명 |
|--------|------|------|
| `GET` | `/api/market/orderbook/:code` | 호가 조회 |
| `WS` | `/api/market/ws/:code` | 실시간 호가 (WebSocket) |
| `GET` | `/api/files/templates` | YAML 전략 템플릿 목록 |
| `POST` | `/api/files/import` | YAML 파일 Import |
| `POST` | `/api/files/export` | 전략 Export |

---

## 디렉토리 구조

```
strategy_builder/
├── assets/                     # 유저 플로우 스크린샷
│
├── backend/                    # FastAPI 서버 (port 8000)
│   ├── main.py                 # 앱 진입점
│   └── routers/
│       ├── auth.py             # 인증 API
│       ├── account.py          # 계좌 API (잔고/보유종목)
│       ├── strategy.py         # 전략 API (목록/실행/미리보기)
│       ├── orders.py           # 주문 API (매수/매도)
│       ├── market.py           # 시장 API (호가/웹소켓)
│       ├── files.py            # 파일 API (YAML 템플릿)
│       └── symbols.py          # 종목 검색
│
├── strategy_core/              # 전략 엔진 (SSoT)
│   ├── registry.py             # StrategyRegistry (@register 데코레이터)
│   ├── executor.py             # 4가지 실행 경로 통합
│   ├── dsl/
│   │   ├── converter.py        # BuilderState → DSL 변환
│   │   ├── parser.py           # DSL → AST 파싱
│   │   └── codegen.py          # AST → Python 코드 생성
│   └── preset/                 # 10개 프리셋 전략 정의
│
├── core/                       # 핵심 모듈
│   ├── signal.py               # Signal, Action 정의
│   ├── indicators.py           # 기술적 지표 계산 (80종)
│   ├── data_fetcher.py         # KIS API 데이터 조회
│   ├── order_executor.py       # 주문 실행
│   ├── position_manager.py     # 포지션 관리
│   └── websocket_manager.py    # 실시간 데이터
│
├── strategy/                   # 전략 구현체
│   ├── base_strategy.py        # BaseStrategy 클래스
│   └── strategy_01 ~ 10.py    # 10개 전략 파일
│
├── frontend/                   # Next.js 프론트엔드 (port 3000)
│   └── src/
│       ├── app/
│       │   ├── builder/        # 전략 빌더 페이지
│       │   └── execute/        # 전략 실행 페이지
│       ├── components/
│       │   ├── builder/        # 빌더 UI (지표, 조건, 리스크, 미리보기)
│       │   ├── execute/        # 실행 UI (전략 선택, 시그널, 주문)
│       │   ├── file/           # FileDropZone, ExportButton
│       │   └── layout/         # Navigation, Settings
│       ├── hooks/              # useStrategyBuilder, useAuth, useOrder ...
│       ├── lib/
│       │   ├── api/            # Backend API 클라이언트
│       │   └── builder/        # 80개 지표 정의, YAML 변환
│       └── types/              # TypeScript 타입 정의
│
├── examples/                   # 실행 예제 (README.md 참조)
└── kis_auth.py                 # KIS API 인증 모듈
```

---

## 연동: Strategy Builder + Backtester

Strategy Builder와 Backtester는 `.kis.yaml` 파일 포맷으로 연동되어 **설계 → 검증 → 실행**의 완전한 퀀트 워크플로우를 구성합니다.

| 단계 | 시스템 | 내용 |
|------|--------|------|
| 1. 전략 설계 | **Strategy Builder** | 비주얼 UI로 지표/조건/리스크 설정 |
| 2. Export | `.kis.yaml` | 설계한 전략을 YAML 파일로 내보내기 |
| 3. 백테스트 | **Backtester** | 과거 데이터(Lean)로 전략 성과 검증 |
| 4. 분석 | **Backtester** | 수익률, 샤프비율, 최대낙폭 분석 |
| 5. 최적화 | **Backtester** | Grid/Random Search로 최적 파라미터 탐색 |
| 6. 실전 적용 | **Strategy Builder** | 검증된 전략으로 실시간 시그널 + 모의/실전 주문 |

```
┌──────────────────────────────────────────────────────────────────┐
│                    전체 퀀트 워크플로우                             │
│                                                                  │
│   Builder ──Export──▶ .kis.yaml ──Import──▶ Backtester            │
│      ▲                                         │                 │
│      │                                    결과 분석               │
│      │                                    (수익률, 샤프비율)       │
│      │                                         │                 │
│      │         성과 좋으면                       │                 │
│   Builder ◀────────────────────────────────────┘                  │
│   (모의투자로 먼저 검증 → 실전투자)                                 │
└──────────────────────────────────────────────────────────────────┘
```

| 기능 | Strategy Builder | Backtester |
|------|------------------|------------|
| 전략 설계 | 비주얼 빌더 | - |
| 시그널 생성 | 실시간 | - |
| 주문 실행 | 모의/실전 | - |
| 백테스트 | - | Lean (Docker) |
| 포트폴리오 분석 | - | 분석/시각화 |
| 파라미터 최적화 | - | Grid/Random |
| **공유 포맷** | `.kis.yaml` Export | `.kis.yaml` Import |

## 미국 단일 종목 백테스트와 해석

상단 **미국 백테스트**에서 `NASDAQ:AAPL` 같은 ID, 시작·종료일, 기본 전략 또는
저장한 시각적 전략, USD 초기 자금, 수수료·슬리피지 비율을 선택합니다.
`/api/backtest`는 기존 빌더 DSL과 공통 지표를 재사용합니다. Python 전용 전략은
이 화면에서 지원하지 않습니다. 기존 국내 Lean 백테스터는 그대로 사용합니다.

일봉 마감 판단을 다음 확보된 거래일 시가에 체결하며, 매수 우선·정수 주식·전액 투자·
공매도 없음·마지막 강제 청산 없음입니다. 수수료는 양방향 거래대금 비율,
슬리피지는 매수 시가 증가/매도 시가 감소 비율입니다. 청산 거래만 거래 횟수와 승률에
포함하고 미청산 보유는 마지막 종가로 평가합니다. 승률이 정의되지 않으면 정의 불가를 표시합니다.
단순 보유 비교는 첫 봉 시가 매수, 비용 제외입니다. 수익률과 낙폭은 API에서 0~1 비율입니다.

가격·실제 사용 지표·자산·낙폭 차트는 날짜와 툴팁을 공유하고 범위 슬라이더로 확대합니다.
신호/체결 점 또는 거래의 진입 날짜를 클릭하면 실제 DSL 피연산자, 비교 결과,
이전 봉 교차 값과 체결 가격·수수료를 표시합니다. 신호는 거래소 일봉 날짜로 제공하며,
응답에 없는 실제 발생 시각은 생성하지 않습니다.

KIS 수정주가 일봉을 종료일부터 역순 페이지 조회합니다. 중복 날짜를 제거하고 잘못된
OHLC·숫자·빈 기간을 거절합니다. 조회 상한은 40페이지이며 거래일 달력과 공급자 내부
결측을 대조하지 않으므로 **전체 기간 완전성 미검증**과 실제 확보 범위를 항상 표시합니다.
과거 환율은 제공하지 않으며 성과는 USD만 표시합니다. 현재 환율로 과거 KRW 수익률을
계산하지 않습니다. 기본 전략의 백테스트는 레지스트리에 저장된 시각적 정의 기준입니다.

검증: `python -m unittest discover -s tests -v`, 프런트엔드 `npm run build`.
브라우저 검증은 별도로 설치한 Playwright를 사용해
`NODE_PATH=/path/to/node_modules node tests/browser/backtest.cjs`를 실행합니다.
브라우저 테스트의 가격과 응답은 명시적인 테스트 fixture이며 실제 KIS 연결 검증이 아닙니다.

첫 단계 검증 기록: 외부 응답을 대체한 Python 회귀 46개 통과. 프런트엔드 빌드 통과.
초기 분리 worktree에서는 실제 연동을 실행하지 않았습니다. 마지막 단계에서 원래 로컬 설정을
재사용해 수행한 실제 읽기 결과는 아래 최종 검증 기록을 참고하세요.
브라우저 검증 통과: 데스크톱/390px 모바일, 요청 종목·초기 자금, 백엔드 성과 숫자,
거래 클릭의 실제 조건값·수수료, 차트 존재와 확대 범위 변경. API 응답 대체 검증입니다.

## 미국 주문 및 계좌 · 전체 모드 통합

**설정 → 인증 및 모드**가 국내·미국의 주문·취소·잔고 조회 모드를 결정합니다.
미국 전용 모드 선택이나 별도 모의투자 메뉴는 없습니다. `/paper`는 `/execute`로 이동합니다.
미국 시그널을 선택해 현재가를 조회한 다음 **주문 확인**을 누릅니다. 기존 국내와 같은
확인·결과 화면에서 종목·거래소·수량·USD 지정가·총액·현재 설정 모드를 확인합니다.
미국은 초기 지정가·정수 수량을 지원하며 호가·시장가 옵션은 제공하지 않습니다.
KRW 설정이면 유효 환율과 조회 시각을 포함한 참고 금액도 표시하지만 주문은 USD입니다.
접수는 체결 완료가 아니며, 모의는 가상 자금·실전은 해당 실전 계좌의 실제 자금입니다.

오른쪽 **국내 주식 / 미국 주식** 계좌 탭에서 계좌 전체의 잔고·미체결을 조회합니다.
탭 선택은 새로고침 후 복원되고 종목 선택과 무관하게 유지됩니다. 미국 탭은 수량·평균가·
현재가·평가액·손익·수익률을 USD로 표시합니다. 국내와 합산하지 않습니다.
미체결은 최근 30일 주문내역 중 남은 수량을 표시하며 **주문 취소**를 요청할 수 있습니다.
조회에 실패하면 이전 데이터와 성공 시각을 유지하고 갱신 지연을 표시합니다.

`/api/us-stock/order`, `/cancel`, `/holdings`, `/pending`, `/buyable`은 설정 모드와
실제 KIS 인증 모드의 일치를 서버에서 확인합니다. 클라이언트에서 모드를 지정하지 않습니다.
NASDAQ/NASD, NYSE/NYSE, AMEX/AMEX를 주문 코드로 매핑하고 시세의 NAS/NYS/AMS와
구분합니다. 클래스 티커를 보존하고 USD 정밀도를 반올림하지 않습니다.
1 USD 이상은 0.01 USD, 미만은 0.0001 USD의 보수적 주문 단위를 지원합니다.
실전/모의 TR ID를 각각 사용하며 미국 모의 매도 ID는 실전 ID의 접두어 치환으로 만들지 않습니다.
이전 `/api/us-paper` 경로는 모의 전용 호환 경로로 남으며 새 화면은 사용하지 않습니다.

인증 전환과 API 요청의 계좌·토큰·서버 주소가 섞이지 않도록 공통 요청 컨텍스트를 잠급니다.
조회나 환율 갱신으로 모드를 바꾸지 않습니다. 실제 모의 API 최소 간격 0.5초, 실전 0.05초가
모드 전환 때 갱신되도록 기존 지역변수 할당 문제도 수정했습니다.

요청 ID별 내용과 접수 결과는 `~/.kis_strategy_builder/paper_orders.sqlite3`에
저장합니다(이전 파일 이름 유지, 모드·계좌별 분리). `KIS_ORDER_JOURNAL`로 경로를 지정할 수
있습니다. 동일 ID·동일 내용은 저장한 결과를 반환하고 다른 내용은 409 오류입니다.
제출 전에 기록하므로 동시 요청·서버 중단·시간 초과 이후에도 자동 재전송하지 않습니다.
`unknown`은 **접수 확인 필요**로 표시하며 새로고침 이후에도 재제출을 막습니다.
계좌 내역으로 수동 대조가 필요합니다. 여러 서버는 같은 journal을 사용해야 합니다.
서로 다른 요청 ID의 명시적인 별도 주문은 독립된 주문입니다.

최초 두 번째 단계는 모의 전용으로 구현됐고, 이후 사용자의 지시에 따라 위 전체 모드
통합과 미국 실전 매핑을 마지막 기능 브랜치에 추가했습니다. 기존 국내 경로의 시장 분리
검증과 모의 전용 호환 경로 검증은 유지하고, 새 공통 미국 경로의 모의/실전 매핑을 별도로
검증합니다. 실제 모의·실전 주문은 이 작업에서 제출하지 않았습니다.

## 관심 종목 자동 갱신

상단 **관심 종목**(`/watchlist`)에서 기본/저장한 시각적 전략을 선택하고 종목 검색
또는 공통 ID로 국내·미국 종목을 추가합니다. 거래소가 다른 같은 티커는 별도 종목이며,
목록·종목별 전략·갱신 간격·시작 설정은 새로고침 후 복원됩니다. 최대 20종목을 지원합니다.

**시작**, **일시정지**, **수동 새로고침**을 제공합니다. 기본 시세 30초·시그널 60초이며,
실제 최소 간격은 종목 수에 따라 시세 `종목 수×2초`, 시그널 `종목 수×10초`로 늘어납니다.
서버 캐시는 모드·종목·전략 정의별로 분리하고 시세 25초·판단 60초 동안 같은 조회를
합칩니다. 캐시를 다시 받았을 때 공급자 조회 성공 시각을 새 시각으로 바꾸지 않습니다.

일봉 전략은 거래소 현지 날짜 기준 오늘 봉을 제외합니다. 미국 날짜는
`America/New_York` 시간대를 사용해 서머타임을 적용합니다. 일봉 기준 날짜와 앱 조회
시각은 별개이며 공급자 실제 신호 시각이 없어 시각을 추정하지 않습니다. Python 전용
전략은 이 감시 화면에서 지원하지 않습니다. 완성 일봉과 필요한 지표가 부족하면 오류입니다.

각 종목에 가격·등락률·통화·최근 판단·기준 봉 날짜·마지막 성공 조회·다음 조회·오류를
표시합니다. 실패하면 이전 가격과 성공 시각을 유지하고 갱신 지연을 표시합니다.
USD/KRW 설정과 기존 환율 갱신을 재사용하고 유효 환율이 없으면 USD로 표시합니다.
조회 시각은 `YYYY-MM-DD HH:mm:ss KST`입니다. 공급자의 시세 발생 시각이 응답에 없으면
**미제공**으로 표시합니다. 휴장·조기 폐장 달력을 연결하지 않아 시장 상태는
**알 수 없음**으로 표시하며, 현지 시각을 개장 판단으로 사용하지 않습니다.

동일 종목·전략 정의·기준 봉의 신호 ID를 저장해 같은 일봉을 다시 받은 것을 새 신호로
기록하지 않습니다. 이후 새로운 BUY/SELL 기준 봉이면 해당 행을 강조합니다. 종목명을
누르면 실제 판단 근거가 열리고 미국 종목은 백테스트의 해당 종목·전략으로 연결됩니다.
숨김 탭에서는 요청을 중단하고 복귀 시 확인합니다. 설정 변경·모드 변경·늦은 응답은
이전 요청의 값으로 최신 화면을 덮어쓰지 못합니다. 중복 실행을 방지하고 연속 오류는
최대 5회, 지수 지연 최대 5분 후 수동 확인을 요구합니다. 수동 갱신으로 복구할 수 있습니다.

이 기능에는 주문 호출이 없습니다. 브라우저 화면을 종료하면 감시도 종료됩니다.
서버 상시 감시·자동 주문·시장 달력·진행 중 일봉 옵션은 제공하지 않습니다.

타이머 검증: `node tests/frontend/refresh-loop.cjs`.
브라우저 검증: `NODE_PATH=/path/to/node_modules node tests/browser/watchlist.cjs`.

## 최종 검증 기록

- Python 회귀: 첫 단계 46개, 두 번째 단계 58개, 최종 72개 통과.
- 타이머 테스트: 시작/중지·중복 방지·숨김/복귀·늦은 응답·지수 지연·5회 중지·수동 복구·신호 ID 통과.
- 프런트엔드 production 빌드 통과. 브라우저는 외부 응답을 대체해 데스크톱/390px 모바일에서
  백테스트 값·거래 근거·확대·종목 링크, 전체 모의/실전 주문 확인·USD 값·KRW 참고·접수 불명,
  독립 계좌 탭·선택 복원, 관심 목록 저장/삭제·동일 티커의 다른 거래소·오류/복구·중복 신호·주문 호출 0건을 검증했습니다.
- 실제 읽기: 원래 로컬 `.env`와 저장된 모의 인증을 재사용했습니다(비밀값 복사·출력 없음).
  인증 상태 확인, AAPL 현재가, 완성 일봉 시그널(기준 20261012), 기간 백테스트 조회가 성공했습니다.
  2025-01-01~2025-04-01 요청에서 실제 20250102~20250401의 61개 봉을 확보했습니다.
  휴장 달력/결측 대조는 없으므로 기간 완전성은 계속 미검증으로 표시합니다.
- 실제 계좌 읽기: 미체결은 “모의투자 처리계좌의 ID와 사용자정보가 상이하여 처리 불가능” 오류로
  거절됐습니다. 잔고 읽기에서도 계좌 불일치와 초당 거래건수 제한 실패를 확인했습니다.
  로컬 설정의 모의 앱키·계좌·사용자 ID가 같은 가입 정보에 속하는지 확인해야 합니다.
- 초기 시세/기간 실패의 공급자 500 응답은 `EGW00201`(초당 거래건수 초과)이었습니다.
  모의 최소 간격 수정 후 현재가·61개 봉 백테스트 읽기는 성공했습니다. 여러 백엔드가 같은
  앱키로 동시에 조회하면 공급자 제한을 합산해 적용하므로 중복 서버 실행을 피해야 합니다.
- 실제 모의·실전 주문/취소와 실전 계좌 읽기는 미실행입니다. 실전 매핑 검증은 모든 응답을 대체했습니다.
- 국내 전략/조회/주문 경로의 회귀 검증은 유지했습니다. 국내 Lean Docker 백테스트의 실제 실행은 미실행입니다.

기존에 실행 중인 백엔드가 새 경로를 모르면 종료 후 다시 시작해야 합니다. 빌드 성공과
API 응답 대체 테스트를 실제 KIS 계좌 연결 성공으로 간주하지 않습니다.
