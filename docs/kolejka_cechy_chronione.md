# Kolejka zapytań bez cech chronionych: język, imię, rok urodzenia (2026-11-15)

## Wnioski

1. Język klienta, imię i rok urodzenia nie wchodzą do modelu kolejki ani do żadnego promptu. Sprawdziliśmy, że nie
   wchodziły tam także wcześniej, więc po ponownym uczeniu model daje dokładnie te same wyniki. AUC w oknie migracji
   wynosi 0,7805 przed i po, na teście 0,7880 przed i po, a różnica wyniku żadnego zapytania nie przekracza 0.
2. Od teraz pilnuje tego lista `api/api/ai/features/leady/wykluczone.yaml` i test. Jeśli ktoś doda którąś z tych
   cech do modelu, kod zgłosi błąd, zanim model się nauczy.
3. Imię jest czytane tylko po to, by zamienić je w treści wiadomości na „[imię]” przed wysłaniem do LLM. W żadnej
   z 131 170 wiadomości imię nie zostało w treści.
4. Język da się jednak odgadnąć pośrednio, z tego, co klient napisał. Z cech modelu można odgadnąć, czy
   wiadomość nie jest po polsku, z AUC 0,80. Głównie zdradza to sygnał „relokacja”, bo osoby przeprowadzające się
   do Polski częściej piszą w obcym języku.
5. W oknie migracji model zaniża szansę na umowę dla zapytań po polsku (średnio 7,8% wobec 10,3% faktycznych umów),
   a dla zapytań po angielsku nie zaniża (11,6% wobec 10,7%). Przy podobnej skuteczności obu grup zapytania po
   angielsku trafiają do górnych 10% kolejki ponad dwa razy częściej (19,2% wobec 8,8%). Warto to obserwować
   i zdecydować, czy sygnał „relokacja” ma zostać w modelu.

## Co i dlaczego wykluczamy

| Cecha | Skąd | Dlaczego nie może decydować o kolejności | Gdzie wolno ją czytać | Gdzie była przed zmianą |
|---|---|---|---|---|
| `jezyk` | `crm_leady.jezyk` (pl 133 890, en 14 372, uk 10 790, inne 2 504 zapytań; Q1) | bliska pochodzeniu i narodowości | tylko audyt równego traktowania (ten raport) | nigdzie: ani w cechach, ani w opisie dla LLM |
| `imie` | `crm_leady.imie` | zdradza płeć i często pochodzenie | tylko zamiana imienia na „[imię]” w treści przed LLM (`ocena_llm._bez_imienia`) | w wejściu modelu (`KOLUMNY_WEJSCIA`) tylko do tej zamiany; nie w cechach i nie w prompcie |
| `rok_urodzenia` | `pms_najemcy.rok_urodzenia` | wiek | nigdzie | nigdzie: kolejka nie czyta danych najemców |

Pełne uzasadnienia i znane ślady pośrednie: [`wykluczone.yaml`](../api/api/ai/features/leady/wykluczone.yaml).

**Jak tego pilnujemy:**
- `sprawdz_brak_wykluczonych` zgłasza błąd, gdy wykluczona nazwa pojawi się w `KOLUMNY_CECH`, w wyniku
  `zbuduj_cechy`, w liście cech modelu (`ModelLGBMNaiwny`, `ModelLGBMIPW`, `ModelV3EVKalibracja`) albo w macierzy
  przed predykcją.
- Test [`api/tests/test_cechy_wykluczone.py`](../api/tests/test_cechy_wykluczone.py) (27 przypadków) sprawdza
  m.in., że żadna wykluczona cecha nie trafia do macierzy cech zapisanych modeli v2, v2b i v3 (także do nazw cech
  w LightGBM). Sprawdza też, że macierz v3 pomija te kolumny, nawet gdy są w danych wejściowych, oraz że opis
  zapytania dla LLM nie ma imienia, języka ani roku urodzenia. Szablony wszystkich promptów mają tylko pole
  `{opis}`, a szablon faktów uzasadnienia nie ma faktu dla tych cech.

## Wyniki

### T1. AUC i pozostałe miary przed i po wykluczeniu (v3_ev_kalibracja)

„Przed” to ten sam model i ta sama kalibracja z przebiegu
[`kalibracja.py`](../api/api/ai/lead_model/evals/kalibracja.md) (przed dodaniem listy wykluczeń). „Po” to model
nauczony od nowa i zapisany jako `versions/v3_ev_kalibracja/`. Uczenie: trening z utworzeniem przed 2025-07-01
(98 222 zapytania), kalibracja na obsłużonych zapytaniach 2025-07 – 2026-02 (24 238). W nawiasach 95% CI
(bootstrap, 2 000 losowań).

| Zbiór | Wersja | AUC | lift@10% | precision@k | ECE | Brier |
|---|---|---:|---:|---:|---:|---:|
| okno migracji (5 320, 559 umów, k = 127) | przed | 0,7805 (0,761–0,800) | 3,40 | 50,9% | 2,22 pp | 0,0837 |
| | **po (v3)** | **0,7805** (0,761–0,800) | 3,40 | 50,9% | 2,22 pp | 0,0837 |
| | baseline v0_regula_zrodla | 0,6328 (0,607–0,658) | 1,89 | 22,0% | 3,28 pp | 0,0924 |
| test 2026-03 – 2026-06 (15 217, 1 167 umów, k = 125) | przed | 0,7880 (0,775–0,800) | 3,74 | 34,9% | 1,27 pp | 0,0643 |
| | **po (v3)** | **0,7880** (0,775–0,800) | 3,74 | 34,9% | 1,27 pp | 0,0643 |
| | baseline v0_regula_zrodla | 0,6845 (0,668–0,700) | 2,31 | 17,7% | 0,74 pp | 0,0684 |

- Różnica po − przed: 0 na każdym zapytaniu w obu zbiorach, więc przedziały różnic AUC, liftu i precyzji to 0 … 0.
- Różnica v3 − v0: w oknie AUC +0,123 … +0,173, lift +1,15 … +1,89, precision +21,3 … +36,2 pp; na teście AUC
  +0,089 … +0,119.
- Cechy v3 (19): `zrodlo`, `miasto`, `linia`, `termin_dni`, `liczba_osob`, `zwierze`, `liczba_lokali`,
  `budzet_do_mediany`, `www_liczba_sesji`, `www_spacer_3d`, `www_kalkulator`, `umowa_ramowa`, `dlugosc_wiadomosci`
  i 6 sygnałów LLM `syg_*`.

### T2. Czy imię zostaje w treści wysyłanej do LLM

| | Wiadomości |
|---|---:|
| z wypełnionym polem `imie` i treścią | 131 170 |
| treść zawiera imię (rdzeń: imię bez ostatniej litery, gdy dłuższe niż 4 znaki) przed zamianą | 43 837 |
| po zamianie na „[imię]” wciąż zawiera rdzeń | 16 |

Wszystkie 16 przypadków to imię „Maciej”, którego rdzeń „Macie” pasuje do słowa „macie” („Czy macie coś na 2–3
noce…”). W żadnej wiadomości imię nie zostało.

### T3. Czy z cech modelu da się odgadnąć język (test, 19,05% zapytań nie po polsku)

Klasyfikator LightGBM uczony na treningu, który na podstawie cech modelu zgaduje, czy wiadomość nie jest po polsku.

| Cechy | AUC odgadywania języka |
|---|---:|
| wszystkie cechy v3 | 0,802 |
| bez cech z treści wiadomości (`syg_*`, `dlugosc_wiadomosci`) | 0,682 |

Najwięcej o języku mówią: `syg_relokacja` (69,5% zysku podziałów klasyfikatora), `dlugosc_wiadomosci` (8,8%),
`zrodlo` (7,7%). AUC 0,5 oznaczałoby brak śladu języka.

### T4. Okno migracji: wynik v3 w grupach języka

W oknie call center obsłużyło każde zapytanie, więc odsetek umów nie zależy od tego, do kogo oddzwonili doradcy.
Model ogólnie zaniża szansę na umowę w oknie (średnio 8,28% wobec 10,51%, kalibracja.md).

| Język | Zapytania | Umowy | Odsetek umów | Średnie p | p − umowy (95% CI) | W górnych 10% | AUC w grupie |
|---|---:|---:|---:|---:|---|---:|---:|
| pl | 4 414 | 454 | 10,29% | 7,81% | −2,47 pp (−3,32 … −1,64) | 8,8% | 0,778 |
| en | 449 | 48 | 10,69% | 11,55% | +0,86 pp (−1,67 … +3,42) | 19,2% | 0,829 |
| uk | 366 | 42 | 11,48% | 9,07% | −2,41 pp (−5,57 … +0,66) | 10,9% | 0,745 |
| inne | 91 | 15 | 16,48% | 11,78% | −4,70 pp (−12,10 … +1,99) | 20,9% | 0,843 |

Jak to czytać:
- **pl:** zaniżenie jest pewne, ale podobne do ogólnego zaniżenia w oknie.
- **en:** grupa nie jest zaniżona, a przy podobnym odsetku umów co pl trafia do czołówki ponad dwa razy częściej.
- **uk i inne:** grupy są małe, przedziały szerokie i nic pewnego z nich nie wynika.

Przyczyny nie sprawdzaliśmy. Hipoteza: sygnał „relokacja” podnosi wynik, a pojawia się częściej w wiadomościach
w obcym języku.

## SQL i kod

```bash
pypyr baza
cd api && poetry run python -m api.ai.lead_model.evals.kalibracja --bez-mlflow   # stan „przed” (wyniki/kalibracja.parquet)
cd api && poetry run python -m api.ai.lead_model.evals.ewaluacja_v3              # v3: uczenie, T1–T4, zapis wersji
poetry run pytest api/tests/test_cechy_wykluczone.py
```

Wyniki T1–T4: `api/api/ai/lead_model/versions/v3_ev_kalibracja/metryki.json` (klucze `okno_migracji`, `test`,
`audyt_imienia`, `slad_jezyka_w_cechach`, `okno_migracji.grupy_jezyka_v3`). MLflow: eksperyment `leady`, run
`v3_ev_kalibracja` (`e5071769c0774de2935b66aca2956c61`; wcześniejszy przebieg bez CI w T4 oznaczony jako usunięty).
Model: `versions/v3_ev_kalibracja/model.joblib`, ustawiony w `api/api/ai/lead_model/current.yaml`. Zapytania
uruchamiamy przez `polacz()`, bo CLI `duckdb` 1.5 nie otworzy `domilo.duckdb`.

**Q1. Języki zapytań:**

```sql
SELECT jezyk, count(*) AS zapytania FROM crm_leady GROUP BY 1 ORDER BY 2 DESC;
```

**Q2. Gdzie są pola chronione** (w bazie są tylko `crm_leady.jezyk`, `crm_leady.imie`, `crm_doradcy.imie`
i `pms_najemcy.rok_urodzenia`):

```sql
SELECT table_name, column_name FROM duckdb_columns()
WHERE column_name IN ('rok_urodzenia', 'jezyk', 'imie') ORDER BY 1;
```

**Q3. Język do audytu (T3, T4)**, czytany tylko w `ewaluacja_v3.py`:

```sql
SELECT id_leada, jezyk FROM crm_leady;
```

**Q4. Treść dla LLM (T2)**, `SQL_LEADOW` w `features/leady/ocena_llm.py`. `imie` jest czytane tylko do zamiany:

```sql
SELECT id_leada, utworzono, zrodlo, miasto, linia_pref, budzet_max, termin_wprowadzenia,
       liczba_osob, zwierze, liczba_lokali, wiadomosc, imie
FROM crm_leady ORDER BY id_leada;
```

**Strażnik** (`features/leady/wykluczone.py`):

```python
WYKLUCZONE = frozenset(wczytaj_wykluczone())          # jezyk, imie, rok_urodzenia z wykluczone.yaml

def sprawdz_brak_wykluczonych(kolumny, gdzie):
    zle = sorted(str(k) for k in kolumny
                 if any(str(k) == w or str(k).endswith(f"_{w}") or str(k).startswith(f"{w}_") for w in WYKLUCZONE))
    if zle:
        raise CechaWykluczona(f"{gdzie}: cechy wykluczone (features/leady/wykluczone.yaml): {', '.join(zle)}")
```

**Audyt języka** (fragmenty `ewaluacja_v3.py`): T3 to `LGBMClassifier(n_estimators=200, learning_rate=0.05,
random_state=42)` uczony na treningu na `jezyk != 'pl'`, AUC na teście. W T4 górne 10% to 532 zapytania okna
o najwyższym p, a CI różnicy p − umowy to bootstrap zapytań w grupie (2 000 losowań, ziarno 42).
