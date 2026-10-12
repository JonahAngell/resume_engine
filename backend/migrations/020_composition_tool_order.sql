CREATE TABLE composition_tool_order (
  composition_id uuid NOT NULL REFERENCES resume_compositions (id) ON DELETE CASCADE,
  tool_id uuid NOT NULL REFERENCES tools (id) ON DELETE CASCADE,
  sort_order integer NOT NULL,
  PRIMARY KEY (composition_id, tool_id)
);
