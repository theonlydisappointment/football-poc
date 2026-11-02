import { useEffect, useRef, useState } from "react";
import { api, ApiError, isAbortError, type League, type StandingsResponse } from "./api";
import { LeaguePicker } from "./components/LeaguePicker";
import { StandingsTable } from "./components/StandingsTable";

const errorMessage = (err: unknown) => (err instanceof Error ? err.message : "Something went wrong");

/** "14:32" for today, "31 Oct 14:32" for older data. */
function formatUpdated(iso: string): string {
  const d = new Date(iso);
  const time = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
  if (d.toDateString() === new Date().toDateString()) return time;
  return `${d.toLocaleDateString([], { day: "numeric", month: "short" })} ${time}`;
}

export default function App() {
  const [leagues, setLeagues] = useState<League[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [table, setTable] = useState<StandingsResponse | null>(null);
  const [loadingStored, setLoadingStored] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Lets async callbacks check "is the user still looking at the league I fetched?"
  const selectedRef = useRef<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    api
      .listLeagues(controller.signal)
      .then(setLeagues)
      .catch((err) => !isAbortError(err) && setError(errorMessage(err)));
    return () => controller.abort();
  }, []);

  // On league switch, show what Postgres already has (no provider call) so the screen isn't blank.
  useEffect(() => {
    selectedRef.current = selected;
    if (!selected) return;

    const controller = new AbortController();
    setLoadingStored(true);
    setError(null);
    api
      .getStandings(selected, controller.signal)
      .then(setTable)
      .catch((err) => !isAbortError(err) && setError(errorMessage(err)))
      .finally(() => !controller.signal.aborted && setLoadingStored(false));
    return () => controller.abort();
  }, [selected]);

  async function pullLeagueData() {
    if (!selected) return;
    const code = selected;
    setSyncing(true);
    setError(null);
    try {
      const data = await api.syncLeague(code);
      if (selectedRef.current === code) setTable(data);
    } catch (err) {
      if (selectedRef.current !== code) return;
      setError(errorMessage(err));
      // Keep a table on screen: the backend's last known copy, else whatever is already shown.
      if (err instanceof ApiError && err.lastKnown) setTable(err.lastKnown);
    } finally {
      setSyncing(false);
    }
  }

  const league = leagues.find((l) => l.code === selected) ?? null;
  const visible = table && table.league.code === selected ? table : null;

  return (
    <div className="page">
      <header className="page-header">
        <h1>League Tables</h1>
        <p className="muted">Pick a league, then pull the latest table from football-data.org.</p>
      </header>

      <LeaguePicker leagues={leagues} selected={selected} onSelect={setSelected} />

      <div className="toolbar">
        <button
          type="button"
          className="btn-primary"
          onClick={pullLeagueData}
          disabled={!selected || syncing}
          aria-busy={syncing}
        >
          {syncing && <progress className="spinner" aria-label="Loading" />}
          {syncing ? "Pulling…" : "Pull League Data"}
        </button>

        <p className="status" role="status">
          {syncing && league && `Pulling ${league.name}…`}
          {!syncing && visible?.fetched_at && (
            <>
              Last updated {formatUpdated(visible.fetched_at)} ·{" "}
              <span
                className={`badge badge-${visible.source}`}
                title={
                  visible.source === "live"
                    ? "Fetched from football-data.org just now"
                    : "Served from the database (no provider call)"
                }
              >
                {visible.source}
              </span>
            </>
          )}
        </p>
      </div>

      {error && (
        <div className="banner banner-error" role="alert">
          <span>{error}</span>
          <button type="button" className="banner-close" onClick={() => setError(null)} aria-label="Dismiss error">
            ×
          </button>
        </div>
      )}

      <main>
        {!selected && (
          <div className="empty">
            <p className="empty-title">Pick a league</p>
            <p className="muted">Choose one of the leagues above to see its table.</p>
          </div>
        )}

        {selected && !visible && loadingStored && (
          <div className="empty" aria-busy="true">
            <progress className="spinner spinner-lg" aria-label="Loading table" />
          </div>
        )}

        {selected && visible && visible.rows.length === 0 && (
          <div className="empty">
            <p className="empty-title">No stored table for {visible.league.name} yet</p>
            <p className="muted">Click Pull League Data to fetch it.</p>
          </div>
        )}

        {visible && visible.rows.length > 0 && (
          <section className="card">
            <h2 className="card-title">
              {visible.league.emblem_url && (
                <img src={visible.league.emblem_url} alt="" width={24} height={24} onError={(e) => (e.currentTarget.hidden = true)} />
              )}
              {visible.league.name}
              {visible.season && <span className="season">{visible.season}</span>}
            </h2>
            <StandingsTable
              caption={`${visible.league.name} ${visible.season ?? ""} standings`}
              rows={visible.rows}
              busy={syncing}
            />
          </section>
        )}
      </main>

      <footer className="page-footer muted">
        Data from <a href="https://www.football-data.org" target="_blank" rel="noreferrer">football-data.org</a>
      </footer>
    </div>
  );
}
