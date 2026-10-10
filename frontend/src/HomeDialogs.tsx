import React, { useState } from "react";
import ModalShell from "./ModalShell";
export function RenameResumeDialog({ item, close, save }: any) {
  const [name, setName] = useState(item.name),
    [error, setError] = useState("");
  return (
    <ModalShell title="Rename resume" close={close}>
      <label>
        Internal Name
        <input value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      {error && <div role="alert">{error}</div>}
      <div className="form-actions">
        <button onClick={close}>Cancel</button>
        <button
          className="primary"
          onClick={() =>
            name.trim()
              ? save({ ...item, name: name.trim() }, setError)
              : setError("Internal name is required.")
          }
        >
          Save
        </button>
      </div>
    </ModalShell>
  );
}
export function EditDetailsDialog({ item, close, save }: any) {
  const [x, setX] = useState({ ...item }),
    [error, setError] = useState("");
  const f = (k: string, l: string) => (
    <label>
      {l}
      <input
        value={x[k] || ""}
        onChange={(e) => setX({ ...x, [k]: e.target.value })}
      />
    </label>
  );
  return (
    <ModalShell title="Edit details" close={close}>
      <div className="form-grid">
        {f("name", "Internal Name")}
        {f("display_title", "Display Title")}
        {f("target_company", "Target Company")}
        {f("target_role", "Target Role")}
      </div>
      {error && <div role="alert">{error}</div>}
      <div className="form-actions">
        <button onClick={close}>Cancel</button>
        <button
          className="primary"
          onClick={() =>
            x.name.trim()
              ? save(x, setError)
              : setError("Internal name is required.")
          }
        >
          Save
        </button>
      </div>
    </ModalShell>
  );
}
