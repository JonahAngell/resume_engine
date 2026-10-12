import React, { useMemo, useState } from "react";

export type Choice = { value: string; label: string };

const LONG_LIST = 6;

export default function ChoiceList({
  label,
  value,
  options,
  onChange,
  search = "when-long",
  empty = "Nothing to choose.",
  noMatch = "No matches.",
}: {
  label: string;
  value: string;
  options: Choice[];
  onChange: (value: string) => void;
  search?: "always" | "when-long";
  empty?: string;
  noMatch?: string;
}) {
  const [query, setQuery] = useState("");
  const showSearch = search === "always" || options.length > LONG_LIST;
  const shown = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!showSearch || !needle) return options;
    return options.filter((option) =>
      option.label.toLowerCase().includes(needle),
    );
  }, [options, query, showSearch]);

  if (!options.length) return <p className="choice-list-empty">{empty}</p>;

  return (
    <div className="choice-list">
      {showSearch && (
        <input
          aria-label={`Search ${label.toLowerCase()}`}
          value={query}
          placeholder={`Search ${label.toLowerCase()}`}
          onChange={(event) => setQuery(event.target.value)}
        />
      )}
      <div className="choice-list-options" role="radiogroup" aria-label={label}>
        {shown.length === 0 ? (
          <p className="choice-list-empty">{noMatch}</p>
        ) : (
          shown.map((option) => (
            <button
              type="button"
              role="radio"
              aria-checked={option.value === value}
              key={option.value || "none"}
              onClick={() => onChange(option.value)}
            >
              {option.label}
            </button>
          ))
        )}
      </div>
    </div>
  );
}
