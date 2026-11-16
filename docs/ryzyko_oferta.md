# GET /risk: uplift, wartość oczekiwana oferty i zalecana akcja dla najmu

Stan: 2026-11-16, dzień oceny 2026-09-30 (dzień eksportu danych). Część `oferta` odpowiedzi `GET /risk/{id_najmu}` liczy
[`retention_bc/oferta_najmu.py`](../api/api/contexts_boundaries/retention_bc/oferta_najmu.py). Przegląd wszystkich
aktywnych najmów i przykłady pochodzą z
[`retention_bc/przeglad_ofert.py`](../api/api/contexts_boundaries/retention_bc/przeglad_ofert.py), a wyniki są
w `retention_bc/wyniki/oferty_aktywnych.parquet` i `przyklady_oferty.json`.

## Wnioski

1. Dla każdego aktywnego najmu `/risk` pokazuje teraz, o ile oferta zmienia szansę przedłużenia (uplift), ile jest
   warta w złotych (EV) i co zrobić. Przy obecnych założeniach (rabat 1 800 zł rocznie, odejście 4 920 zł)
   **„rabat” wychodzi tylko dla 56 z 6 578 aktywnych najmów**. 628 najmów dostaje „nie budzić”, a pozostałe
   „bez rabatu”. To zgadza się z [polityka_rabatow.md](polityka_rabatow.md): rabat w tej wysokości prawie nigdzie
   się nie zwraca.
2. **Zalecenia „rabat” są słabe.** Mediana EV to 84 zł na najem, a razem 56 najmów daje +5 640 zł przy spodziewanym
   koszcie rabatów 72 070 zł. Najmy z dodatnim EV nie dały w teście 2025 ani jednego dodatkowego przedłużenia.
   Dlatego odpowiedź API mówi wprost, że to kandydaci do testu, a nie pewny zysk.
3. **2 419 najmów (37%) wykracza poza dane, na których uczono model.** To głównie najmy krótsze niż 304 dni oraz
   najemcy bez pełnych 3 miesięcy danych z portalu. Model zna tylko najmy 60 dni przed końcem umowy. Dla takich
   najmów API nie zgaduje: daje „bez rabatu” z informacją, że zalecenie policzymy w dniu migawki. Bez tego
   zabezpieczenia 73,5% nowych najemców bez danych z portalu trafiałoby do „nie budzić” tylko z powodu braku danych.
4. **„Nie budzić” opiera się głównie na niskiej aktywności w portalu** (np. 2 logowania w 3 miesiące). Próg to dolne
   20% upliftu, czyli uplift ≤ −6,43 p.p. Wybraliśmy go sami, nie podała go firma. W teście 2025 oferta w tej grupie
   rzeczywiście obniżyła przedłużenia z 57,7% do 47,7%, ale ta różnica może być przypadkowa. Próg trzeba potwierdzić.
5. **Budżetu rabatów nie ustalono**, więc warunku „mieści się w budżecie” na razie nie sprawdzamy. Mechanizm jest
   gotowy: oferty idą od najwyższego EV, aż wyczerpie się kwota z `zalozenia.yaml`.

## Wyniki

### Jak API wybiera akcję

| Krok | Warunek | Akcja | Uzasadnienie (jedno zdanie) |
|---:|---|---|---|
| 0 | cecha najmu poza zakresem danych uczących v3 (brak, którego w treningu nie było, albo wartość poza [min, max] treningu) | bez rabatu | które cechy wykraczają poza zakres i kiedy będzie zalecenie (dzień migawki) |
| 1 | uplift ≤ −6,43 p.p. (`PROG_NIE_BUDZIC`) | **nie budzić** | o ile oferta obniża szansę i trzy cechy, które najbardziej ją obniżają |
| 2 | EV > 0 i oferta mieści się w rocznym budżecie (budżet nieustalony = bez limitu, z adnotacją) | **rabat** | o ile oferta podnosi szansę, EV i trzy cechy, które najbardziej ją podnoszą |
| 3 | pozostałe | **bez rabatu** | uplift, szansa przedłużenia z ofertą, EV i trzy cechy o największym wpływie (z kierunkiem: podnosi / obniża) |

- **EV** = uplift × R − D × P(przedłuży | oferta) − k, gdzie R = 4 920 zł, D = 1 800 zł, k = 60 zł
  (`retention_bc/zalozenia.yaml`, założenia od użytkownika).
- **Uplift i obie szanse** pochodzą z `v3_uplift_tlearner`. **Cechy v1** liczymy na dzień decyzji: migawkę (koniec
  okresu − 60 dni), a gdy migawka jeszcze nie nastąpiła, na dzień oceny.
- **Trzy cechy:** wkład cechy w uplift to SHAP z LightGBM dla modelu „z ofertą” i „bez oferty”, przeliczony na
  punkty procentowe. Wkłady razem ze stałą sumują się dokładnie do upliftu.
- **Budżet:** oferty z EV > 0 dla najmów kończących się w ciągu 365 dni układamy od najwyższego EV. Oferta mieści
  się w budżecie, gdy suma D × P(przedłuży | oferta) do niej włącznie nie przekracza budżetu.

### Zalecenia dla aktywnych najmów (dzień oceny 2026-09-30)

| | Najmy | Rabat | Bez rabatu | w tym poza zakresem modelu | Nie budzić |
|---|---:|---:|---:|---:|---:|
| Wszystkie aktywne B2C / B2B | 6 578 | 56 | 5 894 | 2 419 | 628 |
| B2C | 5 282 | 38 | 4 725 | — | 519 |
| B2B | 1 296 | 18 | 1 169 | — | 109 |
| Koniec okresu w ciągu 365 dni | 6 056 | 56 | 5 380 | 1 918 | 620 |

| Akcja (wszystkie aktywne) | Mediana upliftu | Mediana EV |
|---|---:|---:|
| Rabat | +32,1 p.p. | 84 zł |
| Bez rabatu | +6,4 p.p. | −878 zł |
| Nie budzić | −12,7 p.p. | −1 718 zł |

U 5 472 z 6 578 najmów migawka jest jeszcze przed nami. Dla nich zalecenie opiera się na stanie z dnia oceny i może
się zmienić do dnia decyzji.

**Dlaczego najmy wypadają poza zakres modelu** (jeden najem może mieć kilka powodów):

| Cecha poza zakresem treningu | Zakres w treningu v3 | Brak danych | Poniżej | Powyżej | Najmy |
|---|---|---:|---:|---:|---:|
| `staz_dni` | 304 – 2 131 dni | 0 | 2 301 | 47 | 2 348 |
| `portal_miesiace_3m` | zawsze 3 | 0 | 925 | 0 | 925 |
| `portal_logowania_3m` | 0 – 66, bez braków | 510 | 0 | 13 | 523 |
| `portal_odslony_oferty_3m` | 0 – 12, bez braków | 510 | 0 | 3 | 513 |
| `plat_liczba_90d` | 2 – 4 | 0 | 510 | 0 | 510 |
| `plat_srednie_opoznienie_90d` | 0 – 34, bez braków | 282 | 0 | 2 | 284 |
| `plat_max_opoznienie_90d` | 0 – 45, bez braków | 282 | 0 | 0 | 282 |
| `nr_okresu` | 1 – 6 | 0 | 0 | 47 | 47 |

Wszystkie 510 najmów bez danych z portalu to najmy krótsze niż 304 dni.

### 10 przykładów (wynik `GET /risk/{id_najmu}`, część `oferta`)

Po 3 przykłady z każdej akcji: najmy na 25., 50. i 75. percentylu EV w danej akcji. Nie bierzemy skrajnych, bo v3
zawyża skrajne uplifty. Do tego jeden przykład graniczny: najem o EV najbliższym zera. Wszystkie przykłady są
w zakresie modelu. Liczy je ta sama funkcja co endpoint (`ryzyko_najmu` z `model_uplift`). Przykład 10 sprawdziliśmy
też przez HTTP: odpowiedź 200 i te same liczby.

| # | Dlaczego wybrany | Najem (linia) | Koniec okresu | Dzień decyzji | P(przedłuży) z ofertą | bez oferty | Uplift (p.p.) | EV | Akcja |
|---:|---|---|---|---|---:|---:|---:|---:|---|
| 1 | rabat: 25. percentyl EV | N020744 (B2C) | 2027-09-14 | 2026-09-30 | 79,2% | 47,8% | +31,4 | 58 zł | **rabat** |
| 2 | rabat: 50. percentyl EV | N020872 (B2C) | 2026-10-26 | 2026-08-27 | 79,8% | 47,6% | +32,1 | 85 zł | **rabat** |
| 3 | rabat: 75. percentyl EV | N019103 (B2B) | 2027-08-11 | 2026-09-30 | 51,6% | 29,3% | +22,4 | 111 zł | **rabat** |
| 4 | bez rabatu: 25. percentyl EV | N011310 (B2C) | 2027-08-28 | 2026-09-30 | 80,0% | 73,0% | +7,1 | −1 153 zł | **bez rabatu** |
| 5 | bez rabatu: 50. percentyl EV | N020819 (B2C) | 2026-10-22 | 2026-08-23 | 61,3% | 55,7% | +5,7 | −886 zł | **bez rabatu** |
| 6 | bez rabatu: 75. percentyl EV | N012283 (B2C) | 2027-02-20 | 2026-09-30 | 85,4% | 65,5% | +19,9 | −617 zł | **bez rabatu** |
| 7 | nie budzić: 25. percentyl EV | N019006 (B2C) | 2027-03-27 | 2026-09-30 | 37,5% | 62,0% | −24,5 | −1 938 zł | **nie budzić** |
| 8 | nie budzić: 50. percentyl EV | N012014 (B2C) | 2027-05-25 | 2026-09-30 | 59,6% | 71,5% | −11,9 | −1 717 zł | **nie budzić** |
| 9 | nie budzić: 75. percentyl EV | N012029 (B2C) | 2027-06-24 | 2026-09-30 | 47,0% | 59,6% | −12,6 | −1 526 zł | **nie budzić** |
| 10 | graniczny: EV najbliższe zera | N017763 (B2B) | 2027-02-23 | 2026-09-30 | 40,2% | 25,7% | +14,5 | −70 zł | **bez rabatu** |

**Uzasadnienia** (pole `uzasadnienie`) i wkłady trzech cech w uplift (pole `najwazniejsze_cechy`, `wklad_pp`):

1. **N020744, rabat.** Rabat: oferta podnosi szansę przedłużenia o 31,4 punktu procentowego, wartość oczekiwana to
   58 zł (budżetu rabatów jeszcze nie ustalono), a najbardziej podnoszą ją: 31 logowań do portalu w 3 miesiące,
   czynsz 54 zł za m² i czynsz o 14% wyższy niż w podobnych lokalach. Wkłady: `portal_logowania_3m` +6,6;
   `czynsz_m2` +4,0; `czynsz_do_podobnych` +3,1.
2. **N020872, rabat.** Rabat: oferta podnosi szansę przedłużenia o 32,1 punktu procentowego, wartość oczekiwana to
   85 zł (budżetu rabatów jeszcze nie ustalono), a najbardziej podnoszą ją: czynsz o 13% niższy niż w podobnych
   lokalach, 9 logowań do portalu w 3 miesiące i ostatnia ankieta satysfakcji 8 na 10. Wkłady: `czynsz_do_podobnych`
   +5,3; `portal_logowania_3m` +4,9; `ankieta_ostatni_wynik` +3,0.
3. **N019103, rabat.** Rabat: oferta podnosi szansę przedłużenia o 22,4 punktu procentowego, wartość oczekiwana to
   111 zł (budżetu rabatów jeszcze nie ustalono), a najbardziej podnoszą ją: czynsz 71 zł za m², klient firmowy (B2B)
   i ostatnia odpowiedź w ankiecie 292 dni temu. Wkłady: `czynsz_m2` +9,2; `b2b` +6,0; `ankieta_dni_od_odpowiedzi`
   +5,6.
4. **N011310, bez rabatu.** Bez rabatu: oferta podnosi szansę przedłużenia tylko o 7,1 punktu procentowego, a przy
   80% szansy przedłużenia z ofertą rabat kosztuje więcej, niż daje (wartość oczekiwana −1 153 zł); najwięcej ważą:
   15 logowań do portalu w 3 miesiące (podnosi), czynsz 56 zł za m² (podnosi) i ostatnia odpowiedź w ankiecie
   455 dni temu (obniża). Wkłady: `portal_logowania_3m` +6,0; `czynsz_m2` +4,4; `ankieta_dni_od_odpowiedzi` −3,9.
5. **N020819, bez rabatu.** Bez rabatu: oferta podnosi szansę przedłużenia tylko o 5,7 punktu procentowego, a przy
   61% szansy przedłużenia z ofertą rabat kosztuje więcej, niż daje (wartość oczekiwana −886 zł); najwięcej ważą:
   czynsz o 8% niższy niż w podobnych lokalach (podnosi), 4 logowania do portalu w 3 miesiące (obniża) i pierwsza
   umowa, bez wcześniejszej podwyżki (podnosi). Wkłady: `czynsz_do_podobnych` +5,7; `portal_logowania_3m` −4,5;
   `indeksacja_ostatnia_pct` +3,7.
6. **N012283, bez rabatu.** Bez rabatu: oferta podnosi szansę przedłużenia tylko o 19,9 punktu procentowego, a przy
   85% szansy przedłużenia z ofertą rabat kosztuje więcej, niż daje (wartość oczekiwana −617 zł); najwięcej ważą:
   czynsz 57 zł za m² (podnosi), czynsz o 15% wyższy niż w podobnych lokalach (podnosi) i brak zgłoszeń w portalu
   w ciągu roku (obniża). Wkłady: `czynsz_m2` +4,5; `czynsz_do_podobnych` +3,6; `zgl_365d` −3,6.
7. **N019006, nie budzić.** Nie budzić: oferta obniża szansę przedłużenia o 24,5 punktu procentowego (wartość
   oczekiwana −1 938 zł), a najbardziej obniżają ją: 2 logowania do portalu w 3 miesiące, brak odsłon oferty
   przedłużenia w portalu w 3 miesiące i ostatnia podwyżka czynszu 4,0%. Wkłady: `portal_logowania_3m` −29,6;
   `portal_odslony_oferty_3m` −3,2; `indeksacja_ostatnia_pct` −2,6.
8. **N012014, nie budzić.** Nie budzić: oferta obniża szansę przedłużenia o 11,9 punktu procentowego (wartość
   oczekiwana −1 717 zł), a najbardziej obniżają ją: 4 logowania do portalu w 3 miesiące, czynsz 28 zł za m²
   i ostatnia podwyżka czynszu 2,2%. Wkłady: `portal_logowania_3m` −9,3; `czynsz_m2` −5,2;
   `indeksacja_ostatnia_pct` −2,8.
9. **N012029, nie budzić.** Nie budzić: oferta obniża szansę przedłużenia o 12,6 punktu procentowego (wartość
   oczekiwana −1 526 zł), a najbardziej obniżają ją: 2 logowania do portalu w 3 miesiące, czynsz 30 zł za m² i okres
   umowy nr 4. Wkłady: `portal_logowania_3m` −26,4; `czynsz_m2` −4,0; `nr_okresu` −1,4.
10. **N017763, bez rabatu (graniczny).** Bez rabatu: oferta podnosi szansę przedłużenia tylko o 14,5 punktu
    procentowego, a przy 40% szansy przedłużenia z ofertą rabat kosztuje więcej, niż daje (wartość oczekiwana
    −70 zł); najwięcej ważą: klient firmowy (B2B) (obniża), czynsz 68 zł za m² (podnosi) i ostatnia odpowiedź
    w ankiecie 280 dni temu (podnosi). Wkłady: `b2b` −14,2; `czynsz_m2` +7,7; `ankieta_dni_od_odpowiedzi` +5,8.
    Przy R = 4 920 zł zabrakło 70 zł. Ten najem przechodzi na „rabat”, jeśli koszt odejścia jest wyższy albo rabat
    niższy.

**Najem poza zakresem modelu** (dodatkowo, spoza 10 przykładów; HTTP 200): N000020, linia B2C, uplift +15,4 p.p.,
EV −820 zł, `poza_zakresem_modelu = ["nr_okresu", "staz_dni"]`. Uzasadnienie: „Bez rabatu: model jeszcze nie ocenia
tego najmu, bo poza zakresem danych, na których go uczono (najmy 60 dni przed końcem umowy), są: okres umowy nr 8
i najem trwa 7,0 roku; zalecenie policzymy w dniu migawki 2027-07-23.”

### Ograniczenia

- **v3 nie jest lepszy od reguły firmy** „górne 35% score” ([uplift.md](../api/api/ai/churn_model/evals/uplift.md)).
  Zawyża też skrajne uplifty: w najwyższym kwintylu przewiduje +22,2 p.p., a w danych jest +11,4 p.p. Mediana
  upliftu dla „rabat” (+32,1 p.p.) jest więc najpewniej zawyżona.
- **Kierunek wpływu cech to opis modelu, a nie udowodniona przyczyna.** Przykład: model uważa, że dla B2B rabat
  czasem podnosi szansę przedłużenia (przykład 3), choć w całym teście 2025 efekt oferty w B2B wynosił −3,0 p.p.
  (95% przedział od −9,0 do +3,1; [test_rabatu_2025.md](test_rabatu_2025.md)).
- **Uzasadnienie dla najmu poza zakresem modelu** opiera się na cechach spoza zakresu, a nie na trzech
  najważniejszych. Te trzy są wtedy nadal w `najwazniejsze_cechy`.

## SQL i kod

Uruchomienie (wymaga `domilo.duckdb` z `pypyr baza` oraz modeli v2 i v3; v3 zapisuje
`python -m api.ai.churn_model.evals.uplift --bez-mlflow`):

```bash
cd api && poetry run uvicorn api.main:app --port 8101            # GET /risk/N017763
cd api && poetry run python -m api.contexts_boundaries.retention_bc.przeglad_ofert
cd api && poetry run pytest -q tests/test_oferta_najmu.py tests/test_ryzyko_najmu.py
```

Populacja aktywnych najmów i bieżący okres (`przeglad_ofert.aktywne_okresy`): `features/najemcy/okresy_umow.sql`
z `$koniec_obserwacji = 2100-12-31`, ostatni `nr_okresu` w najmie, `data_wyprowadzenia` pusta albo po 2026-09-30.
Cechy na dzień decyzji: `features/najemcy/cechy_okresow.py` (`cechy_okresow`) z `data_migawki` =
min(`data_do` − 60 dni, 2026-09-30), czyli te same pliki SQL co dla migawek, tylko ze zdarzeń sprzed tego dnia.

Próg „nie budzić” (20. percentyl upliftu v3 na zbiorze oceny = −0,0643) i wynik oferty w tej grupie (oferta 47,7%
ze 153 umów, kontrola 57,7% ze 130):

```python
p = pd.read_parquet("api/api/contexts_boundaries/retention_bc/wyniki/ev_najemcow.parquet")
q = p["uplift"].quantile(0.20); m = p["uplift"] <= q
for g in ("oferta", "kontrola"):
    print(g, (1 - p.loc[m & (p.grupa == g), "odejdzie"]).mean(), (m & (p.grupa == g)).sum())
```

Zakres danych uczących: `ModelUpliftT.zakres_cech_` (min, max i braki każdej kolumny `macierz` na treningu v3;
`staz_dni` od 304 do 2 131) oraz `ModelUpliftT.poza_zakresem`. Wkłady cech: `ModelUpliftT.wklady_upliftu`
(SHAP z `pred_contrib`, przeliczony proporcjonalnie na prawdopodobieństwo; suma = uplift).

Kod i testy:

- `api/api/contexts_boundaries/retention_bc/oferta_najmu.py`: `data_decyzji`, `zalecana_akcja`,
  `miesci_sie_w_budzecie`, `trzy_cechy`, `opis_cechy`, `uzasadnienie`, `decyzja`, `oferty_okresow`, `oferta_najmu`;
- `ryzyko_najmu.py` (parametr `model_uplift`), `schematy.py` (`OfertaRetencyjna`), `api/api/main.py` (`model_uplift`);
- `zalozenia.yaml` (`budzet_rabatow_rok` = null) i `zalozenia.py` (`budzet_rabatow`);
- `churn_model/versions/v3_uplift_tlearner/model.py`: `wklady_upliftu`, `zakres_cech_`, `poza_zakresem`. Model
  nauczony ponownie z tymi samymi danymi i parametrami daje identyczne miary
  ([uplift.md](../api/api/ai/churn_model/evals/uplift.md));
- testy: `api/tests/test_oferta_najmu.py` (suma wkładów = uplift, wkłady wskazują cechę z efektem, zakres
  treningu, dzień decyzji, reguła akcji z budżetem, próg z danych, opisy cech, wybór trzech cech, jedno zdanie,
  HTTP `/risk` z ofertą).
