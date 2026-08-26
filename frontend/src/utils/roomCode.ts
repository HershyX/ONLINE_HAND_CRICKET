/**
 * Simple client-side helpers for room codes.
 * Room codes are generated server-side; these are purely presentational.
 */

/** Normalise a user-typed room code: uppercase, trim whitespace. */
export function normaliseRoomCode(raw: string): string {
  return raw.trim().toUpperCase()
}

/** Validate that a string looks like a valid room code (6 alphanumeric chars). */
export function isValidRoomCode(code: string): boolean {
  return /^[A-Z0-9]{6}$/.test(code)
}
