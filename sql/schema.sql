-- schema.sql — LatamPulse
CREATE TABLE IF NOT EXISTS countries (
    country_code VARCHAR(2) PRIMARY KEY,
    country_name VARCHAR(50) NOT NULL,
    currency_code VARCHAR(3) NOT NULL,
    region VARCHAR(50)
);

INSERT INTO countries (country_code, country_name, currency_code, region) VALUES
    ('AR', 'Argentina', 'ARS', 'Sudamérica'),
    ('BR', 'Brasil', 'BRL', 'Sudamérica'),
    ('UY', 'Uruguay', 'UYU', 'Sudamérica'),
    ('CO', 'Colombia', 'COP', 'Sudamérica')
ON CONFLICT (country_code) DO NOTHING;

CREATE TABLE IF NOT EXISTS exchange_rates (
    id SERIAL PRIMARY KEY,
    country_code VARCHAR(2) NOT NULL REFERENCES countries(country_code),
    date DATE NOT NULL,
    rate_type VARCHAR(30) NOT NULL,
    rate_to_usd NUMERIC(14, 4),
    source VARCHAR(50),
    fetched_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS ppp_factors (
    id SERIAL PRIMARY KEY,
    country_code VARCHAR(2) NOT NULL REFERENCES countries(country_code),
    year INTEGER NOT NULL,
    ppp_conversion_factor NUMERIC(14, 4),
    gdp_per_capita_ppp_current NUMERIC(14, 4),
    gdp_per_capita_ppp_constant NUMERIC(14, 4),
    source VARCHAR(50),
    fetched_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS inflation_indices (
    id SERIAL PRIMARY KEY,
    country_code VARCHAR(2) NOT NULL REFERENCES countries(country_code),
    period DATE NOT NULL,
    period_label VARCHAR(200),
    indicator VARCHAR(100) NOT NULL,
    value NUMERIC(14, 4),
    unit VARCHAR(20),
    source VARCHAR(50),
    fetched_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS prices (
    id SERIAL PRIMARY KEY,
    country_code VARCHAR(2) NOT NULL REFERENCES countries(country_code),
    category VARCHAR(50),
    item_name VARCHAR(150),
    unit VARCHAR(50),
    price_local NUMERIC(14, 4),
    currency VARCHAR(3),
    date_captured DATE,
    source VARCHAR(255),
    notes TEXT,
    confidence VARCHAR(30),
    captured_by VARCHAR(50),
    price_usd_nominal NUMERIC(14, 4),
    price_usd_ppp NUMERIC(14, 4)
);

CREATE INDEX IF NOT EXISTS idx_exchange_rates_country_date ON exchange_rates(country_code, date);
CREATE INDEX IF NOT EXISTS idx_inflation_indices_country_period ON inflation_indices(country_code, period);
CREATE INDEX IF NOT EXISTS idx_prices_country_category ON prices(country_code, category);
