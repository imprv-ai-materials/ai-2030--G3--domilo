-- przychod_na_godzine_doradcy: wartość umów podpisanych w okresie / godziny pracy doradców w tym okresie.
--
-- Jeden wiersz = okres zespołu: tydzień (poniedziałek–niedziela) albo kwartał kalendarzowy.
-- Licznik: Σ wartosc_umowy (model wartosc_umowy) podpisań z zapytań CRM (z_zapytania), według data_podpisania.
--   Kolumny *_nowe_wszystkie liczą także nowe umowy bez zapytania w CRM (bez przedłużeń), do porównania.
-- Mianownik: Σ crm_grafik.godziny_pracy wszystkich doradców (D01–D15) w okresie. Godzin call center (CC)
--   w crm_grafik nie ma, więc okresy z oknem migracji (zawiera_okno_migracji) mają zawyżony wynik.
-- pelny_okres: okres w całości w danych (od 2023-01-01 do ostatni_dzien_danych).
{% set okresy = [('tydzien', 'week'), ('kwartal', 'quarter')] %}
with godziny_dzien as (
    select
        cast(g.data as date) as dzien,
        g.id_doradcy,
        g.godziny_pracy
    from {{ source('domilo', 'crm_grafik') }} as g
    join {{ source('domilo', 'crm_doradcy') }} as d using (id_doradcy)
),

podpisania as (
    select * from {{ ref('wartosc_umowy') }} where nowa_umowa
),

{% for okres, czesc in okresy %}
godziny_{{ okres }} as (
    select
        cast(date_trunc('{{ czesc }}', dzien) as date) as poczatek_okresu,
        count(distinct dzien) as dni_pracy,
        count(distinct id_doradcy) as liczba_doradcow,
        sum(godziny_pracy) as godziny_doradcow
    from godziny_dzien
    group by 1
),

umowy_{{ okres }} as (
    select
        cast(date_trunc('{{ czesc }}', data_podpisania) as date) as poczatek_okresu,
        count(*) filter (where z_zapytania) as podpisania_z_zapytan,
        coalesce(sum(liczba_umow) filter (where z_zapytania), 0) as lokale_z_zapytan,
        coalesce(sum(wartosc_umowy) filter (where z_zapytania), 0) as wartosc_umow_z_zapytan,
        count(*) as podpisania_nowe_wszystkie,
        sum(wartosc_umowy) as wartosc_umow_nowe_wszystkie
    from podpisania
    group by 1
),

okres_{{ okres }} as (
    select
        '{{ okres }}' as okres,
        poczatek_okresu,
        cast(
            poczatek_okresu + {% if okres == 'tydzien' %}interval 7 day{% else %}interval 3 month{% endif %}
            - interval 1 day as date
        ) as koniec_okresu,
        coalesce(g.dni_pracy, 0) as dni_pracy,
        coalesce(g.liczba_doradcow, 0) as liczba_doradcow,
        coalesce(g.godziny_doradcow, 0) as godziny_doradcow,
        coalesce(u.podpisania_z_zapytan, 0) as podpisania_z_zapytan,
        coalesce(u.lokale_z_zapytan, 0) as lokale_z_zapytan,
        coalesce(u.wartosc_umow_z_zapytan, 0) as wartosc_umow_z_zapytan,
        coalesce(u.podpisania_nowe_wszystkie, 0) as podpisania_nowe_wszystkie,
        coalesce(u.wartosc_umow_nowe_wszystkie, 0) as wartosc_umow_nowe_wszystkie
    from godziny_{{ okres }} as g
    full outer join umowy_{{ okres }} as u using (poczatek_okresu)
){% if not loop.last %},{% endif %}

{% endfor %}

select
    okres,
    poczatek_okresu,
    koniec_okresu,
    poczatek_okresu >= date '2023-01-01'
        and koniec_okresu <= date '{{ var("ostatni_dzien_danych") }}' as pelny_okres,
    poczatek_okresu <= date '{{ var("okno_migracji_do") }}'
        and koniec_okresu >= date '{{ var("okno_migracji_od") }}' as zawiera_okno_migracji,
    dni_pracy,
    liczba_doradcow,
    godziny_doradcow,
    podpisania_z_zapytan,
    lokale_z_zapytan,
    wartosc_umow_z_zapytan,
    wartosc_umow_z_zapytan / nullif(godziny_doradcow, 0) as przychod_na_godzine_doradcy,
    podpisania_nowe_wszystkie,
    wartosc_umow_nowe_wszystkie,
    wartosc_umow_nowe_wszystkie / nullif(godziny_doradcow, 0) as przychod_na_godzine_nowe_wszystkie
from (
    {% for okres, czesc in okresy %}
    select * from okres_{{ okres }}
    {% if not loop.last %}union all{% endif %}
    {% endfor %}
)
