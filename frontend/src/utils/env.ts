/**
 * Environment configuration helpers.
 *
 * VITE_ variables are embedded at build time by Vite.
 * You MUST set these in Vercel's "Environment Variables" dashboard
 * (or in .env.local for local dev — never commit real values).
 *
 * Required for production (Vercel):
 *   VITE_API_BASE_URL  = https://<your-render-app>.onrender.com/api
 *   VITE_WS_BASE_URL   = wss://<your-render-app>.onrender.com/ws
 *
 * The /api and /ws suffixes are appended automatically if omitted, but set
 * them explicitly to make the intended routing obvious.
 *
 * Leave both unset for local dev — the Vite proxy handles routing automatically.
 */

// ─── Detect environment ───────────────────────────────────────────────────────

const isDev = import.meta.env.DEV  // true during `vite dev`, false after `vite build`

// ─── API base URL ─────────────────────────────────────────────────────────────

const rawApiUrl = import.meta.env.VITE_API_BASE_URL as string | undefined

const hasInvalidProductionApiUrl =
  !isDev && (!rawApiUrl || rawApiUrl.includes('YOUR-RENDER-APP'))

export const API_BASE_URL: string = (() => {
  // In dev without the var set → use Vite's proxy path '/api'
  if (!rawApiUrl) {
    if (!isDev) {
      console.error(
        '[HandCricket] VITE_API_BASE_URL is not set. ' +
        'Add it to Vercel → Settings → Environment Variables → ' +
        'e.g. https://your-app.onrender.com/api'
      )
    }
    return '/api'
  }
  // Strip trailing slash for consistent path joining
  const base = rawApiUrl.replace(/\/$/, '')
  // The backend always mounts REST routes under /api. Append the suffix if it
  // was omitted from the env var, so every call can't 404 with "Not Found".
  return base.endsWith('/api') ? base : `${base}/api`
})()

export const API_CONFIGURATION_ERROR = hasInvalidProductionApiUrl
  ? 'The production API is not configured. Set VITE_API_BASE_URL in Vercel to your Render URL ending in /api, then redeploy.'
  : null

// ─── WebSocket base URL ────────────────────────────────────────────────────────

const rawWsUrl = import.meta.env.VITE_WS_BASE_URL as string | undefined

// Ensure an absolute URL points at the backend's /ws route (suffix optional).
function toWsUrl(url: string): string {
  const base = url.replace(/\/$/, '')
  return base.endsWith('/ws') ? base : `${base}/ws`
}

export const WS_BASE_URL: string = (() => {
  if (rawWsUrl) {
    return toWsUrl(rawWsUrl)
  }

  if (rawApiUrl) {
    // Production without explicit WS URL: derive from VITE_API_BASE_URL
    // by converting https://host/api → wss://host/ws
    return toWsUrl(
      rawApiUrl
        .replace(/^https:\/\//, 'wss://')
        .replace(/^http:\/\//, 'ws://')
        .replace(/\/api$/, '/ws'),
    )
  }

  if (!isDev) {
    console.error(
      '[HandCricket] VITE_WS_BASE_URL is not set. ' +
      'Add it to Vercel → Settings → Environment Variables → ' +
      'e.g. wss://your-app.onrender.com/ws'
    )
  }

  // Dev fallback: derive from the browser's current origin
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/ws`
})()
