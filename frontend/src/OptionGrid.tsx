import React, { useEffect, useId, useRef, useState } from "react";

export type GridOption = { value: string; label: string };

export default function OptionGrid({
  label,
  value,
  options,
  columns,
  onChange,
}: {
  label: string;
  value: string;
  options: GridOption[];
  columns: number;
  onChange: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const focusIndex = useRef(0);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const cells = useRef<Array<HTMLButtonElement | null>>([]);
  const gridId = useId();
  const current = options.find((option) => option.value === value) || options[0];
  const rows: GridOption[][] = [];
  for (let index = 0; index < options.length; index += columns)
    rows.push(options.slice(index, index + columns));

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  useEffect(() => {
    if (open) cells.current[focusIndex.current]?.focus();
  }, [open]);

  const openGrid = () => {
    const index = Math.max(
      0,
      options.findIndex((option) => option.value === value),
    );
    focusIndex.current = index;
    setActive(index);
    setOpen(true);
  };
  const choose = (next: string) => {
    onChange(next);
    setOpen(false);
    trigger.current?.focus();
  };
  const move = (next: number) => {
    const index = Math.max(0, Math.min(options.length - 1, next));
    setActive(index);
    cells.current[index]?.focus();
  };

  return (
    <div className="option-grid" ref={root}>
      <button
        type="button"
        ref={trigger}
        className="option-grid-trigger"
        aria-haspopup="grid"
        aria-expanded={open}
        aria-controls={gridId}
        onClick={() => (open ? setOpen(false) : openGrid())}
        onKeyDown={(event) => {
          if (["ArrowDown", "Enter", " "].includes(event.key)) {
            event.preventDefault();
            openGrid();
          }
        }}
      >
        <span>{current?.label}</span>
        <span aria-hidden="true">▾</span>
      </button>
      {open && (
        <div
          id={gridId}
          className="option-grid-panel"
          role="grid"
          aria-label={label}
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              event.preventDefault();
              setOpen(false);
              trigger.current?.focus();
              return;
            }
            const step =
              event.key === "ArrowRight"
                ? 1
                : event.key === "ArrowLeft"
                  ? -1
                  : event.key === "ArrowDown"
                    ? columns
                    : event.key === "ArrowUp"
                      ? -columns
                      : null;
            if (step !== null) {
              event.preventDefault();
              move(active + step);
            }
            if (event.key === "Home") {
              event.preventDefault();
              move(0);
            }
            if (event.key === "End") {
              event.preventDefault();
              move(options.length - 1);
            }
          }}
        >
          {rows.map((row, rowIndex) => (
            <div
              className="option-grid-row"
              role="row"
              key={rowIndex}
              style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}
            >
              {row.map((option) => {
                const index = options.indexOf(option);
                return (
                  <button
                    type="button"
                    role="gridcell"
                    key={option.value}
                    ref={(node) => {
                      cells.current[index] = node;
                    }}
                    aria-selected={option.value === value}
                    tabIndex={active === index ? 0 : -1}
                    onClick={() => choose(option.value)}
                    onFocus={() => setActive(index)}
                  >
                    {option.label}
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
