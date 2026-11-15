-- Każda umowa zapytania z umowa_45d jest podpisaniem z zapytania w wartosc_umowy, a podpisania z zapytania
-- to tylko nowe umowy (nigdy przedłużenia).
select c.id_leada, c.id_umowy, w.id_podpisania, w.nowa_umowa
from {{ ref('umowa_45d') }} as c
left join {{ ref('wartosc_umowy') }} as w on w.id_leada = c.id_leada and w.id_umowy = c.id_umowy
where c.id_umowy is not null
  and (w.id_podpisania is null or not w.nowa_umowa)
