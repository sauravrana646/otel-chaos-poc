-- Idempotent schema + synthetic seed for otel-chaos-poc
CREATE TABLE IF NOT EXISTS catalog_items (
  item_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  category TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS item_context (
  item_id TEXT PRIMARY KEY REFERENCES catalog_items(item_id),
  context_text TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS recommendations (
  request_id TEXT PRIMARY KEY,
  item_id TEXT NOT NULL REFERENCES catalog_items(item_id),
  result_text TEXT NOT NULL,
  model_name TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO catalog_items (item_id, name, category) VALUES
  ('item-100', 'Trail Runner', 'footwear'),
  ('item-200', 'Camp Stove', 'outdoors'),
  ('item-300', 'Desk Lamp', 'home')
ON CONFLICT (item_id) DO NOTHING;

INSERT INTO item_context (item_id, context_text) VALUES
  ('item-100', 'Popular with weekend hikers; prefer cushioned soles.'),
  ('item-200', 'Lightweight backpacking; fuel efficiency matters.'),
  ('item-300', 'Warm white light preferred for evening reading.')
ON CONFLICT (item_id) DO NOTHING;
