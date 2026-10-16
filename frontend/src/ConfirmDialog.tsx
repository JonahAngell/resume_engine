import React from "react";
import { createRoot } from "react-dom/client";
import ModalShell from "./ModalShell";
export type ConfirmOptions = {
  title: string;
  message: string;
  names?: string[];
  confirmLabel?: string;
  danger?: boolean;
};
export function confirmDialog(options: ConfirmOptions): Promise<boolean> {
  return new Promise((resolve) => {
    const host = document.createElement("div");
    document.body.append(host);
    const root = createRoot(host);
    const done = (v: boolean) => {
      root.unmount();
      host.remove();
      resolve(v);
    };
    const names = options.names || [],
      shown = names.slice(0, 5),
      more = names.length - shown.length;
    root.render(
      <ModalShell title={options.title} close={() => done(false)}>
        <p>{options.message}</p>
        {shown.length > 0 && (
          <ul>
            {shown.map((x) => (
              <li key={x}>{x}</li>
            ))}
            {more > 0 && <li>and {more} more</li>}
          </ul>
        )}
        <div className="form-actions">
          <button onClick={() => done(false)}>Cancel</button>
          <button
            className={options.danger ? "danger-confirm" : "primary"}
            onClick={() => done(true)}
          >
            {options.confirmLabel || "Confirm"}
          </button>
        </div>
      </ModalShell>,
    );
  });
}

export type SaveMode = "variant" | "new" | "overwrite";

export function chooseSaveMode(noun: "bullet" | "entry"): Promise<SaveMode | null> {
  return new Promise((resolve) => {
    const host = document.createElement("div");
    document.body.append(host);
    const root = createRoot(host);
    const done = (value: SaveMode | null) => {
      root.unmount();
      host.remove();
      resolve(value);
    };
    root.render(
      <ModalShell title="Save changes" close={() => done(null)}>
        <p>How should this {noun} be saved?</p>
        <div className="form-actions">
          <button onClick={() => done(null)}>Cancel</button>
          <button onClick={() => done("overwrite")}>
            Overwrite the existing {noun}
          </button>
          <button onClick={() => done("new")}>Create a new {noun}</button>
          <button className="primary" autoFocus onClick={() => done("variant")}>
            Save as a variant
          </button>
        </div>
      </ModalShell>,
    );
  });
}
