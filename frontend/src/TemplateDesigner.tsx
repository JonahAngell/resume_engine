import React, { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "./api";
import { confirmDialog } from "./ConfirmDialog";
import type { Fit } from "./FitIndicator";
import ResumePreview from "./ResumePreview";
import {
  BASE_LABELS,
  type BaseStyle,
  type CustomTemplate,
  type TemplateOptions,
  type TemplateSettings,
} from "./templates";

type Props = {
  composition: {
    id: string;
    revision: number;
    preferred_page_length?: number;
    tools_layout?: string | null;
  };
  options: TemplateOptions;
  /** The custom template being edited, or null to make a new one from `baseStyle`. */
  template: CustomTemplate | null;
  baseStyle: BaseStyle;
  existingNames: string[];
  close: () => void;
  /** A new template was created; the caller links it to the resume. */
  onCreated: (template: CustomTemplate) => Promise<void> | void;
  /** An existing template was saved or deleted; `composition` is the resume's new state. */
  onChanged: (composition: any | null) => Promise<void> | void;
};

const MARGIN_PRESETS: [string, number][] = [
  ["Narrow", 0.5],
  ["Normal", 0.75],
  ["Wide", 1],
];
const SIZE_FIELDS: [keyof TemplateSettings["sizes"], string][] = [
  ["name", "Name"],
  ["heading", "Section headings"],
  ["title", "Job titles and organizations"],
  ["body", "Body text"],
  ["contact", "Contact line"],
];
const SIDES: (keyof TemplateSettings["margins"])[] = [
  "top",
  "right",
  "bottom",
  "left",
];

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value));
}

function NumberField({
  label,
  value,
  onChange,
  limit,
  step,
  unit,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
  limit?: { min: number; max: number };
  step: number;
  unit: string;
}) {
  const [text, setText] = useState(String(value));
  useEffect(() => setText(String(value)), [value]);
  const commit = (raw: string) => {
    const number = Number(raw);
    if (!raw.trim() || !Number.isFinite(number)) return setText(String(value));
    const clamped = Math.min(
      limit?.max ?? number,
      Math.max(limit?.min ?? number, number),
    );
    setText(String(clamped));
    if (clamped !== value) onChange(clamped);
  };
  return (
    <label className="designer-number">
      <span>{label}</span>
      <span className="designer-number-input">
        <input
          type="number"
          aria-label={`${label} (${unit})`}
          inputMode="decimal"
          value={text}
          step={step}
          min={limit?.min}
          max={limit?.max}
          onChange={(event) => {
            setText(event.target.value);
            const number = Number(event.target.value);
            if (
              event.target.value.trim() &&
              Number.isFinite(number) &&
              (!limit || (number >= limit.min && number <= limit.max))
            )
              onChange(number);
          }}
          onBlur={(event) => commit(event.target.value)}
        />
        <small>{unit}</small>
      </span>
    </label>
  );
}

function Choice<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: [T, React.ReactNode][];
  onChange: (value: T) => void;
}) {
  return (
    <div className="designer-choice" role="radiogroup" aria-label={label}>
      <span className="designer-choice-label">{label}</span>
      <div className="qual-filters">
        {options.map(([option, text]) => (
          <button
            key={option}
            type="button"
            role="radio"
            aria-checked={value === option}
            className={value === option ? "active" : ""}
            onClick={() => onChange(option)}
          >
            {text}
          </button>
        ))}
      </div>
    </div>
  );
}

function ColorField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  const [text, setText] = useState(value);
  useEffect(() => setText(value), [value]);
  return (
    <label className="designer-color">
      <span>{label}</span>
      <span className="designer-color-inputs">
        <input
          type="color"
          value={value}
          aria-label={`${label} picker`}
          onChange={(event) => onChange(event.target.value)}
        />
        <input
          type="text"
          value={text}
          maxLength={7}
          spellCheck={false}
          aria-label={`${label} hex code`}
          onChange={(event) => {
            setText(event.target.value);
            if (/^#[0-9a-fA-F]{6}$/.test(event.target.value))
              onChange(event.target.value.toLowerCase());
          }}
          onBlur={() => setText(value)}
        />
      </span>
    </label>
  );
}

export default function TemplateDesigner({
  composition,
  options,
  template,
  baseStyle,
  existingNames,
  close,
  onCreated,
  onChanged,
}: Props) {
  const base = (template?.base_style || baseStyle) as BaseStyle;
  const defaults = useMemo(
    () => options.bases.find((item) => item.id === base)?.defaults,
    [options, base],
  );
  const initial = useMemo(
    () => clone(template?.settings || defaults!),
    [template, defaults],
  );
  const suggestedName = useMemo(() => {
    const stem = `${BASE_LABELS[base]} (custom)`;
    const taken = new Set(existingNames.map((name) => name.toLowerCase()));
    let name = stem;
    for (let index = 2; taken.has(name.toLowerCase()); index++)
      name = `${stem} ${index}`;
    return name;
  }, [base, existingNames]);
  const [name, setName] = useState(template?.name || suggestedName);
  const [settings, setSettings] = useState<TemplateSettings>(initial);
  const [draft, setDraft] = useState<TemplateSettings>(initial);
  const [fit, setFit] = useState<Fit | null>(null);
  const [page, setPage] = useState(1);
  // Start small enough that a whole page fits across a phone screen.
  const [zoom, setZoom] = useState(() =>
    Math.max(
      40,
      Math.min(70, Math.floor(((window.innerWidth - 32) / 816) * 10) * 10),
    ),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const limits = options.limits;
  const dirty =
    JSON.stringify(settings) !== JSON.stringify(initial) ||
    name.trim() !== (template?.name || suggestedName);

  // Re-render the preview a moment after the last change, not on every keystroke.
  useEffect(() => {
    const timer = window.setTimeout(() => setDraft(settings), 300);
    return () => window.clearTimeout(timer);
  }, [settings]);
  const set = <K extends keyof TemplateSettings>(
    key: K,
    value: TemplateSettings[K],
  ) => setSettings((current) => ({ ...current, [key]: value }));
  const setSize = (key: keyof TemplateSettings["sizes"], value: number) =>
    setSettings((current) => ({
      ...current,
      sizes: { ...current.sizes, [key]: value },
    }));
  const setMargin = (key: keyof TemplateSettings["margins"], value: number) =>
    setSettings((current) => ({
      ...current,
      margins: { ...current.margins, [key]: value },
    }));
  const onFit = useCallback((next: Fit) => setFit(next), []);
  const pages = fit?.actualPageCount || 1;
  useEffect(() => setPage((current) => Math.min(current, pages)), [pages]);
  const preset = MARGIN_PRESETS.find(([, inches]) =>
    SIDES.every((side) => settings.margins[side] === inches),
  )?.[0];
  const overridden =
    !!composition.tools_layout &&
    composition.tools_layout !== settings.tools_layout;

  const leave = async () => {
    if (
      dirty &&
      !(await confirmDialog({
        title: "Discard template changes?",
        message: "Your changes to this template haven't been saved.",
        confirmLabel: "Discard",
      }))
    )
      return;
    close();
  };

  const save = async () => {
    if (!name.trim()) return setError("Give the template a name.");
    setBusy(true);
    setError("");
    try {
      if (template) {
        const result = await api<{
          template: CustomTemplate;
          composition: any;
        }>(`/api/templates/${template.id}`, {
          method: "PUT",
          body: JSON.stringify({
            revision: template.revision,
            name: name.trim(),
            settings,
            composition_id: composition.id,
          }),
        });
        await onChanged(result.composition);
      } else {
        const made = await api<CustomTemplate>("/api/templates", {
          method: "POST",
          body: JSON.stringify({
            name: name.trim(),
            base_style: base,
            settings,
          }),
        });
        await onCreated(made);
      }
      close();
    } catch (reason: any) {
      setError(
        reason instanceof ApiError || reason?.message
          ? reason.message
          : "Could not save the template.",
      );
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!template) return;
    const others = Math.max(0, template.used_by - 1);
    if (
      !(await confirmDialog({
        title: `Delete “${template.name}”?`,
        message: `Resumes using it go back to the ${BASE_LABELS[base]} template${
          others
            ? `, including ${others} other resume${others === 1 ? "" : "s"}`
            : ""
        }. Each keeps a history entry.`,
        confirmLabel: "Delete template",
      }))
    )
      return;
    setBusy(true);
    try {
      const result = await api<{ composition: any }>(
        `/api/templates/${template.id}?composition_id=${composition.id}`,
        {
          method: "DELETE",
        },
      );
      await onChanged(result.composition);
      close();
    } catch (reason: any) {
      setError(reason.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="template-designer">
      <header className="designer-header">
        <button type="button" className="link-button" onClick={leave}>
          ← Back to resume
        </button>
        <h1>{template ? "Edit template" : "New template"}</h1>
        <span className="designer-header-spacer" />
        {template && template.used_by > 1 && (
          <span className="designer-shared">
            Used by {template.used_by} resumes. Saving changes all of them.
          </span>
        )}
        <button type="button" onClick={leave} disabled={busy}>
          Cancel
        </button>
        <button
          type="button"
          className="primary"
          onClick={save}
          disabled={busy || (!dirty && !!template)}
        >
          {busy ? "Saving…" : template ? "Save template" : "Save and use"}
        </button>
      </header>
      {error && (
        <p role="alert" className="error designer-error">
          {error}
        </p>
      )}
      <div className="designer-body">
        <form
          className="designer-form"
          onSubmit={(event) => event.preventDefault()}
          aria-label="Template settings"
        >
          <label className="designer-name">
            <span>Template name</span>
            <input
              value={name}
              maxLength={80}
              onChange={(event) => setName(event.target.value)}
            />
          </label>
          <p className="ai-meta">
            Based on {BASE_LABELS[base]}. Layout and section names come from it;
            everything below is yours to change.
          </p>

          <fieldset>
            <legend>Text</legend>
            <label className="designer-select">
              <span>Font</span>
              <select
                value={settings.font}
                onChange={(event) => set("font", event.target.value)}
              >
                {options.fonts.map((font) => (
                  <option key={font.id} value={font.id}>
                    {font.label}
                  </option>
                ))}
              </select>
            </label>
            <div className="designer-grid">
              {SIZE_FIELDS.map(([key, label]) => (
                <NumberField
                  key={key}
                  label={label}
                  value={settings.sizes[key]}
                  limit={limits[`sizes.${key}`]}
                  step={0.5}
                  unit="pt"
                  onChange={(value) => setSize(key, value)}
                />
              ))}
            </div>
          </fieldset>

          <fieldset>
            <legend>Colours</legend>
            <div className="designer-grid">
              <ColorField
                label="Text"
                value={settings.text_color}
                onChange={(value) => set("text_color", value)}
              />
              <ColorField
                label="Name and headings"
                value={settings.accent_color}
                onChange={(value) => set("accent_color", value)}
              />
              <ColorField
                label="Divider lines"
                value={settings.rule_color}
                onChange={(value) => set("rule_color", value)}
              />
            </div>
          </fieldset>

          <fieldset>
            <legend>Section headings</legend>
            <Choice
              label="Letters"
              value={settings.heading_case}
              options={[
                ["upper", "ALL CAPS"],
                ["normal", "As written"],
              ]}
              onChange={(value) => set("heading_case", value)}
            />
            <Choice
              label="Weight"
              value={settings.heading_bold ? "bold" : "regular"}
              options={[
                ["bold", <b key="b">Bold</b>],
                ["regular", "Regular"],
              ]}
              onChange={(value) => set("heading_bold", value === "bold")}
            />
            <Choice
              label="Divider"
              value={settings.heading_rule}
              options={[
                ["none", "None"],
                ["underline", "Line below"],
                ["box", "Lines above and below"],
              ]}
              onChange={(value) => set("heading_rule", value)}
            />
          </fieldset>

          <fieldset>
            <legend>Entries</legend>
            <Choice
              label="Bullet"
              value={settings.bullet}
              options={options.bullets.map((bullet) => [
                bullet.id,
                <span key={bullet.id} className="designer-bullet">
                  {bullet.mark}
                </span>,
              ])}
              onChange={(value) => set("bullet", value)}
            />
            <Choice
              label="Dates"
              value={settings.date_position}
              options={[
                ["right", "Right-aligned"],
                ["inline", "After the title"],
              ]}
              onChange={(value) => set("date_position", value)}
            />
            <Choice
              label="Tools section"
              value={settings.tools_layout}
              options={[
                ["inline", "One line per group"],
                ["table", "Table"],
              ]}
              onChange={(value) => set("tools_layout", value)}
            />
            {settings.tools_layout === "table" && (
              <small className="coaching-note">
                Some applicant tracking systems read tables poorly; the ATS
                score counts it.
              </small>
            )}
            {overridden && (
              <small className="coaching-note">
                This resume sets its own Tools layout, so the preview keeps the
                template's choice. Change it in the Tools section.
              </small>
            )}
          </fieldset>

          <fieldset>
            <legend>Page</legend>
            <Choice
              label="Margins"
              value={preset || "custom"}
              options={[
                ...MARGIN_PRESETS.map(
                  ([label]) => [label, label] as [string, string],
                ),
                ["custom", "Custom"],
              ]}
              onChange={(value) => {
                const inches = MARGIN_PRESETS.find(
                  ([label]) => label === value,
                )?.[1];
                if (inches)
                  set("margins", {
                    top: inches,
                    right: inches,
                    bottom: inches,
                    left: inches,
                  });
              }}
            />
            <div className="designer-grid designer-margins">
              {SIDES.map((side) => (
                <NumberField
                  key={side}
                  label={side[0].toUpperCase() + side.slice(1)}
                  value={settings.margins[side]}
                  limit={limits[`margins.${side}`]}
                  step={0.05}
                  unit="in"
                  onChange={(value) => setMargin(side, value)}
                />
              ))}
            </div>
            <label className="designer-range">
              <span>
                Line spacing <output>{settings.line_height.toFixed(2)}</output>
              </span>
              <input
                type="range"
                min={limits.line_height?.min ?? 1}
                max={limits.line_height?.max ?? 1.6}
                step={0.05}
                value={settings.line_height}
                onChange={(event) =>
                  set("line_height", Number(event.target.value))
                }
              />
            </label>
            <div className="designer-grid">
              <NumberField
                label="Space after each section"
                value={settings.section_gap}
                limit={limits.section_gap}
                step={1}
                unit="pt"
                onChange={(value) => set("section_gap", value)}
              />
              <NumberField
                label="Space after each bullet"
                value={settings.bullet_gap}
                limit={limits.bullet_gap}
                step={0.5}
                unit="pt"
                onChange={(value) => set("bullet_gap", value)}
              />
            </div>
          </fieldset>

          <div className="designer-footer-actions">
            <button
              type="button"
              className="link-button"
              onClick={() => setSettings(clone(defaults!))}
            >
              Start over from {BASE_LABELS[base]}
            </button>
            {template && (
              <button
                type="button"
                className="link-button danger"
                onClick={remove}
                disabled={busy}
              >
                Delete template
              </button>
            )}
          </div>
        </form>

        <section className="designer-preview" aria-label="Template preview">
          <div className="preview-toolbar designer-preview-toolbar">
            <span
              className={`designer-fit ${fit && !fit.fits ? "over" : ""}`}
              aria-live="polite"
            >
              {fit?.state === "measurement-error"
                ? fit.message || "Preview failed"
                : fit
                  ? `${pages} page${pages === 1 ? "" : "s"} · target ${composition.preferred_page_length || 1}`
                  : "Measuring…"}
            </span>
            <span className="preview-toolbar-spacer" />
            {pages > 1 && (
              <>
                <button
                  type="button"
                  aria-label="Previous page"
                  disabled={page <= 1}
                  onClick={() => setPage(page - 1)}
                >
                  ‹
                </button>
                <output aria-label="Preview page">
                  {page} / {pages}
                </output>
                <button
                  type="button"
                  aria-label="Next page"
                  disabled={page >= pages}
                  onClick={() => setPage(page + 1)}
                >
                  ›
                </button>
              </>
            )}
            <button
              type="button"
              onClick={() => setZoom((value) => Math.max(40, value - 10))}
              aria-label="Zoom out"
            >
              −
            </button>
            <output aria-label="Preview zoom">{zoom}%</output>
            <button
              type="button"
              onClick={() => setZoom((value) => Math.min(150, value + 10))}
              aria-label="Zoom in"
            >
              +
            </button>
          </div>
          <div
            className="preview-canvas designer-canvas"
            style={{ "--preview-zoom": zoom / 100 } as React.CSSProperties}
          >
            <ResumePreview
              compositionId={composition.id}
              revision={composition.revision}
              preferredPageCount={composition.preferred_page_length || 1}
              currentPage={page}
              onFit={onFit}
              draft={{ baseStyle: base, settings: draft }}
            />
          </div>
        </section>
      </div>
    </div>
  );
}
