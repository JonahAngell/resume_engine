-- Named profile variants. One user can keep several contact headers and
-- choose which one a resume uses.
ALTER TABLE profiles
DROP CONSTRAINT profiles_user_id_key;

ALTER TABLE profiles
ADD COLUMN label text,
ADD COLUMN sort_order integer NOT NULL DEFAULT 0,
ADD CONSTRAINT profiles_sort_order_check CHECK (sort_order >= 0);

UPDATE profiles
SET label = 'Default'
WHERE label IS NULL;

ALTER TABLE profiles
ALTER COLUMN label SET NOT NULL;

ALTER TABLE profiles
ADD CONSTRAINT profiles_user_label_key UNIQUE (user_id, label);

CREATE INDEX profiles_user_order ON profiles (user_id, sort_order, id);

ALTER TABLE resume_compositions
ADD COLUMN profile_id uuid REFERENCES profiles (id);

UPDATE resume_compositions AS composition
SET profile_id = profile.id
FROM profiles AS profile
WHERE profile.user_id = composition.user_id
  AND composition.profile_id IS NULL;
