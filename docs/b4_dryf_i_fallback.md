# Dryf cech wind (PSI), błędy drzwi Liftar po LF-5 i reguła zapasowa dla nowych wind

Data: 2026-11-16. Model: `v3_punkt_pracy` (`failure_model/current.yaml`). Kod: `failure_model/evals/dryf.py`
(PSI, ocena korekty), `features/windy/cechy.py` (`SQL_BLEDY_DRZWI_LF5`, `korekta_lf5`),
`failure_model/versions/zapasowa_if/` + `failure_model/evals/zapasowa.py` (reguła zapasowa),
`maintenance_bc/ryzyko_dzienne.py`, `wyjasnienie.py` (alert z flagą). Tabele: `psi_cech_windy`,
`cechy_windy_korekta_lf5` (domilo.duckdb).

## Wnioski

1. Od 2025-11-17 wszystkie 38 wind Liftar ma firmware LF-5, które przy błędzie drzwi wysyła dodatkowo kod E17.
   Licznik błędów drzwi się podwoił, choć samych błędów (kod E07) i awarii drzwi nie przybyło (D1–D3). PSI cech
   błędów drzwi Liftar jest od tego dnia powyżej zmienności z treningu w każdym z 44 tygodni (D4).
2. Proponujemy poprawić definicję cechy zamiast uczyć model od nowa: dla LF-5 liczyć tylko kody E07. Przed
   2025-11-17 nic się nie zmienia (dane treningowe identyczne), PSI wraca do normy, a ten sam model na teście trafia
   trochę lepiej: Liftar PR-AUC +0,009 (95% CI +0,001 … +0,019), 57 zamiast 56 trafnych alarmów (D5). Poprawka
   jest gotowa w kodzie, ale wyłączona do Twojej decyzji (`current.yaml`: `cechy.korekta_bledow_drzwi_lf5`).
3. Poza Liftar PSI pokazuje głównie dwie rzeczy, które nie są awarią danych. Pierwsza to wibracje: w treningu
   połowa dni nie miała czujnika, a od 2025-07 ma go każda winda. Druga to dni od zmiany firmware Liftar
   (wszystkie windy zaktualizowane tego samego dnia; D4).
4. Nowe windy (pierwsze 44 dni bez normy) ocenia teraz reguła zapasowa: Isolation Forest porównujący windę
   z innymi windami tego samego modelu. Alert z tej reguły ma osobną flagę. Na 11 windach B37/B38 złapała
   1 z 4 awarii (6 z 15 dni z alarmem było trafnych). To za mało zdarzeń na pewny wniosek (D6).
   W symulacji nowej windy na teście 2026 reguła zapasowa wyraźnie wyprzedza model bez normy:
   PR-AUC 0,207 wobec 0,128, różnica +0,079 (+0,042 … +0,120). Model z normą (0,354) pozostaje dużo lepszy (D7).

## Tabele

### D1. Firmware Liftar (`telemetra_firmware`)

| Zmiana wersji głównej | Pierwsza | Ostatnia | Zmian | Wind |
|---|---|---|---:|---:|
| LF-3 → LF-3 (poprawki) | 2023-07-10 | 2025-11-08 | 30 | 19 |
| LF-4 → LF-4 (poprawki) | 2023-05-27 | 2025-09-26 | 22 | 14 |
| **LF-3 → LF-5** | **2025-11-17** | **2025-11-17** | 21 | 21 |
| **LF-4 → LF-5** | **2025-11-17** | **2025-11-17** | 17 | 17 |

### D2. Kody błędów drzwi Liftar na 1 000 okien 10-min (`telemetra_windy.kody_bledow`, `bledy_drzwi`)

| Miesiąc | Firmware | Okna | E07 | E17 | `bledy_drzwi` (obecna definicja) |
|---|---|---:|---:|---:|---:|
| 2025-07 | LF-3 / LF-4 | 93 744 / 75 888 | 1,472 / 1,199 | 0 / 0 | 1,472 / 1,199 |
| 2025-08 | LF-3 / LF-4 | 93 744 / 75 888 | 1,227 / 1,489 | 0 / 0 | 1,227 / 1,489 |
| 2025-09 | LF-3 / LF-4 | 90 720 / 73 440 | 1,378 / 1,879 | 0 / 0 | 1,378 / 1,879 |
| 2025-10 | LF-3 / LF-4 | 93 870 / 75 990 | 2,003 / 1,184 | 0 / 0 | 2,003 / 1,184 |
| 2025-11 (od 17.) | LF-5 | 76 152 | 1,760 | 2,049 | 3,808 |
| 2025-12 | LF-5 | 169 632 | 1,539 | 1,710 | 3,248 |
| 2026-01 | LF-5 | 169 632 | 1,515 | 1,497 | 3,012 |
| 2026-03 | LF-5 | 169 404 | 1,564 | 1,694 | 3,258 |
| 2026-06 | LF-5 | 164 160 | 1,511 | 1,700 | 3,210 |
| 2026-09 | LF-5 | 164 160 | 1,559 | 1,736 | 3,296 |

E17 nie występuje przed LF-5. Okna z kodami 2025-09 – 2026-01 (Liftar):
- LF-5: `E07|E17` (bledy_drzwi = 2) — 557, samotny `E07` — 76, samotny `E17` — 119;
- LF-3: `E07` — 363; LF-4: `E07` — 279.

`bledy_drzwi` = liczba kodów drzwi w oknie (E07 + E17 dla Liftar; DR01 Dźwigmet, ED2 Elmont, VD3 Vertica).

Warianty korekty, LF-5, kwartały 2025-Q4 – 2026-Q3, błędy na 1 000 okien:

| Wariant | LF-5 po aktualizacji | LF-3 / LF-4 przed nią (2025-Q1 – Q3) |
|---|---|---|
| obecna (E07 + E17) | 3,13–3,42 | 1,36–1,60 |
| max(E07, E17) | 1,82–1,98 | — |
| **tylko E07 (wybrana)** | 1,43–1,76 (miesięcznie) | — |

Wybrano „tylko E07”, bo tylko on wraca do poziomu sprzed aktualizacji. Wariant max zostawia samotne E17 i daje
więcej błędów niż przed LF-5.

### D3. Awarie Liftar według kwartału startu (`awarie_odtworzone`)

| Kwartał | 2024-Q3 | 2024-Q4 | 2025-Q1 | 2025-Q2 | 2025-Q3 | 2025-Q4 | 2026-Q1 | 2026-Q2 | 2026-Q3 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| awarie drzwi | 7 | 10 | 11 | 11 | 9 | 15 | 6 | 18 | 9 |
| wszystkie awarie | 29 | 32 | 24 | 35 | 40 | 34 | 19 | 46 | 39 |

Podwojeniu licznika błędów od 2025-Q4 nie towarzyszy podwojenie awarii drzwi.

### D4. PSI cech modelu tydzień po tygodniu (`psi_cech_windy`)

Punkt odniesienia: wiersze treningu modelu danego producenta (2023-03 – 2025-06, bez 28 wind poza treningiem). Na
treningu wyznaczamy 10 przedziałów z decyli (powtórzone granice łączymy) i osobny przedział braków. Tygodnie
liczymy pełne, poniedziałek–niedziela, od 2025-06-30 do 2026-09-14 (64), 179 cech × 4 producentów.
`ponad_trening` = PSI tygodnia wyższe niż największe PSI tej cechy w pełnych tygodniach treningu (próg z danych,
bez progów „z literatury”).

| Producent | Wiersze | Wiersze ponad trening | Cechy, które choć raz były ponad trening | Mediana PSI (bez wibracji) |
|---|---:|---:|---:|---:|
| Dźwigmet | 11 456 | 2,2% | 110 | 0,044 |
| Elmont | 11 456 | 1,4% | 79 | 0,075 |
| **Liftar** | 11 456 | **3,3%** | 32 | 0,096 |
| Vertica | 11 456 | 1,1% | 59 | 0,051 |

Liftar, tygodnie ponad trening: 259 z 382 wierszy to cechy błędów drzwi po 2025-11-17. Odsetek cech ponad treningiem
w kwartale: 0,8% (2025-Q3), 2,7% (2025-Q4), 4,3% (2026-Q1), 4,4% (2026-Q2), 5,0% (2026-Q3); u pozostałych
producentów 0,7–3,1%.

Błędy drzwi Liftar, wariant obecny i po korekcie (mediana PSI w tygodniach po 2025-11-17; tygodnie ponad trening z 44):

| Cecha | Próg (maks. PSI w treningu) | Obecna: mediana PSI | Obecna: tygodnie ponad | Korekta: tygodnie ponad |
|---|---:|---:|---:|---:|
| drzwi_bledy_sr_24h | 0,080 | 0,303 | 44 | 1 |
| drzwi_bledy_max_24h | 0,067 | 0,936 | 44 | 0 |
| drzwi_bledy_max_3d | 0,113 | 2,131 | 44 | 0 |
| drzwi_bledy_max_7d | 0,175 | 3,378 | 44 | 0 |
| drzwi_bledy_sr_3d | 0,187 | 0,422 | 44 | 0 |
| drzwi_bledy_sr_7d | 0,373 | 0,518 | 38 | 0 |
| drzwi_bledy_do_normy_7d | 0,364 | 0,202 | 1 | 0 |

Najwyższe PSI u pozostałych producentów:
- **Wibracje (PSI 4,7–5,9):** braki w treningu stanowią 50,4–57,3% (czujniki montowano od 2024-Q2 do 2025-Q1), a od 2025-07 0%.
  Próg z treningu też wynosi 4,8–5,6, więc reguła „ponad trening” odfiltrowuje większość tych tygodni.
- **Liftar `firmware_dni_od_zmiany` (PSI 9,54 wobec progu 4,11 we wszystkich 44 tygodniach):** wszystkie windy
  zmieniły firmware tego samego dnia. To prawdziwa zmiana, nie błąd definicji.

### D5. Korekta bez ponownego uczenia: ten sam model na cechach obecnych i po korekcie (test 2026-01-01 – 2026-09-22)

| Zakres | Miara | Obecna definicja | Po korekcie | Różnica (95% CI, bootstrap wind) |
|---|---|---:|---:|---|
| Wszystkie windy (36 774 dni, 2 205 z awarią) | PR-AUC | 0,3522 | 0,3544 | +0,0022 (−0,0007 … +0,0059) |
| | ROC AUC | 0,7730 | 0,7740 | +0,0011 (+0,0002 … +0,0021) |
| Liftar (9 976 dni, 689 z awarią, 38 wind) | PR-AUC | 0,3710 | 0,3802 | +0,0093 (+0,0007 … +0,0185) |
| | ROC AUC | 0,7807 | 0,7847 | +0,0040 (+0,0010 … +0,0074) |
| Reguła alarmu (38 poniedziałków, 3 alarmy) | trafne / alarmy | 56 / 114 (49,1%) | 57 / 114 (50,0%) | +1 |
| | złapane awarie | 57 z 322 | 58 z 322 | +1 |
| | alarmy dla Liftar | 31 | 30 | −1 |

Baseline korekty = obecna definicja cechy. Dane treningowe są identyczne: 0 okien z LF-5 przed 2025-11-17, 0 różnic
w `bledy_drzwi` przed tym dniem. Dlatego model nie wymaga ponownego uczenia.

### D6. Reguła zapasowa na pierwszych 44 dniach wind B37 i B38 (2024-09-15 – 2024-10-28)

Reguła: Isolation Forest osobno dla modelu windy (Liftar Compact, Flow, Flow+), uczony na dojrzałych windach tego
samego modelu z dni przed 2024-09-15 (5 032 / 4 470 / 5 589 dni). Cechy: średnia i maksimum z 24 h / 3 / 7 dni
11 sygnałów ze wskazanym podzespołem. Próg = kwantyl 1 − 3/140 wyników na danych uczących, czyli alarmy tak częste
jak w modelu głównym (3 alarmy na 140 wind tygodniowo).

| Miara (478 dni, 11 wind, 28 dni z awarią = 4 awarie) | Isolation Forest | v3 na tych samych dniach* | Losowo |
|---|---:|---:|---:|
| ROC AUC (95% CI, bootstrap wind) | 0,549 (0,160 … 0,936) | 0,848 (0,564 … 1,000) | 0,5 |
| PR-AUC | 0,272 (0,018 … 0,725) | 0,650 (0,378 … 1,000) | 0,059 |
| Dni z alarmem / trafne | 15 / 6 | — | — |
| Awarie złapane (podzespół) | 1 z 4: B37-W4 (napęd) | — | — |

\\* 10 z 11 wind (wszystkie poza B37-W2) było w treningu v3, a dni bez normy w treningu to niemal wyłącznie te
windy. Wynik v3 jest więc liczony na danych, które model widział, i jest zawyżony. Awarie: B37-W2 (zewnętrzna,
bez sygnału), B37-W3 (napęd), B37-W4 (napęd), B37-W5 (sterownik).

Poniedziałki (7):
- reguła zapasowa: alarmy 2024-09-23 B38-W3 (bez awarii), 2024-10-14 B38-W3 (bez awarii) i 2024-10-28 B37-W4
  (awaria napędu w 7 dni);
- reguła modelu na całej flocie: jeden alarm dla nowej windy, 2024-10-21 B37-W4, bez awarii w swoim oknie;
- dni-poniedziałki nowych wind z awarią w 7 dni: 4.

### D7. Symulacja nowej windy poza próbą (test 2026-01-01 – 2026-09-22, 140 wind, 2 205 dni z awarią)

Isolation Forest uczony na treningu 2023-03 – 2025-06 bez ocenianej windy (ten sam model windy). v3 bez normy:
60 cech `*_norma` i `*_do_normy_*` ustawionych na NULL, tak jak u nowej windy. Cechy po korekcie LF-5.

| Wariant | ROC AUC (95% CI) | PR-AUC (95% CI) |
|---|---|---|
| Isolation Forest (reguła zapasowa) | 0,686 (0,656 … 0,716) | **0,207** (0,168 … 0,255) |
| v3 bez normy (obecne zachowanie dla nowej windy) | 0,682 (0,651 … 0,713) | 0,128 (0,101 … 0,163) |
| v3 z normą (dojrzała winda) | 0,774 (0,745 … 0,804) | 0,354 (0,307 … 0,404) |
| **IF − v3 bez normy** | +0,004 (−0,029 … +0,038) | **+0,079 (+0,042 … +0,120)** |

### D8. Alert z reguły zapasowej (zadania produkcyjne na kopii bazy, 7 poniedziałków 2024-09-16 – 2024-10-28)

Pokaz formatu: artefakt produkcyjny jest uczony na 2023-03 – 2025-06, czyli także na dniach po tych poniedziałkach.
Liczby oceny są w D6 i D7. W każdy poniedziałek 11 wind miało tryb `zapasowa`. Alarmy zapasowe: 2024-09-23
B38-W3 i 2024-10-28 B37-W4, oba na pozycji 1; pozostałe miejsca wypełnił ranking modelu.

```json
{"id_urzadzenia": "B37-W4", "klucz_idempotencji": "B37-W4:2024-10-28",
 "tresc_zgloszenia": "Reguła zapasowa (nowa winda, 43 dni telemetrii, bez normy): błędy napędu (3 dni) 1,3 na dobę (zwykle 0 w windach Liftar Flow), …. Sprawdź silnik, przekładnię i łożyska napędu.",
 "alarm": {"dzien": "2024-10-28", "pozycja": 1, "tryb_oceny": "zapasowa",
   "regula_zapasowa": {"wersja": "zapasowa_if", "dni_telemetrii": 43, "wynik": 0.583086, "prog": 0.570703,
     "odchylenia": [{"cecha": "naped_bledy_sr_3d", "wartosc": 0.0093, "mediana_modelu": 0.0, "odchylenie_iqr": 10.31}, …]},
   "podejrzane_podzespoly": [{"podzespol": "naped", "wklad": 17.44, "sygnaly": ["naped_bledy"]}]}}
```

Zasady w produkcji (`maintenance_bc/ryzyko_dzienne.py`):
- winda z `dni_telemetrii` < 44 dostaje `tryb_oceny = zapasowa`, nie bierze udziału w rankingu modelu, a jej
  `ryzyko` (P z modelu) = NULL;
- w poniedziałek najpierw idą alarmy zapasowe (wynik ≥ próg modelu windy, od największej nadwyżki), potem ranking
  modelu, razem najwyżej 3; przerwa 7 dni i reguła „stoi” obowiązują obie grupy;
- flaga jest w `alarm.tryb_oceny` + `alarm.regula_zapasowa` w zgłoszeniu, w `alarmy_wind.tryb_oceny` i w
  `GET /lifts/{id}/risk` (`tryb_oceny`, `dni_telemetrii`, `wynik_zapasowy`, `prog_zapasowy`).

## SQL i kod

D1:

```sql
SELECT split_part(wersja_na, '.', 1) AS glowna_na, split_part(wersja_z, '.', 1) AS glowna_z,
       CAST(min(data) AS DATE) AS pierwsza, CAST(max(data) AS DATE) AS ostatnia, count(*) AS zmian,
       count(DISTINCT id_windy) AS windy
FROM telemetra_firmware WHERE wersja_z LIKE 'LF%' OR wersja_na LIKE 'LF%' GROUP BY ALL ORDER BY pierwsza;
```

D2 (na 1 000 okien; warianty korekty: `features/windy/cechy.py`, `SQL_BLEDY_DRZWI_LF5`):

```sql
SELECT date_trunc('month', ts_utc) AS mies, split_part(firmware, '.', 1) AS glowna, count(*) AS okna,
    1e3 * sum(len(regexp_extract_all(coalesce(kody_bledow, ''), 'E07'))) / count(*) AS e07,
    1e3 * sum(len(regexp_extract_all(coalesce(kody_bledow, ''), 'E17'))) / count(*) AS e17,
    1e3 * sum(bledy_drzwi) / count(*) AS bledy_drzwi
FROM telemetra_windy
WHERE id_windy IN (SELECT id_windy FROM serwis_windy WHERE producent = 'Liftar') AND ts_utc >= '2025-05-01'
GROUP BY ALL ORDER BY 1, 2;
-- kombinacje kodów: ... WHERE kody_bledow <> '' AND ts_utc >= '2025-09-01' AND ts_utc < '2026-01-31'
--   GROUP BY split_part(firmware, '.', 1), kody_bledow, bledy_drzwi
-- korekta (tylko E07 dla LF-5):
-- CASE WHEN firmware LIKE 'LF-5%' THEN len(list_filter(string_split(coalesce(kody_bledow, ''), '|'),
--      lambda k: k = 'E07')) ELSE bledy_drzwi END
```

D3:

```sql
SELECT date_trunc('quarter', a.start_awarii_tz) AS kw, count(*) FILTER (a.podzespol = 'drzwi') AS drzwi, count(*) AS wszystkie
FROM awarie_odtworzone AS a JOIN serwis_windy AS s USING (id_windy)
WHERE s.producent = 'Liftar' AND a.start_awarii_tz >= '2024-07-01' GROUP BY ALL ORDER BY 1;
```

D4, D5: `cd api && poetry run python -m api.ai.failure_model.evals.dryf --buduj-korekte` (buduje
`cechy_windy_korekta_lf5` i `psi_cech_windy`, wypisuje D5; ok. 1 min). Zestawienia D4:

```sql
SELECT wariant, producent, count(*), avg(ponad_trening::INT), count(DISTINCT cecha) FILTER (ponad_trening)
FROM psi_cech_windy GROUP BY ALL;
SELECT cecha, wariant, median(psi) FILTER (tydzien >= DATE '2025-11-17'), sum(ponad_trening::INT), max(psi_trening_maks)
FROM psi_cech_windy WHERE producent = 'Liftar' AND sygnal = 'drzwi_bledy' GROUP BY ALL;
SELECT producent, any_value(brak_trening), max(brak_tydzien), median(psi), any_value(psi_trening_maks)
FROM psi_cech_windy WHERE cecha = 'wibracje_rms_max_7d' AND wariant = 'obecna' GROUP BY 1;
SELECT producent, date_trunc('quarter', CAST(czujnik_wibracji_od AS DATE)), count(*) FROM serwis_windy GROUP BY ALL;
```

D6, D7 (i zapis artefaktu `versions/zapasowa_if/model.joblib`):
`cd api && poetry run python -m api.ai.failure_model.evals.zapasowa --zapisz` (ok. 1 min). Miary: `ocen` i `roznica`
z `failure_model/evals/ewaluacja_v2.py` (bootstrap wind, 1 000 losowań).

D8: kopia `domilo.duckdb`, dla każdego poniedziałku `cechy_dzienne.wykonaj_cechy_wind` +
`ryzyko_dzienne.wykonaj_ryzyko_wind` z atrapą klienta Serwisownika (jak w `docs/b4_ryzyko_dzienne.md`).

Testy: `api/tests/test_dryf_i_fallback_wind.py` (korekta na przykładach kodów i brak zmian przed LF-5, PSI na danych
syntetycznych i kompletność tabeli, reguła zapasowa: odsetek alarmów, odstająca winda, nieznany model, artefakt,
kolejność alarmów zapasowych i modelu, tryb i flaga w zgłoszeniu).
