ALTER TABLE public.employees
DROP CONSTRAINT IF EXISTS chk_employees_employee_number_length;

ALTER TABLE public.employees
ADD CONSTRAINT chk_employees_employee_number_length
CHECK (char_length(employee_number) <= 10)
NOT VALID;

ALTER TABLE public.employees
DROP CONSTRAINT IF EXISTS chk_employees_full_name_length;

ALTER TABLE public.employees
ADD CONSTRAINT chk_employees_full_name_length
CHECK (char_length(full_name) <= 50)
NOT VALID;
