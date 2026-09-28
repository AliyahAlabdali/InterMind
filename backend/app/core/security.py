"""Password hashing for recruiter accounts.

Algorithm choice
----------------
``hashlib.scrypt`` from the standard library. It is a memory-hard password KDF (RFC 7914),
it is not a hand-rolled construction, and it costs no new dependency.

``argon2-cffi`` happens to be importable in this checkout, but only because ``jupyter_server``
pulls it in - it is not a declared dependency of this project. This repository has already been
bitten by depending on a transitively-present package (see the ``httpx`` note in
``pyproject.toml``), so relying on it again would be luck rather than design. If a future
milestone wants Argon2id, declare it properly first.

Storage format
--------------
A single self-describing string, the same shape passlib and Django use, so the parameters travel
with the hash and can be raised later without invalidating existing hashes::

    scrypt$<n>$<r>$<p>$<base64 salt>$<base64 derived key>

Only the hash is ever stored or configured. The plaintext password exists solely inside a single
login request and is never written to disk, logged, or returned.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

#: scrypt cost parameters. n=2**15 with r=8 needs ~32 MB per hash, which is a meaningful cost to
#: an attacker and unnoticeable for one interactive login. Raise `n` later if desired: existing
#: hashes keep working because their own parameters are stored alongside them.
_N = 2**15
_R = 8
_P = 1
_SALT_BYTES = 16
_KEY_LEN = 32
_PREFIX = "scrypt"


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _maxmem(n: int, r: int, p: int) -> int:
    """Memory ceiling to hand OpenSSL for these parameters.

    OpenSSL refuses scrypt above 32 MB unless told otherwise, and the defaults here need
    exactly that much - so without an explicit ceiling the very first hash raises
    "memory limit exceeded". Derived from the parameters rather than hard-coded, with headroom,
    so raising the cost later does not reintroduce the same failure.
    """
    return 128 * n * r * p * 2


def hash_password(password: str, *, salt: bytes | None = None, n: int = _N) -> str:
    """Return an encoded scrypt hash of ``password``.

    ``salt`` and ``n`` are injectable for tests, which would otherwise pay the full memory-hard
    cost on every sign-in and turn a fast suite into a slow one. Production always uses fresh
    entropy and the module default. The chosen cost travels inside the hash, so
    :func:`verify_password` honours whatever it was hashed with.
    """
    if not password:
        raise ValueError("password must not be empty")
    salt = salt or secrets.token_bytes(_SALT_BYTES)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=n,
        r=_R,
        p=_P,
        dklen=_KEY_LEN,
        maxmem=_maxmem(n, _R, _P),
    )
    return f"{_PREFIX}${n}${_R}${_P}${_b64(salt)}${_b64(derived)}"


def verify_password(password: str, encoded: str | None) -> bool:
    """Whether ``password`` matches ``encoded``.

    Returns ``False`` rather than raising for any malformed or missing hash: an unknown email
    has no hash to check, and a login attempt against one must be refused, not crash.
    The final comparison is constant-time.
    """
    if not password or not encoded:
        return False

    try:
        prefix, n_raw, r_raw, p_raw, salt_raw, key_raw = encoded.split("$")
        if prefix != _PREFIX:
            return False
        n, r, p = int(n_raw), int(r_raw), int(p_raw)
        salt = base64.b64decode(salt_raw, validate=True)
        expected = base64.b64decode(key_raw, validate=True)
    except (ValueError, TypeError):
        return False

    try:
        candidate = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=n,
            r=r,
            p=p,
            dklen=len(expected),
            maxmem=_maxmem(n, r, p),
        )
    except ValueError:
        # Nonsensical stored parameters (e.g. a non-power-of-two n) - treat as unusable.
        return False

    return hmac.compare_digest(candidate, expected)


def _main() -> None:
    """Print an scrypt hash for a password typed at the prompt.

    Recruiters register through the product, so this is not part of normal setup - it exists for
    operational use (seeding an account directly, checking the format).

    Usage::

        python -m app.core.security

    Prompts without echoing, prints only the hash, and never writes the password anywhere.
    """
    import getpass

    password = getpass.getpass("Recruiter password: ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        raise SystemExit("Passwords did not match.")
    if len(password) < 12:
        raise SystemExit("Use at least 12 characters.")
    print()
    print("Password hash (the password itself is never stored):")
    print()
    print(hash_password(password))


if __name__ == "__main__":  # pragma: no cover - developer utility
    _main()
