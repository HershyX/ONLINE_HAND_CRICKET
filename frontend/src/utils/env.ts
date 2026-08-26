/**
 * Environment configuration helpers.
 * All runtime config is sourced from import.meta.env (Vite env vars).
 * Set VITE_API_BASE_URL and VITE_WS_BASE_URL in a .env.local file for local
 * overrides; the defaults below work with the Vite dev-server proxy.
 */

export const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '/api'

export const WS_BASE_URL: string =
  (import.meta.env.VITE_WS_BASE_URL as string | undefined) ??
  // In dev the proxy forwards /ws → ws://localhost:8000, so we derive
  // an absolute WS URL from the current page origin.
  (() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${protocol}//${window.location.host}/ws`
  })()
