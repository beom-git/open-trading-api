"""US orders and account reads follow Settings > Authentication and mode."""
from datetime import datetime,timezone
from decimal import Decimal
from fastapi import APIRouter,HTTPException
from core import us_stock
from backend import get_current_mode
from backend.routers.us_paper import Order,Cancel,guard,once
router=APIRouter()
@router.post('/order')
def order(request:Order):
    mode=guard(False)
    try:return once(request,'order',lambda code:us_stock.submit(code,request.action,request.quantity,request.price,mode),paper_only=False)
    except ValueError as e:raise HTTPException(422,str(e)) from e
@router.post('/cancel')
def cancel(request:Cancel):
    mode=guard(False)
    try:return once(request,'cancel',lambda code:us_stock.cancel(code,request.order_no,request.quantity,mode),paper_only=False)
    except ValueError as e:raise HTTPException(422,str(e)) from e

def read(call):
    mode=guard(False)
    try:
        data=call(mode)
        if mode!=get_current_mode():raise ValueError('조회 중 인증 모드 변경: 다시 조회하세요')
        return dict(status='success',data=data,mode=mode,fetched_at=datetime.now(timezone.utc).isoformat())
    except Exception as e:raise HTTPException(502,str(e)) from e
@router.get('/holdings')
def holdings():return read(us_stock.holdings)
@router.get('/pending')
def pending():return read(lambda mode:us_stock.pending(mode=mode))
@router.get('/buyable')
def buyable(instrument_id:str,price:Decimal):return read(lambda mode:us_stock.buyable(instrument_id,price,mode))

@router.get("/history")
def history():return read(lambda mode:us_stock.order_history(mode=mode))
