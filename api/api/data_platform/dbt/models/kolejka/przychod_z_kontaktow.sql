-- przychod_z_kontaktow: przychód przypisany do tygodnia, w którym doradcy pierwszy raz skontaktowali się z zapytaniem.
-- Metryka główna eksperymentu kolejki (docs/kolejka_eksperyment.md). Jeden wiersz = tydzień (poniedziałek–niedziela).
--
-- Dlaczego nie tydzień podpisania (przychod_na_godzine_doradcy): kolejka decyduje, z kim doradca kontaktuje się
-- najpierw, a umowa przychodzi później (w tygodniu kontaktu podpisuje się ok. 30% wartości). Przy zmianie wariantu co
-- tydzień przychód tygodnia podpisania mierzyłby głównie pracę z poprzednich tygodni, czyli inny wariant.
--
-- Licznik: Σ wartości podpisań (wartosc_umowy) z zapytań, z którymi pierwszy kontakt doradcy (pierwszy_kontakt, bez
--   call center) nastąpił w kolejce tego tygodnia (data_kolejki_kontaktu, od poniedziałku 05:30). Wartość jednej
--   umowy ograniczona do limit_wartosci_umowy (95. percentyl; brak umowy = 0, bo least() w DuckDB pomija NULL), żeby kilka dużych umów ramowych nie decydowało o wyniku;
--   wartosc_umow_bez_limitu do porównania.
-- Mianownik: godziny doradców z crm_grafik w tym tygodniu (jak przychod_na_godzine_doradcy).
-- Zmienne do korekty (znane bez względu na wariant): godziny doradców i nowe zapytania w tym i poprzednim tygodniu.
-- kompletny: umowy z kontaktów tygodnia mogły już przyjść (koniec tygodnia + 45 dni <= ostatni dzień danych).
with kontakty as (
    select
        cast(date_trunc('week', k.data_kolejki_kontaktu) as date) as tydzien,
        k.id_leada,
        w.id_podpisania,
        w.liczba_umow,
        w.wartosc_umowy
    from {{ ref('pierwszy_kontakt') }} as k
    left join {{ ref('wartosc_umowy') }} as w on w.id_leada = k.id_leada
    where not k.kontakt_cc
),

tygodnie_kontaktow as (
    select
        tydzien,
        count(*) as pierwsze_kontakty,
        count(id_podpisania) as umowy,
        coalesce(sum(liczba_umow), 0) as lokale,
        coalesce(sum(wartosc_umowy), 0) as wartosc_umow_bez_limitu,
        coalesce(sum(least(coalesce(wartosc_umowy, 0), {{ var('limit_wartosci_umowy') }})), 0) as wartosc_umow
    from kontakty
    group by tydzien
),

godziny as (
    select poczatek_okresu as tydzien, pelny_okres, godziny_doradcow
    from {{ ref('przychod_na_godzine_doradcy') }}
    where okres = 'tydzien'
),

naplyw as (
    select cast(date_trunc('week', utworzono) as date) as tydzien, count(*) as nowe_zapytania
    from {{ ref('umowa_45d') }}
    group by 1
)

select
    g.tydzien,
    g.pelny_okres,
    cast(g.tydzien + interval 6 day as date) + interval 45 day <= date '{{ var("ostatni_dzien_danych") }}' as kompletny,
    g.godziny_doradcow,
    coalesce(n0.nowe_zapytania, 0) as nowe_zapytania,
    coalesce(n1.nowe_zapytania, 0) as nowe_zapytania_poprzedni_tydzien,
    coalesce(k.pierwsze_kontakty, 0) as pierwsze_kontakty,
    coalesce(k.umowy, 0) as umowy,
    coalesce(k.lokale, 0) as lokale,
    coalesce(k.wartosc_umow, 0) as wartosc_umow,
    coalesce(k.wartosc_umow_bez_limitu, 0) as wartosc_umow_bez_limitu,
    coalesce(k.wartosc_umow, 0) / nullif(g.godziny_doradcow, 0) as przychod_z_kontaktow_na_godzine,
    coalesce(k.wartosc_umow_bez_limitu, 0) / nullif(g.godziny_doradcow, 0) as przychod_z_kontaktow_bez_limitu_na_godzine,
    coalesce(k.umowy, 0) / nullif(g.godziny_doradcow, 0) as umowy_z_kontaktow_na_godzine
from godziny as g
left join tygodnie_kontaktow as k using (tydzien)
left join naplyw as n0 on n0.tydzien = g.tydzien
left join naplyw as n1 on n1.tydzien = g.tydzien - interval 7 day
