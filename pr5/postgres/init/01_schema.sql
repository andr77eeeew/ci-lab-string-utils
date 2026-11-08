-- ПР5. Схема бази даних. Виконується автоматично під час
-- першого запуску контейнера postgres (том даних порожній).

-- Виміри станцій: один рядок — один вимір
CREATE TABLE air (
    ts       timestamptz NOT NULL,   -- час виміру
    station  text        NOT NULL,   -- ідентифікатор станції
    pm25     real        NOT NULL    -- мкг/м³
             CHECK (pm25 BETWEEN 0 AND 1000),
    pm25_ema real        NOT NULL,   -- згладжене, мкг/м³
    t        real,                   -- температура, °C
    rh       real,                   -- вологість, %
    aqi      smallint    NOT NULL,   -- індекс AQI
    alarm    smallint    NOT NULL    -- тривога: 0 або 1
             CHECK (alarm IN (0, 1)),
    lag_ms   integer     NOT NULL,   -- затримка конвеєра, мс
    PRIMARY KEY (station, ts)        -- один вимір на момент
);
-- Запити дашборду відбирають рядки за часом
CREATE INDEX air_ts_idx ON air (ts);

-- Зміни стану станцій (online/offline)
CREATE TABLE station_status (
    ts      timestamptz NOT NULL DEFAULT now(),
    station text        NOT NULL,
    online  smallint    NOT NULL CHECK (online IN (0, 1))
);
CREATE INDEX station_status_ts_idx ON station_status (ts);
