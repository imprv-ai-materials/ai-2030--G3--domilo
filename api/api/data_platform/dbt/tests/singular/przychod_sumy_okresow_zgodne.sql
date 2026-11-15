-- Tygodnie i kwartały dzielą ten sam licznik i mianownik: ich sumy są równe sumom z modeli źródłowych.
with okresy as (
    select
        okres,
        sum(wartosc_umow_z_zapytan) as wartosc,
        sum(godziny_doradcow) as godziny
    from {{ ref('przychod_na_godzine_doradcy') }}
    group by okres
),

wzorzec as (
    select
        (select sum(wartosc_umowy) from {{ ref('wartosc_umowy') }} where z_zapytania) as wartosc,
        (select sum(godziny_pracy) from {{ source('domilo', 'crm_grafik') }}) as godziny
)

select o.okres, o.wartosc, w.wartosc as wartosc_wzorzec, o.godziny, w.godziny as godziny_wzorzec
from okresy as o
cross join wzorzec as w
where abs(o.wartosc - w.wartosc) > 0.01 or abs(o.godziny - w.godziny) > 0.01
