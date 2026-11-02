import type { League } from "../api";

interface Props {
  leagues: League[];
  selected: string | null;
  onSelect: (code: string) => void;
}

export function LeaguePicker({ leagues, selected, onSelect }: Props) {
  return (
    <div className="league-picker" role="group" aria-label="League">
      {leagues.map((league) => (
        <button
          key={league.code}
          type="button"
          className="league-btn"
          aria-pressed={league.code === selected}
          onClick={() => onSelect(league.code)}
        >
          {league.emblem_url && (
            <img
              src={league.emblem_url}
              alt=""
              width={20}
              height={20}
              loading="lazy"
              onError={(e) => (e.currentTarget.hidden = true)}
            />
          )}
          <span>{league.name}</span>
        </button>
      ))}
    </div>
  );
}
