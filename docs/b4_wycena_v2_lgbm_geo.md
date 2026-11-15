# B4. Wycena lokali: otoczenie i sąsiedztwo (v2_lgbm_geo) oraz ablacja rodzin cech

Źródło: `domilo.duckdb` zbudowana z `data/` (eksport 2026-09-30 23:59 Europe/Warsaw) przez `pypyr baza`.
Policzono 2026-11-15. Podział czasowy jak w [b1_dane.md](b1_dane.md): trening 2023-01 – 2025-06 (38 522),
walidacja 2025-07 – 2025-12 (7 686), test 2026-01 – 2026-06 (7 487). Cechy otoczenia opisuje
[b3_wycena_v2_geo.md](b3_wycena_v2_geo.md). Liczby pochodzą z
[`ewaluacja_v2_geo.py`](../api/api/ai/valuation_model/evals/ewaluacja_v2_geo.py) (zapis:
`versions/v2_lgbm_geo/metryki.json` i `ablacja.json`) oraz z zapytań w sekcji [SQL i kod](#sql-i-kod).

## Wnioski

Dodanie otoczenia i cen sąsiednich transakcji do LightGBM obniża błąd wyceny na I półroczu 2026 z 10,2% do 8,6%
(MAPE), a średni błąd w złotych z 63 tys. do 51 tys. zł. Cały ten zysk dają nowe informacje, a nie zmiana metody:
sam boosting (v2_lightgbm) dawał 10,2%. Najwięcej wnoszą ceny sąsiednich transakcji z ostatnich 12 miesięcy.
Bez nich MAPE rośnie do 9,3%, a model wraca do zaniżania cen o ok. 6,3% (mediana błędu), bo to one niosą bieżący
poziom rynku. Cechy położenia (odległości, centrum, dane dzielnicy) dodają mniej: bez nich MAPE rośnie do 8,9%.
Same odległości do przystanków, stacji, parków i uczelni przy pozostałych cechach dodają już niewiele (0,07 pp).
Wariant realistyczny, czyli sąsiedzi tylko spośród transakcji już opublikowanych w rejestrze, wypada tak samo
(8,56% wobec 8,55%). Opóźnienie publikacji więc nie psuje wyniku. Warunek banku (MAPE ≤ 8%) wciąż nie jest
spełniony, model nadal zaniża ceny z 2026 (mediana −4,5%) i nie ma przedziału P10–P90.

## Tabele

### 1. Test (akty 2026-01-01 – 2026-06-30, 7 487 transakcji): ile daje metoda, a ile informacja

MAE i RMSE w zł, MAPE i MdAPE w %. „Mediana błędu” = mediana (wycena − cena) / cena (< 0 = model zaniża).
Test otwarty raz, 2026-11-15, jednym przebiegiem dla wszystkich wariantów. Wariant główny i wybór geohash6
ustalono wcześniej na walidacji.

| Wersja / wariant | Cechy | MAE | RMSE | MAPE | MdAPE | Mediana błędu |
|---|---|---:|---:|---:|---:|---:|
| v0_mediana_dzielnicy (baseline) | dzielnica, metraż | 83 401 | 118 320 | 13,4 | 11,3 | −6,4 |
| v1_liniowa | 6 cech lokalu | 63 252 | 94 999 | 10,17 | 8,30 | −6,35 |
| v2_lightgbm | 6 cech lokalu | 63 095 | 95 538 | 10,16 | 8,30 | −6,43 |
| v2_lgbm_geo, bez sąsiedztwa | + geo | 57 016 | 86 595 | 9,32 | 7,49 | −6,33 |
| v2_lgbm_geo, bez geo | + sąsiedztwo | 52 519 | 81 829 | 8,87 | 6,69 | −3,53 |
| v2_lgbm_geo, bez POI | + sąsiedztwo + centrum i GUS | 51 132 | 80 256 | 8,61 | 6,61 | −4,30 |
| **v2_lgbm_geo (główny)** | **+ geo + sąsiedztwo** | **50 540** | **78 933** | **8,55** | **6,49** | **−4,46** |
| v2_lgbm_geo, sąsiedzi wg publikacji | jak główny, sąsiedzi opublikowani przed dniem aktu | 50 765 | 79 258 | 8,56 | 6,54 | −4,58 |

Rozkład zysku MAPE na teście względem v1 (10,17%):

| Krok | Zmiana MAPE (pp) |
|---|---:|
| v1 → v2_lightgbm (sama metoda) | −0,01 |
| v2_lightgbm → + geo (bez sąsiedztwa) | −0,84 |
| v2_lightgbm → + sąsiedztwo (bez geo) | −1,29 |
| v2_lightgbm → + geo + sąsiedztwo (główny) | −1,61 |

Rodziny częściowo się dublują: obie opisują położenie. Dlatego zyski z osobna (0,84 + 1,29) dają więcej niż zysk
łączny (1,61).

### 2. Ablacja rodzin cech: walidacja i test

Zmiana = wariant − główny (dodatnia = gorzej bez tej rodziny). Na walidacji wszystkie warianty wybierały liczbę drzew,
więc wyniki walidacyjne są lekko optymistyczne.

| Wariant | Usunięte cechy | Drzewa | Walidacja MAPE | Zmiana | Test MAPE | Zmiana | Test MAE | Zmiana MAE |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| główny | — | 261 | 8,72 | — | 8,55 | — | 50 540 | — |
| bez geo | wszystkie z geo.sql: 8 POI + `odl_centrum_m`, `gestosc_os_km2`, `wskaznik_dochodu` | 218 | 9,25 | +0,53 | 8,87 | +0,32 | 52 519 | +1 978 |
| bez sąsiedztwa | `sasiedzi_mediana_ceny_m2`, `sasiedzi_liczba` | 352 | 9,16 | +0,44 | 9,32 | +0,77 | 57 016 | +6 476 |
| bez POI | `odl_stacja_m`, `odl_metro_m`, `odl_tramwaj_m`, `odl_park_m`, `odl_uczelnia_m`, 3 flagi | 254 | 8,82 | +0,10 | 8,61 | +0,07 | 51 132 | +591 |
| sąsiedzi wg publikacji | — (inna definicja sąsiedztwa) | 255 | 8,69 | −0,03 | 8,56 | +0,01 | 50 765 | +225 |

Kolejność ważności rodzin różni się między walidacją a testem: na walidacji więcej traci „bez geo”, na teście
„bez sąsiedztwa”. Na teście sąsiedztwo kompensuje też wzrost cen. Mediana błędu bez sąsiedztwa wynosi −6,33%,
z sąsiedztwem −4,46%.

### 3. Wybór geohash6 (walidacja, przed otwarciem testu)

| Wariant | Drzewa | MAE | MAPE | MdAPE | Mediana błędu |
|---|---:|---:|---:|---:|---:|
| **wszystkie rodziny, bez geohash6** (wybrany) | 261 | 46 772 | 8,7 | 6,0 | −3,0 |
| wszystkie rodziny + geohash6 jako kategoria | 192 | 48 157 | 8,9 | 6,2 | −2,9 |

geohash6 jako kategoria pogarsza wynik (drobne komórki, zob. b3, tabela 7), więc go nie używamy.

### 4. Test według miasta i rynku: v1 a v2_lgbm_geo

| Grupa | Transakcje | v1 MAE | v1 MAPE | v1 MdAPE | v2_lgbm_geo MAE | v2_lgbm_geo RMSE | v2_lgbm_geo MAPE | v2_lgbm_geo MdAPE | v2_lgbm_geo mediana błędu |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Warszawa | 2 978 | 70 549 | 9,7 | 8,1 | 54 902 | 91 279 | 7,8 | 6,2 | −4,5 |
| Kraków | 1 252 | 62 227 | 10,0 | 7,9 | 49 984 | 72 215 | 8,4 | 6,1 | −4,6 |
| Wrocław | 1 122 | 59 336 | 9,7 | 8,2 | 47 540 | 69 976 | 8,3 | 6,3 | −3,9 |
| Poznań | 754 | 56 366 | 11,3 | 8,7 | 47 011 | 71 986 | 9,7 | 7,1 | −4,9 |
| Gdańsk | 750 | 60 496 | 10,1 | 8,2 | 49 095 | 68 269 | 8,7 | 6,7 | −3,7 |
| Łódź | 631 | 49 309 | 12,5 | 10,1 | 42 328 | 61 782 | 11,3 | 8,5 | −5,9 |
| rynek wtórny | 7 204 | 62 381 | 10,1 | 8,2 | 49 281 | 77 488 | 8,4 | 6,4 | −4,5 |
| rynek pierwotny | 283 | 85 415 | 11,8 | 10,8 | 82 605 | 109 467 | 11,5 | 10,6 | −3,4 |

v2_lgbm_geo jest lepszy od v1 w każdym mieście i na obu rynkach. Tylko Warszawa schodzi poniżej 8% MAPE.

### 5. Ważność cech v2_lgbm_geo (gain, % sumy)

| Cecha | Udział |
|---|---:|
| metraz | 72,9 |
| dzielnica | 14,4 |
| sasiedzi_mediana_ceny_m2 | 7,5 |
| rok_budowy | 4,1 |
| pietro | 0,3 |
| odl_stacja_m | 0,3 |
| odl_centrum_m | 0,2 |
| odl_park_m | 0,2 |
| odl_tramwaj_m | 0,1 |
| odl_uczelnia_m | 0,1 |
| pozostałe 9 cech | 0,0 każda (po zaokrągleniu) |

### 6. Cechy sąsiedztwa: definicja i pokrycie

| Element | Wartość |
|---|---|
| Sąsiedzi transakcji T | 20 najbliższych (haversine) transakcji z tego samego miasta, z dniem aktu w [dzień aktu T − 12 mies., dzień aktu T) |
| Wykluczone | T, transakcje z tego samego dnia i późniejsze; transakcje opublikowane po dniu eksportu (spoza `podzial.sql`) |
| Out-of-fold (tylko trening) | fold = `md5_number(id_transakcji) % 5`; sąsiad transakcji treningowej musi być z innego foldu |
| Walidacja i test | pula = wszystkie wcześniejsze transakcje (trening, walidacja, test), bez wykluczania foldu |
| Remisy odległości | bliższa, potem nowsza, potem mniejsze `id_transakcji` (20 786 różnych punktów na 54 000 transakcji, więc remisy są częste) |
| Cechy | `sasiedzi_mediana_ceny_m2` (mediana `cena_m2`), `sasiedzi_liczba` (0–20) |
| Wariant „wg publikacji” | dodatkowo `data_publikacji_rejestru` sąsiada < dzień aktu T |

| Sąsiedzi | Zbiór | Transakcje | Bez sąsiadów | Mniej niż 20 sąsiadów |
|---|---|---:|---:|---:|
| wg daty aktu | trening | 38 522 | 23 | 176 |
| wg daty aktu | walidacja | 7 686 | 0 | 0 |
| wg daty aktu | test | 7 487 | 0 | 0 |
| wg daty publikacji | trening | 38 522 | 2 577 | 3 290 |
| wg daty publikacji | walidacja | 7 686 | 0 | 0 |
| wg daty publikacji | test | 7 487 | 0 | 0 |

Braki są w treningu z początku 2023, bo dane RCN zaczynają się 2023-01-01. Wcześniejszych transakcji brak w danych.
Opóźnienie publikacji w `rcn_transakcje` wynosi 60–120 dni (mediana 90).

Kontrola wycieku (`api/tests/test_wycena_sasiedztwo.py`, na bazie zbudowanej od zera z `data/`): dla 20 losowych
transakcji (`random_state=20261115`) żaden sąsiad nie ma daty ≥ daty transakcji ani nie jest nią samą. Wszyscy są
z 12 miesięcy wstecz, a w treningu z innego foldu. Niezależne przeliczenie w numpy daje ten sam zbiór 20 sąsiadów
i tę samą medianę. Przypadki brzegowe (ten sam dzień, dokładnie 12 miesięcy, inne miasto, remisy, fold, wariant
publikacji) sprawdzają testy na danych syntetycznych.

### 7. Decyzje podjęte bez konsultacji (do potwierdzenia)

- **Out-of-fold**: 5 foldów losowych (stały skrót md5 z `id_transakcji`), a nie przestrzennych ani czasowych.
  W treningu sąsiedzi pochodzą więc z 4/5 puli, czyli średnio leżą nieco dalej niż w walidacji i teście.
- **Główny wariant liczy sąsiadów wg daty aktu**, jak w poleceniu. Wariant „wg publikacji” odpowiada temu, co
  Domilo naprawdę wie w dniu wyceny. Daje ten sam wynik, więc proponuję go jako definicję produkcyjną.
- **geohash6** odrzucony na walidacji (tabela 3). „Bez geo” usuwa wszystkie kolumny geo.sql, „bez POI” tylko
  odległości do punktów z `geo_poi` i 3 flagi.
- **Hiperparametry** jak w v2_lightgbm (stałe). Każdy wariant ma własne wczesne zatrzymanie na walidacji.
- **`current.yaml` nadal wskazuje v1**. v2_lgbm_geo jest lepszy na teście, ale do wyceny lokali Domilo potrzebuje
  cech policzonych dla lokalu (współrzędne budynku, sąsiedzi z RCN znani w dniu wyceny), a tego jeszcze nie ma.

## SQL i kod

Odtworzenie (z katalogu głównego repozytorium):

```bash
pypyr baza                                                                     # jeśli nie ma domilo.duckdb
cd api && poetry run python -m api.ai.valuation_model.evals.ewaluacja_v2_geo    # tabele 2–6 bez testu
poetry run python -m api.ai.valuation_model.evals.ewaluacja_v2_geo --otworz-test  # tabele 1–6; już wykonane, drugi raz odmówi
cd .. && pypyr test tests="api/tests/test_wycena_sasiedztwo.py api/tests/test_wycena_modele.py"
```

`--otworz-test` zapisał `versions/v2_lgbm_geo/model.joblib`, `metryki.json` (wariant główny) i `ablacja.json`
(wszystkie warianty) oraz runy `v2_lgbm_geo` i `v2_lgbm_geo/<wariant>` w eksperymencie MLflow `wycena`.

### Sąsiedztwo: `api/api/ai/features/wycena/sasiedztwo.sql` (rdzeń; pełna treść z komentarzem w pliku)

```sql
WITH baza AS (
    SELECT t.id_transakcji, t.miasto, t.lat, t.lon, t.data_aktu::DATE AS dzien_aktu,
           t.data_publikacji_rejestru, t.cena_m2, p.zbior, md5_number(t.id_transakcji) % 5 AS fold
    FROM rcn_transakcje t JOIN (<podzial.sql>) p USING (id_transakcji)
),
pary AS (
    SELECT t.id_transakcji, s.id_transakcji AS id_sasiada, s.cena_m2, s.dzien_aktu AS dzien_sasiada,
           2 * 6371008.8 * asin(sqrt(power(sin(radians(s.lat - t.lat) / 2), 2)
               + cos(radians(t.lat)) * cos(radians(s.lat)) * power(sin(radians(s.lon - t.lon) / 2), 2))) AS odl_m
    FROM baza t JOIN baza s
      ON s.miasto = t.miasto
     AND s.dzien_aktu < t.dzien_aktu                                   -- tylko wcześniejsze dni
     AND s.dzien_aktu >= (t.dzien_aktu - INTERVAL 12 MONTH)::DATE      -- 12 miesięcy wstecz
     AND (t.zbior <> 'trening' OR s.fold <> t.fold)                    -- out-of-fold w treningu
     AND (NOT coalesce(getvariable('sasiedzi_wg_publikacji'), false)
          OR s.data_publikacji_rejestru < t.dzien_aktu)                 -- wariant „wg publikacji”
),
najblizsi AS (
    SELECT id_transakcji,
           min_by(struct_pack(id := id_sasiada, cena_m2 := cena_m2),
                  struct_pack(o := odl_m, d := -epoch(dzien_sasiada), i := id_sasiada), 20) AS sasiedzi
    FROM pary GROUP BY id_transakcji
)
SELECT b.id_transakcji,
       list_aggregate(list_transform(n.sasiedzi, lambda x: x.cena_m2), 'median') AS sasiedzi_mediana_ceny_m2,
       coalesce(len(n.sasiedzi), 0) AS sasiedzi_liczba,
       coalesce(list_transform(n.sasiedzi, lambda x: x.id), []::VARCHAR[]) AS sasiedzi_id
FROM baza b LEFT JOIN najblizsi n USING (id_transakcji);
```

Wczytanie: `api.ai.features.wycena.sasiedztwo.cechy_sasiedztwa(con, wg_publikacji=False)`. Zbiór do modelu:
`api.ai.features.wycena.zbior.wczytaj_transakcje_z_cechami(con)` (transakcje + `geo.sql` + `sasiedztwo.sql`).

### Model: `api/api/ai/valuation_model/versions/v2_lgbm_geo/model.py` (rdzeń)

```python
class ModelLightGBMGeo(ModelLightGBM):          # ln(ceny), wczesne zatrzymanie, hiperparametry jak v2_lightgbm
    wersja = "v2_lgbm_geo"
    cechy = KOLUMNY_CECH + cechy_liczbowe (+ cechy_kategorii)
# główny: cechy_liczbowe = RODZINA_POI + RODZINA_GEO_BEZ_POI + RODZINA_SASIEDZTWO, cechy_kategorii = ()
```

### Ablacja: `api/api/ai/valuation_model/evals/ewaluacja_v2_geo.py`

```python
kandydaci = [pelny, pelny + geohash6]                  # wybór: min MAPE na walidacji -> pelny
warianty = [pelny,
            pelny - (RODZINA_POI + RODZINA_GEO_BEZ_POI),  # bez_geo
            pelny - RODZINA_SASIEDZTWO,                   # bez_sasiedztwa
            pelny - RODZINA_POI,                          # bez_poi
            pelny, sąsiedzi wg publikacji]                # sasiedzi_wg_publikacji
for w in warianty:
    m = ModelLightGBMGeo(cechy_liczbowe=w.cechy).fit(X_trening, y_trening, X_walidacja, y_walidacja)
    metryki(y, m.predict(X)) dla trening, walidacja, test
```

### Pokrycie sąsiedztwa (tabela 6)

```python
d = wczytaj_transakcje_z_cechami(con, sasiedzi_wg_publikacji=...)
bez_sasiadow = (d["sasiedzi_liczba"] == 0).sum();  mniej_niz_20 = (d["sasiedzi_liczba"] < 20).sum()
```

```sql
-- opóźnienie publikacji i liczba różnych punktów
SELECT min(date_diff('day', data_aktu, data_publikacji_rejestru)),
       median(date_diff('day', data_aktu, data_publikacji_rejestru)),
       max(date_diff('day', data_aktu, data_publikacji_rejestru)),
       count(*), count(DISTINCT (lat, lon)), min(data_aktu)
FROM rcn_transakcje;
```
