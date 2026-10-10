ALTER TABLE resume_compositions
ADD COLUMN revision integer NOT NULL DEFAULT 1;

ALTER TABLE resume_compositions
ADD COLUMN autosaved_at timestamptz;

ALTER TABLE composition_items
ADD CONSTRAINT composition_items_section_check CHECK (
  section IN (
    'education',
    'tool_groups',
    'projects',
    'work_experience',
    'leadership',
    'personal_interests'
  )
);

CREATE INDEX composition_items_order ON composition_items (composition_id, section, sort_order);

CREATE INDEX composition_bullets_order ON composition_bullets (composition_id, sort_order);
