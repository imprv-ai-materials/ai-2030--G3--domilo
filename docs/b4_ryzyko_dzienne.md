# Alerty o awariach wind w produkcji: okna Telemetry, cechy o 05:50, ryzyko o 06:00, zgłoszenia w Serwisowniku

Data: 2026-11-16. Model: `v3_punkt_pracy` z `failure_model/current.yaml`. Kod: `api/api/adapters/telemetra.py`,
`adapters/serwisownik.py` (`KlientSerwisownika`), `adapters/ryzyko_wind.py`, `contexts_boundaries/maintenance_bc/`
(`telemetria_biezaca.py`, `cechy_dzienne.py`, `ryzyko_dzienne.py`, `wyjasnienie.py`, `podzespoly.yaml`),
`inngest_app.py`, `main.py`; atrapa Serwisownika `dev/serwisownik_mock/`.

## Wnioski

1. Ryzyko awarii wind liczy się samo: co 10 minut okna z Telemetry trafiają do magazynu Parquet, o 05:50 powstają
   cechy, o 06:00 ryzyko każdej windy, a w poniedziałek 3 windy o najwyższym ryzyku trafiają do Serwisownika jako
   zgłoszenie z jednym zdaniem dla technika, np. „Drzwi: najdłuższy czas zamykania 2,8× względem normy z 30 dni,
   ponowne otwarcia 10×. Sprawdź operator drzwi i rolki.” (T1, T9).
2. Codzienne liczenie daje to samo co trening: cechy bez różnic, ryzyko równe wynikowi modelu, a 113 ze 114 alertów
   z okresu testowego to te same windy co w ocenie offline; 56 alertów było trafnych, jak w ocenie punktu pracy (T2, T3, T8).
3. Wskazany podzespół zwykle się zgadza: w trafnych alertach pierwszy podzespół z alertu był tym, który się
   zepsuł, w 96,1% przypadków (stała lista według częstości awarii: 64,7%), a we wszystkich dniach przed awarią
   w 66,7% (baseline 51,2%; T5). Najsłabiej rozpoznajemy sterownik (19%).
4. Jeden alert z testu (B27-W1, 2026-06-29) poszedł do windy, która od poprzedniego popołudnia stała po awarii
   napędu: reguła „winda stoi” patrzy tylko na tryb `wylaczona` o 05:50 i tej awarii nie widzi (T8). Do decyzji
   zostają też: 3 alarmy nawet przy niskim ryzyku (2026-09-28: 5,4%, T3) i zapasy czasu na spóźnione okna (T6).

## Tabele

### T1. Zadania i endpoint

| Funkcja Inngest | Harmonogram (zdarzenie ręczne) | Kroki | Wynik |
|---|---|---|---|
| `telemetra-okna` | co 10 min (`domilo/telemetra.okna`, opcjonalnie `od`, `do`) | `zakres` → `okna-<n>` | `telemetra_biezaca/telemetra_windy/rok=RRRR/miesiac=MM/okna.parquet`, idempotentnie po (id_windy, ts_utc) |
| `cechy-wind` | 05:50 Europe/Warsaw (`domilo/windy.cechy`, opcjonalnie `dzien`) | `parametry` → `kompletnosc` (czeka na okno 05:50 do 05:58) → `cechy` | `windy_dzienne/<dzien>/cechy.parquet` (168 cech ręcznych + 21 tsfresh + stan telemetrii) |
| `ryzyko-wind` | 06:00 Europe/Warsaw (`domilo/windy.ryzyko`, opcjonalnie `dzien`) | `parametry` → `ryzyko` → `zapis-ryzyka` → `alarmy` → `serwisownik-<id_windy>` (krok na alarm) | tabele `ryzyko_wind`, `alarmy_wind`; zgłoszenia w Serwisowniku przez `adapters/serwisownik.py` (klucz idempotencji `{id_windy}:{data_alarmu}`, treść = opis alertu jednym zdaniem) |
| `GET /lifts/{id_windy}/risk[?dzien=]` | — | odczyt `ryzyko_wind` + `alarmy_wind` | ryzyko (P awarii w 7 dni), data oceny, 3 najsilniejsze sygnały, podejrzane podzespoły, opis alertu, alarm dnia |

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

Model: suma wkładów SHAP (`v3_punkt_pracy`, dzień oceny) wszystkich cech przypisanych do podzespołu w
`maintenance_bc/podzespoly.yaml`; na liście podzespoły z sumą > 0, malejąco. Baseline: stała kolejność według liczby
dni z awarią na treningu 2023-03 – 2025-06 (drzwi 2 158, napęd 979, sterownik 668, hamulec/liny 549); „w liście”
dla baseline = tyle pierwszych podzespołów, ile ma lista modelu w tym wierszu. 95% CI: bootstrap awarii (2 000 losowań).

| Wiersze | Dni | Awarie | 1. miejsce: model | 1. miejsce: baseline | Model − baseline (pp, 95% CI) | W liście: model | W liście: baseline | Model − baseline (pp, 95% CI) | Średnia długość listy | Pusta lista |
|---|---:|---:|---:|---:|---|---:|---:|---|---:|---:|
| Wszystkie dni z awarią z sygnałem | 1 476 | 220 | 66,7% | 51,2% | +15,4 (+7,3 … +23,7) | 74,4% | 68,4% | +6,0 (+0,5 … +11,8) | 2,10 | 9,8% |
| Trafne alarmy reguły | 51 | 51 | 96,1% | 64,7% | +31,4 (+19,6 … +43,1) | 100,0% | 90,2% | +9,8 (+2,0 … +19,6) | 2,63 | 0,0% |

1. miejsce według faktycznego podzespołu (wszystkie dni): drzwi 72,0% (baseline 100%), napęd 85,1% (0%),
hamulec/liny 70,3% (0%), sterownik 19,0% (0%). Awarie sterownika model wskazuje najczęściej jako napęd (64 dni)
albo hamulec/liny (50 dni) z 216. Wcześniejsza wersja listy (sygnały z dodatnim wkładem, sygnał mógł wskazywać dwa
podzespoły; `podzespoly_sygnalow.yaml`): 61,8% / 90,2% przy średnio 3,18 podzespołu na liście.

### T7. Wybór podzespołu dla sygnałów niejednoznacznych (walidacja 2025-07-01 – 2025-12-31, 966 dni z awarią, 145 awarii)

Reguła ustalona przed oceną na teście: wariant o najwyższym trafieniu 1. podzespołu na walidacji (pozostałe sygnały
według tego, co mierzą; `podzespoly.yaml`). Baseline na walidacji: 51,0%.

| `naped_blad_poziomowania` | `wibracje_rms` | 1. miejsce | Średnia długość listy |
|---|---|---:|---:|
| **hamulec_liny** | **hamulec_liny** | **75,8%** | 2,10 |
| hamulec_liny | naped | 75,6% | 2,04 |
| naped | hamulec_liny | 69,1% | 2,16 |
| naped | naped | 69,1% | 1,65 |

Dwa najlepsze warianty różnią się o 0,2 pp (2 dni), więc przypisanie wibracji jest w praktyce obojętne.

### T8. Alerty z okresu testowego (produkcyjne zadania na kopii bazy, 38 poniedziałków 2026-01-05 – 2026-09-21)

`failure_model/evals/przyklady_alertow.py`: `cechy-wind` + `ryzyko-wind` dla każdego poniedziałku po kolei (przerwa
7 dni z tabeli `alarmy_wind`), wysyłka przez `adapters/serwisownik.py` do atrapy na `http://127.0.0.1:8103`,
wynik z `dni_wind`.

| Miara | Wartość |
|---|---:|
| Zgłoszenia przyjęte przez atrapę | 114 |
| Trafne (awaria w 7 dni) | 56 (49,6% ze 113 z wierszem w `dni_wind`) |
| Te same windy co w regule offline na `dni_wind` | 113 ze 114 |
| 1. podzespół w alertach: drzwi / napęd / hamulec i liny / sterownik | 73 / 29 / 11 / 1 |
| Trafne z podzespołem z sygnałem: 1. podzespół = faktyczny | 49 z 51 |
| Długość opisu (znaki): min / mediana / maks. | 108 / 117 / 168 |
| Opisy bez wartości („odchylenia w kilku sygnałach”) / bez podzespołu | 0 / 0 |

Jedyna różnica z regułą offline: 2026-06-29 produkcja wysłała alert do B27-W1 (pozycja 1), offline do B18-W1.
B27-W1 stała wtedy po awarii napędu (`awarie_odtworzone`: B27-W1/Z022958, start 2026-06-28 15:10, 143 okna
przestoju), więc `dni_wind` nie ma tego dnia. O 05:50 tryb nie był `wylaczona` (przestój = okna bez kursów), więc
reguła „stoi” (T4) go nie wykryła.

### T9. Trzy przykładowe alerty (reguła wyboru ustalona przed uruchomieniem: pozycja 1 z trzech pierwszych poniedziałków testu)

| Klucz idempotencji (winda:data alarmu) | Zgłoszenie | Treść zgłoszenia (opis alertu) | Podejrzane podzespoły (suma SHAP) | P awarii 7 dni | Co się stało (`dni_wind`) |
|---|---|---|---|---:|---|
| B23-W1:2026-01-05 | A000001 | Drzwi: najdłuższy czas zamykania 2,8× względem normy z 30 dni, ponowne otwarcia 10×. Sprawdź operator drzwi i rolki. | drzwi | 100%* | awaria drzwi po 30,2 h |
| B24-W2:2026-01-12 | A000004 | Drzwi: najdłuższy czas zamykania 2,0× względem normy z 30 dni, ponowne otwarcia 7,1×. Sprawdź operator drzwi i rolki. | drzwi | 46,5% | awaria drzwi po 6,8 h |
| B08-W4:2026-01-19 | A000007 | Napęd: szczytowy prąd silnika +13% względem normy z 30 dni, temperatura silnika +11 °C. Sprawdź silnik, przekładnię i łożyska napędu. | napęd, sterownik, hamulec i liny | 46,5% | awaria napędu po 98,7 h |

\* Kalibracja izotoniczna daje 1,0 dla najwyższych wyników z walidacji. To „bardzo wysokie”, a nie pewność.

Pełne zgłoszenie (pierwszy przykład, pola `alarm.sygnaly` skrócone do jednego):

```json
{"id_budynku": "B23", "id_urzadzenia": "B23-W1", "typ_urzadzenia": "winda", "zrodlo": "model_awarii",
 "kategoria": "przegląd", "priorytet": "normalny", "firma_serwisowa": "Serwis-Lift",
 "klucz_idempotencji": "B23-W1:2026-01-05",
 "tresc_zgloszenia": "Drzwi: najdłuższy czas zamykania 2,8× względem normy z 30 dni, ponowne otwarcia 10×. Sprawdź operator drzwi i rolki.",
 "alarm": {"id_windy": "B23-W1", "dzien": "2026-01-05", "pozycja": 1, "wynik": 0.74109163, "p_awarii_7d": 1.0,
   "wersja_modelu": "v3_punkt_pracy",
   "podejrzane_podzespoly": [{"podzespol": "drzwi", "wklad": 4.4872,
     "sygnaly": ["drzwi_czas_zamykania_max", "drzwi_ponowne_otwarcia", "drzwi_bledy", "drzwi_czas_zamykania_sr"]}],
   "sygnaly": [{"sygnal": "drzwi_czas_zamykania_max", "cecha": "drzwi_czas_zamykania_max_do_normy_24h",
     "wartosc": 2.8455, "wklad": 2.5191, "podzespol": "drzwi", "rodzina": "drzwi",
     "zrodlo": "czas_zamykania_drzwi_max_s", "jednostka": "s"}]}}
```

### T6. Parametry techniczne przyjęte w tej pracy (nie z danych, do potwierdzenia)

| Parametr | Wartość | Gdzie | Po co |
|---|---|---|---|
| `ZAKLADKA` | 1 h | `telemetria_biezaca.py` | okna spóźnione do 1 h też trafią do magazynu (powtórzenia pomija klucz) |
| `MAKS_ZAKRES`, `KROK_ZAPYTANIA` | 24 h, 6 h | `telemetria_biezaca.py` | nadrabianie zaległości po 24 h na przebieg, zapytania do API po 6 h |
| `CZEKAJ_DO`, `PONOW_PO` | 8 min, 1 min | `cechy_dzienne.py` | czekanie na okno 05:40–05:50 (oba zadania ruszają o 05:50) |
| `CZEKAJ_NA_CECHY`, `PONOW_PO` | 30 min, 2 min | `ryzyko_dzienne.py` | czekanie zadania 06:00 na plik cech |
| Kontrakt API Telemetry i Serwisownika | `GET /okna?od&do`, `POST /api/zgloszenia` | `adapters/telemetra.py`, `adapters/serwisownik.py` | przyjęty; atrapy: eksport z `data/`, `dev/serwisownik_mock/` |
| Teksty alertu | nazwy sygnałów, „Sprawdź …” dla napędu, hamulca i lin, sterownika | `podzespoly.yaml` | zaproponowane w tej pracy (drzwi: przykład użytkownika); do potwierdzenia przez dział techniczny |
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

T5: `cd api && poetry run python -m api.ai.failure_model.evals.podzespoly`; T7: to samo z `--wybor` (miary i
bootstrap w module). T8, T9: `pypyr serwisownik_mock` (albo `SERWISOWNIK_MOCK_STAN=/tmp/stan.json poetry run uvicorn
app:app --app-dir dev/serwisownik_mock --port 8103`), potem
`cd api && poetry run python -m api.ai.failure_model.evals.przyklady_alertow --wyjscie /tmp/alerty.json`
(ok. 2 min), a z pliku: liczby T8 i wiersze z `pozycja = 1` trzech pierwszych dni (T9). Różnica z regułą offline:

```python
t = zb[zb.dzien.between("2026-01-05", "2026-09-22")].reset_index(drop=True)      # zb = wczytaj_zbior(con)[0]
off = wybierz_alarmy(t.assign(ryzyko=wczytaj_obecny().predict(t)), limit=3, przerwa_dni=7)
# zbiór (dzień, winda) z off vs z zgłoszeń atrapy; przestój B27-W1:
# SELECT id_awarii, podzespol, start_awarii_tz, okna_przestoju FROM awarie_odtworzone
# WHERE id_windy = 'B27-W1' AND start_awarii_tz BETWEEN DATE '2026-06-19' AND DATE '2026-06-30'
```

Wyjaśnienie (`maintenance_bc/wyjasnienie.py`): `explain` aktywnej wersji daje SHAP (`wklad_<cecha>`, log-szansa).
- Podzespoły: `wklad` każdej cechy sumujemy według `podzespoly.yaml` (`cechy`: cecha → podzespół, null = kontekst);
  na liście podzespoły z sumą > 0, malejąco.
- Sygnały: cechy grupujemy w sygnały (`<sygnał>_<statystyka>`, tsfresh → sygnał o tym samym źródle, `firmware_*` →
  `sterownik_firmware`); 3 najsilniejsze to te o największej dodatniej sumie wkładów.
- Opis (`opis_alertu`): pierwszy podzespół, jego 2 sygnały o największym wkładzie. Dla każdego sygnału bierzemy
  okno (24 h / 3 / 7 dni), którego cecha `<sygnał>_do_normy_<okno>` ma największy wkład, i piszemy
  `średnia / norma`: „+38%” poniżej 2×, „3×” od 2×. Dla temperatur piszemy różnicę w °C. Gdy norma = 0 (błędy),
  podajemy liczbę w ostatniej dobie = `<sygnał>_sr_24h × okna_24h`. Na końcu dodajemy „Sprawdź …” z `podzespoly.yaml`.

Testy: `api/tests/test_ryzyko_dzienne_wind.py` (20 testów: magazyn, zakres, źródło, równość cech, kompletność,
reguła z przerwą z tabeli, „stoi”, suma SHAP według podzespoly.yaml, opis alertu, spójność podzespoly.yaml z modelem,
atrapa Serwisownika z kluczem winda:data, konfiguracja Inngest, pełny przebieg na kopii bazy i endpoint).
