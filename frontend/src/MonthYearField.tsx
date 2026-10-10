import React, { useMemo, useState } from "react";

type Props = {
  label: string;
  year?: number | string | null;
  month?: number | string | null;
  disabled?: boolean;
  onChange: (value: { year: number | null; month: number | null }) => void;
};
export default function MonthYearField({
  label,
  year,
  month,
  disabled,
  onChange,
}: Props) {
  const initialYearOnly = !!year && !month;
  const [yearOnly, setYearOnly] = useState(initialYearOnly);
  const [error, setError] = useState("");
  const supportsMonth = useMemo(() => {
    const input = document.createElement("input");
    input.type = "month";
    return input.type === "month";
  }, []);
  const value = year
    ? month
      ? `${String(year).padStart(4, "0")}-${String(month).padStart(2, "0")}`
      : String(year)
    : "";
  const fallback =
    month && year
      ? `${String(month).padStart(2, "0")}/${year}`
      : year
        ? String(year)
        : "";
  const parse = (raw: string) => {
    if (!raw) {
      setError("");
      onChange({ year: null, month: null });
      return;
    }
    const match = raw.match(/^(?:(0[1-9]|1[0-2])\/)?(\d{4})$/);
    if (!match) {
      setError("Enter a year (2024) or month/year (03/2024).");
      return;
    }
    setError("");
    onChange({
      year: Number(match[2]),
      month: match[1] ? Number(match[1]) : null,
    });
  };
  const id = `month-year-${label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
  return (
    <div className="month-year-field">
      <label htmlFor={id}>{label}</label>
      <label className="choice">
        <input
          type="checkbox"
          checked={yearOnly}
          disabled={disabled}
          onChange={(e) => {
            setYearOnly(e.target.checked);
            onChange({ year: year ? Number(year) : null, month: null });
          }}
        />
        Year only {label}
      </label>
      {yearOnly ? (
        <input
          id={id}
          inputMode="numeric"
          pattern="\d{4}"
          value={year || ""}
          disabled={disabled}
          aria-describedby={error ? `${id}-error` : undefined}
          onChange={(e) =>
            onChange({
              year: e.target.value ? Number(e.target.value) : null,
              month: null,
            })
          }
          onBlur={(e) => parse(e.target.value)}
        />
      ) : supportsMonth ? (
        <input
          id={id}
          type="month"
          value={value.includes("-") ? value : ""}
          disabled={disabled}
          onChange={(e) => {
            const [y, m] = e.target.value.split("-");
            onChange({
              year: y ? Number(y) : null,
              month: m ? Number(m) : null,
            });
          }}
        />
      ) : (
        <input
          id={id}
          type="text"
          placeholder="MM/YYYY"
          defaultValue={fallback}
          disabled={disabled}
          aria-describedby={error ? `${id}-error` : undefined}
          onBlur={(e) => parse(e.target.value)}
        />
      )}
      {error && (
        <span id={`${id}-error`} role="alert">
          {error}
        </span>
      )}
    </div>
  );
}
