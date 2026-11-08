-- ПР5, варіант 2. Схема бази даних. Виконується автоматично під час
-- першого запуску контейнера postgres (том даних порожній).

-- Виміри індивідуальних теплових пунктів: один рядок — один вимір
CREATE TABLE heat (
    ts       timestamptz NOT NULL,   -- час виміру
    station  text        NOT NULL,   -- ідентифікатор ІТП
    t_sup    real        NOT NULL    -- T_под, °C
             CHECK (t_sup BETWEEN 30 AND 110),
    t_ret    real        NOT NULL    -- T_зв, °C
             CHECK (t_ret BETWEEN 20 AND 80),
    g        real        NOT NULL    -- витрата G, м³/год
             CHECK (g BETWEEN 0 AND 50),
    t_out    real                    -- зовнішнє повітря, °C
             CHECK (t_out BETWEEN -40 AND 50),
    q        real        NOT NULL    -- теплова потужність Q, кВт
             CHECK (q >= 0),
    q_ema    real        NOT NULL,   -- згладжена Q, кВт
    g_ema    real        NOT NULL,   -- згладжена G, м³/год
    alarm    smallint    NOT NULL    -- тривога: 0 або 1
             CHECK (alarm IN (0, 1)),
    cause    smallint    NOT NULL    -- 0 — норма, 1 — зупинка насоса,
             CHECK (cause IN (0, 1, 2)), -- 2 — низьке теплоспоживання
    lag_ms   integer     NOT NULL,   -- затримка конвеєра, мс
    PRIMARY KEY (station, ts),       -- один вимір на момент
    CHECK (t_ret <= t_sup)           -- зворотна вода не гарячіша за подачу
);
-- Запити дашборду відбирають рядки за часом
CREATE INDEX heat_ts_idx ON heat (ts);

-- Зміни стану ІТП (online/offline)
CREATE TABLE station_status (
    ts      timestamptz NOT NULL DEFAULT now(),
    station text        NOT NULL,
    online  smallint    NOT NULL CHECK (online IN (0, 1))
);
CREATE INDEX station_status_ts_idx ON station_status (ts);
