from typing import Literal
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from core.auto_trading import service, Settings
router=APIRouter()
class Start(BaseModel):
    mode: Literal['vps','prod']

def call(operation):
    try:return operation()
    except ValueError as error:raise HTTPException(409,str(error)) from error
    except Exception as error:raise HTTPException(502,str(error)) from error

@router.get('')
def status():return service().snapshot()
@router.get('/settings')
def settings():return service().snapshot()['config']
@router.put('/settings')
def save(request:Settings):return call(lambda:service().configure(request))
@router.post('/start')
def start(request:Start):return call(lambda:service().start(request.mode))
@router.post('/stop')
def stop():return call(service().stop)
@router.post('/preview')
def preview():return call(service().preview)
@router.get('/history')
def history():
    snapshot=service().snapshot()
    return dict(orders=snapshot['orders'],signals=snapshot['signals'],fetched_at=snapshot['fetched_at'])

@router.post("/verify")
def verify():
    from core.auto_verification import verify as run
    return call(run)
