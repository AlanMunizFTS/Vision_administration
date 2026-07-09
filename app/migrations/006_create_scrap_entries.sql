CREATE TABLE IF NOT EXISTS public.scrap_entries (
    id SERIAL PRIMARY KEY,
    station_pair TEXT NOT NULL,
    scrap_date DATE NOT NULL,
    scrap_time TIME NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT chk_scrap_entries_whole_hour
        CHECK (
            date_part('minute', scrap_time) = 0
            AND date_part('second', scrap_time) = 0
        )
);

CREATE INDEX IF NOT EXISTS idx_scrap_entries_station_date
ON public.scrap_entries(station_pair, scrap_date);
