-- pominiecia: pominięcia pozycji kolejki z powodem (CRM -> POST /leads/skips -> kolejka_pominiecia) z miejscem
-- zapytania w rankingu dnia. Jeden wiersz = pominięta pozycja (data_kolejki, id_leada).
select
    s.data_kolejki,
    cast(date_trunc('week', s.data_kolejki) as date) as tydzien,
    s.id_leada,
    s.id_doradcy,
    s.pozycja,
    s.powod,
    s.komentarz,
    s.zgloszono,
    s.zmieniono,
    r.miasto,
    r.ranga,
    r.gorny_decyl,
    r.zrodlo_kolejki,
    r.ev_pln
from {{ source('domilo', 'kolejka_pominiecia') }} as s
left join {{ ref('ranking_dzien') }} as r using (data_kolejki, id_leada)
