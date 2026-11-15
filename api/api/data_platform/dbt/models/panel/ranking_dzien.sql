-- ranking_dzien: ranking kolejki z jednego dnia z flagami metryk panelu kierownika (docs/kolejka_panel.md).
-- Jeden wiersz = otwarte zapytanie w dniu kolejki (source kolejka_ranking, klucz data_kolejki + id_leada).
--   gorny_decyl: ranga w mieście <= ceil(udzial_gornego_decyla × liczba otwartych zapytań w mieście tego dnia);
--   top_adopcji: zapytanie na pozycjach 1..top_adopcji kolejki swojego doradcy.
-- zrodlo_kolejki: 'zadanie' (kolejka poszła do CRM) albo 'symulacja_wstecz' (doradcy jej nie widzieli).
select
    data_kolejki,
    id_leada,
    miasto,
    ranga,
    otwarte_w_miescie,
    p,
    ev_pln,
    id_doradcy,
    pozycja,
    zrodlo_kolejki,
    wersja_modelu,
    ranga <= ceil({{ var('udzial_gornego_decyla') }} * otwarte_w_miescie) as gorny_decyl,
    coalesce(pozycja <= {{ var('top_adopcji') }}, false) as top_adopcji
from {{ source('domilo', 'kolejka_ranking') }}
