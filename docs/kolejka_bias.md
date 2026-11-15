# Kolejka zapytań: co naprawdę przewiduje v2_lgbm_naiwny i co zmienia v2b_lgbm_ipw

Analiza z 2026-11-15. Pierwsza część dotyczy zapisanego modelu `versions/v2_lgbm_naiwny/model.joblib` (bez
ponownego uczenia; skrypt `lead_model/evals/analiza_biasu_v2.py`, wynik `lead_model/evals/wyniki/bias_v2.json`).
Część o v2b (tabele B5–B9) liczy `lead_model/evals/ewaluacja_v2b.py`; run MLflow
`9b7285f2324c4a83937bd12dd71b73e8` w eksperymencie `leady`. Zbiory jak w
[kolejka_v2_lgbm_naiwny.md](kolejka_v2_lgbm_naiwny.md):
- trening: zamknięte zapytania 2023-01 – 2026-02 bez okna migracji;
- zwykły test: 2026-03 – 2026-06;
- okno migracji CRM: 2025-03-03 – 2025-04-13; w oknie call center obsłużyło każde zapytanie.

## Wnioski

1. Naiwny model (v2) przewiduje szansę na umowę **przy dzisiejszym sposobie pracy zespołu**, czyli razem: „czy
   doradca w ogóle się odezwie” i „czy po kontakcie klient podpisze”. Na teście jego wynik przewiduje samo
   „czy doradca się odezwie” z AUC 0,766, prawie tak dobrze jak umowę (0,793). `domteraz` dostaje średnio 2,9%,
   czyli tyle, ile wynosi 41,1% obsłużonych × 6,98% umów po kontakcie. W oknie migracji, gdy obsłużono wszystkich,
   `domteraz` miało 8,19%: v2 zaniża je 2,8 raza, inne źródła 1,15–1,42 raza.
2. v2b uczy się tylko na zapytaniach, do których doradca się odezwał. Każde ma wagę tym większą, im rzadziej
   doradcy odzywają się do podobnych zapytań. v2b przewiduje więc szansę na umowę **pod warunkiem, że doradca
   zadzwoni**. Na teście jego średni wynik (9,06%) jest równy konwersji obsłużonych zapytań (9,05%), a samo
   obsłużenie przewiduje dużo słabiej niż v2 (AUC 0,615 wobec 0,766).
3. W oknie migracji, jedynym okresie bez wpływu decyzji doradców, v2b układa kolejkę lepiej niż v2:
   - AUC 0,785 wobec 0,764 (różnica +0,013 … +0,030);
   - lift@10% 3,52 wobec 3,33 (+0,02 … +0,37);
   - w pierwszych 127 zapytaniach różnica nierozstrzygnięta (48,0% wobec 49,6%; −5,5 … +3,1 pp).

   Na zwykłym teście v2b i v2 są praktycznie równe (AUC −0,008 … +0,001). Oba modele są wyraźnie lepsze od
   baseline v0 i od v1 na obu zbiorach.
4. `domteraz` przestaje być karane za brak telefonu. W oknie v2b daje mu średnio 6,32% wobec rzeczywistych 8,19%,
   czyli zaniża je 1,30 raza, tak jak inne źródła (1,16–1,34). W czołówce 10% kolejki `domteraz` ma 7,1%
   zapytań zamiast 0,2%.
5. Same wagi dokładają niewiele. LightGBM tylko na obsłużonych, bez wag, ma w oknie AUC 0,784 (v2b: 0,785).
   Poprawa bierze się głównie z tego, że brak telefonu przestał liczyć się jako porażka.
   - Wagi są łagodne: mediana 1,03, maksimum 6,77; przycięcie do 10 nie zadziałało ani razu.
   - Największe wagi mają obsłużone zapytania `domteraz` z linii MID z budżetem ok. 0,6–0,7 mediany czynszu.
   - Do wyboru wersji do `current.yaml` potrzebna jest decyzja (pytania w czacie).

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
