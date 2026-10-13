"""Load KIS settings without writing environment credentials to disk."""

import os
import re
from pathlib import Path

import yaml
from dotenv import dotenv_values


DEFAULTS = {
    "my_app": "", "my_sec": "", "paper_app": "", "paper_sec": "",
    "my_htsid": "", "my_acct_stock": "", "my_acct_future": "",
    "my_paper_stock": "", "my_paper_future": "", "my_token": "",
    "my_prod": "01",
    "prod": "https://openapi.koreainvestment.com:9443",
    "vps": "https://openapivts.koreainvestment.com:29443",
    "ops": "ws://ops.koreainvestment.com:21000",
    "vops": "ws://ops.koreainvestment.com:31000",
    "my_agent": "KIS-Strategy-Builder/1.0",
}
ENV_KEYS = (
    "paper_app", "paper_sec", "my_paper_stock", "my_paper_future",
    "my_htsid", "my_prod", "my_app", "my_sec", "my_acct_stock", "my_acct_future",
)


def load_kis_config(config_path=None, dotenv_path=None):
    """Precedence: process environment > local .env > optional legacy YAML."""
    config_path = Path(config_path) if config_path is not None else Path.home() / "KIS/config/kis_devlp.yaml"
    dotenv_path = Path(dotenv_path) if dotenv_path is not None else Path(__file__).resolve().parents[1] / ".env"
    config = DEFAULTS.copy()
    if config_path.exists():
        try:
            saved = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            # YAML parser diagnostics can include the line containing a secret.
            raise ValueError("kis_devlp.yaml 형식이 올바르지 않습니다") from None
        if not isinstance(saved, dict):
            raise ValueError("kis_devlp.yaml에는 키와 값으로 된 설정이 필요합니다")
        config.update(saved)

    # No interpolation: an app secret must retain literal '$' characters.
    local = dotenv_values(dotenv_path, interpolate=False) if dotenv_path.is_file() else {}
    for source in (local, os.environ):
        for key in ENV_KEYS:
            if source.get(key):
                config[key] = source[key]

    if not isinstance(config["my_prod"], str) or not re.fullmatch(r"[0-9]{2}", config["my_prod"]):
        raise ValueError("my_prod는 두 자리 문자열이어야 합니다. 환경변수 입력란에는 따옴표 없이 01 등을 입력하세요")
    return config
