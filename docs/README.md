# Documentation

Developer documentation for InterMind. The root `README.md` is the project overview and the
setup guide; these are the deeper notes that would bloat it.

| Document | Covers |
|---|---|
| [`recruiter-auth.md`](recruiter-auth.md) | How a recruiter signs in: accounts and persistence, password hashing, session and cookie mechanics, CSRF, tenant isolation, and the boundary between recruiter and candidate access. |
| [`deployment.md`](deployment.md) | The deployment architecture (Vercel, Azure, Azure Database for PostgreSQL), the environment variables each tier needs, the migration step, and the known limitations of the current topology. Nothing has been provisioned; this is the guide, not a record of a live deployment. |

Architecture rationale that belongs next to the code lives in module docstrings rather than
here, so it stays in view of whoever changes the code.
