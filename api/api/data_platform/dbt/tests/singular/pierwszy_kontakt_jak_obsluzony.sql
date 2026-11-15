-- pierwszy_kontakt liczy to samo co obsluzony (leady_cel.sql): te same zapytania i ten sam moment pierwszego kontaktu.
select coalesce(k.id_leada, o.id_leada) as id_leada, k.pierwszy_kontakt, o.pierwszy_kontakt as z_obsluzony
from {{ ref('pierwszy_kontakt') }} as k
full outer join (select * from {{ ref('obsluzony') }} where obsluzony) as o using (id_leada)
where k.id_leada is null or o.id_leada is null or k.pierwszy_kontakt <> o.pierwszy_kontakt
