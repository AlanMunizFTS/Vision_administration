ALTER TABLE public.change_log_entries
DROP CONSTRAINT IF EXISTS fk_change_log_employee;

UPDATE public.change_log_entries
SET employee_id = NULL
WHERE employee_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM public.employees
      WHERE public.employees.id = public.change_log_entries.employee_id
  );

ALTER TABLE public.change_log_entries
ADD CONSTRAINT fk_change_log_employee
FOREIGN KEY (employee_id) REFERENCES public.employees(id)
ON DELETE SET NULL;
