"""The recruiter account.

Email plus password hash and nothing else: data minimisation. InterMind has no use for a name,
a company, a job title or a phone number, so it does not ask for them and has nowhere to put
them.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, Field

#: Minimum password length. Length is the only rule - composition requirements (an uppercase, a
#: digit, a symbol) push people toward `Password1!` and away from the long passphrases and
#: generated strings that are actually strong, and NIST dropped them for that reason.
MIN_PASSWORD_LENGTH = 12

#: Upper bound so nobody can make the server scrypt a megabyte. Far above any real password, and
#: long enough that no password manager's output is ever truncated - which must never happen
#: silently, because the account would then be unopenable with the password the user was given.
MAX_PASSWORD_LENGTH = 1024

#: Practical maximum for an address (RFC 5321's limit on a forward path).
MAX_EMAIL_LENGTH = 320


def normalize_email(email: str) -> str:
    """Trim and lower-case, so one person cannot register twice with different capitalisation.

    Applied on every write *and* on every lookup, and the unique index is on the normalised
    column - so `A@B.com` and `a@b.com` are one account at the database level, not merely by
    convention.

    Deliberately conservative: no dot-stripping, no plus-tag removal. Those are provider
    -specific behaviours, and treating `a.b@example.com` as `ab@example.com` would be wrong for
    any provider that does not.
    """
    return email.strip().lower()


class Recruiter(BaseModel):
    """A persisted recruiter. ``password_hash`` never leaves the backend."""

    id: str = Field(default_factory=lambda: uuid4().hex)
    email: str
    password_hash: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
