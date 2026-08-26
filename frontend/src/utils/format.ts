/** Format a score + wickets pair as "42/3". */
export function formatScore(runs: number, wickets: number): string {
  return `${runs}/${wickets}`
}

/** Format balls bowled as overs string: 18 balls → "3.0", 19 → "3.1". */
export function formatOvers(ballsBowled: number, ballsPerOver = 6): string {
  const overs = Math.floor(ballsBowled / ballsPerOver)
  const rem = ballsBowled % ballsPerOver
  return `${overs}.${rem}`
}

/** Derive a run-rate string from score and balls bowled. */
export function runRate(runs: number, ballsBowled: number): string {
  if (ballsBowled === 0) return '0.00'
  return ((runs / ballsBowled) * 6).toFixed(2)
}

/** Capitalise first letter of a string. */
export function capitalise(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1).toLowerCase()
}
