import React, { useEffect, useState } from "react";
import ModalShell from "./ModalShell";
import { api } from "./api";
export default function RevisionHistoryPanel({
  comp,
  close,
  preview,
  restore,
}: any) {
  const [rows, setRows] = useState<any[]>([]),
    [selected, setSelected] = useState(0),
    [error, setError] = useState("");
  useEffect(() => {
    api<any[]>(`/api/compositions/${comp.id}/revisions`)
      .then(setRows)
      .catch((e: any) => setError(e.message));
  }, [comp.id, comp.revision]);
  const choose = (i: number) => {
    setSelected(i);
    if (rows[i]) preview(rows[i]);
  };
  return (
    <ModalShell title="Revision History" variant="side-panel" close={close}>
      <div
        className="revision-history"
        role="listbox"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") {
            e.preventDefault();
            choose(Math.min(rows.length - 1, selected + 1));
          }
          if (e.key === "ArrowUp") {
            e.preventDefault();
            choose(Math.max(0, selected - 1));
          }
        }}
      >
        {error && <div role="alert">{error}</div>}
        {rows.map((r, i) => (
          <button
            role="option"
            aria-selected={selected === i}
            key={r.id}
            onClick={() => choose(i)}
          >
            <strong>Revision {r.revision}</strong>
            <span>{new Date(r.created_at).toLocaleString()}</span>
            <span>
              {r.source}
              {r.note ? ` · ${r.note}` : ""}
            </span>
          </button>
        ))}
      </div>
      <div className="form-actions">
        <button onClick={close}>Return to current</button>
        <button
          className="primary"
          disabled={!rows[selected]}
          onClick={() => restore(rows[selected], setError)}
        >
          Restore as new revision
        </button>
      </div>
    </ModalShell>
  );
}
