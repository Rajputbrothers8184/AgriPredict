-- ===========================================================================
-- AgriPredict — reference data: commodities
-- Idempotent: safe to re-run (ON CONFLICT DO UPDATE keeps names in sync).
--
-- Slugs match the identifiers used by the ML pipeline (ml/datasets) and by the
-- backend's forecast catalogue, so never rename a slug without migrating data.
--
-- name_ur values are the common Urdu names used on Pakistani mandi boards.
-- ===========================================================================

BEGIN;

INSERT INTO commodities (slug, name_en, name_ur, category, price_unit) VALUES
    ('wheat',        'Wheat',        'گندم',      'cereal',     'PKR/40kg'),
    ('rice-basmati','Basmati Rice',  'باسمتی چاول', 'cereal',   'PKR/40kg'),
    ('rice-irri',   'IRRI Rice',     'آئی آر آر آئی چاول', 'cereal', 'PKR/40kg'),
    ('maize',       'Maize',         'مکئی',      'cereal',     'PKR/40kg'),
    ('cotton',      'Cotton',        'کپاس',      'cash_crop',  'PKR/40kg'),
    ('sugarcane',   'Sugarcane',     'گنا',       'cash_crop',  'PKR/40kg'),
    ('potato',      'Potato',        'آلو',       'vegetable',  'PKR/40kg'),
    ('onion',       'Onion',         'پیاز',      'vegetable',  'PKR/40kg'),
    ('tomato',      'Tomato',        'ٹماٹر',     'vegetable',  'PKR/40kg'),
    ('chilli-red',  'Red Chilli',    'لال مرچ',   'vegetable',  'PKR/40kg'),
    ('mango',       'Mango',         'آم',        'fruit',      'PKR/40kg'),
    ('kinnow',      'Kinnow',        'کینو',      'fruit',      'PKR/40kg'),
    ('gram',        'Gram (Chickpea)','چنا',      'pulse',      'PKR/40kg'),
    ('lentil',      'Lentil (Masoor)','مسور',     'pulse',      'PKR/40kg'),
    ('mungbean',    'Mung Bean',     'مونگ',      'pulse',      'PKR/40kg'),
    ('mustard',     'Mustard Seed',  'سرسوں',     'other',      'PKR/40kg')
ON CONFLICT (slug) DO UPDATE
    SET name_en    = EXCLUDED.name_en,
        name_ur    = EXCLUDED.name_ur,
        category   = EXCLUDED.category,
        price_unit = EXCLUDED.price_unit;

COMMIT;
