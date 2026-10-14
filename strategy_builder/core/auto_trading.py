"""Durable single-worker automation. Read APIs never submit orders."""
import asyncio
import fcntl
import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager, closing
from datetime import datetime, timezone, timedelta
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field
import kis_auth as ka
from backend import is_authenticated, get_current_mode
from core import us_stock, watchlist, overseas_data, us_calendar
from core.instruments import parse_instrument
from strategy_core.preset.golden_cross import GoldenCrossPreset
from backend.routers.us_paper import Order, Cancel, once, journal_path

CODE = 'NASDAQ:AAPL'
ACTIVE = ('accepted', 'partial', 'unknown', 'cancel_pending')

def now(): return datetime.now(timezone.utc)

def whole_quantity(value):
    quantity=Decimal(str(value))
    if not quantity.is_finite() or quantity<0 or quantity!=quantity.to_integral_value():
        raise ValueError('공급자 수량은 0 이상의 정수여야 합니다')
    return int(quantity)

def scope(mode):
    us_stock._account(mode)
    env = ka.getTREnv()
    return hashlib.sha256(f'{mode}:{env.my_acct}:{env.my_prod}'.encode()).hexdigest()

class Settings(BaseModel):
    instrument_id: Literal['NASDAQ:AAPL'] = CODE
    strategy_id: Literal['golden_cross'] = 'golden_cross'
    buy_percent: Decimal = Field(default=Decimal(10), gt=0, le=100, allow_inf_nan=False)
    sell_percent: Decimal = Field(default=Decimal(100), gt=0, le=100, allow_inf_nan=False)
    buy_offset_percent: Decimal = Field(default=Decimal('.1'), ge=0, le=5, allow_inf_nan=False)
    sell_offset_percent: Decimal = Field(default=Decimal('.1'), ge=0, le=5, allow_inf_nan=False)
    cancel_seconds: int = Field(default=300, ge=30, le=3600, strict=True)

def calculation(amount, maximum, reference, config, action='BUY', owned=0):
    price = Decimal(str(reference))
    offset = Decimal(str(config['buy_offset_percent' if action=='BUY' else 'sell_offset_percent'])) / 100
    price *= 1 + offset if action=='BUY' else 1 - offset
    tick = Decimal('.01') if price >= 1 else Decimal('.0001')
    price = price.quantize(tick, rounding=ROUND_UP if action=='BUY' else ROUND_DOWN)
    us_stock.validate_price(price)
    available = Decimal(str(amount))
    maximum = Decimal(str(maximum))
    if not available.is_finite() or available < 0 or not maximum.is_finite() or maximum < 0:
        raise ValueError('주문 가능 금액/수량 오류')
    budget = available * Decimal(str(config['buy_percent'])) / 100
    spendable = budget * Decimal('.99')
    quantity = min(int(spendable / price), int(maximum)) if action=='BUY' else int(Decimal(owned)*Decimal(str(config['sell_percent']))/100)
    return dict(available_usd=str(available),provider_max_quantity=int(maximum),budget_usd=str(budget),
                spendable_usd=str(spendable),fee_reserve_usd=str(budget-spendable),quantity=quantity,
                limit_price_usd=str(price),total_usd=str(price*quantity),action=action)

class Engine:
    def __init__(self, path=None):
        self.path=Path(path or os.environ.get('KIS_AUTO_TRADING_DB',str(Path.home()/'.kis_strategy_builder'/'auto_trading.sqlite3')))
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY, data TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS orders (id TEXT PRIMARY KEY, data TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS signals (id TEXT PRIMARY KEY, data TEXT NOT NULL)')
            initial=dict(config=Settings().model_dump(mode='json'),running=False,reason='사용자 시작 대기',basis=None,
                         account=None,mode=None,owned=0,manual=0,last_success=None,next_run=None,heartbeat=None,decision=None,preview=None)
            db.execute('INSERT OR IGNORE INTO state VALUES (1,?)',(json.dumps(initial),))
        os.chmod(self.path,0o600)
        self.owner=None

    @contextmanager
    def locked(self):
        with open(str(self.path)+'.operation.lock','a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            with closing(sqlite3.connect(self.path,timeout=60)) as db:
                state=json.loads(db.execute('SELECT data FROM state WHERE id=1').fetchone()[0])
                try:
                    yield db,state
                finally:
                    db.execute('UPDATE state SET data=? WHERE id=1',(json.dumps(state),));db.commit()

    def acquire(self):
        handle=open(str(self.path)+'.owner.lock','a')
        try: fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: handle.close();return False
        self.owner=handle
        with self.locked() as (_,s):
            s.update(running=False,reason='서버 재시작: 주문 복구 후 사용자 시작 필요',basis=None,next_run=None,heartbeat=now().isoformat())
        return True

    def release(self):
        if self.owner:
            with self.locked() as (_,s):s.update(running=False,reason='서버 종료',heartbeat=None)
            self.owner.close();self.owner=None

    def orders(self,db):return [json.loads(row[0]) for row in db.execute('SELECT data FROM orders ORDER BY rowid DESC')]
    def save_order(self,db,order):
        db.execute('INSERT OR REPLACE INTO orders VALUES (?,?)',(order['id'],json.dumps(order)));db.commit()

    def snapshot(self):
        with self.locked() as (db,s):
            return dict(s,orders=self.orders(db)[:100],signals=[json.loads(r[0]) for r in db.execute('SELECT data FROM signals ORDER BY rowid DESC LIMIT 30')],
                        current_mode=get_current_mode(),authenticated=is_authenticated(),fetched_at=now().isoformat())

    def configure(self,settings):
        with self.locked() as (_,s):
            if s['running']:raise ValueError('설정 변경 전에 중지하세요')
            s['config']=settings.model_dump(mode='json');s['preview']=None
        return self.snapshot()

    def start(self,mode):
        with ka.trading_context_lock, self.locked() as (db,s):
            if not is_authenticated() or mode!=get_current_mode():raise ValueError('화면 모드와 현재 인증 모드가 일치해야 합니다')
            identity=scope(mode)
            if not s['heartbeat'] or (now()-datetime.fromisoformat(s['heartbeat'])).total_seconds()>90:raise ValueError('서버 감시 작업이 준비되지 않았습니다')
            if any(o['status'] in ACTIVE for o in self.orders(db)):raise ValueError('진행 중 주문 또는 접수 확인 필요 주문이 있습니다')
            if s['owned'] and s['account']!=identity:raise ValueError('기존 자동매매 보유 계좌와 다릅니다')
            baseline=watchlist.signal(CODE,mode,GoldenCrossPreset.builder_state,'golden_cross')
            holdings=us_stock.holdings(mode)
            held=sum(whole_quantity(h['quantity']) for h in holdings if h['instrument_id']==CODE)
            if held<s['owned']:raise ValueError('자동매매 보유량과 실제 잔고 불일치')
            pending=us_stock.pending(mode=mode)
            if any(o['instrument_id']==CODE for o in pending):raise ValueError('계좌에 기존 미체결 주문 있음')
            quote=overseas_data.latest_minute(parse_instrument(CODE))
            price=calculation(0,0,quote['price'],s['config'])['limit_price_usd']
            us_stock.buyable(CODE,price,mode)
            self.check(dict(mode=mode,account=identity))
            s.update(running=True,reason=None,account=identity,mode=mode,basis=baseline['basis_date'],decision=baseline,
                     manual=held-s['owned'],next_run=now().isoformat())
        return self.snapshot()

    def stop(self):
        with self.locked() as (_,s):s.update(running=False,reason='사용자 중지',next_run=None)
        return self.snapshot()

    def check(self,s):
        if not is_authenticated() or get_current_mode()!=s['mode'] or scope(s['mode'])!=s['account']:
            raise ValueError('인증 해제 또는 모드·계좌 변경')

    def track(self,db,s,current):
        active=[o for o in self.orders(db) if o['status'] in ACTIVE]
        if not active:return
        self.check(s)
        start=min(o['created_at'][:10].replace('-','') for o in active)
        history=us_stock.order_history(start=start,mode=s['mode'])
        for order in active:
            if order['status']=='unknown':
                # A crash after the shared journal saved acceptance can leave the
                # automation row unknown. Recover that known order without resending.
                with closing(sqlite3.connect(journal_path())) as journal:
                    table=journal.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='requests'").fetchone()
                    saved=journal.execute('SELECT result FROM requests WHERE key=?',(order['account']+':'+order['id'],)).fetchone() if table else None
                result=json.loads(saved[0]) if saved else {}
                if result.get('status') in ('accepted','rejected'):
                    order.update(status=result['status'],order_no=result.get('order_no'),result=result)
                    self.save_order(db,order)
                else:
                    s.update(running=False,reason='접수 확인 필요: 자동 재전송 금지');continue
            if order['status']=='rejected':continue
            matches=[r for r in history if str(r['order_no'])==str(order['order_no']) and r['instrument_id']==CODE]
            if len(matches)!=1:raise ValueError('주문번호별 체결 내역 확인 불가')
            row=matches[0]
            filled=whole_quantity(row['filled']);remaining=whole_quantity(row['remaining'])
            if row['action']!=order['action'] or whole_quantity(row['quantity'])!=order['quantity'] or filled<order['filled'] or filled>order['quantity'] or remaining<0 or filled+remaining>order['quantity']:
                raise ValueError('계좌 주문 내역 불일치')
            delta=filled-order['filled']
            updated_owned=s['owned']+(delta if order['action']=='BUY' else -delta)
            if updated_owned<0:raise ValueError('자동매매 보유량 불일치')
            s['owned']=updated_owned
            order['filled']=filled
            cancelled=row['cancelled'] or any(r['cancelled'] and str(r.get('original_order_no'))==str(order['order_no']) for r in history)
            order['status']='filled' if filled==order['quantity'] else 'rejected' if row['rejected'] else 'cancelled' if remaining==0 and cancelled else 'partial' if filled else 'accepted'
            if order.get('cancel_requested') and order['status'] in ('accepted','partial'):order['status']='cancel_pending'
            order['provider_date']=row.get('provider_date');order['provider_time']=row.get('provider_time')
            db.execute('INSERT OR REPLACE INTO orders VALUES (?,?)',(order['id'],json.dumps(order)))
            # Persist position alongside cumulative fill BEFORE a cancel/network request.
            db.execute('UPDATE state SET data=? WHERE id=1',(json.dumps(s),));db.commit()
            if remaining>0 and order['status'] in ('accepted','partial') and current>=datetime.fromisoformat(order['cancel_at']):
                order['cancel_requested']=True;order['status']='cancel_pending';self.save_order(db,order)
                result=once(Cancel(request_id=order['id']+'_cancel',instrument_id=CODE,order_no=str(order['order_no']),quantity=remaining),
                            'cancel',lambda code:us_stock.cancel(code,order['order_no'],remaining,s['mode']),paper_only=False)
                order['cancel_result']=result;self.save_order(db,order)

    def preview(self):
        # Explicit read-only account/amount refresh, also usable while stopped.
        with ka.trading_context_lock, self.locked() as (_,s):
            if not is_authenticated():raise ValueError('인증이 필요합니다')
            mode=get_current_mode();identity=scope(mode)
            quote=overseas_data.latest_minute(parse_instrument(CODE))
            cfg=s['config'];price=calculation(0,0,quote['price'],cfg)['limit_price_usd']
            balances=us_stock.holdings(mode);pending=us_stock.pending(mode=mode);buyable=us_stock.buyable(CODE,price,mode)
            held=sum(whole_quantity(h['quantity']) for h in balances if h['instrument_id']==CODE)
            owned=s['owned'] if identity==s['account'] else 0
            if not s['running']:s['manual']=max(0,held-owned)
            sell=calculation(buyable.get('amount_decimal',buyable['amount']),buyable.get('quantity_decimal',buyable['quantity']),quote['price'],cfg,'SELL',owned)
            orderable=[h.get('orderable_quantity') for h in balances if h['instrument_id']==CODE]
            maximum_sell=sum(int(q) for q in orderable) if all(q is not None for q in orderable) else None
            if maximum_sell is not None:
                sell['quantity']=min(sell['quantity'],maximum_sell)
                sell['total_usd']=str(Decimal(sell['limit_price_usd'])*sell['quantity'])
            sell['provider_max_quantity']=maximum_sell
            s['preview']=calculation(buyable.get('amount_decimal',buyable['amount']),buyable.get('quantity_decimal',buyable['quantity']),quote['price'],cfg)|dict(provider_at=quote['provider_at'],fetched_at=now().isoformat(),
                        sell=sell,pending_count=len(pending),mode=mode)
        return self.snapshot()

    def tick(self,current=None):
        current=current or now()
        with ka.trading_context_lock, self.locked() as (db,s):
            s['heartbeat']=current.isoformat()
            try:
                self.track(db,s,current)
                if not s['running']:return
                self.check(s)
                if s['next_run'] and current<datetime.fromisoformat(s['next_run']):return
                s['next_run']=(current+timedelta(seconds=60)).isoformat()
                holdings=us_stock.holdings(s['mode'])
                held=sum(whole_quantity(h['quantity']) for h in holdings if h['instrument_id']==CODE)
                if held!=s['manual']+s['owned']:raise ValueError('수동 보유량 또는 자동매매 잔고 변경: 재시작 필요')
                calendar=us_calendar.session(current)
                if not calendar['is_open']:return
                decision=watchlist.signal(CODE,s['mode'],GoldenCrossPreset.builder_state,'golden_cross')
                s['decision']=decision;s['last_success']=current.isoformat()
                basis=decision['basis_date']
                if basis<=s['basis']:return
                s['basis']=basis
                signal_id=hashlib.sha256(f"{s['account']}:{CODE}:golden_cross:{basis}:{decision['action']}".encode()).hexdigest()
                if db.execute('SELECT 1 FROM signals WHERE id=?',(signal_id,)).fetchone():return
                # Consume stale or blocked new bars once; never replay a missed signal.
                event=dict(decision,outcome='보류',reason=None)
                db.execute('INSERT INTO signals VALUES (?,?)',(signal_id,json.dumps(event)))
                db.execute('UPDATE state SET data=? WHERE id=1',(json.dumps(s),));db.commit()
                try:
                    if not calendar['is_open'] or basis!=calendar['previous']:raise ValueError('정규장 또는 직전 거래일 신호가 아님')
                    action=decision['action']
                    if action not in ('BUY','SELL'):raise ValueError('매매 신호 없음')
                    if any(o['status'] in ACTIVE for o in self.orders(db)):raise ValueError('진행 중 주문 있음')
                    if action=='BUY' and s['owned'] or action=='SELL' and not s['owned']:raise ValueError('청산 전 추가 매수 금지 / 자동매매 보유분 없음')
                    quote=overseas_data.latest_minute(parse_instrument(CODE))
                    age=(now()-datetime.fromisoformat(quote['provider_at'])).total_seconds()
                    if not 0<=age<120:raise ValueError('공급자 분봉 시각이 2분 이상 오래됨 또는 미래 시각')
                    price=calculation(0,0,quote['price'],s['config'],action,s['owned'])['limit_price_usd']
                    holdings=us_stock.holdings(s['mode']);pending=us_stock.pending(mode=s['mode']);buyable=us_stock.buyable(CODE,price,s['mode'])
                    held=sum(whole_quantity(h['quantity']) for h in holdings if h['instrument_id']==CODE)
                    if held!=s['manual']+s['owned']:
                        s.update(running=False,reason='수동 보유량 또는 자동매매 잔고 변경: 재시작 필요')
                        raise ValueError(s['reason'])
                    if any(o['instrument_id']==CODE for o in pending):raise ValueError('계좌에 기존 미체결 주문 있음')
                    preview=calculation(buyable.get('amount_decimal',buyable['amount']),buyable.get('quantity_decimal',buyable['quantity']),quote['price'],s['config'],action,s['owned'])
                    if action=='SELL':
                        sellable=[h.get('orderable_quantity') for h in holdings if h['instrument_id']==CODE]
                        if not sellable or any(q is None for q in sellable):raise ValueError('공급자 매도 가능 수량 확인 불가')
                        maximum_sell=sum(int(q) for q in sellable)
                        preview['quantity']=min(preview['quantity'],maximum_sell)
                        preview['total_usd']=str(Decimal(price)*preview['quantity'])
                    s['preview']=preview|dict(provider_at=quote['provider_at'],fetched_at=now().isoformat())
                    if preview['quantity']<=0:raise ValueError('계산된 주문 수량 0')
                    self.check(s)
                    if not us_calendar.session(now())['is_open'] or (now()-datetime.fromisoformat(quote['provider_at'])).total_seconds()>=120:raise ValueError('주문 직전 장 마감 또는 시세 만료')
                    order=dict(id=signal_id,account=s['account'],mode=s['mode'],basis_date=basis,action=action,quantity=preview['quantity'],price=price,
                               status='unknown',filled=0,created_at=now().isoformat(),cancel_at=(now()+timedelta(seconds=s['config']['cancel_seconds'])).isoformat())
                    self.save_order(db,order)
                    result=once(Order(request_id=signal_id,instrument_id=CODE,action=action,quantity=order['quantity'],price=price),
                                'order',lambda code:us_stock.submit(code,action,order['quantity'],price,s['mode']),paper_only=False)
                    order.update(status=result['status'],order_no=result.get('order_no'),result=result);self.save_order(db,order)
                    event.update(outcome=result['status'])
                    if result['status']=='unknown':s.update(running=False,reason='접수 확인 필요: 자동 재전송 금지')
                except Exception as error:event['reason']=str(error)
                db.execute('UPDATE signals SET data=? WHERE id=?',(json.dumps(event),signal_id))
            except Exception as error:
                s.update(running=False,reason=str(error),next_run=None)

    async def run(self):
        try:
            while True:
                if self.owner or self.acquire():
                    work=asyncio.create_task(asyncio.to_thread(self.tick))
                    try:await asyncio.shield(work)
                    except asyncio.CancelledError:
                        await work
                        raise
                await asyncio.sleep(30)
        finally:self.release()

_service=None
def service():
    global _service
    if _service is None:_service=Engine()
    return _service
