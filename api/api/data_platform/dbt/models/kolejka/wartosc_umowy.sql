-- wartosc_umowy: wartość podpisanej umowy = czynsz × miesiące umowy × liczba lokali (pms_umowy).
--
-- Jeden wiersz = jedno podpisanie: umowa poza umową ramową albo cała umowa ramowa (B2B, kilka lokali).
-- W pms_umowy umowa ramowa ma po jednym wierszu na lokal, a każdy wiersz ma liczba_lokali = liczba lokali całej
-- ramowej. Wzór liczony na każdym wierszu policzyłby więc ramową N × N razy. Dlatego:
--   wartosc_umowy    = Σ po lokalach (czynsz × miesiące); przy równym czynszu i okresie lokali to dokładnie
--                      czynsz × miesiące × liczba_lokali, a gdy lokale ramowej różnią się czynszem, sumuje faktyczne;
--   wartosc_wg_wzoru = czynsz × miesiące × liczba_lokali umowy głównej (tej z zapytania CRM), do kontroli.
-- Miesiące umowy: pełne miesiące od data_od do data_do (włącznie) + reszta dni / 30,4375
--   (umowa roczna 2025-01-10 – 2026-01-09 = 12,0; dwuletnia = 24,0; średnioterminowa np. 92 dni ≈ 3,0).
-- Czynsz bez rabatu (rabat_mies) i bez indeksacji w umowach dwuletnich.
-- Tylko umowy z data_podpisania (rekordy importu sprzed 2023-03-01 jej nie mają).
-- z_zapytania: podpisanie powstało z zapytania CRM (crm_leady.id_umowy przez leady_cel). Przedłużenia
-- (typ 'przedłużenie') nigdy nie mają zapytania; nowa_umowa = typ inny niż przedłużenie.
with umowy as (
    select
        u.id_umowy,
        u.id_najmu,
        u.id_umowy_ramowej,
        coalesce(u.id_umowy_ramowej, u.id_umowy) as id_podpisania,
        u.typ,
        cast(u.data_podpisania as date) as data_podpisania,
        cast(u.data_od as date) as data_od,
        cast(u.data_do as date) as data_do,
        u.czynsz,
        u.liczba_lokali,
        n.linia,
        c.id_leada
    from {{ source('domilo', 'pms_umowy') }} as u
    join {{ source('domilo', 'pms_najmy') }} as n using (id_najmu)
    left join {{ ref('umowa_45d') }} as c on c.id_umowy = u.id_umowy
    where u.data_podpisania is not null
),

z_miesiacami as (
    select
        *,
        date_sub('month', data_od, data_do + 1) as pelne_miesiace
    from umowy
),

miesiace as (
    select
        *,
        pelne_miesiace
        + date_diff('day', cast(data_od + to_months(pelne_miesiace) as date), data_do + 1) / 30.4375
            as miesiace_umowy,
        row_number() over (
            partition by id_podpisania order by id_leada is null, id_umowy
        ) as nr_w_podpisaniu
    from z_miesiacami
),

glowna as (
    select * from miesiace where nr_w_podpisaniu = 1
),

podpisania as (
    select
        id_podpisania,
        count(*) as liczba_umow,
        count(distinct data_podpisania) as liczba_dni_podpisania,
        count(id_leada) as liczba_zapytan,
        min(data_od) as data_od,
        max(data_do) as data_do,
        sum(czynsz) as czynsz_mies_razem,
        sum(czynsz * miesiace_umowy) as wartosc_umowy
    from miesiace
    group by id_podpisania
)

select
    p.id_podpisania,
    g.id_umowy,
    g.id_umowy_ramowej,
    g.id_leada,
    g.id_leada is not null as z_zapytania,
    g.typ,
    g.typ <> 'przedłużenie' as nowa_umowa,
    g.linia,
    g.data_podpisania,
    p.liczba_dni_podpisania,
    p.liczba_zapytan,
    p.data_od,
    p.data_do,
    g.liczba_lokali,
    p.liczba_umow,
    g.czynsz,
    p.czynsz_mies_razem,
    g.miesiace_umowy,
    p.wartosc_umowy,
    g.czynsz * g.miesiace_umowy * g.liczba_lokali as wartosc_wg_wzoru
from podpisania as p
join glowna as g using (id_podpisania)
