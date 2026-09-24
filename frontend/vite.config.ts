/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

/**
 * The dev server proxies the API so the app is **same-origin with its backend**.
 *
 * This is load-bearing for authentication, not a convenience. Recruiter auth is a session in an
 * `HttpOnly`, `SameSite=Strict` cookie; a Strict cookie is only sent on same-site requests, and
 * the previous setup served the page from `localhost:5173` while calling the API on
 * `127.0.0.1:8000` - different hosts, therefore cross-site, therefore the cookie would never
 * have been sent at all. Proxying `/api` through the dev server means the browser only ever
 * talks to one origin.
 *
 * It is also what makes the CSRF position honest rather than assumed: with one origin and a
 * Strict cookie, no cross-site request can carry the session, so there is nothing for a forged
 * request to ride on and no separate CSRF token scheme is needed. A deployment that splits the
 * frontend and API across different sites would break that property and would need to revisit
 * both the cookie policy and CSRF - see `app/api/routes/auth.py`.
 *
 * `API_PROXY_TARGET` points the proxy at a backend on another host/port; it is a dev-server
 * setting and is never exposed to browser code (no `VITE_` prefix).
 */
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const target = env.API_PROXY_TARGET || 'http://127.0.0.1:8000'

  return {
    plugins: [react()],
    server: {
      proxy: {
        '/api': {
          target,
          changeOrigin: true,
          // The backend serves its routes at the root, so the `/api` marker is stripped on the
          // way through. It exists only to tell the dev server what to forward.
          rewrite: (path) => path.replace(/^\/api/, ''),
          // Drop any Domain attribute so the session cookie is scoped to the origin the
          // browser actually sees (the dev server), not to the proxy target's host.
          cookieDomainRewrite: '',
        },
      },
    },
    test: {
      environment: 'jsdom',
      globals: true,
      include: ['src/**/*.test.{ts,tsx}'],
    },
  }
})
