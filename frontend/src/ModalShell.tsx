import React, { useEffect, useId, useRef } from "react";
import { createPortal } from "react-dom";

type ModalShellProps = {
  title: string;
  close: () => void;
  children: React.ReactNode;
  variant?: "dialog" | "side-panel";
  className?: string;
};
const FOCUSABLE =
  'button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),a[href],[tabindex]:not([tabindex="-1"])';
export default function ModalShell({
  title,
  close,
  children,
  variant = "dialog",
  className = "",
}: ModalShellProps) {
  const titleId = useId();
  const panel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    const inertTarget =
      variant === "side-panel"
        ? document.querySelector<HTMLElement>(".editing-shell .editor")
        : document.querySelector<HTMLElement>("#root");
    inertTarget?.setAttribute("inert", "");
    requestAnimationFrame(() =>
      panel.current?.querySelector<HTMLElement>(FOCUSABLE)?.focus(),
    );
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        close();
        return;
      }
      if (event.key !== "Tab" || !panel.current) return;
      const items = [...panel.current.querySelectorAll<HTMLElement>(FOCUSABLE)];
      if (!items.length) return;
      const first = items[0],
        last = items.at(-1)!;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      }
      if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    addEventListener("keydown", onKey);
    return () => {
      removeEventListener("keydown", onKey);
      inertTarget?.removeAttribute("inert");
      opener?.focus();
    };
  }, [close, variant]);
  return createPortal(
    <div className={`modal-backdrop ${variant}`} role="presentation">
      <div
        ref={panel}
        className={`modal-shell ${variant} ${className}`}
        role="dialog"
        aria-modal={variant === "dialog" ? "true" : undefined}
        aria-labelledby={titleId}
      >
        <div className="modal-heading">
          <h2 id={titleId}>{title}</h2>
          <button type="button" aria-label={`Close ${title}`} onClick={close}>
            ×
          </button>
        </div>
        {children}
      </div>
    </div>,
    document.body,
  );
}
