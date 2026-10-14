"""Retry explicit rate rejection of reads only; callers must never pass a mutation."""
import time
from core.provider_errors import kis_error


def retry_read(call, attempts=3):
    for attempt in range(attempts):
        response = call()
        if response is None or response.isOK():
            return response
        message, _ = kis_error(response)
        if not message.startswith('EGW00201:') or attempt == attempts-1:
            return response
        time.sleep(attempt+1)
