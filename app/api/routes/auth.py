"""Recruiter sign-in, sign-out, and "am I signed in?".

Recruiters register their own accounts here: there is no credential in configuration and no
shared account (see ``docs/recruiter-auth.md``). A password is verified against that account's
scrypt hash, held server-side in the recruiter repository; the browser receives only an opaque
session identifier in an ``HttpOnly`` cookie, and never any part of the credential.

Nothing in this module returns or logs the password, the password hash, or the session token.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Cookie, Depends, Response, status
from pydantic import BaseModel, Field

from app.api.deps import get_recruiter_repository, get_recruiter_session_store
from app.api.recruiter_session import RecruiterSessionStore
from app.core.config import Settings, get_settings
from app.core.exceptions import AccessDenied, InvalidSignup
from app.core.security import hash_password, verify_password
from app.domain.recruiter import (
    MAX_EMAIL_LENGTH,
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    Recruiter,
    normalize_email,
)
from app.repositories.ports import RecruiterRepository

logger = logging.getLogger(__name__)

#: Verified against when the email is unknown, so a failed sign-in always costs the same work.
#: A fixed hash of a value nothing can match.
_DUMMY_HASH = hash_password("unused-placeholder-for-constant-time-login", n=2**12)

router = APIRouter(tags=["auth"])

#: Cookie carrying the recruiter session identifier. `HttpOnly`, so page JavaScript - and
#: therefore any XSS on the page - cannot read it.
RECRUITER_SESSION_COOKIE = "intermind_recruiter_session"


class RecruiterSignupRequest(BaseModel):
    """A new recruiter account.

    Email and password only - InterMind has no use for a name, company or job title, so it does
    not ask. `max_length` on both is resource protection, not policy: it stops anyone making the
    server hash a megabyte. The password bound is far above any real password and far above any
    password manager's output, so nothing is ever silently truncated.
    """

    email: str = Field(min_length=3, max_length=MAX_EMAIL_LENGTH)
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)


class RecruiterLoginRequest(BaseModel):
    """Credentials for one registered recruiter account.

    Neither field is ever logged, echoed back, or stored by the browser. The password exists
    only for the lifetime of this request.
    """

    # A plain string, not pydantic's EmailStr: that would pull in `email-validator` purely to
    # validate the shape of a value that is only ever looked up by exact match against a
    # registered address. The browser input already carries type="email", and an address that
    # matches no account is rejected the same way a malformed one would be.
    email: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class RecruiterSessionResponse(BaseModel):
    """Deliberately carries no identity and no secret.

    The signed-in recruiter's identity is deliberately not reported: no screen needs it, and
    the server resolves the owner of every request from the session itself. The session token
    lives in the cookie - putting it in the body as well would hand it straight back to page
    JavaScript and undo the point of `HttpOnly`.
    """

    authenticated: bool
    expires_in_seconds: int | None = None


def _set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        key=RECRUITER_SESSION_COOKIE,
        value=token,
        max_age=settings.recruiter_session_ttl_seconds,
        httponly=True,
        # Strict rather than Lax: the recruiter workspace is a destination people navigate to
        # themselves, never something another site should be able to link *into* with the
        # session attached. Combined with the app being served same-origin with its API (the
        # frontend proxies /api rather than calling a second origin), this is what makes CSRF
        # structurally impossible here rather than merely unlikely - a cross-site request
        # cannot carry this cookie at all, so there is nothing for a forged request to ride on
        # and no need for a separate CSRF token scheme.
        samesite="strict",
        secure=settings.recruiter_session_cookie_secure,
        path="/",
    )


def _validate_new_password(password: str) -> None:
    """Server-side password policy. The frontend mirrors this; only this enforces it.

    Length is the whole rule. Composition requirements (an uppercase, a digit, a symbol) reliably
    produce `Password1!` and discourage the long passphrases and generated strings that are
    actually strong, which is why NIST dropped them.
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        raise InvalidSignup(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
        )


def _looks_like_email(value: str) -> bool:
    """Deliberately minimal: one @, something either side, no whitespace.

    Real deliverability cannot be established by a regex, and the strict grammar would need
    `email-validator` as a dependency to reject addresses this product will never receive. The
    account is only ever reached by exact match against what was registered.
    """
    local, _, domain = value.partition("@")
    return bool(local) and bool(domain) and "." in domain and not any(c.isspace() for c in value)


@router.post(
    "/auth/recruiter/signup",
    response_model=RecruiterSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def recruiter_signup(
    payload: RecruiterSignupRequest,
    response: Response,
    settings: Settings = Depends(get_settings),
    recruiters: RecruiterRepository = Depends(get_recruiter_repository),
    store: RecruiterSessionStore = Depends(get_recruiter_session_store),
) -> RecruiterSessionResponse:
    """Create a recruiter account and sign them straight in.

    No confirm-your-email round trip, and no "now log in with the credentials you just typed":
    the session is issued here, so signing up lands in the workspace.

    The account is **not** marked verified, because nothing has verified it - there is no email
    delivery in this product. See docs/recruiter-auth.md.
    """
    email = normalize_email(payload.email)
    if not _looks_like_email(email):
        raise InvalidSignup("Please enter a valid email address.")
    _validate_new_password(payload.password)

    # Uniqueness is the database's unique index, enforced inside `add` - not a lookup here.
    # A check-then-insert would let two concurrent signups for the same address both pass.
    recruiter = Recruiter(email=email, password_hash=hash_password(payload.password))
    created = await recruiters.add(recruiter)

    session = store.create(created.id)
    _set_session_cookie(response, session.token, settings)
    return RecruiterSessionResponse(
        authenticated=True,
        expires_in_seconds=settings.recruiter_session_ttl_seconds,
    )


@router.post("/auth/recruiter/login", response_model=RecruiterSessionResponse)
async def recruiter_login(
    payload: RecruiterLoginRequest,
    response: Response,
    settings: Settings = Depends(get_settings),
    recruiters: RecruiterRepository = Depends(get_recruiter_repository),
    store: RecruiterSessionStore = Depends(get_recruiter_session_store),
) -> RecruiterSessionResponse:
    """Sign in and start a session.

    The failure response is deliberately identical whether the email is unknown or the password
    is wrong, so it cannot be used to discover which addresses have accounts. A dummy
    verification runs when the email is unknown, so an unregistered address is not measurably
    faster to reject than a wrong password.
    """
    recruiter = await recruiters.get_by_email(payload.email)

    # Verified unconditionally. Returning early on an unknown email would skip the ~0.5s scrypt
    # cost and turn response time into an account-existence oracle.
    password_ok = verify_password(
        payload.password, recruiter.password_hash if recruiter else _DUMMY_HASH
    )

    if recruiter is None or not password_ok:
        # Never says which half failed, and never echoes the submitted values.
        raise AccessDenied("Incorrect email or password.")

    session = store.create(recruiter.id)
    _set_session_cookie(response, session.token, settings)
    return RecruiterSessionResponse(
        authenticated=True,
        expires_in_seconds=settings.recruiter_session_ttl_seconds,
    )


@router.post("/auth/recruiter/logout", response_model=RecruiterSessionResponse)
async def recruiter_logout(
    response: Response,
    session_cookie: str | None = Cookie(default=None, alias=RECRUITER_SESSION_COOKIE),
    store: RecruiterSessionStore = Depends(get_recruiter_session_store),
) -> RecruiterSessionResponse:
    """End the session server-side and clear the cookie.

    Revoking on the server is the part that matters: clearing the cookie alone would leave a
    still-valid session token usable by anyone who had copied it.
    """
    store.revoke(session_cookie)
    response.delete_cookie(RECRUITER_SESSION_COOKIE, path="/")
    return RecruiterSessionResponse(authenticated=False)


@router.get("/auth/recruiter/session", response_model=RecruiterSessionResponse)
async def recruiter_session_status(
    session_cookie: str | None = Cookie(default=None, alias=RECRUITER_SESSION_COOKIE),
    store: RecruiterSessionStore = Depends(get_recruiter_session_store),
) -> RecruiterSessionResponse:
    """Whether this browser currently holds a live session.

    Lets the workspace show its sign-in screen without first firing a protected request and
    catching the 401. Intentionally unauthenticated - it reveals only a boolean about the
    caller's own cookie.
    """
    return RecruiterSessionResponse(authenticated=store.is_valid(session_cookie))
