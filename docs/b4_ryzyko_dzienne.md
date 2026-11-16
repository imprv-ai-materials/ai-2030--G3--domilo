# Alerty o awariach wind w produkcji: okna Telemetry, cechy o 05:50, ryzyko o 06:00, zgłoszenia w Serwisowniku

Data: 2026-11-16. Model: `v3_punkt_pracy` z `failure_model/current.yaml`. Kod: `api/api/adapters/telemetra.py`,
`adapters/serwisownik_alarmy.py`, `adapters/ryzyko_wind.py`, `contexts_boundaries/maintenance_bc/`
(`telemetria_biezaca.py`, `cechy_dzienne.py`, `ryzyko_dzienne.py`, `wyjasnienie.py`), `inngest_app.py`, `main.py`.

## Wnioski

1. Ryzyko awarii wind liczy się teraz samo: co 10 minut nowe okna z Telemetry trafiają do magazynu Parquet,
   o 05:50 powstają cechy, a o 06:00 ryzyko każdej windy. W poniedziałek 3 windy o najwyższym ryzyku trafiają
   do Serwisownika jako zgłoszenie „przegląd” (T1). Każdy z tych etapów to osobne zadanie Inngest.
2. Cechy liczone codziennie dają dokładnie te same wartości co w treningu (0 różnic w 2 dniach, także w dniu zmiany
   czasu), a ryzyko jest takie samo jak wynik modelu na zbiorze treningowym. Alarmy z czterech poniedziałków
   września 2026 są takie same jak przy regule liczonej offline (T2, T3).
3. Lista podejrzanych podzespołów pomaga przede wszystkim pierwszą pozycją: w trafnych alarmach pierwszy podzespół
   był właściwy w 90,2% przypadków. Stała lista według częstości awarii trafia w 64,7% (T5). Cała lista jest
   jednak prawie zawsze długa (średnio 3,2 z 4 podzespołów), więc technik powinien patrzeć głównie na pierwszy.
4. Dwa ryzyka do decyzji. Po pierwsze, reguła zawsze wysyła 3 alarmy: 2026-09-28 trzecia winda miała tylko 5,4%
   szans na awarię (T3). Po drugie, nie wiemy, jak bardzo Telemetra spóźnia okna, więc przyjęto techniczne
   zapasy czasu (T6), które trzeba potwierdzić.

## Tabele

### T1. Zadania i endpoint

| Funkcja Inngest | Harmonogram (zdarzenie ręczne) | Kroki | Wynik |
|---|---|---|---|
| `telemetra-okna` | co 10 min (`domilo/telemetra.okna`, opcjonalnie `od`, `do`) | `zakres` → `okna-<n>` | `telemetra_biezaca/telemetra_windy/rok=RRRR/miesiac=MM/okna.parquet`, idempotentnie po (id_windy, ts_utc) |
| `cechy-wind` | 05:50 Europe/Warsaw (`domilo/windy.cechy`, opcjonalnie `dzien`) | `parametry` → `kompletnosc` (czeka na okno 05:50 do 05:58) → `cechy` | `windy_dzienne/<dzien>/cechy.parquet` (168 cech ręcznych + 21 tsfresh + stan telemetrii) |
| `ryzyko-wind` | 06:00 Europe/Warsaw (`domilo/windy.ryzyko`, opcjonalnie `dzien`) | `parametry` → `ryzyko` → `zapis-ryzyka` → `alarmy` → `serwisownik-<id_windy>` (krok na alarm) | tabele `ryzyko_wind`, `alarmy_wind`; zgłoszenia w Serwisowniku (klucz `alarm-windy:{id_windy}:{dzien}`) |
| `GET /lifts/{id_windy}/risk[?dzien=]` | — | odczyt `ryzyko_wind` + `alarmy_wind` | ryzyko (P awarii w 7 dni), data oceny, 3 najsilniejsze sygnały, podejrzane podzespoły, alarm dnia |

### T2. Cechy dnia a tabele treningowe (`api/tests/test_ryzyko_dzienne_wind.py`)

| Dzień oceny | Wind w cechach dnia | Wind w `cechy_windy` (dni_wind) | Komórki porównane: ręczne / tsfresh | Różne (rtol 1e-9) | Czas cech dnia |
|---|---:|---:|---:|---:|---:|
| 2026-09-21 | 140 | 139 | 23 352 / 2 919 | 0 / 0 | 2,1 s + 2,5 s tsfresh (pierwsze uruchomienie) |
| 2025-03-31 | 140 | 139 | 23 352 / 2 919 | 0 / 0 | 1,2 s + 0,4 s |
| 2024-03-31 (zmiana czasu) | — | — | test `test_cechy_dnia_takie_same_jak_tabele_treningowe` | 0 | — |

Różnica 140 / 139: `dni_wind` nie ma dnia, w którym winda o 06:00 stoi po awarii; cechy dnia liczą każdą windę,
a regułę „stoi” stosuje krok `alarmy` (T4). Ryzyko z zadania (`ryzyko_wind.wynik`) dla 2026-09-21 jest równe
`predict` modelu na wierszach `wczytaj_zbior` tego dnia (test `test_ryzyko_dnia_to_samo_co_model_na_zbiorze_treningowym`,
atol 1e-7).

### T3. Przebieg pokazowy na kopii bazy: cztery poniedziałki (eksport + magazyn, atrapa Serwisownika)

| Dzień | Windy ocenione | Stoją o 05:50 | Alarmy (id_windy: wynik / P awarii 7 dni) | W przerwie (alarm 7 dni wcześniej) | Reguła offline na `dni_wind` (historia od 2026-01-05) |
|---|---:|---:|---|---|---|
| 2026-09-07 | 140 | 0 | B32-W3: 0,502 / 46,5%; B22-W3: 0,442 / 43,3%; B06-W1: 0,395 / 37,6% | — (brak wcześniejszych alarmów w tabeli) | B32-W3, B22-W3, B06-W1 |
| 2026-09-14 | 140 | 2 | B25-W1: 0,592 / 53,7%; B12-W1: 0,415 / 37,8%; B21-W4: 0,410 / 37,6% | B06-W1, B22-W3, B32-W3 | B25-W1, B12-W1, B21-W4 |
| 2026-09-21 | 140 | 0 | B31-W1: 0,643 / 67,2%; B29-W1: 0,580 / 47,6%; B06-W1: 0,499 / 46,5% | B12-W1, B21-W4, B25-W1 | B31-W1, B29-W1, B06-W1 |
| 2026-09-28 | 140 | 1 | B15-W3: 0,458 / 43,3%; B36-W1: 0,422 / 37,8%; B02-W1: 0,069 / 5,4% | B06-W1, B29-W1, B31-W1 | poza `dni_wind` (kończy się 2026-09-22) |

Czas na kopii bazy (MacBook, DuckDB 2.0): cechy dnia 1,1–3,4 s, ryzyko z zapisem i alarmami 0,5 s. Drugi przebieg
2026-09-21 (test) nie zmienia alarmów (`zapisano_teraz = false`), a Serwisownik zwraca te same zgłoszenia
(`utworzono = false`).

### T4. Reguła „winda stoi” wobec wykluczeń w treningu (dni 2023-03-01 – 2026-09-22 z telemetrią na całe okno)

| Tryb okna kończącego się o 05:50 | Dni wykluczone z `dni_wind` (stoi po awarii) | Dni w `dni_wind` |
|---|---:|---:|
| `wylaczona` | 943 | 62 |
| `normalny` | 511 | 174 560 |

Reguła łapie 943 z 1 454 dni, w których trening uznał windę za stojącą (64,9%), i myli się w 62 ze 174 622 dni
ocenianych (0,04%). W treningu przestój wynika z awarii odtworzonej przez LLM ze zgłoszeń, a tych na żywo jeszcze
nie ma. Dlatego w produkcji używamy samej telemetrii.

### T5. Trafność listy podejrzanych podzespołów (test v2b 2026-01-01 – 2026-09-22; `failure_model/evals/podzespoly.py`)

Baseline: stała kolejność podzespołów według liczby dni z awarią na treningu 2023-03 – 2025-06 (drzwi 2 158,
napęd 979, sterownik 668, hamulec/liny 549). „W liście” dla baseline: tyle pierwszych podzespołów, ile ma lista
modelu w tym wierszu. 95% CI: bootstrap awarii (2 000 losowań).

| Wiersze | Dni | Awarie | 1. miejsce: model | 1. miejsce: baseline | Model − baseline (pp, 95% CI) | W liście: model | W liście: baseline | Model − baseline (pp, 95% CI) | Średnia długość listy |
|---|---:|---:|---:|---:|---|---:|---:|---|---:|
| Wszystkie dni z awarią z sygnałem | 1 476 | 220 | 61,8% | 51,2% | +10,6 (+3,6 … +17,9) | 88,8% | 88,5% | +0,3 (−3,8 … +4,7) | 3,18 |
| Trafne alarmy reguły | 51 | 51 | 90,2% | 64,7% | +25,5 (+13,7 … +37,3) | 100,0% | 100,0% | 0,0 | 3,22 |

1. miejsce według faktycznego podzespołu (wszystkie dni): drzwi 75,0% (baseline 100%), napęd 90,7% (0%),
sterownik 23,6% (0%), hamulec/liny 9,9% (0%). Przypisanie sygnałów do podzespołów
(`maintenance_bc/podzespoly_sygnalow.yaml`) jest założeniem tej pracy, nie wynikiem z danych.

### T6. Parametry techniczne przyjęte w tej pracy (nie z danych, do potwierdzenia)

| Parametr | Wartość | Gdzie | Po co |
|---|---|---|---|
| `ZAKLADKA` | 1 h | `telemetria_biezaca.py` | okna spóźnione do 1 h też trafią do magazynu (powtórzenia pomija klucz) |
| `MAKS_ZAKRES`, `KROK_ZAPYTANIA` | 24 h, 6 h | `telemetria_biezaca.py` | nadrabianie zaległości po 24 h na przebieg, zapytania do API po 6 h |
| `CZEKAJ_DO`, `PONOW_PO` | 8 min, 1 min | `cechy_dzienne.py` | czekanie na okno 05:40–05:50 (oba zadania ruszają o 05:50) |
| `CZEKAJ_NA_CECHY`, `PONOW_PO` | 30 min, 2 min | `ryzyko_dzienne.py` | czekanie zadania 06:00 na plik cech |
| Kontrakt API Telemetry i Serwisownika | `GET /okna?od&do`, `POST /api/zgloszenia` | `adapters/telemetra.py`, `adapters/serwisownik_alarmy.py` | przyjęty; atrapy: eksport z `data/`, `dev/mock_serwisownik/` |
| Zgłoszenie | `kategoria = przegląd`, `priorytet = normalny`, `zrodlo = model_awarii` | `ryzyko_dzienne.zgloszenie_alarmu` | kategorie i priorytety jak w `serwis_zgloszenia` |

Idempotencja magazynu (odtworzenie z eksportu 2026-09-30 00:00 – 22:00 UTC, 4 zapytania po 6 h): pierwszy przebieg
18 480 okien pobranych / 18 480 nowych, drugi 18 480 pobranych / 0 nowych / 18 480 powtórzeń, 0 konfliktów.

## SQL i kod

Cechy dnia: te same pliki `features/windy/sql/*.sql` i `sql_rodziny` co trening. Nowe parametry nie zmieniają
treningu: `przygotuj(con, bez_serwisu, zrodlo, dni)` i `sql_rodziny(..., od_s=None)` mają domyślnie dawne wartości.

```python
# api/api/ai/features/windy/cechy.py
def cechy_dnia(con, dzien, zrodlo="telemetra_windy", bez_serwisu=True):
    pierwszy = dzien - timedelta(days=NORMA_DNI[1] - 1)            # kotwice t−43 … t (norma 15–44 dni, trend 7 dni)
    przygotuj(con, bez_serwisu=bez_serwisu, zrodlo=zrodlo, dni=(pierwszy.isoformat(), dzien.isoformat()))
    czesci = _tabele_rodzin(con, od_s=odciecie_s(pierwszy) - max(OKNA_GODZIN.values()) * 3600)
    ...  # SELECT k.id_windy, k.dzien, <rodziny> FROM kotwice ... WHERE k.dzien = ?
# api/api/ai/features/windy/tsfresh_cechy.py: cechy_tsfresh_dnia(con, dzien, zrodlo) — przygotuj(..., wiersze=, od_s=)
```

Źródło okien (eksport tylko do odczytu + magazyn; eksport ma pierwszeństwo dla swojego okresu):

```sql
-- adapters/telemetra.sql_zrodla -> TEMP VIEW telemetra_windy_biezaca
SELECT <kolumny> FROM read_parquet('data/telemetra/telemetra_windy/*/*/*.parquet', hive_partitioning = false)
UNION ALL
SELECT b.<kolumny>
FROM read_parquet('telemetra_biezaca/telemetra_windy/*/*/okna.parquet', hive_partitioning = false) AS b
ANTI JOIN (SELECT id_windy, ts_utc FROM <eksport> WHERE ts_utc >= (SELECT min(ts_utc) FROM <magazyn>)) AS e
    USING (id_windy, ts_utc)
```

T2 (porównanie cech dnia z tabelami treningowymi):

```python
from api.ai.features.windy.cechy import cechy_dnia
from api.ai.features.windy.tsfresh_cechy import cechy_tsfresh_dnia
with polaczenie() as con:
    c, ts = cechy_dnia(con, d), cechy_tsfresh_dnia(con, d)
    ref = con.execute("SELECT * FROM cechy_windy WHERE dzien = ?", [d]).df()
    reft = con.execute("SELECT * FROM cechy_windy_tsfresh WHERE dzien = ?", [d]).df()
# np.isclose(c[kolumny ref], ref, rtol=1e-9, atol=1e-9, equal_nan=True) na windach z ref
```

T3: kopia `domilo.duckdb` w katalogu tymczasowym, `wykonaj_telemetre_okna(krok, "2026-09-30T00:00:00+00:00",
"2026-09-30T22:00:00+00:00", magazyn)` dwa razy, potem dla każdego poniedziałku
`cechy_dzienne.wykonaj_cechy_wind(krok, dzien, magazyn, baza, katalog)` i
`ryzyko_dzienne.wykonaj_ryzyko_wind(krok, "demo", dzien, baza, katalog, klient_atrapa)`. Reguła offline:

```python
zb, _ = wczytaj_zbior(con)
t = zb[zb.dzien.between("2026-01-05", "2026-09-28")].reset_index(drop=True)
alarmy_wind.wybierz_alarmy(t.assign(ryzyko=wczytaj_obecny().predict(t)), limit=3, przerwa_dni=7)
```

T4:

```sql
WITH k AS (
  SELECT w.id_windy, CAST(d.dzien AS DATE) AS dzien, timezone('Europe/Warsaw', d.dzien + INTERVAL '05:50') AS odc
  FROM (SELECT id_windy, min(ts_utc) AS pierwsze, max(ts_utc) AS ostatnie FROM telemetra_windy GROUP BY 1) w
  CROSS JOIN generate_series(TIMESTAMP '2023-03-01', TIMESTAMP '2026-09-22', INTERVAL 1 DAY) d(dzien)
  WHERE timezone('Europe/Warsaw', d.dzien + INTERVAL 6 HOUR) >= w.pierwsze
    AND timezone('Europe/Warsaw', d.dzien + INTERVAL 7 DAY + INTERVAL 6 HOUR) <= w.ostatnie
),
ost AS (SELECT k.id_windy, k.dzien, t.tryb FROM k LEFT JOIN telemetra_windy t ON t.id_windy = k.id_windy AND t.ts_utc = k.odc),
s AS (SELECT o.*, d.id_windy IS NULL AS wykluczony FROM ost o LEFT JOIN dni_wind d USING (id_windy, dzien))
SELECT wykluczony, tryb, count(*) FROM s GROUP BY ALL ORDER BY ALL;
```

T5: `cd api && poetry run python -m api.ai.failure_model.evals.podzespoly` (miary i bootstrap w module).

Wyjaśnienie (`maintenance_bc/wyjasnienie.py`): `explain` aktywnej wersji daje SHAP (`wklad_<cecha>`, log-szansa).
Cechy grupujemy w sygnały (`<sygnał>_<statystyka>`, tsfresh → sygnał o tym samym źródle, `firmware_*` →
`sterownik_firmware`). 3 najsilniejsze sygnały to te o największej dodatniej sumie wkładów. Podzespoły to podzespoły
sygnałów z dodatnim wkładem (`podzespoly_sygnalow.yaml`), ułożone według sumy wkładów.

Testy: `api/tests/test_ryzyko_dzienne_wind.py` (19 testów: magazyn, zakres, źródło, równość cech, kompletność,
reguła z przerwą z tabeli, „stoi”, wyjaśnienie, atrapa Serwisownika, konfiguracja Inngest, pełny przebieg na kopii
bazy i endpoint).
