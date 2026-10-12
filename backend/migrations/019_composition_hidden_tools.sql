CREATE TABLE composition_hidden_tools (
  composition_id uuid NOT NULL REFERENCES resume_compositions (id) ON DELETE CASCADE,
  tool_id uuid NOT NULL REFERENCES tools (id) ON DELETE CASCADE,
  PRIMARY KEY (composition_id, tool_id)
);
