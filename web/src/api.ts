// Typed client for the FastAPI backend. The browser only ever talks to our API, never to
// football-data.org, so no provider key exists anywhere in the frontend.

export interface League {
  code: string;
  name: string;
  country: string | null;
  emblem_url: string | null;
}

export interface StandingRow {
  position: number;
  team_id: number;
  team_name: string;
  team_crest: string | null;
  played: number;
  won: number;
  draw: number;
  lost: number;
  goals_for: number;
  goals_against: number;
  goal_difference: number;
  points: number;
  form: string | null;
}

export interface StandingsResponse {
  league: League;
  season: string | null;
  fetched_at: string | null; // ISO timestamp
  source: "live" | "cache";
  rows: StandingRow[];
}

// Empty = same origin (Vercel serves the API under /api). Docker Compose sets http://localhost:8000.
export const API_URL = (import.meta.env.VITE_API_URL ?? "").replace(/\/+$/, "");

export class ApiError extends Error {
  readonly status: number;
  /** On a 502 the backend sends the stored table (if any) so the UI can keep showing it. */
  readonly lastKnown: StandingsResponse | null;

  constructor(message: string, status: number, lastKnown: StandingsResponse | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.lastKnown = lastKnown;
  }
}

export function isAbortError(err: unknown): boolean {
  return err instanceof DOMException && err.name === "AbortError";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, init);
  } catch (err) {
    if (isAbortError(err)) throw err;
    throw new ApiError(`Can't reach the API at ${API_URL || window.location.origin}. Is it running?`, 0);
  }

  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = typeof body?.detail === "string" ? body.detail : `Request failed (HTTP ${response.status})`;
    throw new ApiError(detail, response.status, body?.last_known ?? null);
  }
  return body as T;
}

const leaguePath = (code: string) => `/api/leagues/${encodeURIComponent(code)}`;

export const api = {
  listLeagues: (signal?: AbortSignal) => request<League[]>("/api/leagues", { signal }),

  getStandings: (code: string, signal?: AbortSignal) =>
    request<StandingsResponse>(`${leaguePath(code)}/standings`, { signal }),

  syncLeague: (code: string) => request<StandingsResponse>(`${leaguePath(code)}/sync`, { method: "POST" }),
};
