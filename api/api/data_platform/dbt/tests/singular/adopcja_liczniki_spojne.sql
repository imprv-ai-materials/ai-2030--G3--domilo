-- Liczniki adopcji: z top <= pierwsze kontakty, a suma pierwszych kontaktów dni z danymi = liczba pierwszych kontaktów
-- doradców (bez CC) w czasie obowiązywania tych kolejek. Brak zgubionych i podwójnie liczonych kontaktów.
with dni as (
    select data_kolejki, id_doradcy from {{ ref('adopcja_dzien') }} where dane_kontaktow
),

oczekiwane as (
    select count(*) as n
    from {{ ref('pierwszy_kontakt') }} as k
    join dni as d on d.data_kolejki = k.data_kolejki_kontaktu and d.id_doradcy = k.id_doradcy_kontaktu
    where not k.kontakt_cc
),

policzone as (
    select sum(pierwsze_kontakty) as n, count(*) filter (where z_top > pierwsze_kontakty) as zle
    from {{ ref('adopcja_dzien') }}
    where dane_kontaktow
)

select o.n as oczekiwane, p.n as policzone, p.zle
from oczekiwane as o, policzone as p
where coalesce(o.n, 0) <> coalesce(p.n, 0) or p.zle > 0
