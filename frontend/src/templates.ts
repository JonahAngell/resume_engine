import { useCallback, useEffect, useState } from "react";
import { api } from "./api";

export type BaseStyle = "classic" | "sheets" | "harvard" | "dais" | "sre";
export type ToolsLayout = "table" | "inline";

/** Built-in templates, in picker order, with the names the editor has always shown. */
export const BASE_LABELS: Record<BaseStyle, string> = {
  classic: "Default",
  sheets: "Ruled Serif",
  harvard: "Harvard Style",
  dais: "Times Serif",
  sre: "Skill Table",
};

export type TemplateSettings = {
  font: string;
  sizes: {
    name: number;
    heading: number;
    title: number;
    body: number;
    contact: number;
  };
  text_color: string;
  accent_color: string;
  rule_color: string;
  heading_case: "upper" | "normal";
  heading_bold: boolean;
  heading_rule: "none" | "underline" | "box";
  bullet: string;
  date_position: "right" | "inline";
  margins: { top: number; right: number; bottom: number; left: number };
  line_height: number;
  section_gap: number;
  bullet_gap: number;
  tools_layout: ToolsLayout;
};

export type CustomTemplate = {
  id: string;
  name: string;
  base_style: BaseStyle;
  settings: TemplateSettings;
  revision: number;
  used_by: number;
};

export type TemplateOptions = {
  fonts: { id: string; label: string }[];
  bullets: { id: string; mark: string }[];
  bases: { id: BaseStyle; label: string; defaults: TemplateSettings }[];
  limits: Record<string, { min: number; max: number }>;
};

/** The user's custom templates and the designer's choices, loaded once per editor session. */
export function useTemplates(enabled: boolean) {
  const [templates, setTemplates] = useState<CustomTemplate[]>([]);
  const [options, setOptions] = useState<TemplateOptions | null>(null);
  const reload = useCallback(async () => {
    const result = await api<{
      templates: CustomTemplate[];
      options: TemplateOptions;
    }>("/api/templates");
    setTemplates(result.templates);
    setOptions(result.options);
    return result.templates;
  }, []);
  useEffect(() => {
    if (enabled) reload().catch(() => undefined);
  }, [enabled, reload]);
  return { templates, options, reload };
}

/** Table or one line: the resume's own choice, else its template's, else the built-in's. */
export function effectiveToolsLayout(
  comp: {
    template_style?: string;
    template_id?: string | null;
    tools_layout?: string | null;
  },
  templates: CustomTemplate[],
): ToolsLayout {
  if (comp.tools_layout === "table" || comp.tools_layout === "inline")
    return comp.tools_layout;
  const linked = comp.template_id
    ? templates.find((item) => item.id === comp.template_id)
    : undefined;
  if (linked) return linked.settings.tools_layout;
  return comp.template_style === "sre" ? "table" : "inline";
}
