# B2. Wycena lokali: baseline (v0) i regresja liniowa (v1)

Źródło: `domilo.duckdb` zbudowana z `data/` (eksport 2026-09-30 23:59 Europe/Warsaw) przez `pypyr baza`.
Policzono 2026-11-15. Dane i podział czasowy opisuje [b1_dane.md](b1_dane.md). Liczby pochodzą z
[`ewaluacja.py`](../api/api/ai/valuation_model/evals/ewaluacja.py) i zapytań w sekcji [SQL i kod](#sql-i-kod).

## Wnioski

Regresja liniowa (v1) wycenia mieszkania wyraźnie lepiej niż prosta reguła „mediana ceny m² dzielnicy × metraż” (v0).
Na transakcjach z I półrocza 2026 średni błąd względny spada z 13,4% do 10,2%, a średni błąd w złotych z 83 tys. do
63 tys. zł. v1 wygrywa w każdym mieście i na obu rynkach. Do warunku banku (MAPE ≤ 8%) wciąż brakuje 2,2 punktu
procentowego. Główna przyczyna jest znana: oba modele nie uwzględniają czasu i zaniżają wyceny z 2026 o około 6%
(mediana błędu −6,3% i −6,4%), czyli mniej więcej o wzrost cen od okresu treningowego. v1 nie ma jeszcze przedziału
P10–P90 ani odpowiedzi „nie wiem”, a operatów kontrolnych banku jeszcze na nim nie liczyliśmy.

## Tabele

### 1. Metryki na zbiorze testowym (akty 2026-01-01 – 2026-06-30, 7 487 transakcji)

MAE i RMSE w zł, MAPE i MdAPE w %. „Mediana błędu” = mediana (wycena − cena) / cena: wartość ujemna oznacza, że model
zaniża wycenę.

| Wersja | MAE | RMSE | MAPE | MdAPE | Mediana błędu |
|---|---:|---:|---:|---:|---:|
| v0_mediana_dzielnicy (baseline) | 83 401 | 118 320 | 13,4 | 11,3 | −6,4 |
| **v1_liniowa** | **63 252** | **94 999** | **10,2** | **8,3** | −6,3 |

### 2. Wszystkie zbiory

| Wersja | Zbiór | Transakcje | MAE | RMSE | MAPE | MdAPE | Mediana błędu |
|---|---|---:|---:|---:|---:|---:|---:|
| v0_mediana_dzielnicy | trening | 38 522 | 75 740 | 105 863 | 13,7 | 11,0 | 0,0 |
| v0_mediana_dzielnicy | walidacja | 7 686 | 80 020 | 111 434 | 13,6 | 11,0 | −4,5 |
| v0_mediana_dzielnicy | test | 7 487 | 83 401 | 118 320 | 13,4 | 11,3 | −6,4 |
| v1_liniowa | trening | 38 522 | 52 572 | 75 274 | 9,9 | 7,3 | −0,5 |
| v1_liniowa | walidacja | 7 686 | 57 814 | 84 156 | 10,2 | 7,6 | −4,7 |
| v1_liniowa | test | 7 487 | 63 252 | 94 999 | 10,2 | 8,3 | −6,3 |

Na treningu mediana błędu jest bliska zera, ale na walidacji (II półrocze 2025) spada do około −4,6%, a na teście do
około −6,4%. Rośnie razem z odległością od okresu treningowego, co odpowiada wzrostowi cen opisanemu w
[b1_dane.md](b1_dane.md) (tabela 2b: mediana ceny m² w teście jest o 6,0–8,4% wyższa niż w treningu).

### 3. Test według miasta i rynku

| Grupa | Transakcje | v0 MAE | v0 MAPE | v0 MdAPE | v1 MAE | v1 RMSE | v1 MAPE | v1 MdAPE | v1 mediana błędu |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Warszawa | 2 978 | 94 658 | 13,1 | 11,4 | 70 549 | 109 038 | 9,7 | 8,1 | −6,1 |
| Kraków | 1 252 | 83 039 | 13,5 | 11,2 | 62 227 | 89 160 | 10,0 | 7,9 | −6,3 |
| Wrocław | 1 122 | 76 928 | 12,6 | 10,3 | 59 336 | 87 593 | 9,7 | 8,2 | −6,0 |
| Poznań | 754 | 71 279 | 14,2 | 11,2 | 56 366 | 83 034 | 11,3 | 8,7 | −6,8 |
| Gdańsk | 750 | 83 806 | 13,9 | 11,9 | 60 496 | 83 605 | 10,1 | 8,2 | −6,6 |
| Łódź | 631 | 56 506 | 14,6 | 11,8 | 49 309 | 70 762 | 12,5 | 10,1 | −7,7 |
| rynek wtórny | 7 204 | 82 611 | 13,4 | 11,2 | 62 381 | 93 997 | 10,1 | 8,2 | −6,4 |
| rynek pierwotny | 283 | 103 522 | 14,3 | 12,1 | 85 415 | 117 656 | 11,8 | 10,8 | −3,1 |

Pełne metryki v0 z RMSE i medianą błędu wypisuje `ewaluacja.py` (sekcja „Metryki na teście: miasta i rynek”).
Najsłabiej v1 wycenia Łódź (MAPE 12,5%) i rynek pierwotny (11,8%).

### 4. Wybór postaci metrażu w v1 (zbiór walidacyjny)

| Metraż w modelu | MAE | RMSE | MAPE | MdAPE | Mediana błędu |
|---|---:|---:|---:|---:|---:|
| **ln(metraż)** | 57 814 | 84 156 | 10,2 | 7,6 | −4,7 |
| metraż w m² | 87 807 | 149 361 | 13,4 | 10,6 | −5,5 |

Przy celu ln(ceny) cena rośnie z metrażem prawie proporcjonalnie, więc ln(metrażu) pasuje lepiej niż metraż w m².
Wariant wybraliśmy na walidacji, a zbioru testowego nie używaliśmy do żadnego wyboru.

### 5. Budowa v1

**Cechy:** ln(metraż), pokoje, piętro (liczbowo), przedział roku budowy (0/1) i dzielnica (0/1). Cel to ln(ceny
transakcyjnej), a wycena = exp(prognozy). Model: `sklearn.linear_model.LinearRegression(fit_intercept=False)`, czyli
zwykła metoda najmniejszych kwadratów. Każda dzielnica ma własny poziom ceny, który pełni rolę wyrazu wolnego.

**Przedziały roku budowy** (granice wyznaczone przez typową zabudowę; w danych nie ma budynków z lat 1940–1949):

| Przedział | Transakcje w treningu | Mediana ceny m² w treningu | Współczynnik ln | Efekt na cenę vs 1970–1989 |
|---|---:|---:|---:|---:|
| do 1944 | 3 749 | 14 464 | 0,1434 | +15,4% |
| 1945–1969 | 6 450 | 12 284 | −0,0072 | −0,7% |
| 1970–1989 (odniesienie) | 8 537 | 12 277 | 0 | 0 |
| 1990–2009 | 7 224 | 14 320 | 0,1486 | +16,0% |
| 2010–2019 | 7 812 | 15 504 | 0,2485 | +28,2% |
| od 2020 | 4 750 | 15 318 | 0,2288 | +25,7% |

**Pozostałe współczynniki** (przy tej samej dzielnicy i przedziale roku):

| Cecha | Współczynnik ln | Znaczenie |
|---|---:|---|
| ln(metraż) | 0,9260 | metraż większy o 1% → cena wyższa o ok. 0,93% |
| pokoje | 0,0005 | +0,1% za pokój: przy tym samym metrażu liczba pokoi prawie nie zmienia ceny |
| piętro | 0,0076 | +0,8% za piętro |

R² dla ln(ceny) na zbiorze treningowym: 0,9332.

**Dzielnice z < 30 transakcjami w treningu → „reszta miasta”.** Dzielnicę rozpoznajemy po parze (miasto, dzielnica),
bo te same nazwy występują w kilku miastach (101 par, 98 nazw). Dzielnica z mniej niż 30 transakcjami treningowymi
miałaby niestabilny własny poziom ceny, więc łączymy ją z innymi takimi dzielnicami tego samego miasta w jedną
kategorię „reszta miasta”. W treningu dotyczy to 3 dzielnic:

| Miasto | Dzielnica | Transakcje w treningu | Kategoria w modelu |
|---|---|---:|---|
| Gdańsk | Letnica | 27 | Gdańsk \| reszta miasta (38 transakcji) |
| Gdańsk | Młode Miasto | 11 | Gdańsk \| reszta miasta (38 transakcji) |
| Łódź | Księży Młyn | 28 | Łódź \| reszta miasta (28 transakcji) |

Model ma 100 kategorii dzielnic (98 dzielnic + 2 „reszty miasta”). „Resztą miasta” wyceniamy 66 transakcji
z treningu, 30 z walidacji i 33 z testu. Dzielnica, której nie było w treningu, też dostaje „resztę miasta”. Jeśli
jej miasto nie ma „reszty”, dostaje średni poziom dzielnic miasta ważony liczbą transakcji („średnia miasta”). Na
walidacji i teście takich przypadków nie ma (0). Miasto nieznane w treningu daje błąd. Młode Miasto ma 11 transakcji
w treningu, ale 21 w samym teście (zapytanie w sekcji SQL), więc ta dzielnica szybko rośnie i przy następnym
uczeniu może dostać własną kategorię.

**v0 (baseline):** mediana `cena_pln / metraz` w parze (miasto, dzielnica) ze zbioru treningowego × metraż. Dla
dzielnicy spoza treningu bierzemy medianę miasta.

### 6. Kontrakt modelu (`api/api/ai/valuation_model/base.py`)

| Metoda | Zwraca | v0 | v1 |
|---|---|---|---|
| `fit(X, y)` | self; `X` = kolumny `miasto, dzielnica, metraz, pokoje, pietro, rok_budowy`, `y` = cena transakcyjna w PLN | ✓ | ✓ |
| `predict(X)` | wycena w PLN (tablica) | ✓ | ✓ |
| `predict_interval(X)` | DataFrame `p10, p50, p90` w PLN | `NotImplementedError` | `NotImplementedError` |
| `explain(X)` | z czego wynika wycena, wiersz na lokal | mediana m², źródło mediany (dzielnica / miasto), metraż | wkłady do ln(wyceny): dzielnica, metraż, pokoje, piętro, rok budowy (suma = ln wyceny) |
| `zapisz` / `wczytaj` | plik joblib | ✓ | ✓ |

Te same kolumny wejściowe da się zbudować dla lokali Domilo (`pms_lokale` + `pms_budynki.miasto`, `dzielnica`,
`rok_oddania`). Dzięki temu model wyceni też lokale z operatów kontrolnych.

## SQL i kod

Odtworzenie (z katalogu głównego repozytorium):

```bash
pypyr baza                                                   # jeśli nie ma domilo.duckdb
cd api && poetry run python -m api.ai.valuation_model.evals.ewaluacja   # tabele 1–5, zapis modeli i metryk
cd .. && pypyr test tests=api/tests/test_wycena_modele.py                # testy kontraktu, v0, v1, metryk
```

Skrypt `ewaluacja.py` zapisuje `versions/v0_mediana_dzielnicy/` i `versions/v1_liniowa/`: pliki `model.joblib`
(nauczony model) i `metryki.json` (metryki dla każdego zbioru). Wersję używaną obecnie wskazuje
[`current.yaml`](../api/api/ai/valuation_model/current.yaml).

### Dane: `api/api/ai/features/wycena/zbior.py`

```sql
SELECT t.id_transakcji, p.zbior, t.data_aktu, t.data_publikacji_rejestru,
       t.miasto, t.dzielnica, t.metraz, t.pokoje, t.pietro, t.rok_budowy, t.rynek,
       t.cena_pln, t.cena_m2
FROM rcn_transakcje t JOIN (<podzial.sql>) p USING (id_transakcji)
ORDER BY t.data_aktu, t.id_transakcji;
```

`(<podzial.sql>)` = treść [`podzial.sql`](../api/api/ai/features/wycena/podzial.sql) (w b1_dane.md).

### Metryki: `api/api/ai/valuation_model/evals/metryki.py`

```python
blad = wycena - cena
blad_wzgl = abs(blad) / cena
MAE = mean(abs(blad)); RMSE = sqrt(mean(blad**2))
MAPE = 100 * mean(blad_wzgl); MdAPE = 100 * median(blad_wzgl)
mediana_bledu = 100 * median(blad / cena)
```

### v0: `versions/v0_mediana_dzielnicy/model.py` (rdzeń)

```python
cena_m2 = y / X["metraz"]
mediana_dzielnicy = cena_m2.groupby([X["miasto"], X["dzielnica"]]).median()
mediana_miasta = cena_m2.groupby(X["miasto"]).median()
wycena = mediana_dzielnicy[(miasto, dzielnica)] (albo mediana_miasta[miasto]) * metraz
```

### v1: `versions/v1_liniowa/model.py` (rdzeń)

```python
liczby = X.groupby(["miasto", "dzielnica"]).size()
male = liczby[liczby < 30]                       # -> "miasto | reszta miasta"
A = [ln(metraz), pokoje, pietro,
     rok_budowy=<przedział> (0/1, bez 1970–1989),
     dzielnica=<miasto | dzielnica albo reszta miasta> (0/1, wszystkie)]
reg = LinearRegression(fit_intercept=False).fit(A, ln(cena_pln))
wycena = exp(A_nowe @ reg.coef_)
```

### Wybór metrażu i ewaluacja: `api/api/ai/valuation_model/evals/ewaluacja.py`

```python
df = wczytaj_transakcje(polacz())
tr = df[df.zbior == "trening"]
# wybór postaci metrażu na walidacji (tabela 4)
for metraz_log in (True, False):
    ModelLiniowy(metraz_log=metraz_log).fit(tr[KOLUMNY_CECH], tr.cena_pln) -> metryki na walidacji
# modele końcowe: tylko trening; metryki na trening / walidacja / test, test także per miasto i rynek
ModelMedianaDzielnicy().fit(...);  ModelLiniowy(metraz_log=<wybrany>).fit(...)
```

### R² ln(ceny) na treningu (sekcja 5)

```python
df = wczytaj_transakcje(polacz()); tr = df[df.zbior == "trening"]
m = ModelWyceny.wczytaj("api/api/ai/valuation_model/versions/v1_liniowa/model.joblib")
p = np.log(m.predict(tr[list(KOLUMNY_CECH)])); y = np.log(tr.cena_pln)
r2 = 1 - ((y - p) ** 2).sum() / ((y - y.mean()) ** 2).sum()   # 0,9332
```

### Przedziały roku budowy w treningu (sekcja 5)

```sql
SELECT CASE WHEN rok_budowy <= 1944 THEN 'do 1944' WHEN rok_budowy <= 1969 THEN '1945–1969'
            WHEN rok_budowy <= 1989 THEN '1970–1989' WHEN rok_budowy <= 2009 THEN '1990–2009'
            WHEN rok_budowy <= 2019 THEN '2010–2019' ELSE 'od 2020' END AS przedzial,
       count(*) AS transakcje_trening, round(median(cena_m2)) AS mediana_ceny_m2
FROM rcn_transakcje
WHERE data_aktu >= TIMESTAMP '2023-01-01' AND data_aktu < TIMESTAMP '2025-07-01'
  AND data_publikacji_rejestru < TIMESTAMP '2026-10-01'
GROUP BY ALL ORDER BY min(rok_budowy);
```

### Małe dzielnice w treningu i teście (sekcja 5)

```sql
SELECT miasto, dzielnica,
       count(*) FILTER (data_aktu < TIMESTAMP '2025-07-01') AS trening,
       count(*) FILTER (data_aktu >= TIMESTAMP '2026-01-01' AND data_publikacji_rejestru < TIMESTAMP '2026-10-01') AS test
FROM rcn_transakcje
WHERE (miasto, dzielnica) IN (SELECT (miasto, dzielnica) FROM rcn_transakcje
                              WHERE data_aktu < TIMESTAMP '2025-07-01' GROUP BY ALL HAVING count(*) < 30)
GROUP BY ALL;
-- Gdańsk Letnica 27 / 8; Gdańsk Młode Miasto 11 / 21; Łódź Księży Młyn 28 / 4 (razem w teście 33)
```
