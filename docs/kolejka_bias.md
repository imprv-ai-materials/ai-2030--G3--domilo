# Kolejka zapytań: co naprawdę przewiduje v2_lgbm_naiwny i co zmienia v2b_lgbm_ipw

Analiza z 2026-11-15. Pierwsza część dotyczy zapisanego modelu `versions/v2_lgbm_naiwny/model.joblib` (bez
ponownego uczenia; skrypt `lead_model/evals/analiza_biasu_v2.py`, wynik `lead_model/evals/wyniki/bias_v2.json`).
Część o v2b (tabele B5–B9) liczy `lead_model/evals/ewaluacja_v2b.py`; run MLflow
`9b7285f2324c4a83937bd12dd71b73e8` w eksperymencie `leady`. Cenzurowanie, czas do kontaktu i zestawienie wersji
(tabele B10–B12) liczy `lead_model/evals/analiza_cenzura_kontakt.py`; wynik
`lead_model/evals/wyniki/cenzura_kontakt.json`. Zbiory jak w
[kolejka_v2_lgbm_naiwny.md](kolejka_v2_lgbm_naiwny.md):
- trening: zamknięte zapytania 2023-01 – 2026-02 bez okna migracji;
- zwykły test: 2026-03 – 2026-06;
- okno migracji CRM: 2025-03-03 – 2025-04-13; w oknie call center obsłużyło każde zapytanie.

## Wnioski

1. Naiwny model (v2) przewiduje szansę na umowę **przy dzisiejszym sposobie pracy zespołu**, czyli łącznie „czy
   doradca się odezwie” i „czy klient podpisze”. Na teście jego wynik przewiduje samo obsłużenie z AUC 0,766.
   `domteraz` dostaje średnio 2,9% (41,1% obsłużonych × 6,98% umów po kontakcie), choć w oknie migracji, gdy
   obsłużono wszystkich, miało 8,19%.
2. Poprawiony model (v2b) uczy się tylko na obsłużonych zapytaniach i przewiduje szansę na umowę **pod warunkiem
   kontaktu**. W oknie migracji układa kolejkę najlepiej ze wszystkich wersji: AUC 0,785 wobec 0,764 dla v2
   (różnica +0,013 … +0,030), lift@10% 3,52. `domteraz` ma w czołówce 10% kolejki 7,1% zapytań zamiast 0,2%. Na
   zwykłym teście v2 i v2b są praktycznie równe. Same wagi dokładają niewiele: bez nich AUC w oknie wynosi 0,784.
3. Zapytań, którym nie minęło jeszcze 45 dni, nie wolno liczyć jako „bez umowy”. Dla zapytań z 2026-08-16 –
   2026-09-30 taka naiwna konwersja wynosi 3,75%, a z ostatniego tygodnia 0%. Estymator, który uwzględnia
   niepełną obserwację (Kaplan–Meier), daje 4,93% (4,32–5,55%). Na sprawdzianie z udawanym eksportem 2026-05-31
   KM dał 7,61% przy prawdziwych 7,50%, a liczenie naiwne 5,36%. Konwersja zapytań z sierpnia i września 2026
   wygląda więc na niższą niż w miesiącach 2026-04 – 07 (7,45–7,80%), ale pewność da dopiero pełne 45 dni.
4. Szybki kontakt idzie w parze z umową. Poza oknem zapytania z pierwszym kontaktem w ≤ 1 dniu kończą się umową
   w 12,35%, po > 7 dniach w 5,32%, a bez kontaktu w 1,05%. Ta zależność występuje w każdym źródle. W oknie
   migracji 97% zapytań miało kontakt w ≤ 1 dniu, a po > 7 dniach nie było żadnego. Z danych nie da się
   rozdzielić, ile to efekt szybkości, a ile tego, że doradcy szybciej dzwonią do obiecujących zapytań.
5. Na tle kosztów (tabela B12): reguła źródła nie potrzebuje niczego poza tabelą konwersji, ale ma AUC tylko
   0,633. LLM v1 kosztuje ok. 1,19 mln tokenów wejścia na 1 000 zapytań i jest najsłabszy (AUC 0,620). v2 i v2b
   są najlepsze, ale potrzebują tych samych wywołań LLM (sygnały v1) oraz danych z www i CRM. Kwoty w zł nie da
   się podać, bo w `leasing_bc/zalozenia.yaml` nie ma cennika.

## Co przewiduje model, prostym językiem

Model uczył się na historii, w której „brak umowy” ma dwie różne przyczyny:

- klient nie chciał (zapytanie słabe);
- nikt do klienta nie zadzwonił (decyzja doradcy). Przy „nieobsłużone = 0” takie zapytanie liczy się jako porażka.

Model nie ma żadnej cechy, która mówi „doradca zadzwonił”, więc nie potrafi tych przyczyn rozdzielić. Uczy się
więc, które zapytania **zwykle kończą się umową w Domilo takim, jakie jest dziś**. Dla `domteraz` odpowiedź
brzmi: rzadko, bo 59% z nich nikt nie obsługuje. To prawda o zespole, a nie o klientach z `domteraz`. Kiedy
w oknie migracji call center zadzwoniło do wszystkich, `domteraz` dało 21,3% umów i miało wyższą konwersję
(8,19%) niż `lokum24` (6,52%) i `social` (4,84%).

Kolejka ma odpowiadać na pytanie: „do kogo warto zadzwonić?”. Model naiwny odpowiada na inne: „do kogo zwykle
dzwonimy i z kim podpisujemy?”.

v2b robi to w dwóch krokach.

1. **Model skłonności** (regresja logistyczna) uczy się, do jakich zapytań doradcy zwykle się odzywają. Na
   przykład do `domteraz` w ok. 41% przypadków, do `www` w 99%.
2. **Właściwy model** uczy się już tylko na zapytaniach, do których ktoś zadzwonił, więc „brak umowy” znaczy
   w nim tylko „klient nie chciał”. Zapytania obsłużone rzadko (głównie `domteraz`) dostają większą wagę: jedno
   obsłużone `domteraz` z wagą 2,4 „zastępuje” też te podobne, do których nikt nie zadzwonił.

v2b odpowiada więc na pytanie: „jaka jest szansa na umowę, jeśli zadzwonimy?”. To założenie działa tylko wtedy,
gdy doradcy wybierają zapytania na podstawie tego, co widać w formularzu. Jeśli kierują się czymś spoza danych
(np. tonem rozmowy w pierwszym kontakcie), wagi tego nie naprawią.

## Tabele

### B1. Źródła: obsłużone i konwersja (zwykły test, trening, okno migracji)

| Źródło | Obsłużone (trening) | Obsłużone (test) | Konwersja wszystkich (test) | Konwersja obsłużonych (test) | Konwersja nieobsłużonych (test) | Konwersja w oknie migracji (wszystkie obsłużone) |
|---|---:|---:|---:|---:|---:|---:|
| domteraz | 41,1% | 40,6% | 3,61% (139 z 3 849) | 7,24% | 1,14% (z 2 288) | **8,19%** (119 z 1 453) |
| lokum24 | 95,7% | 95,8% | 4,87% (268 z 5 506) | 5,08% | 0,00% (z 234) | 6,52% (133 z 2 040) |
| polecenie | 98,9% | 99,0% | 14,52% (113 z 778) | 14,42% | 25,00% (z 8) | 18,47% (46 z 249) |
| relokacja_b2b | 99,5% | 99,3% | 17,72% (303 z 1 710) | 17,84% | 0,00% (z 12) | 22,01% (79 z 359) |
| social | 90,5% | 89,1% | 3,19% (23 z 722) | 3,27% | 2,53% (z 79) | 4,84% (12 z 248) |
| www | 99,0% | 99,0% | 12,10% (321 z 2 652) | 12,22% | 0,00% (z 26) | 17,51% (170 z 971) |

Ten sam podział dla treningu (tego, z czego model się uczył):

| Źródło | Zapytania | Konwersja wszystkich | Konwersja obsłużonych | Konwersja nieobsłużonych | Target uczenia („nieobsłużone = 0”) |
|---|---:|---:|---:|---:|---:|
| domteraz | 33 916 | 3,52% | 6,98% | 1,11% (z 19 992) | **2,87%** |
| lokum24 | 48 156 | 4,80% | 4,99% | 0,72% (z 2 094) | 4,77% |
| polecenie | 6 219 | 15,81% | 15,96% | 1,47% (z 68) | 15,79% |
| relokacja_b2b | 10 061 | 19,97% | 20,05% | 3,92% (z 51) | 19,95% |
| social | 6 492 | 3,13% | 3,39% | 0,65% (z 614) | 3,07% |
| www | 22 683 | 13,02% | 13,14% | 1,31% (z 229) | 13,01% |

Konwersja nieobsłużonych w źródłach innych niż `domteraz`, `lokum24` i `social` opiera się na 8–229
zapytaniach, więc jest niepewna (np. 25,00% w `polecenie` na teście to 2 umowy z 8 zapytań).

Wyższa konwersja w oknie dotyczy wszystkich źródeł, nie tylko `domteraz`. W oknie call center odzywało się też
szybciej (mediana 12,5 godziny zamiast ok. 74; [kolejka_target.md](kolejka_target.md), R3). Z danych nie da się
rozdzielić wpływu szybkości kontaktu od wpływu kontaktu z każdym. Dla `domteraz` różnica jest jednak dużo
większa niż dla innych źródeł (tabela B3).

### B2. Miary v2: zwykły test a okno migracji

| Miara | Zwykły test | Okno migracji |
|---|---:|---:|
| zapytania / umowy | 15 217 / 1 167 | 5 320 / 559 |
| rzeczywista konwersja | 7,67% | 10,51% |
| średni wynik v2 | 8,09% | 7,26% |
| AUC (umowa), wszystkie zapytania | 0,793 | 0,764 |
| AUC (umowa), tylko obsłużone | 0,771 | 0,764 (wszystkie obsłużone) |
| lift@10% | 3,75 | 3,33 |
| precision@k (k = dzienna liczba zapytań: 125 / 127) | 43,2% | 49,6% |
| **AUC wyniku v2 dla samego obsłużenia** (czy doradca się odezwie) | **0,766** | brak (obsłużone wszystkie) |

AUC (umowa) wewnątrz jednego źródła i AUC wyniku v2 dla obsłużenia wewnątrz źródła:

| Źródło | AUC umowy: test | AUC umowy: okno | AUC obsłużenia: test |
|---|---:|---:|---:|
| domteraz | 0,763 | 0,737 | 0,629 |
| lokum24 | 0,745 | 0,741 | 0,520 |
| polecenie | 0,751 | 0,756 | 0,557 |
| relokacja_b2b | 0,705 | 0,730 | 0,499 |
| social | 0,721 | 0,705 | 0,535 |
| www | 0,760 | 0,761 | 0,559 |

- **Obsłużenie a źródło:** AUC 0,766 dla obsłużenia wynika głównie z różnic między źródłami (`domteraz` nisko).
  W obrębie źródła wynik v2 prawie nie przewiduje obsłużenia (0,50–0,56), z wyjątkiem `domteraz` (0,629). Tam
  doradcy częściej obsługują zapytania, które model ocenia wyżej, i odwrotnie.
- **`domteraz` na teście a w oknie:** AUC umowy wewnątrz `domteraz` jest na teście wyższe niż w oknie (0,763
  wobec 0,737). Część tej trafności na teście to zgadywanie, które zapytania `domteraz` doradca wybierze.

### B3. Okno migracji: średni wynik v2 dla źródła wobec rzeczywistej konwersji

| Źródło | Zapytania | Konwersja w oknie | Średni wynik v2 | Konwersja / wynik | Target uczenia (trening) | Konwersja obsłużonych (trening) | Średni wkład `zrodlo` w log-szansę |
|---|---:|---:|---:|---:|---:|---:|---:|
| domteraz | 1 453 | 8,19% | 2,92% | **2,80** | 2,87% | 6,98% | −0,72 |
| lokum24 | 2 040 | 6,52% | 4,60% | 1,42 | 4,77% | 4,99% | −0,11 |
| polecenie | 249 | 18,47% | 15,81% | 1,17 | 15,79% | 15,96% | +1,23 |
| relokacja_b2b | 359 | 22,01% | 19,08% | 1,15 | 19,95% | 20,05% | +1,14 |
| social | 248 | 4,84% | 3,68% | 1,32 | 3,07% | 3,39% | −0,74 |
| www | 971 | 17,51% | 13,69% | 1,28 | 13,01% | 13,14% | +0,72 |

Ten sam przekrój na zwykłym teście, gdzie model jest dobrze skalibrowany ogółem (8,09% wobec 7,67%):

| Źródło | Średni wynik v2: wszystkie | Konwersja wszystkich | Średni wynik v2: obsłużone | Konwersja obsłużonych |
|---|---:|---:|---:|---:|
| domteraz | 2,98% | 3,61% | 3,76% | **7,24%** |
| lokum24 | 4,83% | 4,87% | 4,85% | 5,08% |
| polecenie | 15,50% | 14,52% | 15,51% | 14,42% |
| relokacja_b2b | 21,15% | 17,72% | 21,15% | 17,84% |
| social | 3,45% | 3,19% | 3,49% | 3,27% |
| www | 12,95% | 12,10% | 12,97% | 12,22% |

- **Jak czytać:** średni wynik v2 dla każdego źródła jest blisko targetu uczenia, czyli konwersji przy
  dzisiejszej obsłudze. Dla `domteraz` to 2,87% = 41,1% obsłużonych × 6,98% konwersji obsłużonych.
- **Wkład `zrodlo`:** pokazuje, ile sama informacja o źródle przesuwa wynik (SHAP z LightGBM, log-szansa,
  średnio w źródle). Dla `domteraz` i `social` to ok. −0,72 do −0,74. `social` ma jednak niską konwersję także
  po obsłużeniu (3,39%), a `domteraz` nie (6,98%).

### B4. 10 najważniejszych cech v2

| # | Cecha | Udział w gain (uczenie) | Średni \|wkład\| w log-szansę: test | Średni \|wkład\|: okno |
|---:|---|---:|---:|---:|
| 1 | zrodlo | 34,8% | 0,58 | 0,54 |
| 2 | budzet_do_mediany | 19,7% | 0,44 | 0,44 |
| 3 | termin_dni | 14,8% | 0,39 | 0,40 |
| 4 | dlugosc_wiadomosci | 4,0% | 0,08 | 0,08 |
| 5 | www_liczba_sesji | 3,6% | 0,13 | 0,13 |
| 6 | www_spacer_3d | 3,5% | 0,14 | 0,14 |
| 7 | linia | 3,3% | 0,18 | 0,19 |
| 8 | syg_niedopasowanie_oferty | 2,9% | 0,11 | 0,12 |
| 9 | liczba_lokali | 2,6% | 0,04 | 0,03 |
| 10 | syg_konkretne_pytania | 2,6% | 0,12 | 0,12 |

Kolejność według gain z zapisanego modelu (`waznosc_cech()`). Średni |wkład| to średnia wartość bezwzględna SHAP
(`explain`, `pred_contrib`). Pozostałe 9 cech ma łącznie 8,1% gain
([kolejka_v2_lgbm_naiwny.md](kolejka_v2_lgbm_naiwny.md), T6).

### B5. v2b_lgbm_ipw: okno migracji i zwykły test

Zbiór uczący jak w v2, czyli tylko dane spoza okna migracji:
- **model skłonności:** wszystkie 127 527 zapytań treningu;
- **LightGBM:** 104 479 obsłużonych zapytań, 9 407 umów, target `umowa_45d` bez zmian, waga
  `min(1 / P(obsłużony), 10)`; 182 drzewa z wczesnego zatrzymania na ostatnich 6 miesiącach treningu (ważone
  AUC walidacji 0,786).

Okno migracji (5 320 zapytań, 559 umów, k = 127):

| Wersja | AUC | lift@10% | precision@127 |
|---|---:|---:|---:|
| v0_regula_zrodla (baseline) | 0,633 (0,608–0,659) | 1,89 (1,60–2,18) | 22,0% (17,8–26,3) |
| v1_llm_zero_shot | 0,620 (0,597–0,642) | 1,40 (1,17–1,64) | 15,1% (11,5–18,8) |
| v2_lgbm_naiwny | 0,764 (0,743–0,784) | 3,33 (3,00–3,68) | 49,6% (40,9–57,5) |
| **v2b_lgbm_ipw** | **0,785** (0,765–0,804) | **3,52** (3,19–3,86) | 48,0% (39,4–56,7) |
| v2b bez wag (kontrola: tylko obsłużone, wagi = 1) | 0,784 | 3,47 | 49,6% |
| v2b − v0 (95% CI) | +0,126 … +0,175 | +1,25 … +2,00 | +18,0 … +34,2 pp |
| v2b − v2 (95% CI) | +0,013 … +0,030 | +0,02 … +0,37 | −5,5 … +3,1 pp |
| v2b − v1 (95% CI) | +0,139 … +0,190 | +1,73 … +2,52 | +24,1 … +41,7 pp |

Zwykły test 2026-03 – 2026-06 (15 217 zapytań, 1 167 umów, k = 125):

| Wersja | AUC | lift@10% | precision@125 |
|---|---:|---:|---:|
| v0_regula_zrodla (baseline) | 0,684 (0,668–0,700) | 2,31 (2,11–2,52) | 17,7% (16,0–19,5) |
| v1_llm_zero_shot | 0,617 (0,601–0,632) | 1,49 (1,33–1,65) | 11,5% (9,7–13,5) |
| v2_lgbm_naiwny | **0,793** (0,780–0,806) | **3,75** (3,50–4,00) | **43,2%** (34,4–52,0) |
| v2b_lgbm_ipw | 0,790 (0,776–0,802) | 3,69 (3,44–3,94) | 40,8% (33,6–50,4) |
| v2b bez wag (kontrola) | 0,790 | 3,73 | 40,0% |
| v2b − v0 (95% CI) | +0,090 … +0,120 | +1,12 … +1,64 | +15,8 … +32,5 pp |
| v2b − v2 (95% CI) | −0,008 … +0,001 | −0,17 … +0,05 | −5,6 … +4,0 pp |
| v2b − v1 (95% CI) | +0,157 … +0,191 | +1,92 … +2,48 | +21,8 … +39,2 pp |

| Miara dodatkowa | v2 | v2b |
|---|---:|---:|
| test: AUC (umowa) tylko na obsłużonych | 0,771 | 0,777 |
| test: AUC wyniku dla samego obsłużenia | 0,766 | 0,615 |
| test: średni wynik (konwersja wszystkich 7,67%, obsłużonych 9,05%) | 8,09% | 9,06% |
| okno: średni wynik (konwersja 10,51%) | 7,26% | 8,32% |

Wariant kontrolny „bez wag” jest wyuczony w tym samym przebiegu, ale bez przedziałów ufności.

### B6. v2b w oknie migracji: średni wynik według źródła i udział w czołówce 10%

| Źródło | Zapytania | Konwersja w oknie | Udział w umowach | Średni wynik v2 | Średni wynik v2b | Konwersja / v2 | Konwersja / v2b | Czołówka 10%: v2 | Czołówka 10%: v2b |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| domteraz | 1 453 | 8,19% | 21,3% | 2,92% | **6,32%** | 2,80 | **1,30** | 0,2% | **7,1%** |
| lokum24 | 2 040 | 6,52% | 23,8% | 4,60% | 4,88% | 1,42 | 1,34 | 5,3% | 5,3% |
| polecenie | 249 | 18,47% | 8,2% | 15,81% | 15,83% | 1,17 | 1,17 | 15,6% | 14,5% |
| relokacja_b2b | 359 | 22,01% | 14,1% | 19,08% | 18,95% | 1,15 | 1,16 | 29,3% | 27,8% |
| social | 248 | 4,84% | 2,1% | 3,68% | 3,94% | 1,32 | 1,23 | 0,0% | 0,0% |
| www | 971 | 17,51% | 30,4% | 13,69% | 13,81% | 1,28 | 1,27 | 49,6% | 45,3% |

- **Niedoszacowanie w oknie:** v2b zaniża w oknie wszystkie źródła o podobny czynnik (1,16–1,34). Pozostała
  różnica to wyższa konwersja w całym oknie: call center odzywało się szybciej
  ([kolejka_target.md](kolejka_target.md), R3).
- **`domteraz` w czołówce:** ma nadal mniejszy udział w czołówce (7,1%) niż w umowach (21,3%), bo jego konwersja
  (8,19%) jest niższa niż `www`, `polecenie` i `relokacja_b2b`.
- **Test:** v2b daje `domteraz` średnio 6,32% przy konwersji obsłużonych `domteraz` 7,24% (B3). W czołówce 10%
  testu `domteraz` ma 3,6% zapytań (v2: 0,1%).

### B7. Model skłonności P(obsłużony | cechy zapytania)

Regresja logistyczna (`LogisticRegression`, `max_iter` 2000) na `KOLUMNY_CECH`: one-hot dla `zrodlo`, `miasto`,
`linia`; liczby z medianą w miejsce braku, wskaźnikiem braku i standaryzacją. AUC dla `obsluzony`: trening 0,909,
test 0,913. Średnia skłonność w oknie migracji: 81,5% (rzeczywiście obsłużone: 100%).

| Źródło | Obsłużone (trening) | Średnia P (trening) | Obsłużone (test) | Średnia P (test) |
|---|---:|---:|---:|---:|
| domteraz | 41,1% | 41,1% | 40,6% | 40,9% |
| lokum24 | 95,7% | 95,7% | 95,8% | 95,7% |
| polecenie | 98,9% | 98,9% | 99,0% | 98,9% |
| relokacja_b2b | 99,5% | 99,5% | 99,3% | 99,5% |
| social | 90,5% | 90,5% | 89,1% | 90,4% |
| www | 99,0% | 99,0% | 99,0% | 99,0% |

### B8. Rozkład wag (104 479 obsłużonych zapytań treningu)

| Statystyka | Waga |
|---|---:|
| minimum | 1,00 |
| kwantyl 10% | 1,01 |
| kwantyl 25% | 1,01 |
| mediana | 1,03 |
| kwantyl 75% | 1,07 |
| kwantyl 90% | 1,79 |
| kwantyl 95% | 2,55 |
| kwantyl 99% | 3,88 |
| maksimum | 6,77 |
| średnia | 1,22 |
| przycięte do 10 | 0 |
| suma wag (≈ liczba wszystkich zapytań treningu, 127 527) | 127 457 |
| efektywna liczebność (Kish: (Σw)² / Σw²) | 86 239 |

| Przedział wagi | Zapytania |
|---|---:|
| [1; 1,25) | 90 812 |
| [1,25; 1,5) | 1 076 |
| [1,5; 2) | 3 796 |
| [2; 3) | 5 778 |
| [3; 5) | 2 984 |
| [5; 10) | 33 |
| ≥ 10 | 0 |

| Źródło | Obsłużone | Średnia waga | Mediana | Maks. | Udział w obsłużonych | Udział w sumie wag |
|---|---:|---:|---:|---:|---:|---:|
| domteraz | 13 924 | 2,43 | 2,32 | 6,77 | 13,3% | **26,5%** |
| lokum24 | 46 062 | 1,05 | 1,04 | 1,19 | 44,1% | 37,8% |
| polecenie | 6 151 | 1,01 | 1,01 | 1,04 | 5,9% | 4,9% |
| relokacja_b2b | 10 010 | 1,01 | 1,01 | 1,02 | 9,6% | 7,9% |
| social | 5 878 | 1,11 | 1,10 | 1,35 | 5,6% | 5,1% |
| www | 22 454 | 1,01 | 1,01 | 1,04 | 21,5% | 17,8% |

Udział `domteraz` w sumie wag (26,5%) odpowiada jego udziałowi we wszystkich zapytaniach treningu
(33 916 / 127 527 = 26,6%, tabela B1). Wagi przywracają więc proporcje źródeł sprzed decyzji doradców.

### B9. 5 zapytań z największą wagą

Wszystkie pięć to obsłużone zapytania `domteraz` z linii MID, z budżetem 0,61–0,70 mediany czynszu w mieście.
Żadne nie skończyło się umową. Imię w treści zastąpiono znacznikiem `[imię]`, a treść skrócono do 120 znaków.

| id_leada | Utworzono | Miasto | Budżet / mediana | Termin (dni) | Osoby | Sesje www | Sygnały v1 | P(obsłużony) | Waga | Umowa 45 dni |
|---|---|---|---:|---:|---:|---:|---|---:|---:|---:|
| L058679 | 2024-06-20 18:10 | Poznań | 0,61 | 46 | 2 | 1 | budzet_niski | 14,8% | 6,77 | 0 |
| L126586 | 2026-01-03 19:32 | Wrocław | 0,67 | 21 | 2 | 1 | konkretne_pytania, pilny_termin, budzet_niski | 16,3% | 6,13 | 0 |
| L071464 | 2024-09-21 17:37 | Gdańsk | 0,68 | 21 | 2 | 2 | pilny_termin, relokacja, budzet_niski | 16,4% | 6,11 | 0 |
| L066064 | 2024-08-14 18:36 | Gdańsk | 0,66 | brak | 5 | 1 | budzet_niski, brak_informacji | 17,0% | 5,89 | 0 |
| L037275 | 2023-11-29 22:48 | Wrocław | 0,70 | brak | 2 | 2 | budzet_niski, brak_informacji | 17,0% | 5,87 | 0 |

Treść wiadomości:

- **L058679:** „jestem zainteresowany ofertą najmu w Poznaniu Pracuję zdalnie, nie palę. Dziękuję i pozdrawiam,
  [imię]”.
- **L126586:** „Cześć, interesuje mnie najem długoterminowy we Wrocławiu Proszę o przesłanie dostępnych lokali.
  Pracuję zdalnie, nie pal…”.
- **L071464:** „Доброго дня! переїжджаю до міста Gdańsk через роботу і шукаю житло. Працюю в польській компанії.
  З повагою, [imię]”. Po ukraińsku: przeprowadzka do Gdańska z powodu pracy, praca w polskiej firmie.
- **L066064:** brak wiadomości.
- **L037275:** „Interesuje mnie oferta.”.

Te zapytania ważą w uczeniu tyle co ok. 6 zwykłych. Gdyby było ich wiele, kilka przypadkowych umów w tej grupie
mocno przesunęłoby model. Tu takich zapytań (waga ≥ 5) jest 33 z 104 479.

### B10. Konwersja zapytań z 2026-08-16 – 2026-09-30: otwarte = 0 wobec poprawnego cenzurowania

Eksport kończy się 2026-09-30 23:59 (tu granica 2026-10-01 00:00). Zapytanie ma wynik `umowa_45d`, gdy do eksportu
minęło pełne 45 dni. Z tego okresu ma go tylko 94 z 6 907 zapytań (część z 2026-08-16).

| Sposób liczenia | Konwersja | Na jakiej podstawie |
|---|---:|---|
| naiwnie: brak umowy do eksportu = 0 (otwarte jako 0) | **3,75%** | 259 umów / 6 907 zapytań |
| definicja `leady_cel`: tylko zapytania z pełnymi 45 dniami | 4,26% | 4 umowy / 94 zapytania (za mało, by wnioskować) |
| **Kaplan–Meier** P(umowa w 45 dni), każde zapytanie obserwowane do eksportu | **4,93%** (95% CI 4,32–5,55) | wszystkie 6 907, na 45. dniu w ryzyku 90 |
| odniesienie: konwersja 45 dni w miesiącach 2026-04 / 05 / 06 / 07 | 7,80% / 7,69% / 7,65% / 7,45% | 3 733 / 3 603 / 4 181 / 4 401 zapytania |
| odniesienie: 2026-08 (tylko 1–16 sierpnia, niecenzurowane) | 6,50% | 2 278 zapytań |

Według tygodnia utworzenia (tydzień od niedzieli):

| Tydzień od | Zapytania | Umowy do eksportu | Naiwnie (otwarte = 0) | Mediana dni obserwacji |
|---|---:|---:|---:|---:|
| 2026-08-16 | 1 058 | 73 | 6,90% | 42,5 |
| 2026-08-23 | 1 014 | 63 | 6,21% | 35,3 |
| 2026-08-30 | 1 027 | 55 | 5,36% | 28,4 |
| 2026-09-06 | 1 070 | 38 | 3,55% | 21,2 |
| 2026-09-13 | 1 098 | 18 | 1,64% | 14,3 |
| 2026-09-20 | 1 041 | 12 | 1,15% | 7,2 |
| 2026-09-27 (do 30.09) | 599 | 0 | 0,00% | 1,6 |

Sprawdzian tej samej metody: udajemy eksport 2026-05-31 23:59 i bierzemy zapytania z 2026-04-16 – 2026-05-31.
Ich prawdziwe `umowa_45d` znamy z pełnych danych.

| Sposób liczenia | Konwersja |
|---|---:|
| naiwnie (otwarte = 0) | 5,36% (294 / 5 490) |
| tylko pełne 45 dni | 7,41% (10 / 135) |
| Kaplan–Meier | **7,61%** (95% CI 6,48–8,74) |
| **prawdziwa `umowa_45d`** | **7,50%** |

| Tydzień od (sprawdzian) | Zapytania | Naiwnie | Prawdziwa | Mediana dni obserwacji |
|---|---:|---:|---:|---:|
| 2026-04-12 (od 16.04) | 389 | 7,46% | 7,46% | 44,5 |
| 2026-04-19 | 894 | 6,49% | 6,60% | 39,3 |
| 2026-04-26 | 836 | 7,66% | 8,37% | 32,4 |
| 2026-05-03 | 805 | 4,84% | 6,09% | 25,5 |
| 2026-05-10 | 842 | 6,29% | 8,67% | 18,2 |
| 2026-05-17 | 827 | 4,47% | 8,71% | 11,4 |
| 2026-05-24 | 826 | 1,69% | 6,66% | 4,4 |
| 2026-05-31 | 71 | 0,00% | 7,04% | 0,4 |

- **Liczenie naiwne:** zaniża wynik tym bardziej, im młodsze zapytanie. Model uczony na takim targecie uznałby
  najnowsze zapytania za gorsze, choć po prostu nie zdążyły się zamknąć.
- **Kaplan–Meier:** zakłada, że czas do umowy rozkłada się tak samo w zapytaniach starszych i młodszych. Na
  sprawdzianie trafił w prawdziwy wynik (7,50% mieści się w przedziale).
- **Okres 2026-08-16 – 2026-09-30:** KM daje 4,93%. Także wczesne tygodnie (mediana obserwacji 28–42 dni) mają
  przy liczeniu naiwnym mniej umów niż odpowiadające im tygodnie sprawdzianu (np. 5,36% wobec 7,66% przy ok. 30
  dniach obserwacji). Spadek wygląda więc na prawdziwy, ale potwierdzą go dopiero pełne 45 dni.

### B11. Konwersja według czasu do pierwszego kontaktu

Niecenzurowane zapytania. Pierwszy kontakt to pierwsza aktywność doradcy lub call center w 45 dni od utworzenia,
bez zapisu podpisania (`leady_cel.godz_do_pierwszego_kontaktu`). W danych żadna umowa nie powstała przed pierwszym
kontaktem.

| Pierwszy kontakt | Poza oknem: zapytania | Poza oknem: umowy | Poza oknem: konwersja | W oknie: zapytania | W oknie: umowy | W oknie: konwersja |
|---|---:|---:|---:|---:|---:|---:|
| **≤ 1 dzień (≤ 24 h)** | 8 073 | 997 | **12,35%** | 5 170 | 545 | **10,54%** |
| 1–7 dni | 97 108 | 9 096 | 9,37% | 150 | 14 | 9,33% |
| **> 7 dni (> 168 h)** | 17 304 | 920 | **5,32%** | 0 | 0 | brak w danych |
| brak kontaktu w 45 dni | 26 938 | 284 | 1,05% | 0 | 0 | brak w danych |

Poza oknem, według źródła (tylko obsłużone):

| Źródło | ≤ 1 dzień: zapytania | ≤ 1 dzień: konwersja | > 7 dni: zapytania | > 7 dni: konwersja |
|---|---:|---:|---:|---:|
| domteraz | 676 | 8,73% | 3 251 | 4,31% |
| lokum24 | 3 499 | 6,83% | 7 331 | 2,80% |
| polecenie | 535 | 18,13% | 865 | 9,36% |
| relokacja_b2b | 965 | 25,60% | 1 574 | 12,64% |
| social | 416 | 5,05% | 1 045 | 1,15% |
| www | 1 982 | 16,85% | 3 238 | 8,74% |

- **Poza oknem:** szybki kontakt to tylko 8 073 zapytania (6,6% obsłużonych), a kontakt po tygodniu to 17 304.
  W każdym źródle konwersja przy kontakcie w ≤ 1 dniu jest mniej więcej dwa razy wyższa niż po > 7 dniach.
- **W oknie:** call center dzwoniło szybko do wszystkich (97% w ≤ 1 dniu), a konwersja wyniosła 10,54%, mniej niż
  12,35% dla szybkich kontaktów poza oknem. Poza oknem doradcy szybko dzwonią głównie do zapytań, które wyglądają
  obiecująco. W oknie szybki kontakt dostali wszyscy, także słabsi.
- **Przyczyna a związek:** z tych danych nie da się powiedzieć, ile umów dałoby samo przyspieszenie kontaktu.
  Wiadomo tylko, że opóźnienie powyżej tygodnia idzie w parze z dwa razy niższą konwersją.

### B12. Zestawienie wersji: okno migracji, koszt, czego wersja potrzebuje

AUC i lift@10% na tych samych 5 320 zapytaniach z okna migracji (559 umów). v0 jest tu uczona na treningu v2;
zapisana wersja v0 liczona z dłuższej historii ma AUC 0,637 i ten sam lift 1,89.

| Wersja | AUC (okno) | lift@10% (okno) | Koszt / 1 000 zapytań | Czego potrzebuje do działania |
|---|---:|---:|---|---|
| v0_regula_zrodla (reguła źródła) | 0,633 | 1,89 | 0 tokenów | pól `zrodlo` i `linia_pref` z formularza oraz tabeli konwersji (źródło × linia) z historii `leady_cel`, odświeżanej okresowo |
| v1_llm_zero_shot (LLM) | 0,620 | 1,40 | wejście 1 190 958 tokenów (1 058 000 z cache promptu), wyjście 70 112; kwota: brak cennika | klucza OpenAI i wywołania `gpt-6-luna` dla każdego zapytania (prompt `ocena_leada_v1`), pól formularza i treści wiadomości (imię usuwane); bez uczenia |
| v2_lgbm_naiwny (naiwny) | 0,764 | 3,33 | jak v1 (sygnały v1 dla każdego zapytania) + LightGBM bez API | wszystkiego, czego potrzebuje v1 (sygnały), oraz pól formularza, sesji `www_sesje` sprzed zapytania, `crm_firmy_b2b` (umowa ramowa z datą), mediany `czynsz_katalogowy` w mieście i pliku modelu; do ponownego uczenia: historii `umowa_45d` i `obsluzony` |
| **v2b_lgbm_ipw (poprawiony)** | **0,785** | **3,52** | jak v2 | jak v2; do ponownego uczenia dodatkowo model skłonności (regresja logistyczna na `obsluzony`) i tylko zapytań z obsługą; do predykcji model skłonności nie jest potrzebny |

- **Tokeny:** średnia z wywołań dla 5 320 zapytań okna (`versions/v1_llm_zero_shot/metryki.json`). v2 i v2b
  wołają ten sam prompt, więc mają te same tokeny. Bez sygnałów LLM v2 miał w oknie AUC 0,751
  ([kolejka_v2_lgbm_naiwny.md](kolejka_v2_lgbm_naiwny.md), T4). Wariantu v2b bez sygnałów nie liczyliśmy.
- **Czas odpowiedzi** API przy nowym zapytaniu: brak w danych (nie mierzyliśmy).

## SQL i kod

Źródło × zbiór (tabela B1), na `domilo.duckdb` przez `polacz()` (strefa Europe/Warsaw). Granice zbiorów są takie
same jak w `features/leady/podzial_v2.py`; liczebności się zgadzają: 127 527 / 15 217 / 5 320.

```sql
WITH z AS (
    SELECT
        c.zrodlo, c.umowa_45d, c.obsluzony,
        CASE
            WHEN c.okno_migracji THEN 'okno_migracji'
            WHEN c.utworzono >= TIMESTAMPTZ '2026-03-01' AND c.utworzono < TIMESTAMPTZ '2026-07-01' THEN 'test'
            WHEN c.zamkniety AND c.utworzono >= TIMESTAMPTZ '2023-01-01'
                 AND c.utworzono < TIMESTAMPTZ '2026-03-01' THEN 'trening'
        END AS zbior
    FROM leady_cel AS c
    WHERE c.umowa_45d IS NOT NULL
)
SELECT
    zbior, zrodlo,
    count(*) AS zapytania,
    count(*) FILTER (WHERE NOT obsluzony) AS nieobsluzone,
    sum(umowa_45d) AS umowy,
    avg(obsluzony::INTEGER) AS obsluzone,
    avg(umowa_45d) AS konwersja_wszystkich,
    avg(umowa_45d) FILTER (WHERE obsluzony) AS konwersja_obsluzonych,
    avg(umowa_45d) FILTER (WHERE NOT obsluzony) AS konwersja_nieobsluzonych,
    avg(CASE WHEN obsluzony THEN umowa_45d ELSE 0 END) AS konwersja_nieobsluzone_0
FROM z
WHERE zbior IS NOT NULL
GROUP BY ALL
ORDER BY zbior, zrodlo;
```

Tabele B2–B4 liczy `api/api/ai/lead_model/evals/analiza_biasu_v2.py`:

- wczytuje zapisany model (`ModelLeadow.wczytaj`) i cechy z `ewaluacja_v2.przygotuj` (sygnały v1 z cache, bez
  API);
- liczy `explain` na teście i w oknie (wynik + wkłady SHAP), AUC ogółem, na obsłużonych i wewnątrz źródła oraz AUC
  wyniku dla `obsluzony`;
- dla każdego źródła liczy średni wynik i średni wkład `zrodlo`;
- bierze ważność cech z `waznosc_cech()` i średni |wkład| z SHAP.

```bash
cd api && poetry run python -m api.ai.lead_model.evals.analiza_biasu_v2   # po `pypyr baza`
```

```python
# rdzeń (fragment analiza_biasu_v2.py)
wyj = model.explain(X)                                   # wynik + wklad_<cecha> (log-szansa)
w, y = wyj["wynik"].to_numpy(), zb["umowa_45d"].astype(int).to_numpy()
auc_umowy = roc_auc_score(y, w)
auc_obsluzonych = roc_auc_score(y[zb["obsluzony"]], w[zb["obsluzony"]])
auc_dla_obsluzenia = roc_auc_score(zb["obsluzony"].astype(int), w)     # czy wynik przewiduje decyzję doradcy
po_zrodle = df.groupby("zrodlo").agg(konwersja=("y", "mean"), sredni_wynik_v2=("w", "mean"),
                                     sredni_wklad_zrodla=("wklad_zrodlo", "mean"))
```

v2b (tabele B5–B9): model w `api/api/ai/lead_model/versions/v2b_lgbm_ipw/model.py`, ewaluacja
w `api/api/ai/lead_model/evals/ewaluacja_v2b.py`.

```bash
set -a && . ./.env && set +a   # klient v1 wymaga klucza; odpowiedzi v1 są w cache, więc API nie jest wołane
cd api && poetry run python -m api.ai.lead_model.evals.ewaluacja_v2b      # zapis + MLflow (`leady`)
```

```python
# rdzeń v2b (fragment model.py)
sklonnosc = make_pipeline(
    ColumnTransformer([
        ("kategorie", OneHotEncoder(handle_unknown="ignore"), ["zrodlo", "miasto", "linia"]),
        ("liczby", make_pipeline(SimpleImputer(strategy="median", add_indicator=True), StandardScaler()), liczby),
    ]),
    LogisticRegression(max_iter=2000),
).fit(X_trening, obsluzony)                                   # wszystkie zapytania treningu
wagi = np.minimum(1 / sklonnosc.predict_proba(X_obsluzone)[:, 1], 10)
lgbm = ModelLGBMNaiwny.fit(X_obsluzone, umowa_45d_obsluzonych, wagi=wagi)  # te same parametry LightGBM co v2
```

Wynik każdego zapytania testu i okna (v0, v1, v2, v2b, v2b bez wag, skłonność):
`api/api/ai/lead_model/evals/wyniki/v2b_lgbm_ipw.parquet`. Rozkład wag, 5 zapytań z największą wagą i model
skłonności: `versions/v2b_lgbm_ipw/metryki.json` (klucze `wagi`, `top5_wag`, `sklonnosc`).

Cenzurowanie, czas do kontaktu i zestawienie (tabele B10–B12): `api/api/ai/lead_model/evals/analiza_cenzura_kontakt.py`.

```bash
cd api && poetry run python -m api.ai.lead_model.evals.analiza_cenzura_kontakt   # po `pypyr baza`
```

```sql
-- B10: zapytania z okresu [od, do) z czasem obserwacji do „eksportu” (parametry: eksport, eksport, od, do)
SELECT id_leada, utworzono, umowa_45d, cenzurowany, zamkniety,
       epoch(?::TIMESTAMPTZ - utworzono) / 86400.0 AS dni_obserwacji,
       CASE WHEN data_umowy < ?::TIMESTAMPTZ THEN dni_do_umowy END AS dni_do_umowy_przed_eksportem
FROM leady_cel
WHERE utworzono >= ?::TIMESTAMPTZ AND utworzono < ?::TIMESTAMPTZ;
-- okres: '2026-08-16' – '2026-10-01', eksport '2026-10-01 00:00:00+02';
-- sprawdzian: '2026-04-16' – '2026-06-01', eksport '2026-06-01 00:00:00+02'

-- B11
SELECT CASE WHEN okno_migracji THEN 'w oknie migracji' ELSE 'poza oknem migracji' END AS okres,
       CASE WHEN NOT obsluzony THEN 'brak kontaktu w 45 dni'
            WHEN godz_do_pierwszego_kontaktu <= 24 THEN '≤ 1 dzień'
            WHEN godz_do_pierwszego_kontaktu <= 168 THEN '1–7 dni'
            ELSE '> 7 dni' END AS pierwszy_kontakt,
       count(*) AS zapytania, sum(umowa_45d) AS umowy, avg(umowa_45d) AS konwersja
FROM leady_cel
WHERE NOT cenzurowany
GROUP BY ALL;
```

```python
# B10: naiwnie i Kaplan–Meier (fragment analiza_cenzura_kontakt.py)
obserwacja = df["dni_obserwacji"].clip(upper=45)
umowa = df["dni_do_umowy_przed_eksportem"]
zdarzenie = umowa.notna() & (umowa <= 45)
naiwna = zdarzenie.mean()                                  # otwarte = 0
czas = np.where(zdarzenie, umowa, obserwacja)              # dni do umowy albo do końca obserwacji
s = 1.0
for t in np.unique(czas[zdarzenie]):                       # Kaplan–Meier: S(t) = Π (1 − d / n)
    n, d = (czas >= t).sum(), ((czas == t) & zdarzenie).sum()
    s *= 1 - d / n
p_umowa_45d = 1 - s                                        # CI: wzór Greenwooda
```

Tabela B12 bierze AUC i lift z `versions/v2b_lgbm_ipw/metryki.json` (klucz `okno_migracji`, wszystkie wersje na
tych samych zapytaniach), a tokeny z `versions/v1_llm_zero_shot/metryki.json` (`koszt_na_1000`).
