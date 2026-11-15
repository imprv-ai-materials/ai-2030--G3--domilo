# Kolejka zapytań: co naprawdę przewiduje v2_lgbm_naiwny

Analiza z 2026-11-15 zapisanego modelu `versions/v2_lgbm_naiwny/model.joblib` (bez ponownego uczenia i bez zmian;
skrypt `lead_model/evals/analiza_biasu_v2.py`, wynik `lead_model/evals/wyniki/bias_v2.json`). Zbiory jak
w [kolejka_v2_lgbm_naiwny.md](kolejka_v2_lgbm_naiwny.md): trening (zamknięte zapytania 2023-01 – 2026-02 bez okna
migracji), zwykły test (2026-03 – 2026-06) i okno migracji CRM (2025-03-03 – 2025-04-13). W oknie call center
obsłużyło każde zapytanie.

## Wnioski

1. Model nie przewiduje czystej szansy na umowę. Przewiduje szansę na umowę **przy dzisiejszym sposobie pracy
   zespołu**, czyli razem: „czy doradca w ogóle się odezwie” i „czy po kontakcie klient podpisze”. Na zwykłym
   teście wynik modelu przewiduje samo to, czy doradca się odezwie, prawie tak dobrze (AUC 0,766) jak umowę
   (AUC 0,793).
2. Najmocniej widać to na `domteraz`. Doradcy odzywają się tylko do 41% tych zapytań. Gdy się odezwą, umową kończy
   się 7,24% (test), a w oknie migracji, gdy obsłużono wszystkich, 8,19%. Model daje `domteraz` średnio 2,9%,
   bo nauczył się iloczynu 41,1% × 6,98% = 2,87% z treningu. W oknie zaniża `domteraz` 2,8 raza, a inne źródła
   1,15–1,42 raza.
3. Na zwykłym teście ten błąd jest niewidoczny, bo zespół dalej pomija `domteraz`. Model trafnie przewiduje, że
   te zapytania nie skończą się umową, choć powodem jest brak telefonu, a nie słabe zapytanie. Gdy policzyć AUC
   tylko na obsłużonych zapytaniach testu, spada z 0,793 do 0,771. W oknie migracji, gdzie wszyscy byli
   obsłużeni, AUC wynosi 0,764.
4. W obrębie jednego źródła model rozróżnia zapytania podobnie na teście i w oknie (AUC 0,70–0,76). Cechy
   formularza (budżet, termin, sesje www, treść) działają. Problemem jest przede wszystkim cecha `zrodlo`,
   najważniejsza w modelu (34,8% gain), która niesie w sobie decyzję doradców.
5. Jeśli taki model ustawi kolejkę, `domteraz` trafi na jej koniec, doradcy będą je pomijać jeszcze częściej,
   a następny model nauczy się tego samego jeszcze mocniej. Na razie niczego nie poprawiamy. Możliwe kierunki
   są w pytaniach na końcu odpowiedzi w czacie.

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
