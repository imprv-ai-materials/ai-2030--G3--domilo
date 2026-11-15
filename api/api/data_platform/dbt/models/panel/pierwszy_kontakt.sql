{{ config(materialized='table') }}
-- pierwszy_kontakt: kto i kiedy pierwszy skontaktował się z zapytaniem.
-- Ten sam filtr aktywności co `obsluzony` (leady_cel.sql, CTE kontakty): doradca (D..) albo call center (CC),
-- bez wyniku 'podpisanie', od utworzenia do utworzenia + 45 dni. Test pilnuje, że moment = obsluzony.pierwszy_kontakt.
-- Remis czasu rozstrzyga id_aktywnosci.
-- data_kolejki_kontaktu: kolejka obowiązująca w chwili kontaktu. Kolejka dnia D obowiązuje od godzina_kolejki (05:30)
-- czasu warszawskiego, więc kontakt przed 05:30 należy do kolejki z dnia poprzedniego. Liczymy na czasie lokalnym
-- (timezone('Europe/Warsaw', ...)), żeby zmiana czasu nie przesuwała granicy.
{% set godz, minuty = var('godzina_kolejki').split(':') %}
with kontakty as (
    select
        a.id_leada,
        a.id_aktywnosci,
        a.id_doradcy,
        a.data_czas
    from {{ source('domilo', 'crm_aktywnosci') }} as a
    join {{ ref('umowa_45d') }} as l using (id_leada)
    where a.id_doradcy is not null
      and a.wynik is distinct from 'podpisanie'
      and a.data_czas >= l.utworzono
      and a.data_czas <= l.utworzono + interval 45 day
    qualify row_number() over (partition by a.id_leada order by a.data_czas, a.id_aktywnosci) = 1
)

select
    id_leada,
    id_aktywnosci,
    id_doradcy as id_doradcy_kontaktu,
    id_doradcy = 'CC' as kontakt_cc,
    data_czas as pierwszy_kontakt,
    cast(
        timezone('Europe/Warsaw', data_czas) - to_hours({{ godz | int }}) - to_minutes({{ minuty | int }}) as date
    ) as data_kolejki_kontaktu
from kontakty
