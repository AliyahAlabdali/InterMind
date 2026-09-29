# Documentation

Notes too detailed for the root `README.md`, which stays the overview and setup guide.

| Document | Covers |
|---|---|
| [`recruiter-auth.md`](recruiter-auth.md) | Recruiter sign-in: accounts and persistence, password hashing, session and cookie mechanics, CSRF, tenant isolation, and the boundary between recruiter and candidate access. |
| [`deployment.md`](deployment.md) | The deployment topology (Vercel, Azure App Service, Azure Database for PostgreSQL), the environment variables each tier needs, the migration step, and the known limitations of the current setup. |
| [`public-launch-security.md`](public-launch-security.md) | The current security model: the minimal public job response, rate limiting and its in-process limitations, input size bounds, Speech credential issuance, and why validation errors never echo a submitted value. |

Architecture rationale stays in module docstrings, next to the code it explains.
