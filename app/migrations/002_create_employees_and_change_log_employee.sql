CREATE TABLE IF NOT EXISTS public.employees (
    id SERIAL PRIMARY KEY,
    employee_number TEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_employees_number ON public.employees(employee_number);

CREATE TABLE IF NOT EXISTS public.change_log_entries (
    id SERIAL PRIMARY KEY,
    station_pair TEXT NOT NULL,
    side TEXT NOT NULL DEFAULT 'both',
    change_date DATE NOT NULL,
    change_time TIME,
    employee_id INTEGER,
    category TEXT NOT NULL DEFAULT 'Other',
    label TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

ALTER TABLE public.change_log_entries
ADD COLUMN IF NOT EXISTS employee_id INTEGER;

CREATE INDEX IF NOT EXISTS idx_change_log_employee ON public.change_log_entries(employee_id);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_change_log_employee'
          AND conrelid = 'public.change_log_entries'::regclass
    ) THEN
        ALTER TABLE public.change_log_entries
        ADD CONSTRAINT fk_change_log_employee
        FOREIGN KEY (employee_id) REFERENCES public.employees(id);
    END IF;
END $$;
