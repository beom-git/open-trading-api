import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.kis_config import load_kis_config


class ConfigTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.yaml = self.root / "config.yaml"
        self.dotenv = self.root / ".env"
        environment = patch.dict(os.environ, {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)

    def load(self):
        return load_kis_config(self.yaml, self.dotenv)

    def test_no_config_files_needed_for_local_builder(self):
        config = self.load()
        self.assertEqual(config["my_prod"], "01")
        self.assertEqual(config["paper_app"], "")
        self.assertEqual(list(self.root.iterdir()), [])

    def test_environment_over_dotenv_over_yaml(self):
        self.yaml.write_text('paper_app: yaml-test-key\npaper_sec: yaml-test-secret\nmy_prod: "03"\n')
        self.dotenv.write_text('paper_app=dotenv-test-key\npaper_sec=dotenv-test-secret\nmy_prod=01\n')
        os.environ["paper_app"] = "environment-test-key"
        config = self.load()
        self.assertEqual(config["paper_app"], "environment-test-key")
        self.assertEqual(config["paper_sec"], "dotenv-test-secret")
        self.assertEqual(config["my_prod"], "01")
        self.assertIn("yaml-test-key", self.yaml.read_text())
        self.assertNotIn("paper_sec", os.environ)

    def test_empty_template_fields_preserve_existing_yaml(self):
        self.yaml.write_text('paper_app: yaml-test-key\nmy_prod: "01"\n')
        self.dotenv.write_text('paper_app=\n')
        os.environ["paper_app"] = ""
        self.assertEqual(self.load()["paper_app"], "yaml-test-key")

    def test_dotenv_keeps_leading_zeros_and_literal_dollar_signs(self):
        self.dotenv.write_text('my_paper_stock=00123456\npaper_sec=${UNSET_TEST_NAME}+x/y=\nmy_prod="01"\n')
        config = self.load()
        self.assertEqual(config["my_paper_stock"], "00123456")
        self.assertEqual(config["paper_sec"], "${UNSET_TEST_NAME}+x/y=")
        self.assertEqual(config["my_prod"], "01")

    def test_legacy_yaml_still_supplies_custom_endpoints(self):
        self.yaml.write_text('vps: https://example.invalid\nmy_prod: "01"\n')
        self.assertEqual(self.load()["vps"], "https://example.invalid")

    def test_bad_product_codes_fail_without_echoing_the_value(self):
        for value in ['"01"', '1', 'not-a-product-code', '０１']:
            with self.subTest(value=value):
                os.environ["my_prod"] = value
                with self.assertRaises(ValueError) as error:
                    self.load()
                self.assertNotIn('not-a-product-code', str(error.exception))

    def test_malformed_yaml_does_not_expose_credential_line(self):
        self.yaml.write_text('paper_sec: [private-test-value\n')
        with self.assertRaises(ValueError) as error:
            self.load()
        self.assertNotIn("private-test-value", str(error.exception))


if __name__ == "__main__":
    unittest.main()
