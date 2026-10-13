"""Paper orders with a durable at-most-once request journal."""
from contextlib import closing
import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Literal
from datetime import datetime, timezone
from decimal import Decimal
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from backend import is_authenticated, get_current_mode
from core import us_paper
import kis_auth as ka
router=APIRouter()

class Order(BaseModel):
    request_id: str = Field(min_length=16,max_length=100,pattern=r'^[A-Za-z0-9_-]+$')
    instrument_id: str
    action: Literal['BUY','SELL']
    quantity: int = Field(gt=0,strict=True)
    price: Decimal = Field(gt=0,allow_inf_nan=False)
    currency: Literal['USD'] = 'USD'

class Cancel(BaseModel):
    request_id: str = Field(min_length=16,max_length=100,pattern=r'^[A-Za-z0-9_-]+$')
    instrument_id: str
    order_no: str = Field(min_length=1,max_length=50)
    quantity: int = Field(gt=0,strict=True)

def guard():
    if not is_authenticated(): raise HTTPException(401,'인증이 필요합니다')
    if get_current_mode()!='vps' or not ka.isPaperTrading():
        raise HTTPException(403,'미국 주문과 계좌 조회는 모의 모드에서만 지원합니다')

def journal_path():
    path=Path(os.environ.get('KIS_ORDER_JOURNAL',str(Path.home()/'.kis_strategy_builder'/'paper_orders.sqlite3')))
    path.parent.mkdir(parents=True,exist_ok=True)
    return path

def once(request,operation,call):
    guard()
    value=us_paper.instrument(request.instrument_id)
    if isinstance(request,Order): us_paper.validate_price(request.price)
    account=ka.getTREnv()
    # Namespace keys by actual paper account; no account credentials are persisted.
    scope=hashlib.sha256(f'{account.my_acct}:{account.my_prod}'.encode()).hexdigest()
    key=scope+':'+request.request_id
    payload=request.model_dump(mode='json') | {'instrument_id':value.id,'operation':operation}
    serialized=json.dumps(payload,sort_keys=True)
    path=journal_path()
    with closing(sqlite3.connect(path,timeout=10)) as db, db:
        os.chmod(path,0o600)
        db.execute('CREATE TABLE IF NOT EXISTS requests (key TEXT PRIMARY KEY, payload TEXT NOT NULL, result TEXT NOT NULL)')
        db.execute('BEGIN IMMEDIATE')
        old=db.execute('SELECT payload,result FROM requests WHERE key=?',(key,)).fetchone()
        if old:
            if old[0]!=serialized: raise HTTPException(409,'같은 요청 ID로 다른 주문을 제출할 수 없습니다')
            return json.loads(old[1])
        initial=dict(status='unknown',message='접수 확인 중 또는 중단됨: 주문내역 재조회 필요. 자동 재전송 금지')
        db.execute('INSERT INTO requests VALUES (?,?,?)',(key,serialized,json.dumps(initial)))
        db.commit() # Durable before the external submission, including server crash/restart.
    try:
        result=call(value.id)
    except us_paper.BrokerRejected as e:
        result=dict(status='rejected',message=str(e))
    except Exception:
        result=dict(status='unknown',message='주문 접수 여부를 확인할 수 없습니다. 주문내역을 재조회하세요. 재전송하지 않습니다.')
    result |= dict(request_id=request.request_id,fetched_at=datetime.now(timezone.utc).isoformat(),mode='vps')
    with closing(sqlite3.connect(path,timeout=10)) as db, db:
        db.execute('UPDATE requests SET result=? WHERE key=?',(json.dumps(result),key))
    return result

@router.post('/order')
def order(request:Order):
    try: return once(request,'order',lambda code:us_paper.submit(code,request.action,request.quantity,request.price))
    except ValueError as e: raise HTTPException(422,str(e)) from e

@router.post('/cancel')
def cancel(request:Cancel):
    try: return once(request,'cancel',lambda code:us_paper.cancel(code,request.order_no,request.quantity))
    except ValueError as e: raise HTTPException(422,str(e)) from e

def read(call):
    guard()
    try: return dict(status='success',data=call(),mode='vps',fetched_at=datetime.now(timezone.utc).isoformat())
    except Exception as e: raise HTTPException(502,str(e)) from e

@router.get('/holdings')
def holdings(): return read(us_paper.holdings)
@router.get('/pending')
def pending(): return read(us_paper.pending)
@router.get('/buyable')
def buyable(instrument_id:str,price:Decimal): return read(lambda:us_paper.buyable(instrument_id,price))
