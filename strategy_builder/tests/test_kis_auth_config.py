import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from core.kis_config import DEFAULTS

# Import without consulting the developer's local credentials or cached token.
with tempfile.TemporaryDirectory() as directory:
    with patch.dict(os.environ, {}, clear=True), patch("pathlib.Path.home", return_value=Path(directory)), patch("os.path.expanduser", return_value=directory), patch("core.kis_config.dotenv_values", return_value={}):
        import kis_auth as ka
        from backend.state import TradingState


class AuthenticationConfigTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config = DEFAULTS | {
            "paper_app": "unit-test-key", "paper_sec": "unit-test-secret",
            "my_paper_stock": "00123456", "my_paper_future": "00876543",
        }
        for patcher in (
            patch.dict(os.environ, {}, clear=True),
            patch.object(ka, "_cfg", self.config.copy()),
            patch.object(ka, "_base_headers", {}),
            patch.object(ka, "_TRENV", tuple()),
            patch.object(ka, "_isPaper", False),
            patch.object(ka, "read_token", return_value=None),
            patch.object(ka, "save_token"),
            patch.object(ka, "_getBaseHeader", return_value={}),
            patch("pathlib.Path.home", return_value=self.root),
            patch("os.path.expanduser", return_value=str(self.root)),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_paper_auth_uses_loaded_credentials_and_current_product(self):
        # The product changes after import, as it can during login reload.
        ka._cfg["my_prod"] = "03"
        response = Mock(status_code=200)
        response.json.return_value = {
            "access_token": "unit-test-token", "access_token_token_expired": "2099-01-01 00:00:00",
        }
        with patch.object(ka.requests, "post", return_value=response) as post:
            ka.auth(svr="vps")
        self.assertEqual(post.call_args.args[0], DEFAULTS["vps"] + "/oauth2/tokenP")
        payload = json.loads(post.call_args.kwargs["data"])
        self.assertEqual(payload["appkey"], "unit-test-key")
        self.assertEqual(payload["appsecret"], "unit-test-secret")
        self.assertEqual(ka.getTREnv().my_prod, "03")
        self.assertEqual(ka.getTREnv().my_acct, "00876543")

    def test_missing_keys_never_make_a_request(self):
        ka._cfg["paper_app"] = ""
        with patch.object(ka.requests, "post") as post:
            with self.assertRaises(ValueError):
                ka.auth(svr="vps")
            post.assert_not_called()

    def test_http_failure_is_not_reported_as_authenticated(self):
        state = TradingState()
        response = Mock(status_code=503)
        with patch.object(ka, "load_kis_config", return_value=self.config), patch.object(ka.requests, "post", return_value=response), patch.object(state, "_save_mode_file") as save_mode:
            with self.assertRaisesRegex(RuntimeError, "HTTP 503"):
                state.authenticate("vps")
            self.assertFalse(state.is_authenticated)
            save_mode.assert_not_called()

    def test_login_reload_keeps_environment_overrides_and_refreshes_dotenv(self):
        yaml_path = self.root / "config.yaml"
        dotenv_path = self.root / ".env"
        yaml_path.write_text('paper_app: yaml-test-key\nmy_prod: "01"\n')
        dotenv_path.write_text('paper_sec=first-test-secret\n')
        os.environ["paper_app"] = "environment-test-key"
        from core.kis_config import load_kis_config
        state = TradingState()
        with patch.object(ka, "load_kis_config", side_effect=lambda: load_kis_config(yaml_path, dotenv_path)):
            state._reload_config()
            self.assertEqual(ka._cfg["paper_app"], "environment-test-key")
            self.assertEqual(ka._cfg["paper_sec"], "first-test-secret")
            dotenv_path.write_text('paper_sec=second-test-secret\n')
            state._reload_config()
            self.assertEqual(ka._cfg["paper_app"], "environment-test-key")
            self.assertEqual(ka._cfg["paper_sec"], "second-test-secret")

    def test_login_endpoint_reports_kis_failure_without_success(self):
        from fastapi.testclient import TestClient
        from backend.main import app
        from backend.state import trading_state

        response = Mock(status_code=503)
        with patch.object(ka, "load_kis_config", return_value=self.config), patch.object(ka.requests, "post", return_value=response), patch.object(trading_state, "_authenticated", False), patch.object(trading_state, "_current_mode", "vps"):
            with TestClient(app) as client:
                login = client.post('/api/auth/login', json={'mode': 'vps'})
                self.assertEqual(login.status_code, 400)
                self.assertIn('HTTP 503', login.json()['detail'])
                self.assertFalse(client.get('/api/auth/status').json()['authenticated'])


class TokenStorageTests(unittest.TestCase):
    def test_first_auth_creates_private_token_cache_without_yaml(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "KIS/config"
            token = root / "token"
            with patch.object(ka, "config_root", str(root)), patch.object(ka, "token_tmp", str(token)):
                ka.save_token("unit-test-token", "2099-01-01 00:00:00")
                self.assertEqual(ka.read_token(), "unit-test-token")
                self.assertFalse((root / "kis_devlp.yaml").exists())
                if os.name == "posix":
                    self.assertEqual(token.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
