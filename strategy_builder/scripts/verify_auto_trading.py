"""Read checks by default; --paper-order opts into one simulated buy/cancel probe.
Never activates unattended automation or submits a live order.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import time
import uuid
from decimal import Decimal, ROUND_DOWN
from datetime import datetime, timezone
import requests


def run(base, paper_order=False, http=None):
    http = http or requests.Session()
    def request(method, path, body=None):
        response = http.request(method, base.rstrip('/')+path, json=body, timeout=45)
        response.raise_for_status()
        return response.json()
    auth = request('GET','/api/auth/status')
    if auth.get('mode') != 'vps' or not auth.get('paper_only'):
        raise ValueError('KIS_PAPER_ONLY=1 서버의 모의 모드에서만 검증합니다')
    request('POST','/api/auth/login',{'mode':'vps'})
    report = request('POST','/api/auto-trading/verify')
    report['paper_order'] = dict(status='not_run',message='읽기 전용 검증')
    if not paper_order:
        return report
    if not report.get('order_ready'):
        report['paper_order'] = dict(status='blocked',message='계좌·시세·정규장 검증 통과 필요')
        return report
    state = request('GET','/api/auto-trading')
    pending = request('GET','/api/us-paper/pending')['data']
    if state.get('running') or any(row['instrument_id']=='NASDAQ:AAPL' for row in pending):
        report['paper_order'] = dict(status='blocked',message='자동매매 실행 중 또는 기존 AAPL 미체결 주문 있음')
        return report
    price = Decimal(report['quote']['price'])*Decimal('.99')
    price = price.quantize(Decimal('.01') if price>=1 else Decimal('.0001'),rounding=ROUND_DOWN)
    amount = request('GET',f'/api/us-paper/buyable?instrument_id=NASDAQ:AAPL&price={price}')['data']
    if Decimal(str(amount['amount']))<price*Decimal('1.01') or Decimal(str(amount['quantity']))<1:
        report['paper_order'] = dict(status='blocked',message='1주 주문 예산 부족')
        return report
    stamp = report['quote'].get('provider_at')
    if not stamp or not 0 <= (datetime.now(timezone.utc)-datetime.fromisoformat(stamp)).total_seconds() < 120:
        report['paper_order'] = dict(status='blocked',message='주문 직전 분봉 시각 누락 또는 만료')
        return report
    key = 'paper-check-'+uuid.uuid4().hex
    probe = dict(status='unknown',request_id=key,quantity=1,price_usd=str(price))
    report['paper_order'] = probe
    try:
        result = request('POST','/api/us-paper/order',dict(request_id=key,instrument_id='NASDAQ:AAPL',action='BUY',quantity=1,price=str(price)))
    except Exception as error:
        probe['message']=f'접수 확인 필요: 재전송 금지 ({error})'
        return report
    probe.update(status=result['status'],order_no=result.get('order_no'))
    if result['status']!='accepted':
        probe['message']=result.get('message','접수 확인 필요: 자동 재전송 금지')
        return report
    # Cancel this exact probe only; do not cancel existing account orders.
    probe['status']='confirmation_required'
    try:
        cancelled = request('POST','/api/us-paper/cancel',dict(request_id=key+'_cancel',instrument_id='NASDAQ:AAPL',order_no=str(result['order_no']),quantity=1))
        probe['cancel_request']=cancelled['status']
    except Exception as error:
        probe['cancel_request']='unknown'
        probe['message']=f'취소 접수 확인 필요: 자동 재전송 금지 ({error})'
    for attempt in range(7):
        if attempt:time.sleep(5)
        try:history=request('GET','/api/us-stock/history')['data']
        except Exception as error:
            probe['message']=f'주문내역 재조회 필요 ({error})'
            continue
        rows=[r for r in history if str(r['order_no'])==str(result['order_no']) and r['instrument_id']=='NASDAQ:AAPL']
        if len(rows)!=1:continue
        row=rows[0];probe['filled']=row['filled'];probe['remaining']=row['remaining']
        child_cancel=any(r['cancelled'] and str(r.get('original_order_no'))==str(result['order_no']) for r in history)
        if row['remaining']==0 and (row['cancelled'] or child_cancel):
            probe['status']='cancel_confirmed';break
        if row['filled']==1:
            probe['status']='filled';probe['message']='모의 1주 체결. 취소 검증은 미완료이며 기존 보유분은 매도하지 않습니다.';break
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url',default='http://127.0.0.1:8000')
    parser.add_argument('--paper-order',action='store_true',help='정규장·계좌 검증 통과 시 AAPL 1주 모의 매수/취소 검증')
    parser.add_argument('--report',type=Path)
    args=parser.parse_args()
    try:report=run(args.base_url,args.paper_order)
    except Exception as error:
        print(str(error),file=sys.stderr);return 1
    content=json.dumps(report,ensure_ascii=False,indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        fd=os.open(args.report,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
        with os.fdopen(fd,'w') as file:file.write(content+'\n')
    print(content)
    return 0 if report['ready'] and (not args.paper_order or report['paper_order']['status']=='cancel_confirmed') else 1

if __name__=='__main__':sys.exit(main())
