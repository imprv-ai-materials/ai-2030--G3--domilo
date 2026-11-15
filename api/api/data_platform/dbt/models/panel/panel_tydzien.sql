-- panel_tydzien: metryki panelu kierownika zespołu najmu tydzień po tygodniu (poniedziałek–niedziela).
-- Jeden wiersz = tydzień z przychodem (przychod_na_godzine_doradcy) albo z kolejką (ranking_dzien).
--   adopcja: Σ z_top / Σ pierwsze_kontakty z adopcja_dzien (dni z danymi kontaktów); adopcja_losowa: średnia ważona
--     pierwszymi kontaktami;
--   górny decyl: zapytania `nowe` i niecenzurowane z kolejka_zapytania według tygodnia pierwszej kolejki:
--     konwersja = średnia umowa_45d, mediana godzin od utworzenia do pierwszego kontaktu (tylko obsłużone),
--     bez_kontaktu = odsetek bez kontaktu w 45 dni; to samo dla zapytań spoza górnego decyla (porównanie);
--   pominięcia: liczba według powodu (pominiecia);
--   przychód na godzinę doradcy (tydzień) i wartość wyjściowa = wynik kwartału kwartal_wyjsciowy (2026-Q2).
-- zrodlo_kolejki: 'symulacja_wstecz', 'zadanie' albo oba (po przecinku); NULL = tydzień bez kolejki.
with adopcja as (
    select
        cast(date_trunc('week', data_kolejki) as date) as tydzien,
        sum(pierwsze_kontakty) as pierwsze_kontakty,
        sum(z_top) as pierwsze_kontakty_z_top,
        sum(poza_rankingiem) as pierwsze_kontakty_poza_rankingiem,
        sum(z_top) / nullif(sum(pierwsze_kontakty), 0) as adopcja,
        sum(adopcja_losowa * pierwsze_kontakty) / nullif(sum(pierwsze_kontakty), 0) as adopcja_losowa
    from {{ ref('adopcja_dzien') }}
    where dane_kontaktow
    group by 1
),

kohorta as (
    select * from {{ ref('kolejka_zapytania') }} where nowe and not cenzurowany
),

decyl as (
    select
        tydzien,
        count(*) filter (where gorny_decyl) as zapytania_decyl,
        sum(umowa_45d) filter (where gorny_decyl) as umowy_decyl,
        avg(umowa_45d) filter (where gorny_decyl) as konwersja_decyl,
        median(godz_do_pierwszego_kontaktu) filter (where gorny_decyl and obsluzony) as mediana_godz_kontaktu_decyl,
        avg(case when obsluzony then 0.0 else 1.0 end) filter (where gorny_decyl) as bez_kontaktu_decyl,
        count(*) filter (where not gorny_decyl) as zapytania_poza_decylem,
        avg(umowa_45d) filter (where not gorny_decyl) as konwersja_poza_decylem,
        median(godz_do_pierwszego_kontaktu) filter (where not gorny_decyl and obsluzony)
            as mediana_godz_kontaktu_poza_decylem
    from kohorta
    group by tydzien
),

kolejki as (
    select
        cast(date_trunc('week', data_kolejki) as date) as tydzien,
        string_agg(distinct zrodlo_kolejki, ',' order by zrodlo_kolejki) as zrodlo_kolejki,
        count(distinct data_kolejki) as dni_kolejki
    from {{ ref('ranking_dzien') }}
    group by 1
),

pominiecia as (
    select
        tydzien,
        count(*) as pominiecia,
        count(*) filter (where powod = 'znam_klienta') as pominiecia_znam_klienta,
        count(*) filter (where powod = 'brak_lokalu') as pominiecia_brak_lokalu,
        count(*) filter (where powod = 'duplikat') as pominiecia_duplikat,
        count(*) filter (where powod = 'inne') as pominiecia_inne
    from {{ ref('pominiecia') }}
    group by tydzien
),

przychod as (
    select
        poczatek_okresu as tydzien,
        pelny_okres as pelny_tydzien_przychodu,
        podpisania_z_zapytan,
        godziny_doradcow,
        wartosc_umow_z_zapytan,
        przychod_na_godzine_doradcy
    from {{ ref('przychod_na_godzine_doradcy') }}
    where okres = 'tydzien'
),

wyjsciowa as (
    select przychod_na_godzine_doradcy as przychod_wartosc_wyjsciowa
    from {{ ref('przychod_na_godzine_doradcy') }}
    where okres = 'kwartal' and poczatek_okresu = date '{{ var("kwartal_wyjsciowy") }}'
),

tygodnie as (
    select tydzien from przychod
    union
    select tydzien from kolejki
)

select
    t.tydzien,
    cast(t.tydzien + interval 6 day as date) as koniec_tygodnia,
    k.zrodlo_kolejki,
    coalesce(k.dni_kolejki, 0) as dni_kolejki,
    a.pierwsze_kontakty,
    a.pierwsze_kontakty_z_top,
    a.pierwsze_kontakty_poza_rankingiem,
    a.adopcja,
    a.adopcja_losowa,
    d.zapytania_decyl,
    d.umowy_decyl,
    d.konwersja_decyl,
    d.mediana_godz_kontaktu_decyl,
    d.bez_kontaktu_decyl,
    d.zapytania_poza_decylem,
    d.konwersja_poza_decylem,
    d.mediana_godz_kontaktu_poza_decylem,
    coalesce(s.pominiecia, 0) as pominiecia,
    coalesce(s.pominiecia_znam_klienta, 0) as pominiecia_znam_klienta,
    coalesce(s.pominiecia_brak_lokalu, 0) as pominiecia_brak_lokalu,
    coalesce(s.pominiecia_duplikat, 0) as pominiecia_duplikat,
    coalesce(s.pominiecia_inne, 0) as pominiecia_inne,
    p.pelny_tydzien_przychodu,
    p.podpisania_z_zapytan,
    p.godziny_doradcow,
    p.wartosc_umow_z_zapytan,
    p.przychod_na_godzine_doradcy,
    w.przychod_wartosc_wyjsciowa
from tygodnie as t
cross join wyjsciowa as w
left join kolejki as k using (tydzien)
left join adopcja as a using (tydzien)
left join decyl as d using (tydzien)
left join pominiecia as s using (tydzien)
left join przychod as p using (tydzien)
