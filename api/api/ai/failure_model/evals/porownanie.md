# Model alertów o awariach wind: v2_lgbm_losowy vs v2b_lgbm_czas_winda

Stan: 2026-11-16, baza `domilo.duckdb` (eksport 2026-09-30). Obie wersje to ten sam LightGBM na tych samych 179
cechach (168 ręcznych z `cechy_windy` + 11 tsfresh wybranych na treningu 2023-03 – 2025-06), target
`dni_wind.awaria_7d`. Różni je **tylko sposób podziału danych**. Kontrakt: `ai/failure_model/base.py`.
Przebiegi: MLflow, eksperyment `windy` (runy `v2_lgbm_losowy`, `v2b_lgbm_czas_winda`).

## Wnioski

1. Przy losowym podziale wierszy model wygląda na prawie doskonały (ROC AUC 0,968, PR-AUC 0,763). Przy podziale
   „jak w życiu” (uczymy na przeszłości, sprawdzamy na 2026 roku, a 28 wind model w ogóle nie widział) ten sam model
   ma ROC AUC 0,773 i PR-AUC 0,352. Odsetek dni z awarią jest w obu testach prawie taki sam (5,7% i 6,0%), więc
   różnica nie wynika z innego testu, tylko z tego, co model mógł podejrzeć.
2. Skąd różnica, po ludzku: jedna awaria daje do 7 kolejnych „alarmowych” dni tej samej windy, a ich cechy są
   prawie identyczne (okna 3 i 7 dni w dużej części się pokrywają). Losowy podział rozrzuca te dni między naukę
   i sprawdzian, więc w teście model rozpoznaje awarię, którą już widział w treningu: dotyczy to 100% dni z awarią
   w teście v2. To jak egzamin z pytaniami, które były na próbnym teście. W praktyce o 06:00 nikt nie zna
   przyszłych dni, więc tej podpowiedzi nie będzie.
3. Najmocniejszy dowód: model, który zna **tylko numer windy i datę** (żadnych danych z czujników), przy losowym
   podziale osiąga PR-AUC 0,396, czyli więcej niż prawdziwy model w uczciwym podziale. Przy podziale w czasie ten
   sam „model pamięci” ma 0,065, tyle co losowa kolejność (odsetek dodatnich 6,0%).
4. Realistyczny wynik do planowania to v2b: na 2026 roku PR-AUC 0,352 wobec 0,238 prostej reguły (różnica +0,114,
   95% CI +0,083 … +0,144), czyli model jest **lepszy od baseline**. Na windach, których nie widział, wynik jest
   podobny (PR-AUC 0,363, ROC AUC 0,778), więc model uczy się objawów, a nie konkretnych wind; przedział jest szeroki
   (tylko 28 wind).
5. Wersja v2_lgbm_losowy służy wyłącznie jako przestroga; jej wyników nie wolno raportować jako jakości modelu.

## Podziały

| | v2_lgbm_losowy | v2b_lgbm_czas_winda |
|---|---|---|
| trening | 70% losowych wierszy (121 859, 140 wind) | dni 2023-03-01 – 2025-06-30, 112 wind (89 172) |
| walidacja (wczesne zatrzymanie) | 10% losowych wierszy (17 499) | dni 2025-07-01 – 2025-12-31, 112 wind (20 433) |
| test | 20% losowych wierszy (35 264, 140 wind) | dni 2026-01-01 – 2026-09-22, 140 wind (36 774), w tym 28 wind niewidzianych (7 352) |
| windy poza treningiem | brak | 28 o najmniejszym `md5(id_windy:v2b_lgbm_czas_winda)`: Dźwigmet 12, Liftar 7, Vertica 7, Elmont 2 |
| drzewa (wczesne zatrzymanie na PR-AUC walidacji) | 3 000 (limit; walidacja też losowa, więc ciągle „poprawia się”) | 111 |

Zastrzeżenie v2b: walidacja zaczyna się dzień po treningu, a okno targetu trwa 7 dni, więc etykiety ostatnich
dni treningu i pierwszych dni walidacji dzielą te same awarie (wpływa tylko na wybór liczby drzew). Między treningiem
a testem jest 6 miesięcy przerwy.

## Tabele

### T1. Wyniki na teście (95% CI: bootstrap wind, 1 000 losowań)

| wersja | zbiór testowy | wiersze | windy | dodatnie | odsetek dodatnich | ROC AUC | PR-AUC | PR-AUC / odsetek |
|---|---|---:|---:|---:|---:|---|---|---:|
| v2_lgbm_losowy | losowe 20% wierszy | 35 264 | 140 | 2 014 | 5,71% | 0,968 (0,963–0,972) | 0,763 (0,742–0,784) | 13,4 |
| v2b_lgbm_czas_winda | 2026-01 – 2026-09, wszystkie windy | 36 774 | 140 | 2 205 | 6,00% | **0,773** (0,743–0,803) | **0,352** (0,305–0,401) | 5,9 |
| v2b_lgbm_czas_winda | jw., windy widziane w treningu | 29 422 | 112 | 1 775 | 6,03% | 0,772 (0,738–0,805) | 0,356 (0,302–0,410) | 5,9 |
| v2b_lgbm_czas_winda | jw., windy niewidziane | 7 352 | 28 | 430 | 5,85% | 0,778 (0,710–0,844) | 0,363 (0,256–0,484) | 6,2 |

„PR-AUC / odsetek” = ile razy lepiej od losowej kolejności (PR-AUC losowej kolejności ≈ odsetek dodatnich).

### T2. Baseline na tych samych zbiorach: reguła `drzwi_ponowne_otwarcia_do_normy_24h` (im wyżej, tym ryzyko większe)

Reguła wybrana na treningu 2023-03 – 2025-06 jako najlepsza pojedyncza cecha ręczna ([b4_tsfresh.md](../../../../../docs/b4_tsfresh.md)).
Różnica model − reguła: te same losowania wind.

| zbiór testowy | reguła ROC AUC | reguła PR-AUC | model − reguła: ROC AUC | model − reguła: PR-AUC |
|---|---|---|---|---|
| v2: losowe 20% | 0,634 (0,617–0,652) | 0,231 (0,208–0,258) | +0,333 (+0,316 … +0,351) | +0,532 (+0,507 … +0,556) |
| v2b: 2026, wszystkie | 0,636 (0,611–0,661) | 0,238 (0,200–0,279) | +0,137 (+0,107 … +0,168) | +0,114 (+0,083 … +0,144) |
| v2b: 2026, widziane | 0,630 (0,603–0,655) | 0,247 (0,201–0,298) | +0,142 (+0,109 … +0,172) | +0,109 (+0,073 … +0,141) |
| v2b: 2026, niewidziane | 0,661 (0,604–0,718) | 0,249 (0,174–0,333) | +0,117 (+0,039 … +0,185) | +0,113 (+0,044 … +0,201) |

Reguła ma prawie ten sam wynik w obu podziałach (0,231 vs 0,238): nie uczy się, więc nie ma czego „podejrzeć”. Cały
spadek dotyczy modelu.

### T3. Dlaczego losowy podział zawyża wynik

| miara | v2_lgbm_losowy | v2b_lgbm_czas_winda |
|---|---:|---:|
| dni z awarią w teście, których awaria (`id_awarii`) ma dni z awarią w treningu lub walidacji | 100,0% | 0,3% |
| wiersze testu, których sąsiedni dzień (t−1 lub t+1) tej samej windy jest w treningu lub walidacji | 95,8% | 0,3% |
| ROC AUC / PR-AUC na treningu | 1,000 / 1,000 | 0,928 / 0,570 |
| ROC AUC / PR-AUC na walidacji | 0,964 / 0,758 | 0,779 / 0,331 |
| „model pamięci” (LightGBM tylko na numerze windy i numerze dnia): ROC AUC / PR-AUC na teście | 0,892 / 0,396 | 0,496 / 0,065 |
| jw., windy niewidziane | — | 0,524 / 0,062 |

0,3% w v2b: awarie z pierwszych dni stycznia 2026 są też etykietami ostatnich dni walidacji (grudzień 2025).

### T4. Najważniejsze cechy (udział w gain, 10 pierwszych)

| v2_lgbm_losowy | udział | v2b_lgbm_czas_winda | udział |
|---|---:|---|---:|
| drzwi_czas_zamykania_max_do_normy_24h | 7,0% | drzwi_czas_zamykania_max_do_normy_24h | 19,3% |
| firmware_dni_od_zmiany | 4,2% | drzwi_ponowne_otwarcia_do_normy_24h | 8,2% |
| drzwi_ponowne_otwarcia_do_normy_24h | 3,8% | naped_temp_silnika_do_normy_24h | 7,3% |
| naped_temp_silnika_do_normy_24h | 2,9% | naped_prad_max_do_normy_24h | 5,8% |
| naped_temp_silnika_norma | 2,3% | naped_blad_poziomowania_do_normy_7d | 3,6% |
| naped_prad_max_do_normy_24h | 2,0% | naped_blad_poziomowania_do_normy_24h | 2,9% |
| naped_blad_poziomowania_do_normy_3d | 1,7% | firmware_dni_od_zmiany | 2,7% |
| naped_temp_maszynowni_norma | 1,6% | sterownik_bledy_max_7d | 1,7% |
| drzwi_ponowne_otwarcia_norma | 1,6% | naped_temp_maszynowni_sr_7d | 1,6% |
| naped_temp_silnika_do_normy_3d | 1,6% | naped_temp_silnika_norma | 1,5% |

W v2 na drugim miejscu jest `firmware_dni_od_zmiany`, a wysoko są normy (`*_norma`). Te cechy zmieniają się
powoli i prawie jednoznacznie wskazują „która winda i kiedy”, więc służą do zapamiętania, kiedy była awaria.
W v2b przeważają objawy (stosunek do normy z ostatnich 24 h).

## Kod

```bash
cd api && poetry run python -m api.ai.failure_model.evals.ewaluacja_v2     # uczy obie wersje, zapisuje model.joblib
                                                                           # i metryki.json, runy MLflow `windy`
poetry run pytest tests/test_failure_model_v2.py                           # kontrakt, podziały, zapisane wersje
```

- Dane: `api/api/ai/features/windy/zbior.py` (`dni_wind` ⋈ `cechy_windy` ⋈ wybrane kolumny `cechy_windy_tsfresh`).
- Kontrakt: `api/api/ai/failure_model/base.py` (`ModelWind`, `KOLUMNY_ZAKAZANE`).
- Wersje: `versions/v2_lgbm_losowy/model.py` (`ModelLGBMWind`), `versions/v2b_lgbm_czas_winda/model.py`
  (`ModelLGBMCzasWinda`, ta sama metoda); artefakty `model.joblib`, `metryki.json` (wszystkie liczby z T1–T3).
- Ewaluacja: `evals/ewaluacja_v2.py`: `podzial_losowy` (ziarno 2026), `podzial_czas_winda` + `windy_poza_treningiem`,
  `ocen` / `roznica` (bootstrap wind), `przeciek` (T3, wiersze 1–2), `diagnoza_pamieci` (T3, „model pamięci”).

Parametry LightGBM (obie wersje): `objective=binary`, `metric=average_precision`, `learning_rate=0.03`,
`num_leaves=31`, `min_child_samples=200`, `feature_fraction=0.8`, `bagging_fraction=0.8`, `bagging_freq=1`,
`lambda_l2=1.0`, `seed=42`, `deterministic=True`; do 3 000 drzew, zatrzymanie po 100 rundach bez poprawy PR-AUC
walidacji.
