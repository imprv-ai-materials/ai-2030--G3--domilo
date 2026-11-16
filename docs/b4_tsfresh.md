# Cechy tsfresh dla wind: czy przebiegi godzinowe poprawiają alerty o awariach (B4)

Stan danych: eksport 2026-09-30 23:59 Europe/Warsaw; `domilo.duckdb` z tabelami `dni_wind`, `cechy_windy`
i `cechy_windy_tsfresh` (zbudowane 2026-11-16). Opis każdej cechy: `api/api/ai/features/windy/katalog.yaml`.

## Wnioski

1. Dodanie cech tsfresh (RMS, kurtoza, energia, pasma FFT z tygodnia godzinowych przebiegów czasu zamykania drzwi,
   prądu silnika i wibracji) daje niewielką poprawę: PR-AUC rośnie z 0,336 do 0,343 na teście (lipiec 2025 –
   wrzesień 2026). Przewaga jest stała, ale mała: od +0,002 do +0,007 zależnie od losowego ziarna modelu.
2. W praktyce to prawie ta sama lista alertów (ROC AUC 0,760 w obu wariantach). Same cechy tsfresh, bez ręcznych,
   dają tylko 0,206, czyli mniej niż prosta reguła na jednej cesze ręcznej (0,239).
3. Model na samych cechach ręcznych jest wyraźnie lepszy od prostej reguły „rośnie liczba ponownych otwarć drzwi
   wobec normy windy”: PR-AUC 0,336 wobec 0,239 (różnica +0,097, 95% CI +0,071 … +0,125). Losowa kolejność daje 0,059.
4. Selekcja na danych treningowych zostawiła 11 z 21 cech tsfresh: wszystkie cechy czasu zamykania drzwi i cztery
   cechy wibracji. Żadna cecha prądu silnika nie okazała się istotna.
5. Rekomendacja: cechy tsfresh można dołączyć (koszt: ok. 1,5 min budowy), ale nie zmienią one jakości alertów
   w odczuwalny sposób; ważniejsze jest rozwiązanie pułapki firmware Liftar i rzadkich zdarzeń z
   [b4_cechy.md](b4_cechy.md).

## Ustawienia

- **Przebieg:** 168 godzinnych średnich (godziny kończące się o :50 UTC) przed odcięciem 05:50 dnia oceny, bez okien
  `tryb = 'serwis'`. Puste godziny (głównie noc bez jazd: ok. 15% godzin 22:00–05:00) — interpolacja liniowa;
  przebieg z < 84 godzinami z wartością pominięty. Wibracje przed montażem czujnika — NULL.
- **Cechy tsfresh** (`extract_features`, tsfresh 0.21.2): `root_mean_square`, `kurtosis`, `abs_energy`,
  `fft_coefficient` (|A_k|, k = 1–84) → udział pasm w energii widma bez składowej stałej: k 1–6 (168–28 h),
  7 (24 h), 8–14 (21–12 h), 15–84 (11,2–2 h). 3 sygnały × 7 = 21 cech.
- **Podział:** trening `dzien` 2023-03-01 – 2025-06-30 (112 317 wierszy, 6 343 z awarią), przerwa 2025-07-01 –
  2025-07-07 (okno targetu ostatnich dni treningu sięga 2025-07-07 06:00), test 2025-07-08 – 2026-09-22 (61 350
  wierszy, 3 613 z awarią).
- **Selekcja:** tylko trening; tsfresh `calculate_relevance_table` (Mann-Whitney, Benjamini-Yekutieli, fdr 0,05),
  osobno cechy wibracji (wiersze z czujnikiem) i reszta, bo tsfresh nie przyjmuje braków. Zastrzeżenie: test zakłada
  niezależne wiersze, a sąsiednie dni tej samej windy dzielą 6 z 7 dni przebiegu, więc p-wartości są zaniżone.
- **Model:** LightGBM o stałych parametrach (500 drzew, learning_rate 0,03, 31 liści, min_child_samples 200,
  subsample i colsample 0,8), bez strojenia, te same dla wszystkich wariantów; wynik = średnia z 3 ziaren (11, 22, 33).
- **Baseline:** (a) losowy ranking; (b) reguła jednej cechy ręcznej o najwyższym PR-AUC na treningu (wybór i kierunek
  tylko na treningu): `drzwi_ponowne_otwarcia_do_normy_24h`, im wyżej, tym większe ryzyko.
- **Niepewność:** 95% CI z bootstrapu wind (klaster = winda, 1 000 losowań, te same dla wszystkich modeli). CI nie
  obejmuje losowości uczenia — tę sprawdzamy osobno innymi ziarnami (T4).

## Tabele

### T1. Selekcja cech tsfresh na treningu

| cecha | grupa | wiersze | z awarią | p-wartość | wybrana |
|---|---|---:|---:|---:|---|
| ts_drzwi_czas_zamykania_rms | pozostałe | 112 148 | 6 342 | 1,1e-181 | tak |
| ts_drzwi_czas_zamykania_energia | pozostałe | 112 148 | 6 342 | 1,1e-181 | tak |
| ts_drzwi_czas_zamykania_fft_krotkie | pozostałe | 112 148 | 6 342 | 4,3e-173 | tak |
| ts_drzwi_czas_zamykania_fft_dlugie | pozostałe | 112 148 | 6 342 | 2,1e-131 | tak |
| ts_drzwi_czas_zamykania_fft_pol_doby | pozostałe | 112 148 | 6 342 | 5,5e-69 | tak |
| ts_drzwi_czas_zamykania_fft_doba | pozostałe | 112 148 | 6 342 | 8,6e-58 | tak |
| ts_drzwi_czas_zamykania_kurtoza | pozostałe | 112 148 | 6 342 | 2,4e-06 | tak |
| ts_naped_prad_fft_krotkie | pozostałe | 112 148 | 6 342 | 0,22 | nie |
| ts_naped_prad_rms | pozostałe | 112 148 | 6 342 | 0,23 | nie |
| ts_naped_prad_energia | pozostałe | 112 148 | 6 342 | 0,23 | nie |
| ts_naped_prad_kurtoza | pozostałe | 112 148 | 6 342 | 0,23 | nie |
| ts_naped_prad_fft_pol_doby | pozostałe | 112 148 | 6 342 | 0,30 | nie |
| ts_naped_prad_fft_dlugie | pozostałe | 112 148 | 6 342 | 0,39 | nie |
| ts_naped_prad_fft_doba | pozostałe | 112 148 | 6 342 | 0,57 | nie |
| ts_wibracje_rms_rms | wibracje | 48 132 | 2 793 | 1,9e-17 | tak |
| ts_wibracje_rms_energia | wibracje | 48 132 | 2 793 | 1,9e-17 | tak |
| ts_wibracje_rms_fft_pol_doby | wibracje | 48 132 | 2 793 | 4,7e-04 | tak |
| ts_wibracje_rms_fft_krotkie | wibracje | 48 132 | 2 793 | 2,5e-03 | tak |
| ts_wibracje_rms_fft_dlugie | wibracje | 48 132 | 2 793 | 0,060 | nie |
| ts_wibracje_rms_kurtoza | wibracje | 48 132 | 2 793 | 0,19 | nie |
| ts_wibracje_rms_fft_doba | wibracje | 48 132 | 2 793 | 0,25 | nie |

Grupa „pozostałe” ma 112 148 z 112 317 wierszy treningu: 169 wierszy ma mniej niż 84 godziny z wartością czasu
zamykania drzwi albo prądu (godziny bez jazd), więc te cechy są tam NULL. RMS i energia są tu tą samą informacją (energia = 168 × RMS²).

### T2. Test (2025-07-08 – 2026-09-22): PR-AUC z 95% CI

| model | cechy | PR-AUC | 95% CI | ROC AUC |
|---|---:|---:|---|---:|
| losowy ranking | — | 0,059 | 0,053–0,065 | 0,503 |
| reguła: `drzwi_ponowne_otwarcia_do_normy_24h` (baseline) | 1 | 0,239 | 0,207–0,271 | 0,640 |
| LightGBM: cechy ręczne | 168 | 0,336 | 0,302–0,369 | 0,760 |
| LightGBM: ręczne + tsfresh wybrane | 179 | **0,343** | 0,308–0,377 | 0,760 |
| LightGBM: ręczne + tsfresh wszystkie | 189 | 0,342 | 0,308–0,376 | 0,761 |
| LightGBM: tylko tsfresh wybrane | 11 | 0,206 | 0,177–0,235 | 0,647 |

### T3. Różnice PR-AUC (te same losowania wind)

| różnica | PR-AUC | 95% CI | losowania z przewagą pierwszego |
|---|---:|---|---:|
| ręczne + tsfresh wybrane − ręczne | +0,0069 | +0,0016 … +0,0119 | 99,3% |
| ręczne + tsfresh wszystkie − ręczne | +0,0060 | +0,0001 … +0,0126 | 97,8% |
| ręczne − reguła | +0,0968 | +0,0714 … +0,1249 | 100,0% |
| ręczne + tsfresh wybrane − reguła | +0,1037 | +0,0779 … +0,1325 | 100,0% |

### T4. Wrażliwość na ziarno modelu (PR-AUC na teście, średnia z 3 ziaren)

| ziarna | ręczne | ręczne + tsfresh wybrane | różnica |
|---|---:|---:|---:|
| 11, 22, 33 (główne) | 0,3361 | 0,3430 | +0,0069 |
| 44, 55, 66 | 0,3371 | 0,3409 | +0,0038 |
| 77, 88, 99 | 0,3370 | 0,3391 | +0,0021 |

## SQL i kod

Powtórzenie (z katalogu głównego):

```bash
poetry run pypyr baza                                                    # ... cechy_windy, cechy_windy_tsfresh
cd api && poetry run python -m api.ai.failure_model.evals.tsfresh_porownanie   # T1–T3, selekcja -> tsfresh_wybrane.yaml, MLflow `windy`
poetry run pytest tests/test_tsfresh_cechy.py tests/test_katalog_windy.py
```

T4: ta sama funkcja `tsfresh_porownanie.przewidz` z `ZIARNA` = (44, 55, 66) i (77, 88, 99), `average_precision_score`
na teście.

Kod: `api/api/ai/features/windy/tsfresh_cechy.py` (przebiegi, tsfresh, pasma, selekcja), `tsfresh_wybrane.yaml`
(wynik selekcji), `katalog.yaml`; `api/api/ai/failure_model/evals/tsfresh_porownanie.py` (podział, modele, bootstrap).

### Godziny i przebiegi (`tsfresh_cechy.przygotuj`, `przebiegi`)

```sql
CREATE OR REPLACE TEMP TABLE ts_godziny AS
SELECT
    t.id_windy,
    CAST(floor((epoch(t.ts_utc) + 540) / 3600) * 3600 + 3000 AS BIGINT) AS koniec_godziny,   -- ts w (H:50 − 1 h; H:50]
    avg(t.czas_zamykania_drzwi_sr_s) AS drzwi_czas_zamykania,
    avg(t.prad_silnika_sr_a) AS naped_prad,
    avg(CASE WHEN t.ts_utc >= timezone('Europe/Warsaw', w.czujnik_wibracji_od) THEN t.wibracje_rms_mg END) AS wibracje_rms
FROM telemetra_windy AS t
JOIN serwis_windy AS w USING (id_windy)
WHERE t.tryb IS DISTINCT FROM 'serwis'
GROUP BY ALL;

CREATE OR REPLACE TEMP TABLE ts_wiersze AS
SELECT row_number() OVER (ORDER BY dzien, id_windy) - 1 AS nr, id_windy, dzien,
    CAST(epoch(timezone('Europe/Warsaw', dzien + INTERVAL '05:50')) AS BIGINT) AS odciecie_s
FROM dni_wind;

-- przebieg wierszy od…do: 168 godzin, godzina 167 kończy się o 05:50 dnia oceny
SELECT r.nr, j.j, g.drzwi_czas_zamykania, g.naped_prad, g.wibracje_rms
FROM ts_wiersze AS r
CROSS JOIN range(168) AS j(j)
LEFT JOIN ts_godziny AS g
    ON g.id_windy = r.id_windy AND g.koniec_godziny = r.odciecie_s - 3600 * (167 - j.j)
WHERE r.nr >= ? AND r.nr < ?
ORDER BY r.nr, j.j;
```

### tsfresh (`tsfresh_cechy.wyciagnij`, `cechy_z_tsfresh`, `wybierz_cechy`)

```python
FC_PARAMETERS = {
    "root_mean_square": None, "kurtosis": None, "abs_energy": None,
    "fft_coefficient": [{"coeff": k, "attr": "abs"} for k in range(1, 85)],
}
surowe = extract_features(dlugi, column_id="id", column_sort="godzina", column_kind="kind",
                          column_value="wartosc", default_fc_parameters=FC_PARAMETERS, n_jobs=0)
moc = {k: surowe[f'{s}__fft_coefficient__attr_"abs"__coeff_{k}'] ** 2 for k in range(1, 85)}
udzial_pasma = sum(moc[k] for k in pasmo) / sum(moc.values())

# selekcja tylko na treningu, osobno wibracje i reszta (bez braków)
calculate_relevance_table(x_trening.dropna(), y_trening, ml_task="classification", fdr_level=0.05)
```

### Ocena (`tsfresh_porownanie.py`)

```python
model = lgb.LGBMClassifier(objective="binary", n_estimators=500, learning_rate=0.03, num_leaves=31,
                           min_child_samples=200, subsample=0.8, subsample_freq=1, colsample_bytree=0.8,
                           deterministic=True, force_row_wise=True, random_state=ziarno)  # ziarna 11, 22, 33 -> średnia
pr_auc = average_precision_score(y_test, wynik)
# bootstrap: 1 000 losowań 140 wind ze zwracaniem (np.random.default_rng(2026)), te same indeksy dla wszystkich modeli
```
