-- eksperyment_tydzien: tydzień eksperymentu switchback kolejki (docs/kolejka_eksperyment.md) z wariantem i metrykami.
-- Jeden wiersz = tydzień (poniedziałek–niedziela) z kolejką z dziennego zadania (kolejka_historia).
--   wariant: wariant kolejki w tygodniu; 'mieszany', gdy w tygodniu były dni z różnymi wariantami (tydzień nieważny);
--   metryka główna: przychod_z_kontaktow_na_godzine (przychod_z_kontaktow), ważna, gdy kompletny;
--   zmienne korekty: godziny_doradcow, nowe_zapytania_2tyg (ten i poprzedni tydzień);
--   metryki pomocnicze: adopcja (panel_tydzien) i konwersja górnego decyla (panel_tydzien);
--   przychod_na_godzine_doradcy (tydzień podpisania) tylko do wglądu: miesza warianty sąsiednich tygodni.
--   pozycje_losowe / pozycje: udział części losowej kolejki (5%).
with dni as (
    select
        cast(date_trunc('week', data_kolejki) as date) as tydzien,
        count(distinct data_kolejki) as dni_kolejki,
        count(distinct wariant) as warianty,
        any_value(wariant) as wariant_dnia,
        count(*) as pozycje,
        count(*) filter (where losowa) as pozycje_losowe
    from {{ source('domilo', 'kolejka_historia') }}
    group by 1
)

select
    d.tydzien,
    case when d.warianty = 1 then d.wariant_dnia else 'mieszany' end as wariant,
    d.dni_kolejki,
    d.pozycje,
    d.pozycje_losowe,
    k.kompletny,
    k.godziny_doradcow,
    k.nowe_zapytania + k.nowe_zapytania_poprzedni_tydzien as nowe_zapytania_2tyg,
    k.pierwsze_kontakty,
    k.umowy,
    k.przychod_z_kontaktow_na_godzine,
    p.adopcja,
    p.adopcja_losowa,
    p.zapytania_decyl,
    p.konwersja_decyl,
    p.przychod_na_godzine_doradcy
from dni as d
left join {{ ref('przychod_z_kontaktow') }} as k using (tydzien)
left join {{ ref('panel_tydzien') }} as p using (tydzien)
