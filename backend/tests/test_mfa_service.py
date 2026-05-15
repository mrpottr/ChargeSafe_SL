import unittest

import pyotp

from app.services.mfa_service import MfaService


class MfaServiceTests(unittest.TestCase):
    def test_verify_code_accepts_standard_30_second_totp(self):
        secret = MfaService.generate_secret()
        code = pyotp.TOTP(secret, interval=30).now()

        self.assertTrue(MfaService.verify_code(secret, code))

    def test_verify_code_accepts_legacy_60_second_totp(self):
        secret = MfaService.generate_secret()
        code = pyotp.TOTP(secret, interval=60).now()

        self.assertTrue(MfaService.verify_code(secret, code))

    def test_verify_code_rejects_non_numeric_values(self):
        secret = MfaService.generate_secret()
        self.assertFalse(MfaService.verify_code(secret, "12-34ab"))


if __name__ == "__main__":
    unittest.main()
