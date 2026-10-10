import React, { useEffect, useRef, useState } from "react";
export type OverflowItem = {
  label: string;
  onSelect: () => void;
  disabled?: boolean;
  danger?: boolean;
};
export default function OverflowMenu({
  label,
  items,
}: {
  label: string;
  items: OverflowItem[];
}) {
  const [open, setOpen] = useState(false),
    root = useRef<HTMLDivElement>(null),
    trigger = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const f = (e: MouseEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", f);
    return () => document.removeEventListener("mousedown", f);
  }, []);
  const focus = (i: number) => {
    const a = [
      ...(root.current?.querySelectorAll<HTMLButtonElement>(
        '[role="menuitem"]:not([disabled])',
      ) || []),
    ];
    a[(i + a.length) % a.length]?.focus();
  };
  return (
    <div className="overflow-menu" ref={root}>
      <button
        ref={trigger}
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        ⋯
      </button>
      {open && (
        <div
          role="menu"
          onKeyDown={(e) => {
            const a = [
                ...(root.current?.querySelectorAll('[role="menuitem"]') || []),
              ],
              i = a.indexOf(document.activeElement as Element);
            if (e.key === "ArrowDown") {
              e.preventDefault();
              focus(i + 1);
            }
            if (e.key === "ArrowUp") {
              e.preventDefault();
              focus(i - 1);
            }
            if (e.key === "Home") {
              e.preventDefault();
              focus(0);
            }
            if (e.key === "End") {
              e.preventDefault();
              focus(-1);
            }
            if (e.key === "Escape") {
              setOpen(false);
              trigger.current?.focus();
            }
          }}
        >
          {items.map((x) => (
            <button
              key={x.label}
              role="menuitem"
              disabled={x.disabled}
              className={x.danger ? "danger-text" : ""}
              onClick={() => {
                setOpen(false);
                x.onSelect();
                requestAnimationFrame(() => trigger.current?.focus());
              }}
            >
              {x.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
