import React, { useCallback, useEffect, useId, useRef, useState } from "react";

function placeSectionHelp(button: HTMLButtonElement, pop: HTMLElement) {
  const margin = 8;
  const width = Math.min(280, window.innerWidth - margin * 2);
  pop.style.width = `${width}px`;
  const rect = button.getBoundingClientRect();
  const height = pop.offsetHeight;
  let top = rect.bottom + 6;
  if (top + height > window.innerHeight - margin) {
    const above = rect.top - height - 6;
    top =
      above >= margin
        ? above
        : Math.max(margin, window.innerHeight - height - margin);
  }
  let left = Math.min(rect.left, window.innerWidth - width - margin);
  if (left < margin) left = margin;
  pop.style.top = `${top}px`;
  pop.style.left = `${left}px`;
}

export function SectionHelp({ name, notes }: { name: string; notes: string[] }) {
  const id = useId().replace(/:/g, "");
  const buttonRef = useRef<HTMLButtonElement>(null);
  const popRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const place = useCallback(() => {
    const button = buttonRef.current;
    const pop = popRef.current;
    if (button && pop) placeSectionHelp(button, pop);
  }, []);
  useEffect(() => {
    if (!open) return;
    const frame = requestAnimationFrame(place);
    const hide = () => {
      const pop = popRef.current;
      if (pop?.matches(":popover-open")) pop.hidePopover();
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") hide();
    };
    const onPointer = (event: Event) => {
      const target = event.target as Node | null;
      if (!target) return;
      if (buttonRef.current?.contains(target) || popRef.current?.contains(target))
        return;
      hide();
    };
    window.addEventListener("resize", place);
    document.addEventListener("scroll", place, true);
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("click", onPointer);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", place);
      document.removeEventListener("scroll", place, true);
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("click", onPointer);
    };
  }, [open, place]);
  return (
    <>
      <button
        type="button"
        className="section-help-button"
        ref={buttonRef}
        popoverTarget={id}
        aria-expanded={open}
        aria-label={`Help for ${name}`}
        aria-describedby={open ? id : undefined}
      >
        ?
      </button>
      <div
        id={id}
        ref={popRef}
        popover="auto"
        role="tooltip"
        className="section-help-popover"
        onToggle={(event) => {
          const next = event.newState === "open";
          setOpen(next);
          if (next) requestAnimationFrame(place);
        }}
      >
        {notes.map((note) => (
          <p key={note}>{note}</p>
        ))}
      </div>
    </>
  );
}
