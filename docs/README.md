# Documentation

Notes too detailed for the root `README.md`, which stays the overview and setup guide.

| Document | Covers |
|---|---|
| [`recruiter-auth.md`](recruiter-auth.md) | Recruiter sign-in: accounts and persistence, password hashing, session and cookie mechanics, CSRF, tenant isolation, and the boundary between recruiter and candidate access. |
| [`deployment.md`](deployment.md) | Current Vercel and Neon topology, backend settings, same-origin routing, and the retained Azure rollback environment. |
| [`public-launch-security.md`](public-launch-security.md) | The current security model: the minimal public job response, PostgreSQL-backed rate limiting, input size bounds, Speech credential issuance, and why validation errors never echo a submitted value. |

Architecture rationale stays in module docstrings, next to the code it explains.
