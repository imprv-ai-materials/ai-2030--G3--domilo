# Punkt pracy alarmów wind: 3 alarmy w poniedziałek (v2b_lgbm_czas_winda, okres testowy 2026)

Stan: 2026-11-16, baza `domilo.duckdb` (eksport 2026-09-30). Model `v2b_lgbm_czas_winda` (zapisany
`model.joblib`, bez douczania; [porownanie.md](../api/api/ai/failure_model/evals/porownanie.md)), okres testowy
2026-01-01 – 2026-09-22, czyli 38 poniedziałków od 2026-01-05 do 2026-09-21. Reguła:
`api/api/contexts_boundaries/maintenance_bc/alarmy_wind.py`, stałe od użytkownika: `maintenance_bc/zalozenia.yaml`.

## Wnioski

1. Przy 3 alarmach w tygodniu (114 alarmów w 38 tygodni) po 56 alarmach (49,1%) winda faktycznie zepsuła się
   w ciągu 7 dni. Przy losowym wyborze wind trafnych byłoby średnio 6,0%, więc technik wysłany na alarm co drugi raz
   znajdzie windę tuż przed awarią.
2. Alarm poprzedził jednak tylko 57 z 322 awarii (17,7%), a wśród awarii, które czujniki mogą zapowiedzieć
   (drzwi, napęd, hamulec/liny, sterownik) 52 z 216 (24,1%). Nawet ranking znający przyszłość przy 3 alarmach
   tygodniowo uprzedziłby 115 awarii (35,7%): przy tym limicie głównym ograniczeniem jest liczba alarmów,
   nie tylko model.
3. Prosta reguła „drzwi częściej otwierają się ponownie niż zwykle” daje 50 trafnych alarmów, model 56. Różnica
   (precyzja +5,3 pp, 95% CI −1,8 … +12,3 pp) jest w granicach przypadku, więc w tym punkcie pracy **nie możemy
   powiedzieć, że model jest lepszy od reguły**. Działają inaczej: reguła łapie więcej awarii drzwi (43 wobec 34),
   model łapie awarie napędu (12 wobec 0) i hamulca/lin (4 wobec 0). Tylko dla awarii z sygnałem przewaga
   modelu jest na granicy (czułość +3,7 pp, 95% CI +0,0 … +7,8 pp).
4. Alarm wyprzedza start awarii o medianę 85 godzin (ok. 3,5 dnia); 10 z 56 trafnych alarmów ma najwyżej dobę
   zapasu. Na windach, których model nie widział w treningu, trafnych jest 11 z 34 alarmów.
5. Wyniki skaczą z tygodnia na tydzień: 5 tygodni bez żadnego trafnego alarmu, 3 tygodnie z trzema. Przerwa 7 dni
   kosztuje 5 trafnych alarmów (bez niej 61), ale rozkłada alarmy na 69 wind zamiast 59.

## Definicje i decyzje

- **Alarm:** w każdy poniedziałek okresu testowego o 06:00 Europe/Warsaw ranking wszystkich wind, które mają ten
  dzień w `dni_wind` (winda stojąca o 06:00 z powodu awarii nie ma wiersza i nie dostaje alarmu). Alarm dostają
  3 windy o najwyższym ryzyku `v2b_lgbm_czas_winda` (remis: `id_windy` rosnąco).
- **Przerwa (interpretacja, do potwierdzenia):** winda z alarmem w dniu t nie dostaje alarmu w dniach t+1 … t+7,
  więc nie dostanie go w następny poniedziałek (najwcześniej po 14 dniach). Odczytanie „odstęp ≥ 7 dni” przy alarmach
  co 7 dni niczego nie blokuje; jego wynik to wiersz „model bez przerwy” w T1.
- **Trafny alarm:** start awarii tej windy (`awarie_odtworzone`, start jak w `dni_wind`) w (06:00 t; 06:00 t+7].
  To dokładnie `dni_wind.awaria_7d` dnia alarmu; skrypt sprawdza zgodność dla każdego alarmu.
- **Precyzja** = trafne alarmy / alarmy. **Czułość** liczona na awariach (nie na dniach): awarie ze startem
  w (2026-01-05 06:00; 2026-09-28 06:00], czyli w oknach 38 poniedziałków; awaria jest złapana, gdy jej start wypada
  w oknie alarmu tej samej windy. Awarie z 2026-01-01 – 2026-01-05 06:00 są poza zakresem (żaden poniedziałek ich nie
  obejmuje). W mianowniku są też awarie wind, które w poniedziałek stały i nie mogły dostać alarmu.
- **Awarie z sygnałem:** `podzespol` ∈ {drzwi, naped, hamulec_liny, sterownik}; bez `zewnetrzna` (zalanie, burza,
  wandalizm) i `brak` (notatka bez przyczyny).
- **Wyprzedzenie:** godziny od alarmu (06:00) do startu pierwszej awarii w oknie, dla trafnych alarmów
  (= `dni_wind.godziny_do_startu`).
- **Baseline:** ta sama reguła (3 windy, poniedziałek, przerwa 7 dni) na rankingu
  `drzwi_ponowne_otwarcia_do_normy_24h` (ta sama reguła co w [evals/porownanie.md](../evals/porownanie.md); brak
  pomiaru = najniższa pozycja). Dodatkowo ranking losowy (1 000 symulacji) i „wyrocznia” (ranking = `awaria_7d`,
  wiedza o przyszłości) jako górna granica przy 3 alarmach tygodniowo.
- **95% CI:** bootstrap tygodni (10 000 losowań 38 tygodni ze zwracaniem, te same dla modelu i baseline). Tygodnie
  nie są całkiem niezależne (przerwa łączy sąsiednie tygodnie), więc przedziały są przybliżone.

## Tabele

Kontrola: PR-AUC wczytanego modelu na całym teście 0,3522 (jak w `metryki.json`); 5 286 wierszy `dni_wind`
w poniedziałki testu (318 z `awaria_7d = 1`); 322 awarie w zakresie, w tym 216 z sygnałem (to samo zwraca zapytanie
SQL w części „SQL i kod”).

### T1. Wynik reguły alarmu: model, baseline i punkty odniesienia

Przedziały w nawiasach: 95% CI z bootstrapu tygodni (model i baseline). „Złapane” może być większe od „trafne”, gdy w oknie jednego alarmu zaczęły się dwie awarie tej windy.

| ranking ryzyka | alarmy | trafne | precyzja | awarie | złapane | czułość | awarie z sygnałem | złapane z sygnałem | czułość z sygnałem | mediana wyprzedzenia (h) | różne windy z alarmem |
|---|---:|---:|---|---:|---:|---|---:|---:|---|---:|---:|
| **model v2b_lgbm_czas_winda** | 114 | 56 | 49,1% (40,4% … 57,9%) | 322 | 57 | 17,7% (14,2% … 21,6%) | 216 | 52 | 24,1% (19,5% … 28,8%) | 85,1 | 69 |
| baseline: reguła `drzwi_ponowne_otwarcia_do_normy_24h` | 114 | 50 | 43,9% (34,2% … 53,5%) | 322 | 51 | 15,8% (12,2% … 19,9%) | 216 | 44 | 20,4% (15,5% … 25,2%) | 82,5 | 77 |
| model bez przerwy (`przerwa_dni = 0`) | 114 | 61 | 53,5% | 322 | 62 | 19,3% | 216 | 56 | 25,9% | 81,5 | 59 |
| wyrocznia (zna `awaria_7d`) | 114 | 114 | 100,0% | 322 | 115 | 35,7% | 216 | 84 | 38,9% | 88,9 | 61 |
| losowo (średnia z 1000; 2,5–97,5 percentyl) | 114 | 6,9 | 6,0% (2,6% … 10,5%) | 322 | 6,9 | 2,1% (0,9% … 3,7%) | 216 | 4,7 | 2,2% (0,5% … 4,2%) | 77,8 | — |

### T2. Model − baseline (te same losowania tygodni)

| miara | model | baseline | model − baseline | 95% CI różnicy |
|---|---|---|---|---|
| precyzja | 49,1% | 43,9% | +5,3 pp | −1,8 pp … +12,3 pp |
| czułość (wszystkie awarie) | 17,7% | 15,8% | +1,9 pp | −0,6 pp … +4,5 pp |
| czułość (awarie z sygnałem) | 24,1% | 20,4% | +3,7 pp | +0,0 pp … +7,8 pp |

### T3. Tydzień po tygodniu

„trafne” = trafne alarmy / alarmy; „awarie” = awarie wszystkich 140 wind ze startem w oknie tygodnia (06:00 pon.; 06:00 następnego pon.]. Tydzień 2026-07-20: 26 awarii, w tym 17 z przyczyną zewnętrzną (zapytanie niżej).

| tydzień (pon. 06:00) | alarmy modelu (✓ trafny: godziny do startu, podzespół) | trafne | awarie | złapane | z sygnałem | złapane z sygnałem | trafne reguły | złapane reguły |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 2026-01-05 | B23-W1 ✓ 30 h, drzwi; B25-W1 ✗; B10-W1 ✓ 96 h, naped | 2 / 3 | 7 | 2 | 6 | 2 | 1 / 3 | 1 |
| 2026-01-12 | B24-W2 ✓ 7 h, drzwi; B29-W1 ✓ 127 h, drzwi; B14-W3 ✗ | 2 / 3 | 5 | 2 | 4 | 2 | 2 / 3 | 2 |
| 2026-01-19 | B08-W4 ✓ 99 h, naped; B05-W4 ✓ 128 h, drzwi; B05-W3 ✓ 122 h, drzwi | 3 / 3 | 8 | 3 | 5 | 3 | 1 / 3 | 1 |
| 2026-01-26 | B23-W4 ✗; B38-W1 ✗; B19-W4 ✓ 95 h, naped | 1 / 3 | 7 | 1 | 6 | 1 | 0 / 3 | 0 |
| 2026-02-02 | B16-W2 ✓ 58 h, brak; B06-W4 ✗; B09-W2 ✓ 90 h, naped | 2 / 3 | 4 | 2 | 2 | 1 | 1 / 3 | 1 |
| 2026-02-09 | B19-W1 ✗; B25-W1 ✗; B04-W2 ✗ | 0 / 3 | 10 | 0 | 6 | 0 | 0 / 3 | 0 |
| 2026-02-16 | B06-W1 ✓ 11 h, drzwi; B18-W1 ✗; B05-W2 ✗ | 1 / 3 | 6 | 1 | 4 | 1 | 0 / 3 | 0 |
| 2026-02-23 | B10-W2 ✗; B29-W3 ✗; B12-W1 ✗ | 0 / 3 | 6 | 0 | 5 | 0 | 0 / 3 | 0 |
| 2026-03-02 | B07-W3 ✓ 151 h, drzwi; B20-W3 ✗; B31-W3 ✓ 28 h, naped | 2 / 3 | 9 | 2 | 8 | 2 | 3 / 3 | 3 |
| 2026-03-09 | B31-W1 ✗; B02-W1 ✓ 69 h, hamulec_liny; B25-W1 ✗ | 1 / 3 | 7 | 1 | 7 | 1 | 2 / 3 | 2 |
| 2026-03-16 | B32-W3 ✓ 148 h, drzwi; B26-W3 ✓ 33 h, drzwi; B10-W1 ✓ 56 h, naped | 3 / 3 | 8 | 3 | 5 | 3 | 3 / 3 | 3 |
| 2026-03-23 | B18-W1 ✗; B30-W2 ✗; B13-W3 ✗ | 0 / 3 | 6 | 0 | 3 | 0 | 0 / 3 | 0 |
| 2026-03-30 | B27-W1 ✓ 152 h, brak; B22-W2 ✗; B37-W3 ✓ 72 h, drzwi | 2 / 3 | 9 | 2 | 6 | 1 | 2 / 3 | 2 |
| 2026-04-06 | B14-W1 ✓ 108 h, drzwi; B05-W4 ✗; B12-W1 ✗ | 1 / 3 | 6 | 1 | 6 | 1 | 1 / 3 | 1 |
| 2026-04-13 | B29-W4 ✗; B38-W4 ✓ 84 h, drzwi; B15-W1 ✓ 4 h, sterownik | 2 / 3 | 8 | 2 | 8 | 2 | 1 / 3 | 1 |
| 2026-04-20 | B26-W3 ✓ 148 h, drzwi; B01-W3 ✓ 80 h, drzwi; B06-W4 ✗ | 2 / 3 | 8 | 2 | 6 | 2 | 2 / 3 | 2 |
| 2026-04-27 | B38-W6 ✗; B08-W3 ✗; B21-W2 ✓ 80 h, drzwi | 1 / 3 | 6 | 1 | 5 | 1 | 1 / 3 | 1 |
| 2026-05-04 | B20-W2 ✓ 46 h, drzwi; B15-W3 ✗; B38-W3 ✗ | 1 / 3 | 8 | 1 | 6 | 1 | 1 / 3 | 1 |
| 2026-05-11 | B17-W1 ✓ 14 h, drzwi; B26-W3 ✓ 80 h, drzwi; B25-W1 ✗ | 2 / 3 | 10 | 2 | 9 | 2 | 2 / 3 | 2 |
| 2026-05-18 | B37-W2 ✓ 148 h, drzwi; B02-W1 ✓ 102 h, drzwi; B02-W4 ✗ | 2 / 3 | 6 | 2 | 6 | 2 | 2 / 3 | 2 |
| 2026-05-25 | B36-W2 ✗; B31-W2 ✗; B04-W4 ✗ | 0 / 3 | 8 | 0 | 7 | 0 | 0 / 3 | 0 |
| 2026-06-01 | B29-W1 ✓ 107 h, hamulec_liny; B15-W3 ✗; B07-W4 ✗ | 1 / 3 | 7 | 1 | 6 | 1 | 0 / 3 | 0 |
| 2026-06-08 | B14-W1 ✗; B20-W2 ✗; B33-W4 ✗ | 0 / 3 | 11 | 0 | 6 | 0 | 1 / 3 | 1 |
| 2026-06-15 | B20-W1 ✓ 82 h, brak; B07-W3 ✗; B16-W1 ✓ 8 h, naped | 2 / 3 | 16 | 2 | 6 | 1 | 1 / 3 | 1 |
| 2026-06-22 | B10-W1 ✗; B33-W4 ✓ 132 h, drzwi; B18-W2 ✗ | 1 / 3 | 7 | 1 | 6 | 1 | 2 / 3 | 2 |
| 2026-06-29 | B04-W4 ✓ 127 h, drzwi; B38-W2 ✓ 124 h, drzwi; B18-W1 ✗ | 2 / 3 | 10 | 2 | 7 | 2 | 2 / 3 | 2 |
| 2026-07-06 | B25-W1 ✓ 102 h, sterownik; B33-W4 ✗; B27-W3 ✗ | 1 / 3 | 7 | 1 | 6 | 1 | 2 / 3 | 2 |
| 2026-07-13 | B30-W2 ✓ 128 h, hamulec_liny; B15-W1 ✓ 1 h, drzwi; B38-W3 ✗ | 2 / 3 | 10 | 2 | 5 | 2 | 2 / 3 | 2 |
| 2026-07-20 | B31-W3 ✓ 151 h, brak; B24-W2 ✗; B24-W3 ✓ 56 h, naped | 2 / 3 | 26 | 2 | 5 | 1 | 2 / 3 | 2 |
| 2026-07-27 | B23-W2 ✓ 127 h, naped; B18-W4 ✗; B11-W3 ✗ | 1 / 3 | 12 | 1 | 6 | 1 | 0 / 3 | 0 |
| 2026-08-03 | B20-W1 ✗; B30-W4 ✗; B24-W2 ✓ 22 h, drzwi | 1 / 3 | 5 | 1 | 4 | 1 | 1 / 3 | 1 |
| 2026-08-10 | B19-W1 ✓ 137 h, drzwi; B36-W2 ✓ 128 h, drzwi; B29-W1 ✗ | 2 / 3 | 13 | 2 | 8 | 2 | 2 / 3 | 2 |
| 2026-08-17 | B20-W1 ✓ 80 h, naped; B02-W2 ✓ 27 h, brak; B30-W2 ✗ | 2 / 3 | 11 | 3 | 5 | 2 | 2 / 3 | 3 |
| 2026-08-24 | B29-W3 ✓ 84 h, drzwi; B19-W4 ✓ 7 h, hamulec_liny; B04-W2 ✗ | 2 / 3 | 8 | 2 | 5 | 2 | 1 / 3 | 1 |
| 2026-08-31 | B17-W3 ✓ 100 h, drzwi; B10-W3 ✗; B04-W4 ✗ | 1 / 3 | 7 | 1 | 5 | 1 | 1 / 3 | 1 |
| 2026-09-07 | B32-W3 ✗; B22-W3 ✓ 108 h, drzwi; B06-W1 ✗ | 1 / 3 | 7 | 1 | 6 | 1 | 1 / 3 | 1 |
| 2026-09-14 | B25-W1 ✓ 86 h, naped; B12-W1 ✗; B21-W4 ✓ 22 h, drzwi | 2 / 3 | 4 | 2 | 4 | 2 | 2 / 3 | 2 |
| 2026-09-21 | B31-W1 ✓ 131 h, drzwi; B29-W1 ✓ 5 h, drzwi; B06-W1 ✓ 34 h, naped | 3 / 3 | 9 | 3 | 6 | 3 | 3 / 3 | 3 |
| **razem** | | **56 / 114** | **322** | **57** | **216** | **52** | **50 / 114** | **51** |

### T4. Tygodnie według liczby trafnych alarmów (z 38)

| ranking ryzyka | 0 / 3 | 1 / 3 | 2 / 3 | 3 / 3 |
|---|---:|---:|---:|---:|
| **model v2b_lgbm_czas_winda** | 5 | 13 | 17 | 3 |
| baseline: reguła `drzwi_ponowne_otwarcia_do_normy_24h` | 8 | 13 | 14 | 3 |
| model bez przerwy (`przerwa_dni = 0`) | 3 | 14 | 16 | 5 |

### T5. Złapane awarie według podzespołu

| podzespół | z sygnałem | awarie | złapane: **model v2b_lgbm_czas_winda** | złapane: baseline: reguła `drzwi_ponowne_otwarcia_do_normy_24h` | złapane: model bez przerwy (`przerwa_dni = 0`) |
|---|---|---:|---:|---:|---:|
| drzwi | tak | 111 | 34 | 43 | 39 |
| zewnetrzna | nie | 71 | 0 | 2 | 0 |
| naped | tak | 44 | 12 | 0 | 9 |
| brak | nie | 35 | 5 | 5 | 6 |
| sterownik | tak | 31 | 2 | 1 | 1 |
| hamulec_liny | tak | 30 | 4 | 0 | 7 |

### T6. Wyprzedzenie trafnych alarmów (godziny od alarmu do startu awarii)

| ranking ryzyka | trafne | min | kwartyl 1 | mediana | kwartyl 3 | max | do 24 h |
|---|---:|---:|---:|---:|---:|---:|---:|
| **model v2b_lgbm_czas_winda** | 56 | 1,2 | 33,7 | 85,1 | 127,1 | 152,2 | 10 |
| baseline: reguła `drzwi_ponowne_otwarcia_do_normy_24h` | 50 | 1,2 | 34,5 | 82,5 | 127,2 | 152,2 | 9 |
| model bez przerwy (`przerwa_dni = 0`) | 61 | 1,2 | 34,0 | 81,5 | 127,0 | 152,2 | 9 |
| wyrocznia (zna `awaria_7d`) | 114 | 1,2 | 33,5 | 88,9 | 121,3 | 157,8 | 16 |

## SQL i kod

Powtórzenie (z katalogu głównego; potrzebna baza z `dni_wind`, `cechy_windy`, `cechy_windy_tsfresh`, `pypyr baza`):

```bash
cd api && poetry run python -m api.contexts_boundaries.maintenance_bc.punkt_pracy   # tabele T1–T6 (ok. 1,5 min)
poetry run pytest tests/test_alarmy_wind.py                                         # reguła, przerwa, okno, miary
```

- Reguła: `api/api/contexts_boundaries/maintenance_bc/alarmy_wind.py` — `wybierz_alarmy(ryzyko, limit, przerwa_dni,
  dzien_alarmu)` (ranking → alarmy), `ocen_alarmy(alarmy, awarie, poniedzialki)` (trafność, czułość, tygodnie,
  wyprzedzenie), `wczytaj_zalozenia()` (`zalozenia.yaml`: `alarmy_na_tydzien` 3, `dzien_alarmu` 0 = poniedziałek,
  `przerwa_dni` 7; źródło: użytkownik, 2026-11-16).
- Ewaluacja: `api/api/contexts_boundaries/maintenance_bc/punkt_pracy.py` — dane: `features/windy/zbior.py`
  (`wczytaj_zbior`), test z `failure_model/evals/ewaluacja_v2.py` (`podzial_czas_winda`, maska `test`), ryzyko
  z `versions/v2b_lgbm_czas_winda/model.joblib`, baseline `wynik_reguly(drzwi_ponowne_otwarcia_do_normy_24h)`;
  losowo: 1 000 symulacji (ziarno 2026); bootstrap tygodni: 10 000 losowań (ziarno 2026); `sprawdz_z_dni_wind`:
  trafność = `dni_wind.awaria_7d`, wyprzedzenie = `dni_wind.godziny_do_startu` dla każdego alarmu.

### Awarie (ten sam start co CTE `awarie` w `features/windy/dni_wind.sql`)

```sql
SELECT id_awarii, id_windy, podzespol,
    coalesce(start_awarii_tz, timezone('Europe/Warsaw', pierwsze_zgloszenie)) AS start_tz
FROM awarie_odtworzone;
```

### Kontrole użyte w opisie

```sql
-- awarie w zakresie czułości i awarie z sygnałem (wynik: 322, 216)
WITH a AS (
    SELECT podzespol, coalesce(start_awarii_tz, timezone('Europe/Warsaw', pierwsze_zgloszenie)) AS s
    FROM awarie_odtworzone
)
SELECT count(*), count(*) FILTER (podzespol IN ('drzwi', 'naped', 'hamulec_liny', 'sterownik'))
FROM a
WHERE s > TIMESTAMPTZ '2026-01-05 06:00:00+01' AND s <= TIMESTAMPTZ '2026-09-28 06:00:00+02';

-- tydzień 2026-07-20 według podzespołu (wynik: zewnetrzna 17, brak 4, drzwi 3, sterownik 1, naped 1)
WITH a AS (
    SELECT podzespol, coalesce(start_awarii_tz, timezone('Europe/Warsaw', pierwsze_zgloszenie)) AS s
    FROM awarie_odtworzone
)
SELECT podzespol, count(*)
FROM a
WHERE s > TIMESTAMPTZ '2026-07-20 06:00:00+02' AND s <= TIMESTAMPTZ '2026-07-27 06:00:00+02'
GROUP BY 1 ORDER BY 2 DESC;

-- poniedziałki testu w dni_wind (wynik: 5 286 wierszy, 318 z awarią, 38 poniedziałków, 2026-01-05 – 2026-09-21)
SELECT count(*), sum(awaria_7d), count(DISTINCT dzien), min(dzien), max(dzien)
FROM dni_wind
WHERE dzien BETWEEN '2026-01-01' AND '2026-09-22' AND dayofweek(dzien) = 1;
```

### Reguła (rdzeń `wybierz_alarmy`)

```python
r = r[r["dzien"].dt.day_of_week == dzien_alarmu]          # tylko poniedziałki
ostatni = {}                                              # id_windy -> dzień ostatniego alarmu
for dzien, grupa in r.groupby("dzien", sort=True):
    granica = dzien - pd.Timedelta(days=przerwa_dni)      # alarm w (dzien − 7; dzien) blokuje; t−7 też blokuje
    wolne = grupa[[not (w in ostatni and ostatni[w] >= granica) for w in grupa["id_windy"]]]
    wybrane = wolne.sort_values(["ryzyko", "id_windy"], ascending=[False, True]).head(limit)
    ...                                                   # zapis alarmów, ostatni[w] = dzien
```
