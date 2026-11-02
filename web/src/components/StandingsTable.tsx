import type { StandingRow } from "../api";

interface Props {
  caption: string;
  rows: StandingRow[];
  busy?: boolean;
}

const RESULT_WORD: Record<string, string> = { W: "Win", D: "Draw", L: "Loss" };

function Form({ form }: { form: string | null }) {
  const results = (form ?? "").split(",").map((r) => r.trim()).filter(Boolean);
  if (results.length === 0) return <span className="muted" aria-label="No form data">—</span>;

  return (
    <span
      className="form"
      role="img"
      aria-label={`Recent form: ${results.map((r) => RESULT_WORD[r] ?? r).join(", ")}`}
    >
      {results.map((r, i) => (
        <span key={i} className={`form-pill form-${r}`} aria-hidden="true">
          {r}
        </span>
      ))}
    </span>
  );
}

const signed = (n: number) => (n > 0 ? `+${n}` : n < 0 ? `\u2212${-n}` : "0");

export function StandingsTable({ caption, rows, busy = false }: Props) {
  return (
    <div
      className="table-wrap"
      role="region"
      aria-labelledby="standings-caption"
      aria-busy={busy}
      tabIndex={0}
    >
      <table className="standings">
        <caption id="standings-caption" className="visually-hidden">
          {caption}
        </caption>
        <thead>
          <tr>
            <th scope="col" className="col-pos"><abbr title="Position">Pos</abbr></th>
            <th scope="col" className="col-club">Club</th>
            <th scope="col"><abbr title="Played">P</abbr></th>
            <th scope="col"><abbr title="Won">W</abbr></th>
            <th scope="col"><abbr title="Drawn">D</abbr></th>
            <th scope="col"><abbr title="Lost">L</abbr></th>
            <th scope="col"><abbr title="Goals for">GF</abbr></th>
            <th scope="col"><abbr title="Goals against">GA</abbr></th>
            <th scope="col"><abbr title="Goal difference">GD</abbr></th>
            <th scope="col"><abbr title="Points">Pts</abbr></th>
            <th scope="col" className="col-form">Form</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.team_id}>
              <td className="col-pos">{row.position}</td>
              <th scope="row" className="col-club">
                <span className="club">
                  {row.team_crest ? (
                    <img
                      src={row.team_crest}
                      alt=""
                      width={22}
                      height={22}
                      loading="lazy"
                      onError={(e) => (e.currentTarget.style.visibility = "hidden")}
                    />
                  ) : (
                    <span className="crest-placeholder" aria-hidden="true" />
                  )}
                  <span className="club-name">{row.team_name}</span>
                </span>
              </th>
              <td>{row.played}</td>
              <td>{row.won}</td>
              <td>{row.draw}</td>
              <td>{row.lost}</td>
              <td>{row.goals_for}</td>
              <td>{row.goals_against}</td>
              <td>{signed(row.goal_difference)}</td>
              <td className="col-pts">{row.points}</td>
              <td className="col-form"><Form form={row.form} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
