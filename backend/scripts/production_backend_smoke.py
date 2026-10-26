"""Bounded, synthetic smoke test for the isolated Vercel production backend.

Run only after verifying the isolated project and Neon runtime URL. This script
prints no passwords, cookies, candidate tokens, answers, reports, or provider
responses. It never calls Azure production or the public frontend. The marker
identifies records for a later guarded cleanup; no credential is saved to disk.
"""

from __future__ import annotations

import argparse
import secrets

import httpx

BACKEND = "https://project-ult57.vercel.app"
MAX_ANSWER_TURNS = 10


class SmokeStop(RuntimeError):
    """Safe stage/status label, never a raw provider response."""


def expect(response: httpx.Response, stage: str, *statuses: int) -> dict:
    if response.status_code not in statuses:
        raise SmokeStop(f"{stage} HTTP {response.status_code}")
    try:
        return response.json() if response.content else {}
    except ValueError:
        raise SmokeStop(f"{stage} returned non-JSON") from None


def run_smoke() -> None:
    marker = "imsmoke-" + secrets.token_hex(6)
    print("SMOKE_MARKER=" + marker)
    email = marker + "@example.invalid"
    password = secrets.token_urlsafe(32)
    answer = (
        "In a synthetic FastAPI and PostgreSQL project, I reproduced a concurrency "
        "defect with parallel requests, wrote a failing regression test, and used a "
        "database transaction to make the write atomic. I checked tenant ownership on "
        "every endpoint, measured latency before and after the fix, and reviewed the "
        "result with another engineer. I would explain the trade-offs and verify the "
        "same approach against the specific requirement in this question."
    )
    timeout = httpx.Timeout(115, connect=20)
    with httpx.Client(base_url=BACKEND, timeout=timeout, follow_redirects=False) as recruiter:
        health = expect(recruiter.get("/health"), "health", 200)
        if health != {"status": "ok", "storage": "postgresql"}:
            raise SmokeStop("health storage mode mismatch")
        print("PASS: isolated backend health and PostgreSQL mode")

        signup_response = recruiter.post(
            "/auth/recruiter/signup", json={"email": email, "password": password}
        )
        signup = expect(signup_response, "signup", 201)
        cookie = signup_response.headers.get("set-cookie", "").lower()
        if (not signup.get("authenticated") or "httponly" not in cookie
                or "secure" not in cookie or "samesite=strict" not in cookie):
            raise SmokeStop("signup session or cookie flags mismatch")
        print("PASS: synthetic signup and secure session cookie")

        current = expect(recruiter.get("/auth/recruiter/session"), "session", 200)
        if current.get("authenticated") is not True:
            raise SmokeStop("recruiter session not durable")
        expect(recruiter.post("/auth/recruiter/logout"), "logout", 200)
        revoked = expect(recruiter.get("/auth/recruiter/session"), "revocation", 200)
        if revoked.get("authenticated") is not False:
            raise SmokeStop("logout revocation failed")
        logged_in = expect(
            recruiter.post("/auth/recruiter/login", json={"email": email, "password": password}),
            "login", 200,
        )
        if logged_in.get("authenticated") is not True:
            raise SmokeStop("recruiter login did not establish a session")
        print("PASS: session persistence, logout revocation, and login")

        with httpx.Client(base_url=BACKEND, timeout=timeout, follow_redirects=False) as anonymous:
            expect(anonymous.get("/jobs"), "anonymous recruiter boundary", 401)
        job = expect(
            recruiter.post(
                "/jobs",
                json={
                    "job_description": (
                        f"InterMind isolated backend smoke {marker}. Python API engineer. "
                        "Required: FastAPI, PostgreSQL transactions, and debugging race "
                        "conditions. The candidate should explain a concrete implementation."
                    )
                },
            ),
            "OpenAI job analysis", 201,
        )
        job_id = job.get("id")
        if not isinstance(job_id, str) or not job_id:
            raise SmokeStop("job id missing")
        print("PASS: real OpenAI job analysis and owned job write")

        plan = expect(
            recruiter.post(f"/jobs/{job_id}/interview-plan"),
            "OpenAI interview plan", 201,
        )
        if not plan.get("coverage_targets"):
            raise SmokeStop("interview plan has no coverage targets")
        print("PASS: real OpenAI interview planning")

        started = expect(
            recruiter.post(
                "/interviews",
                json={
                    "job_id": job_id,
                    "candidate_name": "Synthetic InterMind Candidate",
                    "candidate_email": email,
                },
            ),
            "candidate interview start", 201,
        )
        interview_id = started.get("interview_id")
        candidate_token = started.get("candidate_access_token")
        if not interview_id or not candidate_token or not started.get("current_turn_id"):
            raise SmokeStop("candidate interview state or token missing")
        print("PASS: candidate invitation and first adaptive question")

        with httpx.Client(
            base_url=BACKEND,
            timeout=timeout,
            follow_redirects=False,
            headers={"Authorization": "Bearer " + candidate_token},
        ) as candidate:
            state = expect(candidate.get(f"/interviews/{interview_id}"), "candidate reload", 200)
            if state.get("current_turn_id") != started["current_turn_id"]:
                raise SmokeStop("durable interview turn mismatch")
            speech = expect(
                candidate.get(f"/interviews/{interview_id}/speech-token"),
                "Azure Speech F0 token", 200,
            )
            if not speech.get("token") or speech.get("region") != "eastus":
                raise SmokeStop("Azure Speech token target mismatch")
            print("PASS: durable candidate state and Azure Speech F0 token")

            for turn in range(MAX_ANSWER_TURNS):
                if state.get("finished"):
                    break
                turn_id = state.get("current_turn_id")
                if not isinstance(turn_id, str) or len(turn_id) != 32:
                    raise SmokeStop("current turn identity missing")
                state = expect(
                    candidate.post(
                        f"/interviews/{interview_id}/answers",
                        json={"turn_id": turn_id, "answer": answer},
                    ),
                    f"adaptive answer {turn + 1}", 200,
                )
                reloaded = expect(
                    candidate.get(f"/interviews/{interview_id}"),
                    "candidate state reload", 200,
                )
                if reloaded.get("current_turn_id") != state.get("current_turn_id"):
                    raise SmokeStop("accepted turn did not persist")
            if not state.get("finished"):
                raise SmokeStop("interview exceeded bounded answer-turn budget")
            print("PASS: adaptive interview completed with durable answer turns")

        report = expect(
            recruiter.get(f"/interviews/{interview_id}/report"),
            "real OpenAI report", 200,
        )
        if "overall_score" not in report or "recommendation" not in report:
            raise SmokeStop("report fields missing")
        cached = expect(
            recruiter.get(f"/interviews/{interview_id}/report"),
            "cached report", 200,
        )
        if cached != report:
            raise SmokeStop("stored report changed on read")
        print("PASS: real OpenAI report generation and cached reread")

        expect(recruiter.delete(f"/interviews/{interview_id}"), "owned interview erase", 204)
        print("PASS: synthetic interview/report/candidate erased through owner API")
        print("CLEANUP_PENDING: synthetic recruiter and job identified by SMOKE_MARKER")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="allow bounded paid provider calls")
    args = parser.parse_args()
    if not args.run:
        print("STOP: --run is required; no request sent")
        raise SystemExit(1)
    try:
        run_smoke()
    except SmokeStop as exc:
        print("STOP: " + str(exc))
        raise SystemExit(1) from None
    except Exception as exc:
        print("STOP: " + type(exc).__name__ + "; inspect isolated deployment only")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
