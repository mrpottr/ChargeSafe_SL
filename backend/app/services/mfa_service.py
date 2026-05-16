import base64
from io import BytesIO

import pyotp
import qrcode


class MfaService:
    # MFA helpers are grouped here so registration and login flows can share the
    # same secret generation, QR creation, and verification behavior.
    DEFAULT_TOTP_INTERVAL = 30
    LEGACY_TOTP_INTERVAL = 60

    @staticmethod
    def generate_secret() -> str:
        return pyotp.random_base32()

    @staticmethod
    def build_otp_uri(email: str, secret: str) -> str:
        # Microsoft Authenticator follows the standard 30-second TOTP rhythm, so
        # the provisioning URI uses that interval as the default contract.
        totp = pyotp.TOTP(secret, interval=MfaService.DEFAULT_TOTP_INTERVAL)
        return totp.provisioning_uri(name=email, issuer_name="ChargeSafe SL")

    @staticmethod
    def build_qr_code_data_url(otp_uri: str) -> str:
        image = qrcode.make(otp_uri)
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return f"data:image/png;base64,{encoded}"

    @staticmethod
    def verify_code(secret: str, code: str) -> bool:
        # Verification accepts both the current timing window and the previous
        # legacy interval so older pending setups do not break unexpectedly.
        normalized_code = "".join(ch for ch in code if ch.isdigit())
        if len(normalized_code) != 6:
            return False

        for interval in (MfaService.DEFAULT_TOTP_INTERVAL, MfaService.LEGACY_TOTP_INTERVAL):
            totp = pyotp.TOTP(secret, interval=interval)
            if totp.verify(normalized_code, valid_window=1):
                return True
        return False
