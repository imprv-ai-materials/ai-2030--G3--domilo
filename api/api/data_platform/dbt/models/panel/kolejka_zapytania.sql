-- kolejka_zapytania: każde zapytanie z rankingu z jego pierwszym dniem w kolejce i wynikiem. Jeden wiersz = zapytanie.
-- Pierwszy dzień = najwcześniejszy dzień rankingu; tam liczymy rangę i górny decyl (ranking_dzien.gorny_decyl).
-- nowe = pierwszy dzień rankingu to pierwsza kolejka po utworzeniu zapytania (kolejka z 05:30 następnego dnia, a dla
--   zapytań sprzed 05:30 z tego samego dnia). Zapytania otwarte już w pierwszym dniu okna symulacji mają nowe = false:
--   ich pierwszy dzień rankingu nie jest pierwszym dniem po utworzeniu, więc nie wchodzą do metryk kohorty.
-- Wynik: umowa_45d i cenzurowany (umowa_45d), obsluzony i godz_do_pierwszego_kontaktu od utworzenia (obsluzony).
{% set godz, minuty = var('godzina_kolejki').split(':') %}
with pierwsze as (
    select *
    from {{ ref('ranking_dzien') }}
    qualify row_number() over (partition by id_leada order by data_kolejki) = 1
)

select
    p.id_leada,
    p.data_kolejki as pierwsza_kolejka,
    cast(date_trunc('week', p.data_kolejki) as date) as tydzien,
    p.miasto,
    p.ranga,
    p.otwarte_w_miescie,
    p.gorny_decyl,
    p.top_adopcji,
    p.id_doradcy,
    p.pozycja,
    p.zrodlo_kolejki,
    p.p,
    p.ev_pln,
    c.utworzono,
    p.data_kolejki = cast(
        timezone('Europe/Warsaw', c.utworzono) - to_hours({{ godz | int }}) - to_minutes({{ minuty | int }}) as date
    ) + 1 as nowe,
    c.cenzurowany,
    c.umowa_45d,
    o.obsluzony,
    o.godz_do_pierwszego_kontaktu
from pierwsze as p
join {{ ref('umowa_45d') }} as c using (id_leada)
join {{ ref('obsluzony') }} as o using (id_leada)
