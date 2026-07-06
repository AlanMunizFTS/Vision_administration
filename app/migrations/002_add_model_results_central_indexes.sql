-- Indexes used by reports.py filters, grouping and ordering.

CREATE INDEX IF NOT EXISTS model_results_central_source_station_idx
    ON public.model_results_central (source_station);

CREATE INDEX IF NOT EXISTS model_results_central_class_name_idx
    ON public.model_results_central (class_name);

CREATE INDEX IF NOT EXISTS model_results_central_created_at_idx
    ON public.model_results_central (created_at);

CREATE INDEX IF NOT EXISTS model_results_central_jsn_idx
    ON public.model_results_central (jsn);

CREATE INDEX IF NOT EXISTS model_results_central_station_date_idx
    ON public.model_results_central (source_station, created_at);

CREATE INDEX IF NOT EXISTS model_results_central_station_jsn_idx
    ON public.model_results_central (source_station, jsn);

CREATE UNIQUE INDEX IF NOT EXISTS model_results_central_unique_record_idx
    ON public.model_results_central (source_station, img_name, class_name, created_at);
