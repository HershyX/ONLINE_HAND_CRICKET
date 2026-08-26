// ─── Game State Machine ───────────────────────────────────────────────────────

export type GameStatus =
  | 'LOBBY'
  | 'TOSS'
  | 'TOSS_DECISION'
  | 'INNINGS_SETUP'
  | 'CHOOSING_NUMBERS'
  | 'RESOLVING_BALL'
  | 'PLAYER_OUT'
  | 'EXTRA_WICKET_VOTE'
  | 'BOWLER_SWITCH'
  | 'INNINGS_BREAK'
  | 'SECOND_INNINGS'
  | 'GAME_OVER'

export type RoomStatus = 'WAITING' | 'READY' | 'IN_GAME' | 'FINISHED'

export type TossDecision = 'BAT' | 'BOWL'

export type HandNumber = 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10

export type TeamId = 'team_a' | 'team_b'

// ─── Domain Models ────────────────────────────────────────────────────────────

export interface BattingStats {
  runs_scored: number
  balls_faced: number
  fours: number
  sixes: number
  is_out: boolean
  highest_score: number
  innings_count: number
}

export interface BowlingStats {
  balls_bowled: number
  runs_conceded: number
  wickets_taken: number
}

export interface Player {
  id: string
  display_name: string
  team_id: TeamId | null
  ready: boolean
  connected: boolean
  batting_stats: BattingStats
  bowling_stats: BowlingStats
}

export interface Team {
  id: TeamId
  name: string
  player_ids: string[]
  score: number
  wickets: number
  extra_wicket_available: boolean
}

export interface BallResult {
  batsman_number: number
  bowler_number: number
  runs: number
  is_wicket: boolean
  ball_number: number
}

export interface InningsHistory {
  innings_number: number
  batting_team_id: TeamId
  bowling_team_id: TeamId
  score: number
  wickets: number
  balls: BallResult[]
  completed: boolean
}

export interface FinalResult {
  winner_team_id: string | null
  margin_runs: number | null
  margin_wickets: number | null
  is_tie: boolean
  mvp_player_id: string | null
}

export interface InningsState {
  batting_team_id: TeamId
  bowling_team_id: TeamId
  batting_order: string[]
  dismissed: Record<string, boolean>
  current_batsman_idx: number
  extra_wicket_batsman_id: string | null
  extra_wicket_used: boolean
  score: number
  wickets: number
  total_balls: number
  current_bowler_id: string
  total_wickets_available: number
  /** Last resolved ball — both numbers shown publicly after each delivery */
  last_ball: BallResult | null
  /** Set when a wicket falls — cleared on next non-wicket ball */
  last_dismissed_name: string | null
}

export interface ExtraWicketVoteState {
  round: number
  eligible_voters: string[]
  votes: Record<string, string>
  candidates: string[]
}

export interface BowlerSwitchState {
  requested_by: string
  current_bowler: string
  /** Additional players queued behind the active request */
  queue: string[]
}

export interface BatsmanSwitchState {
  /** All bowling-team players who have requested the switch */
  requests: string[]
  /** The current batsman who must accept or decline */
  current_batsman: string
}

export interface GameState {
  status: GameStatus
  innings_number: number
  /** Monotonically increasing. Frontend drops any event with version ≤ last applied. */
  state_version: number
  toss_winner_team_id: TeamId | null
  toss_caller_player_id: string | null
  toss_responder_player_id: string | null
  toss_call_made: 'ODD' | 'EVEN' | null
  toss_decision: TossDecision | null
  /** Revealed publicly after toss resolves */
  toss_caller_number: number | null
  toss_responder_number: number | null
  /** Public announcement after toss decision, e.g. "Team 1 won the toss and chose to BAT FIRST" */
  toss_announcement: string | null
  innings: InningsState | null
  target: number | null
  innings_history: InningsHistory[]
  final_result: FinalResult | null
  extra_wicket_vote: ExtraWicketVoteState | null
  bowler_switch: BowlerSwitchState | null
  batsman_switch: BatsmanSwitchState | null
}

export interface Room {
  room_code: string
  host_id: string
  players: Record<string, Player>
  teams: Record<TeamId, Team>
  room_status: RoomStatus
  game: GameState | null
  max_players: number
  created_at: string
  chat_messages: ChatMessage[]
}

export interface ChatMessage {
  id: string
  player_id: string
  display_name: string
  team_id: string | null
  /** 'global' | 'team' */
  scope: string
  content: string
  timestamp: string
}

// ─── Start-match validation ───────────────────────────────────────────────────

export interface StartMatchValidation {
  can_start: boolean
  reasons: string[]
}

// ─── WebSocket Message Types ──────────────────────────────────────────────────

export type WSMessageType =
  // Server → Client
  | 'ROOM_STATE'
  | 'PLAYER_JOINED'
  | 'PLAYER_LEFT'
  | 'PLAYER_UPDATED'
  | 'PLAYER_READY'
  | 'READY_STATE_CHANGED'
  | 'TEAM_UPDATED'
  | 'GAME_STATE'
  | 'GAME_STARTED'
  | 'BALL_RESOLVED'
  | 'PLAYER_OUT'
  | 'INNINGS_COMPLETE'
  | 'EXTRA_WICKET_VOTE'
  | 'BOWLER_SWITCH'
  | 'GAME_OVER'
  | 'CHAT_MESSAGE'
  | 'ERROR'
  | 'PING'
  // Client → Server
  | 'JOIN_ROOM'
  | 'UPDATE_NAME'
  | 'SWITCH_TEAM'
  | 'SET_READY'
  | 'START_MATCH'
  | 'TRANSFER_HOST'
  | 'RETURN_TO_LOBBY'
  | 'CHAT_MESSAGE'
  | 'TOSS_CALL'
  | 'TOSS_RESPONSE'
  | 'TOSS_DECISION'
  | 'CHOOSE_NUMBER'
  | 'VOTE_EXTRA_WICKET'
  | 'REQUEST_BOWLER_SWITCH'
  | 'RESPOND_BOWLER_SWITCH'
  | 'REQUEST_BATSMAN_SWITCH'
  | 'RESPOND_BATSMAN_SWITCH'
  | 'START_SECOND_INNINGS'
  | 'PONG'

export interface WSMessage<T = unknown> {
  type: WSMessageType
  payload: T
  timestamp: string
  player_id?: string
}

// ─── Action Payloads (Client → Server) ───────────────────────────────────────

export interface JoinRoomPayload { room_code: string; display_name: string; player_id?: string }
export interface UpdateNamePayload { display_name: string }
export interface SwitchTeamPayload { team_id: TeamId }
export interface SetReadyPayload { ready: boolean }
export interface TossCallPayload { call: 'ODD' | 'EVEN'; number: number }
export interface TossResponsePayload { number: number }
export interface TossDecisionPayload { decision: TossDecision }
export interface ChooseNumberPayload { number: HandNumber }
export interface RespondBowlerSwitchPayload { accept: boolean }
export interface RespondBatsmanSwitchPayload {
  accept: boolean
  /** When multiple requests exist, optionally specify which requester steps in */
  chosen_player_id?: string
}

export interface TransferHostPayload { new_host_id: string }
export interface ChatMessagePayload { content: string; scope: 'global' | 'team' }

// ─── Event Payloads (Server → Client) ────────────────────────────────────────

export interface RoomStatePayload { room: Room; your_player_id: string }
export interface ErrorPayload { code: string; message: string }

// ─── UI / App State ───────────────────────────────────────────────────────────

export interface ConnectionState {
  connected: boolean
  connecting: boolean
  error: string | null
}

export type AppPage = 'landing' | 'create' | 'join' | 'room'
