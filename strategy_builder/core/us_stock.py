"""KIS US adapter following the globally authenticated trading mode. All amounts stay USD; unknown submission is never retried."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import kis_auth as ka
from core.instruments import parse_instrument
from core.provider_errors import kis_error

class BrokerRejected(RuntimeError):
    pass

ORDER_EXCHANGES = {'nasdaq':'NASD','nyse':'NYSE','amex':'AMEX'}
REVERSE_EXCHANGES = {v:k for k,v in ORDER_EXCHANGES.items()}

def instrument(code):
    value = parse_instrument(code)
    if not value.is_overseas:
        raise ValueError('미국 종목 ID가 필요합니다')
    return value

def number(row, key):
    if key not in row or row[key] in ('', None):
        raise ValueError(f'공급자 응답 필드 누락: {key}')
    value = Decimal(str(row[key]))
    if not value.is_finite():
        raise ValueError(f'공급자 응답 숫자 오류: {key}')
    return float(value)

def validate_price(price):
    value=Decimal(str(price))
    if not value.is_finite() or value <= 0:
        raise ValueError('USD 지정가는 양수여야 합니다')
    tick=Decimal('.01') if value >= 1 else Decimal('.0001')
    if value % tick:
        raise ValueError('1 USD 이상은 0.01 USD, 미만은 0.0001 USD 주문 단위를 사용하세요')
    return format(value,'f')

def _account(mode='vps'):
    if mode not in ('vps','prod') or ka.isPaperTrading() != (mode=='vps'):
        raise ValueError('앱 모드와 실제 KIS 인증 모드가 일치하지 않습니다')
    env=ka.getTREnv()
    if not env.my_acct or not env.my_prod:
        raise ValueError('계좌 인증이 필요합니다')
    return {'CANO':env.my_acct,'ACNT_PRDT_CD':env.my_prod}

@ka.with_trading_context
def _call(endpoint, tr_id, params, post=False, continuation='', mode='vps'):
    # Check the actual authenticated KIS mode again immediately before each request.
    payload=_account(mode) | params
    res=ka._url_fetch('/uapi/overseas-stock/v1/trading/'+endpoint,tr_id,continuation,payload,
                      postFlag=post,timeout=30)
    if res is None:
        raise RuntimeError('KIS 응답이 없습니다')
    if not res.isOK():
        message,denied=kis_error(res)
        if denied:raise BrokerRejected(message)
        raise RuntimeError(message)
    return res

def submit(code, action, quantity, price, mode='vps'):
    value=instrument(code)
    if action not in ('BUY','SELL') or type(quantity) is not int or quantity <= 0:
        raise ValueError('BUY/SELL과 양의 정수 수량이 필요합니다')
    params={'OVRS_EXCG_CD':ORDER_EXCHANGES[value.exchange],'PDNO':value.ticker,
            'ORD_QTY':str(quantity),'OVRS_ORD_UNPR':validate_price(price),
            'CTAC_TLNO':'','MGCO_APTM_ODNO':'','SLL_TYPE':'00' if action=='SELL' else '',
            'ORD_SVR_DVSN_CD':'0','ORD_DVSN':'00'}
    # Paper sell ID differs from the live sell ID; do not derive it by prefix substitution.
    tr_id = ('VTTT1002U' if action=='BUY' else 'VTTT1001U') if mode=='vps' else ('TTTT1002U' if action=='BUY' else 'TTTT1006U')
    body=_call('order',tr_id,params,True,mode=mode).getBody()
    output=getattr(body,'output',None)
    if not isinstance(output,dict) or not (output.get('ODNO') or output.get('odno')):
        return {'status':'unknown','message':'응답에 주문번호 없음: 주문내역 재조회 필요'}
    return {'status':'accepted','order_no':output.get('ODNO') or output.get('odno'),
            'message':'주문 접수 (체결 완료 아님)','currency':'USD','instrument_id':value.id}

def _pages(endpoint,tr_id,params,field,mode='vps'):
    rows,seen,continuation=[],set(),''
    for _ in range(40):
        response=_call(endpoint,tr_id,params,continuation=continuation,mode=mode)
        body=response.getBody()
        page=getattr(body,field,None)
        if page is None:
            raise ValueError(f'응답 필드 누락: {field}')
        if isinstance(page,dict): page=[page] if page else []
        if not isinstance(page,list): raise ValueError('조회 응답 형식 오류')
        rows.extend(page)
        if getattr(response.getHeader(),'tr_cont','') not in ('M','F'): return rows
        cursor=(getattr(body,'ctx_area_fk200',''),getattr(body,'ctx_area_nk200',''))
        if cursor in seen or not any(cursor): raise ValueError('계좌 페이지가 진행되지 않습니다')
        seen.add(cursor)
        params=params | {'CTX_AREA_FK200':cursor[0],'CTX_AREA_NK200':cursor[1]}
        continuation='N'
    raise ValueError('계좌 조회 페이지 상한 초과: 일부 잔고를 전체로 표시할 수 없습니다')

def holdings(mode='vps'):
    rows=_pages('inquire-balance','VTTS3012R' if mode=='vps' else 'TTTS3012R',{'OVRS_EXCG_CD':'NASD','TR_CRCY_CD':'USD',
                 'CTX_AREA_FK200':'','CTX_AREA_NK200':''},'output1',mode)
    result=[]
    for row in rows:
        exchange=REVERSE_EXCHANGES.get(row.get('ovrs_excg_cd'))
        if not exchange: raise ValueError('미지원 또는 누락된 거래소 응답')
        value=instrument(exchange.upper()+':'+row['ovrs_pdno'])
        if row.get('tr_crcy_cd') not in (None, 'USD'):
            raise ValueError('USD 외 잔고 응답을 합산할 수 없습니다')
        qty=number(row,'ovrs_cblc_qty')
        if qty <= 0: continue
        result.append(dict(instrument_id=value.id,name=row.get('ovrs_item_name',value.ticker),
                           currency='USD',exchange=exchange,quantity=qty,
                           orderable_quantity=number(row,'ord_psbl_qty') if row.get('ord_psbl_qty') not in (None,'') else None,avg_price=number(row,'pchs_avg_pric'),
                           current_price=number(row,'now_pric2'),eval_amount=number(row,'ovrs_stck_evlu_amt'),
                           profit_loss=number(row,'frcr_evlu_pfls_amt'),profit_rate=number(row,'evlu_pfls_rt')))
    return result

def order_history(start=None,end=None,mode='vps',include_fills=True):
    # inquire-nccs is live-only. Paper uses the supported all-order inquiry and filters remaining qty.
    today=datetime.now(timezone.utc).date()
    start=start or (today-timedelta(days=30)).strftime('%Y%m%d')
    end=end or today.strftime('%Y%m%d')
    rows=_pages('inquire-ccnl','VTTS3035R' if mode=='vps' else 'TTTS3035R',dict(PDNO='' if mode=='vps' else '%',ORD_STRT_DT=start,ORD_END_DT=end,
        SLL_BUY_DVSN='00',CCLD_NCCS_DVSN='00',OVRS_EXCG_CD='' if mode=='vps' else 'NASD',SORT_SQN='DS',ORD_DT='',
        ORD_GNO_BRNO='',ODNO='',CTX_AREA_FK200='',CTX_AREA_NK200=''),'output',mode)
    result=[]
    for row in rows:
        remaining=number(row,'nccs_qty')
        exchange=REVERSE_EXCHANGES.get(row.get('ovrs_excg_cd'))
        if not exchange: continue # this all-market query can include non-US orders
        value=instrument(exchange.upper()+':'+row['pdno'])
        result.append(dict(order_no=row['odno'],instrument_id=value.id,currency='USD',
                           exchange=exchange,quantity=number(row,'ft_ord_qty'),remaining=remaining,
                           price=number(row,'ft_ord_unpr3'),filled=number(row,'ft_ccld_qty') if include_fills else None,
                           cancelled=row.get('rvse_cncl_dvsn')=='02',rejected=bool(str(row.get('rjct_rson') or '').strip('0 ')),
                           original_order_no=row.get('orgn_odno'),provider_date=row.get('ord_dt'),
                           provider_time=row.get('ord_tmd'),action={'02':'BUY','01':'SELL'}.get(row.get('sll_buy_dvsn_cd'),'UNKNOWN')))
    return result

def buyable(code,price,mode='vps'):
    value=instrument(code)
    body=_call('inquire-psamount','VTTS3007R' if mode=='vps' else 'TTTS3007R',{'OVRS_EXCG_CD':ORDER_EXCHANGES[value.exchange],
              'OVRS_ORD_UNPR':validate_price(price),'ITEM_CD':value.ticker},mode=mode).getBody()
    row=getattr(body,'output',None)
    if not isinstance(row,dict): raise ValueError('주문 가능 응답 형식 오류')
    return dict(currency='USD',amount=number(row,'ovrs_ord_psbl_amt'),quantity=number(row,'max_ord_psbl_qty'),
                amount_decimal=str(row['ovrs_ord_psbl_amt']),quantity_decimal=str(row['max_ord_psbl_qty']))

def cancel(code,order_no,quantity,mode='vps'):
    value=instrument(code)
    if not order_no or type(quantity) is not int or quantity<=0: raise ValueError('주문번호와 취소 수량이 필요합니다')
    body=_call('order-rvsecncl','VTTT1004U' if mode=='vps' else 'TTTT1004U',{'OVRS_EXCG_CD':ORDER_EXCHANGES[value.exchange],
         'PDNO':value.ticker,'ORGN_ODNO':order_no,'RVSE_CNCL_DVSN_CD':'02','ORD_QTY':str(quantity),
         'OVRS_ORD_UNPR':'0','MGCO_APTM_ODNO':'','ORD_SVR_DVSN_CD':'0'},True,mode=mode).getBody()
    return dict(status='accepted',order_no=order_no,message='취소 요청 접수: 주문내역 재조회로 확인하세요')


def pending(start=None,end=None,mode='vps'):
    return [row for row in order_history(start,end,mode,include_fills=False) if row['remaining'] > 0 and not row['cancelled'] and not row['rejected']]
