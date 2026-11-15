-- Każda kolejka doradcy ma int(5% × długość + 0,5) pozycji losowych (40 pozycji -> 2), a p_losowania jest takie samo
-- dla wszystkich pozycji miasta w danym dniu.
with kolejki as (
    select data_kolejki, id_doradcy, count(*) as dlugosc, count(*) filter (where losowa) as losowe
    from {{ source('domilo', 'kolejka_historia') }}
    group by all
),

miasta as (
    select data_kolejki, miasto, count(distinct p_losowania) as rozne_p
    from {{ source('domilo', 'kolejka_historia') }}
    group by all
)

select data_kolejki, id_doradcy as klucz, 'liczba losowych' as problem
from kolejki where losowe <> cast(floor(0.05 * dlugosc + 0.5) as integer)
union all
select data_kolejki, miasto, 'rozne p_losowania' from miasta where rozne_p > 1
