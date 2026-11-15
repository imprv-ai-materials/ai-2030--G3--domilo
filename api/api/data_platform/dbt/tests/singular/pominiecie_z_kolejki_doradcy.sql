-- Pominąć można tylko pozycję z kolejki tego doradcy tego dnia, z tą samą pozycją.
select s.*
from {{ source('domilo', 'kolejka_pominiecia') }} as s
left join {{ ref('ranking_dzien') }} as r using (data_kolejki, id_leada)
where r.id_leada is null or r.id_doradcy is distinct from s.id_doradcy or r.pozycja is distinct from s.pozycja
