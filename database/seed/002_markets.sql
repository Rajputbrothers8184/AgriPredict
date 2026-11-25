-- ===========================================================================
-- AgriPredict — reference data: markets (mandis)
--
-- Only markets with verifiable public locations are listed. Coordinates are
-- approximate city-centre positions (6 dp) and are used solely to rank
-- "nearby" results — they are not survey-accurate.
--
-- Idempotent: ON CONFLICT (slug) DO UPDATE.
-- ===========================================================================

BEGIN;

INSERT INTO markets (slug, name, district, province, latitude, longitude, is_active) VALUES
    ('lahore-sabzi-mandi',  'Lahore Sabzi Mandi',        'Lahore',      'Punjab',               31.520400, 74.358700, TRUE),
    ('multan-mandi',        'Multan Fruit & Veg Market', 'Multan',      'Punjab',               30.197800, 71.469700, TRUE),
    ('faisalabad-mandi',    'Faisalabad Mandi',          'Faisalabad',  'Punjab',               31.418700, 73.079100, TRUE),
    ('rawalpindi-mandi',    'Rawalpindi Mandi',          'Rawalpindi',  'Punjab',               33.565100, 73.016900, TRUE),
    ('gujranwala-mandi',    'Gujranwala Mandi',          'Gujranwala',  'Punjab',               32.187700, 74.194500, TRUE),
    ('sargodha-mandi',      'Sargodha Mandi',            'Sargodha',    'Punjab',               32.083600, 72.671100, TRUE),
    ('bahawalpur-mandi',    'Bahawalpur Mandi',          'Bahawalpur',  'Punjab',               29.395600, 71.683600, TRUE),
    ('sahiwal-mandi',       'Sahiwal Mandi',             'Sahiwal',     'Punjab',               30.668200, 73.111400, TRUE),
    ('okara-mandi',         'Okara Mandi',               'Okara',       'Punjab',               30.813800, 73.453400, TRUE),
    ('karachi-sabzi-mandi', 'Karachi Sabzi Mandi',       'Karachi',     'Sindh',                24.860700, 67.001100, TRUE),
    ('hyderabad-mandi',     'Hyderabad Mandi',           'Hyderabad',   'Sindh',                25.396000, 68.357800, TRUE),
    ('sukkur-mandi',        'Sukkur Mandi',              'Sukkur',      'Sindh',                27.705200, 68.857400, TRUE),
    ('peshawar-mandi',      'Peshawar Mandi',            'Peshawar',    'Khyber Pakhtunkhwa',   34.015100, 71.524900, TRUE),
    ('abbottabad-mandi',    'Abbottabad Mandi',          'Abbottabad',  'Khyber Pakhtunkhwa',   34.168800, 73.221500, TRUE),
    ('quetta-mandi',        'Quetta Mandi',              'Quetta',      'Balochistan',          30.179800, 66.975000, TRUE),
    ('islamabad-mandi',     'Islamabad Fruit & Veg Market','Islamabad', 'Islamabad',            33.684400, 73.047900, TRUE)
ON CONFLICT (slug) DO UPDATE
    SET name      = EXCLUDED.name,
        district  = EXCLUDED.district,
        province  = EXCLUDED.province,
        latitude  = EXCLUDED.latitude,
        longitude = EXCLUDED.longitude,
        is_active = EXCLUDED.is_active;

COMMIT;
