-- adopcja_dzien: czy doradcy zaczynają od góry swojej kolejki. Jeden wiersz = doradca × dzień kolejki.
--   pierwsze_kontakty: zapytania, z którymi ten doradca skontaktował się jako pierwszy w czasie obowiązywania kolejki
--     tego dnia (pierwszy_kontakt.data_kolejki_kontaktu);
--   z_top: z nich te, które były na pozycjach 1..top_adopcji (20) kolejki tego doradcy tego dnia;
--   adopcja = z_top / pierwsze_kontakty;
--   adopcja_losowa: odsetek, jakiego należałoby się spodziewać, gdyby doradca wybierał losowo spośród otwartych
--     zapytań swojego miasta (= min(top_adopcji, długość jego kolejki) / otwarte zapytania w mieście);
--   poza_rankingiem: pierwsze kontakty z zapytaniami spoza rankingu dnia (np. utworzonymi po 05:30).
-- dane_kontaktow = false: dzień po końcu danych (crm_aktywnosci kończy się ostatni_dzien_danych), metryki puste.
with ranking as (
    select * from {{ ref('ranking_dzien') }}
),

dni as (
    select
        data_kolejki,
        id_doradcy,
        any_value(miasto) as miasto,
        any_value(zrodlo_kolejki) as zrodlo_kolejki,
        count(*) as dlugosc_kolejki,
        any_value(otwarte_w_miescie) as otwarte_w_miescie
    from ranking
    where id_doradcy is not null
    group by data_kolejki, id_doradcy
),

kontakty as (
    select * from {{ ref('pierwszy_kontakt') }} where not kontakt_cc
)

select
    d.data_kolejki,
    d.id_doradcy,
    d.miasto,
    d.zrodlo_kolejki,
    d.dlugosc_kolejki,
    d.otwarte_w_miescie,
    d.data_kolejki <= date '{{ var("ostatni_dzien_danych") }}' as dane_kontaktow,
    count(k.id_leada) as pierwsze_kontakty,
    count(k.id_leada) filter (where r.top_adopcji and r.id_doradcy = d.id_doradcy) as z_top,
    count(k.id_leada) filter (where r.id_leada is null) as poza_rankingiem,
    count(k.id_leada) filter (where r.top_adopcji and r.id_doradcy = d.id_doradcy)
        / nullif(count(k.id_leada), 0) as adopcja,
    least({{ var('top_adopcji') }}, d.dlugosc_kolejki) / d.otwarte_w_miescie as adopcja_losowa
from dni as d
left join kontakty as k
    on k.id_doradcy_kontaktu = d.id_doradcy and k.data_kolejki_kontaktu = d.data_kolejki
left join ranking as r
    on r.data_kolejki = k.data_kolejki_kontaktu and r.id_leada = k.id_leada
group by all
