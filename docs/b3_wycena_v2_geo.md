# B3. Wycena lokali: sam boosting (v2) i cechy otoczenia

Źródło: `domilo.duckdb` zbudowana z `data/` (eksport 2026-09-30 23:59 Europe/Warsaw) przez `pypyr baza`.
Policzono 2026-11-15. Podział czasowy jak w [b1_dane.md](b1_dane.md) i [b2_wycena_v0_v1.md](b2_wycena_v0_v1.md):
trening 2023-01 – 2025-06 (38 522), walidacja 2025-07 – 2025-12 (7 686), test 2026-01 – 2026-06 (7 487).
Liczby pochodzą z [`ewaluacja_v2.py`](../api/api/ai/valuation_model/evals/ewaluacja_v2.py),
[`opis_geo.py`](../api/api/ai/features/wycena/opis_geo.py) i [`geo.sql`](../api/api/ai/features/wycena/geo.sql)
(sekcja [SQL i kod](#sql-i-kod)).

## Wnioski

Sama zmiana metody na boosting (LightGBM) przy tych samych sześciu cechach co v1 nie poprawia wyceny. Na transakcjach
z I półrocza 2026 MAPE wynosi 10,2% w obu modelach (różnica −0,01 pp). Średni błąd w złotych jest niższy o 157 zł,
a RMSE wyższy o 540 zł. v2 lepiej dopasowuje się tylko do danych treningowych (MAPE 9,0% wobec 9,9%), ale ta
poprawa nie przenosi się na nowe transakcje. Z tych sześciu cech prosta regresja wyciągnęła już prawie wszystko:
brakuje informacji, a nie elastyczności modelu. Policzyliśmy cechy otoczenia dla wszystkich 54 000 transakcji.
Na walidacji v2 zaniża wycenę wyraźniej przy metrze, tramwaju i parku, np. przy metrze w promieniu 700 m mediana
zaniżenia to 9,4%, a dalej od metra 4,6%. To sygnał, że otoczenie może pomóc, ale zysku jeszcze nie zmierzyliśmy:
modelu z cechami otoczenia nie trenowaliśmy, a testu dla niego nie otwieraliśmy. Problem czasu nadal jest
nierozwiązany: v2 zaniża ceny z 2026 o 6,4% (mediana błędu), tak samo jak v1. v2 nie zastępuje v1, a
`current.yaml` dalej wskazuje v1.

## Tabele

### 1. Sam boosting: v2 a v1 na zbiorze testowym (akty 2026-01-01 – 2026-06-30, 7 487 transakcji)

MAE i RMSE w zł, MAPE i MdAPE w %. „Mediana błędu” = mediana (wycena − cena) / cena (< 0 = model zaniża).
Test dla v2 otwarty raz, 2026-11-15 (`versions/v2_lightgbm/metryki.json`, pole `test_otwarty`).

| Wersja | MAE | RMSE | MAPE | MdAPE | Mediana błędu |
|---|---:|---:|---:|---:|---:|
| v0_mediana_dzielnicy (baseline) | 83 401 | 118 320 | 13,4 | 11,3 | −6,4 |
| v1_liniowa | 63 252 | 94 999 | 10,17 | 8,30 | −6,35 |
| v2_lightgbm | 63 095 | 95 538 | 10,16 | 8,30 | −6,43 |
| **v2 − v1** | −157 | +540 | −0,01 | +0,005 | −0,09 |

### 2. Wszystkie zbiory

| Wersja | Zbiór | Transakcje | MAE | RMSE | MAPE | MdAPE | Mediana błędu |
|---|---|---:|---:|---:|---:|---:|---:|
| v1_liniowa | trening | 38 522 | 52 572 | 75 274 | 9,9 | 7,3 | −0,5 |
| v2_lightgbm | trening | 38 522 | 48 421 | 69 128 | 9,0 | 6,7 | −0,4 |
| v1_liniowa | walidacja | 7 686 | 57 814 | 84 156 | 10,2 | 7,6 | −4,7 |
| v2_lightgbm | walidacja* | 7 686 | 57 667 | 84 950 | 10,2 | 7,5 | −4,6 |
| v1_liniowa | test | 7 487 | 63 252 | 94 999 | 10,2 | 8,3 | −6,3 |
| v2_lightgbm | test | 7 487 | 63 095 | 95 538 | 10,2 | 8,3 | −6,4 |

\* Na walidacji v2 wybierał liczbę drzew (wczesne zatrzymanie), więc ten wynik jest lekko optymistyczny.

### 3. Test według miasta i rynku

| Grupa | Transakcje | v1 MAE | v1 MAPE | v1 MdAPE | v2 MAE | v2 RMSE | v2 MAPE | v2 MdAPE | v2 mediana błędu |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Warszawa | 2 978 | 70 549 | 9,7 | 8,1 | 70 023 | 109 529 | 9,6 | 8,1 | −6,2 |
| Kraków | 1 252 | 62 227 | 10,0 | 7,9 | 61 899 | 88 762 | 10,0 | 7,9 | −6,5 |
| Wrocław | 1 122 | 59 336 | 9,7 | 8,2 | 59 219 | 86 088 | 9,8 | 8,2 | −6,1 |
| Poznań | 754 | 56 366 | 11,3 | 8,7 | 55 949 | 84 157 | 11,1 | 8,6 | −6,6 |
| Gdańsk | 750 | 60 496 | 10,1 | 8,2 | 61 834 | 88 407 | 10,3 | 8,4 | −6,3 |
| Łódź | 631 | 49 309 | 12,5 | 10,1 | 49 701 | 71 560 | 12,7 | 10,3 | −8,0 |
| rynek wtórny | 7 204 | 62 381 | 10,1 | 8,2 | 61 983 | 94 099 | 10,1 | 8,2 | −6,5 |
| rynek pierwotny | 283 | 85 415 | 11,8 | 10,8 | 91 388 | 126 799 | 12,5 | 11,8 | −3,5 |

Różnice w miastach mieszczą się w ±0,2 pp MAPE. Jedyna większa różnica: na rynku pierwotnym (283 transakcje)
v2 jest gorszy o 0,7 pp MAPE.

### 4. Budowa v2

| Element | Wartość |
|---|---|
| Cechy | `miasto` (kategoria), `dzielnica` jako para miasto + dzielnica (kategoria), `metraz`, `pokoje`, `pietro`, `rok_budowy` (liczbowo, bez ln i bez przedziałów) |
| Target | ln(`cena_pln`); wycena = exp(predykcji), czyli mediana ceny przy danych cechach (jak w v1) |
| Hiperparametry (stałe, niestrojone) | learning_rate 0,05; num_leaves 31; min_child_samples 20; random_state 42; deterministic |
| Wczesne zatrzymanie | l2 na ln(ceny) na zbiorze walidacyjnym, stop po 200 rundach bez poprawy, maks. 5 000 drzew |
| Najlepsza iteracja | 265 drzew, l2 ln(ceny) na walidacji 0,02184 |
| Uczony na | wyłącznie trening (38 522); walidacja tylko do zatrzymania |
| Dzielnice nieznane w treningu | 0 w walidacji, 0 w teście |

Ważność cech v2 (gain, % sumy): metraż 74,1; dzielnica 21,2; rok budowy 4,3; piętro 0,4; pokoje 0,0; miasto 0,0.
Miasto ma 0, bo para miasto + dzielnica już je zawiera.

### 5. Cechy otoczenia (`geo.sql`): co policzono

| Kolumna | Definicja |
|---|---|
| `odl_centrum_m` | haversine (m) do centrum miasta: `gus_dzielnice.lat_centrum_miasta`, `lon_centrum_miasta` (jedno centrum na miasto) |
| `odl_stacja_m` | do najbliższej stacji metra lub kolei (`geo_poi.typ` ∈ {metro, kolej}) |
| `odl_metro_m` | do najbliższej stacji metra (`typ = 'metro'`); poza Warszawą brak (NULL) |
| `odl_tramwaj_m` | do najbliższego przystanku tramwajowego (`typ = 'tramwaj'`) |
| `odl_park_m` | do najbliższego parku ≥ 2 ha (`typ = 'park' AND powierzchnia_ha >= 2`) |
| `odl_uczelnia_m` | do najbliższej uczelni (`typ = 'uczelnia'`) |
| `metro_do_700m`, `tramwaj_do_300m`, `park_do_400m` | 0/1: odległość ≤ 700 / 300 / 400 m; brak punktu w mieście = 0 |
| `gestosc_os_km2`, `wskaznik_dochodu` | z `gus_dzielnice` (złączenie po miasto + dzielnica) |
| `geohash6` | geohash, 6 znaków; komórka 360/2¹⁵ × 180/2¹⁵ stopnia, czyli przy szerokościach transakcji (49,95–54,45°) 0,71–0,79 km (wschód–zachód) × 0,61 km (północ–południe) |

Najbliższy punkt szukamy tylko w mieście transakcji. Promień Ziemi 6 371 008,8 m (średni). Na danych:
54 000 wierszy (wszystkie transakcje `rcn_transakcje`), każda transakcja ma dzielnicę w `gus_dzielnice`, braki tylko
w `odl_metro_m` (32 491 transakcji spoza Warszawy).

### 6. Cechy otoczenia według miasta (wszystkie transakcje RCN; mediany odległości w m)

| Miasto | Transakcje | Centrum | Stacja | Metro | Tramwaj | Park ≥ 2 ha | Uczelnia | % metro ≤ 700 m | % tramwaj ≤ 300 m | % park ≤ 400 m | Komórki geohash6 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Warszawa | 21 509 | 7 002 | 1 553 | 2 213 | 913 | 874 | 1 914 | 15,9 | 20,1 | 18,7 | 1 421 |
| Kraków | 9 147 | 5 306 | 3 707 | brak metra | 1 008 | 1 009 | 2 413 | 0,0 | 17,7 | 14,2 | 646 |
| Wrocław | 8 144 | 4 042 | 2 602 | brak metra | 665 | 894 | 1 244 | 0,0 | 26,6 | 19,1 | 530 |
| Poznań | 5 500 | 3 686 | 2 121 | brak metra | 870 | 710 | 1 258 | 0,0 | 21,0 | 22,5 | 350 |
| Gdańsk | 5 381 | 5 091 | 2 331 | brak metra | 1 175 | 1 147 | 2 664 | 0,0 | 16,7 | 14,2 | 431 |
| Łódź | 4 319 | 3 765 | 2 077 | brak metra | 714 | 771 | 1 242 | 0,0 | 27,1 | 21,6 | 379 |

`geo_poi` i `gus_dzielnice` mają też Katowice, ale w `rcn_transakcje` nie ma transakcji z Katowic.

### 7. geohash6 a zbiory

| Zbiór | Transakcje | Komórki | Transakcje w komórce bez transakcji treningowych | … w komórce z < 10 transakcjami treningowymi |
|---|---:|---:|---:|---:|
| trening | 38 522 | 3 640 | 0 | 9 203 |
| walidacja | 7 686 | 2 541 | 65 | 2 080 |
| test | 7 487 | 2 549 | 96 | 2 055 |

Komórki geohash6 są drobne: w walidacji i teście ok. 27% transakcji (2 080 / 7 686 i 2 055 / 7 487) leży w komórce, która w treningu ma mniej niż
10 transakcji. Jako kategoria z własnym poziomem ceny geohash6 będzie więc wymagał wygładzania.

### 8. Czy otoczenie wyjaśnia to, czego v2 nie wyjaśnia? (tylko walidacja, test nietknięty)

Reszta = ln(cena) − ln(wycena v2). Reszta > 0 oznacza, że v2 zaniża wycenę. Na całej walidacji reszta jest dodatnia
(v2 zaniża o ok. 4,6%, bo nie zna czasu transakcji), więc liczą się różnice między grupami, a nie poziom.

| Cecha | Transakcje | Korelacja Spearmana z resztą |
|---|---:|---:|
| odl_centrum_m | 7 686 | −0,157 |
| odl_stacja_m | 7 686 | −0,177 |
| odl_metro_m | 3 092 | −0,142 |
| odl_tramwaj_m | 7 686 | −0,134 |
| odl_park_m | 7 686 | −0,175 |
| odl_uczelnia_m | 7 686 | −0,141 |
| metro_do_700m | 7 686 | 0,105 |
| tramwaj_do_300m | 7 686 | 0,122 |
| park_do_400m | 7 686 | 0,176 |
| gestosc_os_km2 | 7 686 | −0,016 |
| wskaznik_dochodu | 7 686 | −0,013 |

| Flaga | Wartość | Transakcje | Mediana zaniżenia przez v2 (%) |
|---|---:|---:|---:|
| metro ≤ 700 m | 0 | 7 164 | 4,59 |
| metro ≤ 700 m | 1 | 522 | 9,38 |
| tramwaj ≤ 300 m | 0 | 6 100 | 4,22 |
| tramwaj ≤ 300 m | 1 | 1 586 | 7,30 |
| park ≤ 400 m | 0 | 6 274 | 4,00 |
| park ≤ 400 m | 1 | 1 412 | 8,75 |

Odległości korelują z resztą ujemnie: im bliżej centrum, stacji, parku czy tramwaju, tym bardziej v2 zaniża wycenę.
Gęstość i dochód dzielnicy prawie nie korelują z resztą (|ρ| < 0,02), bo są stałe w obrębie dzielnicy, a dzielnicę
v2 już zna. Nowej informacji dostarczają więc cechy liczone dla położenia lokalu, a nie dla dzielnicy. To korelacje
z jedną cechą naraz, a cechy otoczenia są ze sobą powiązane, więc ich wpływu nie wolno sumować. Ile da otoczenie,
pokaże dopiero model z tymi cechami, oceniony na tym samym podziale.

### 9. Decyzje podjęte bez konsultacji (do potwierdzenia)

- Hiperparametry v2 są stałe, niestrojone. Na walidacji ustalamy tylko liczbę drzew. Po strojeniu porównanie
  „sam boosting” mogłoby wypaść trochę lepiej.
- v2 uczy się tylko na treningu, bez douczania na treningu + walidacji, tak jak v1.
- Kryterium zatrzymania to l2 na ln(ceny), a nie MAPE.
- „Odległość do stacji” obejmuje metro i kolej, a flaga `metro_do_700m` tylko metro (poza Warszawą zawsze 0).
- Najbliższy punkt szukamy tylko w mieście transakcji.
- Haversine i geohash liczymy w czystym SQL, bez rozszerzenia DuckDB `spatial` (nie jest zainstalowane, a jego
  instalacja wymaga pobrania z sieci). Geohash sprawdzono na wartościach referencyjnych (test).
- `geo_poi` i `gus_dzielnice` nie mają dat, czyli to jeden stan. Jeśli jakiś przystanek albo stacja powstała w trakcie
  okresu 2023–2026, cecha dla wcześniejszej transakcji „widzi przyszłość”. Dat otwarcia POI: brak w danych.

## SQL i kod

Odtworzenie (z katalogu głównego repozytorium):

```bash
pypyr baza                                                                  # jeśli nie ma domilo.duckdb
cd api && poetry run python -m api.ai.valuation_model.evals.ewaluacja_v2    # tabele 2–4 bez testu (przebieg roboczy)
poetry run python -m api.ai.valuation_model.evals.ewaluacja_v2 --otworz-test  # tabele 1–4; już wykonane, drugi raz odmówi
poetry run python -m api.ai.features.wycena.opis_geo                        # tabele 6–8 (wymaga v2 model.joblib)
cd .. && pypyr test tests="api/tests/test_wycena_modele.py api/tests/test_wycena_geo.py"
```

`ewaluacja_v2.py --otworz-test` zapisał `versions/v2_lightgbm/model.joblib` i `metryki.json` oraz run `v2_lightgbm`
w eksperymencie MLflow `wycena`. Dane wejściowe i metryki są te same co w b2: `zbior.py` (transakcje + `podzial.sql`)
i `metryki.py`.

### v2: `api/api/ai/valuation_model/versions/v2_lightgbm/model.py` (rdzeń)

```python
A = DataFrame({
    "miasto": Categorical(miasto, categories=<miasta z treningu>),
    "dzielnica": Categorical(miasto + " | " + dzielnica, categories=<pary z treningu>),  # nieznana -> NaN
    "metraz": ..., "pokoje": ..., "pietro": ..., "rok_budowy": ...,
})
reg = LGBMRegressor(n_estimators=5000, objective="regression", learning_rate=0.05, num_leaves=31,
                    min_child_samples=20, random_state=42, deterministic=True, force_row_wise=True, n_jobs=4)
reg.fit(A_trening, ln(cena_trening), eval_X=(A_walidacja,), eval_y=(ln(cena_walidacja),),
        categorical_feature=["miasto", "dzielnica"], callbacks=[early_stopping(200)])
wycena = exp(reg.predict(A_nowe, num_iteration=reg.best_iteration_))
```

### Cechy otoczenia: `api/api/ai/features/wycena/geo.sql`

Pełna treść (z komentarzem) jest w pliku. Rdzeń:

```sql
WITH transakcje AS (SELECT id_transakcji, miasto, dzielnica, lat, lon FROM rcn_transakcje),
punkty AS (
    SELECT miasto, typ, lat, lon FROM geo_poi
    WHERE typ IN ('metro', 'kolej', 'tramwaj', 'uczelnia') OR (typ = 'park' AND powierzchnia_ha >= 2)
    UNION ALL
    SELECT DISTINCT miasto, 'centrum', lat_centrum_miasta, lon_centrum_miasta FROM gus_dzielnice
),
odleglosci AS (
    SELECT t.id_transakcji, p.typ,
           2 * 6371008.8 * asin(sqrt(power(sin(radians(p.lat - t.lat) / 2), 2)
               + cos(radians(t.lat)) * cos(radians(p.lat)) * power(sin(radians(p.lon - t.lon) / 2), 2))) AS odl_m
    FROM transakcje t JOIN punkty p ON p.miasto = t.miasto
),
najblizsze AS (
    SELECT id_transakcji,
           min(odl_m) FILTER (WHERE typ = 'centrum') AS odl_centrum_m,
           min(odl_m) FILTER (WHERE typ IN ('metro', 'kolej')) AS odl_stacja_m,
           min(odl_m) FILTER (WHERE typ = 'metro') AS odl_metro_m,
           min(odl_m) FILTER (WHERE typ = 'tramwaj') AS odl_tramwaj_m,
           min(odl_m) FILTER (WHERE typ = 'park') AS odl_park_m,
           min(odl_m) FILTER (WHERE typ = 'uczelnia') AS odl_uczelnia_m
    FROM odleglosci GROUP BY id_transakcji
),
siatka AS (
    SELECT id_transakcji,
           least(floor((lon + 180) / 360 * 32768), 32767)::BIGINT AS lon_i,   -- 15 bitów długości
           least(floor((lat + 90) / 180 * 32768), 32767)::BIGINT AS lat_i     -- 15 bitów szerokości
    FROM transakcje
)
SELECT t.id_transakcji, n.*,  -- odległości
       coalesce(n.odl_metro_m <= 700, false)::INTEGER AS metro_do_700m,
       coalesce(n.odl_tramwaj_m <= 300, false)::INTEGER AS tramwaj_do_300m,
       coalesce(n.odl_park_m <= 400, false)::INTEGER AS park_do_400m,
       g.gestosc_os_km2, g.wskaznik_dochodu,
       <geohash6 z lon_i, lat_i: bity przeplatane od długości, po 5 bitów na znak base32>
FROM transakcje t
LEFT JOIN najblizsze n USING (id_transakcji)
LEFT JOIN siatka s USING (id_transakcji)
LEFT JOIN gus_dzielnice g ON g.miasto = t.miasto AND g.dzielnica = t.dzielnica;
```

Wczytanie w Pythonie: `api.ai.features.wycena.geo.cechy_geo(polacz())`, jeden wiersz na transakcję.

### Tabele 6–7: `api/api/ai/features/wycena/opis_geo.py`

```sql
-- tabela 6
SELECT t.miasto, count(*) AS transakcje,
       round(median(g.odl_centrum_m))::BIGINT, ... ,              -- mediany każdej odległości
       round(100 * avg(g.metro_do_700m), 1), ... ,                -- % flag
       count(DISTINCT g.geohash6), count(*) FILTER (g.odl_metro_m IS NULL)
FROM rcn_transakcje t JOIN (<geo.sql>) g USING (id_transakcji)
GROUP BY t.miasto;

-- tabela 7
WITH z AS (SELECT p.zbior, g.geohash6 FROM (<podzial.sql>) p JOIN (<geo.sql>) g USING (id_transakcji)),
tr AS (SELECT geohash6, count(*) AS n FROM z WHERE zbior = 'trening' GROUP BY geohash6)
SELECT z.zbior, count(*), count(DISTINCT z.geohash6),
       count(*) FILTER (tr.geohash6 IS NULL),
       count(*) FILTER (coalesce(tr.n, 0) < 10)
FROM z LEFT JOIN tr USING (geohash6) GROUP BY z.zbior;
```

### Tabela 8: reszty v2 na walidacji (`opis_geo.py`)

```python
wal = transakcje[zbior == "walidacja"].merge(cechy_geo, on="id_transakcji")
reszta_ln = ln(cena_pln) - ln(v2.predict(wal[KOLUMNY_CECH]))
spearman = wal[cecha].corr(reszta_ln, method="spearman")          # bez braków (odl_metro_m: tylko Warszawa)
mediana_zanizenia_proc = 100 * (exp(median(reszta_ln w grupie flagi)) - 1)
```
