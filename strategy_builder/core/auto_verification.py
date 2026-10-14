"""Independent, read-only broker checks. Authentication is not account readiness."""
from datetime import datetime, timezone
from decimal import Decimal
import kis_auth as ka
from backend import is_authenticated, get_current_mode
from core import us_stock, overseas_data, watchlist, us_calendar
from core.instruments import parse_instrument
from core.auto_trading import CODE, calculation, service
from strategy_core.preset.golden_cross import GoldenCrossPreset


def verify():
    checks = {}
    values = {}
    def check(name, call):
        started = datetime.now(timezone.utc).isoformat()
        try:
            values[name] = call()
            checks[name] = dict(status='passed', fetched_at=started)
        except Exception as error:
            checks[name] = dict(status='failed', fetched_at=started, message=str(error).strip())
            if '90070000' in str(error):
                checks[name]['remedy'] = '모의 앱키 발급 사용자에 연결된 my_paper_stock와 my_htsid를 .env에서 확인 후 모의 재인증하세요.'

    with ka.trading_context_lock:
        mode = get_current_mode()
        if mode != 'vps' or not is_authenticated() or not ka.isPaperTrading():
            return dict(mode=mode, ready=False, order_ready=False, checks=dict(authentication=dict(status='failed',message='모의투자 인증이 필요합니다')),fetched_at=datetime.now(timezone.utc).isoformat())
        check('authentication', lambda: us_stock._account('vps'))
        check('calendar', lambda: us_calendar.session(datetime.now(timezone.utc)))
        check('daily_signal', lambda: watchlist.signal(CODE,'vps',GoldenCrossPreset.builder_state,'golden_cross'))
        check('minute_quote', lambda: overseas_data.latest_minute(parse_instrument(CODE)))
        check('holdings', lambda: us_stock.holdings('vps'))
        check('order_history', lambda: us_stock.order_history(mode='vps'))
        quote = values.get('minute_quote')
        if quote:
            def amount():
                price = calculation(0,0,quote['price'],service().snapshot()['config'])['limit_price_usd']
                return us_stock.buyable(CODE,price,'vps')
            check('buyable', amount)
            def freshness():
                age = (datetime.now(timezone.utc)-datetime.fromisoformat(quote['provider_at'])).total_seconds()
                if not 0 <= age < 120:
                    raise ValueError('분봉이 2분 이상 오래되었거나 미래 시각입니다. 정규장에 다시 확인하세요.')
                return age
            check('quote_freshness', freshness)
        else:
            for name in ('buyable','quote_freshness'):
                checks[name] = dict(status='skipped',message='분봉 확인 실패')
        required = ('authentication','holdings','order_history','buyable','daily_signal','minute_quote','calendar')
        ready = all(checks.get(name,{}).get('status') == 'passed' for name in required)
        market = values.get('calendar',{})
        order_ready = ready and market.get('is_open',False) and checks.get('quote_freshness',{}).get('status')=='passed'
        # Do not include authentication values: they contain account identity.
        return dict(mode='vps',paper_only=ka.paper_only(),ready=ready,order_ready=order_ready,checks=checks,
                    market=market,signal=values.get('daily_signal'),quote=quote,
                    holdings_count=len(values['holdings']) if 'holdings' in values else None,order_count=len(values['order_history']) if 'order_history' in values else None,
                    buyable=values.get('buyable'),fetched_at=datetime.now(timezone.utc).isoformat(),
                    limitation='조회 검증입니다. 주문 접수·체결·취소 검증은 별도로 수행해야 합니다.')
