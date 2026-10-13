"""Expose structured KIS error codes/messages without dumping response bodies."""
import json

def kis_error(response):
    body=response.getBody() if hasattr(response,'getBody') else None
    code=getattr(body,'msg_cd',None) or response.getErrorCode()
    message=getattr(body,'msg1',None)
    explicit_denial=not hasattr(response,'status_code')
    if not message and hasattr(response,'getErrorMessage'):
        try:
            parsed=json.loads(response.getErrorMessage())
            if isinstance(parsed,dict):
                code=parsed.get('msg_cd') or code
                message=parsed.get('msg1')
                explicit_denial=parsed.get('rt_cd')=='1'
        except (ValueError,TypeError):
            pass
    return f'{code}: {message or "KIS 요청 응답 오류"}',explicit_denial
