from datetime import timedelta


MAX_FAILED_LOGIN_ATTEMPTS = 5
ACCOUNT_LOCKOUT_DURATION = timedelta(minutes=30)


# These helpers keep the lockout policy small and predictable so the login route
# can enforce retry limits without duplicating the timing rules in several places.
def clear_expired_lockout(user, now) -> bool:
    if user.locked_until and user.locked_until <= now:
        user.locked_until = None
        user.failed_login_attempts = 0
        return True
    return False


def is_account_locked(user, now) -> bool:
    return bool(user.locked_until and user.locked_until > now)


def register_failed_login_attempt(user, now) -> bool:
    user.failed_login_attempts += 1
    if user.failed_login_attempts >= MAX_FAILED_LOGIN_ATTEMPTS:
        user.locked_until = now + ACCOUNT_LOCKOUT_DURATION
        return True
    return False


def reset_lockout_state(user) -> None:
    user.failed_login_attempts = 0
    user.locked_until = None
