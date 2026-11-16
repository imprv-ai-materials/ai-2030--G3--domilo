# Ekstrakcja awarii z notatek: ocena na złotym zbiorze (B4)

Stan danych: eksport 2026-09-30 23:59 Europe/Warsaw, baza `domilo.duckdb` z 2026-11-16. Ekstrakcja: prompt
`awaria_v1`, model `gpt-6-luna` (reasoning effort `none`, temperatura 0), wejście = zgłoszenie z wszystkimi notatkami,
bez kategorii (`api/api/ai/llm/ekstrakcja_awarii.py`). Prawda: `serwis_zloty_zbior` (400 zgłoszeń wind oznaczonych
ręcznie przez koordynatora). Punkt odniesienia: etykieta Serwisownika `kategoria = 'awaria'` na tych samych zgłoszeniach.

## Wnioski

1. Odczyt notatek przez LLM znajduje prawie wszystkie awarie z listy koordynatora i nie daje fałszywych alarmów.
   Na 400 zgłoszeniach wskazał 176 awarii, wszystkie prawdziwe, i pominął 4 ze 180 (F1 98,9%, przedział 95%:
   97,7–99,7%). Kategoria „awaria” z Serwisownika znajduje tylko 55 ze 180 awarii (F1 46,4%). Różnica F1 wynosi
   +52,5 p.p. (+45,0 … +60,1).
2. Podzespół jest trafny w 157 ze 180 prawdziwych awarii (87,2%). Za każdym razem, gdy LLM nazwał podzespół
   (157 razy), zgadzał się z koordynatorem. Pozostałe 23 to 4 pominięte awarie i 19 zgłoszeń, w których notatki nie
   mówią, co się zepsuło („Interwencja — winda nie jeździła, po naprawie OK.”). Przy 15 z tych 19 zgłoszeń przyczynę
   wskazuje wymieniona część w `serwis_czesci` (np. falownik, enkoder, zamek kabinowy).
3. Wszystkie 4 pominięte awarie mają ten sam układ. Zgłoszenie mówi o uwięzieniu albo postoju windy, a notatka
   opisuje wymianę dużego podzespołu (łożyska i hamulec silnika, karta I/O sterownika, zasilacz w szafie sterownika)
   albo „usunięto usterkę, winda w ruchu”, ale nie pisze wprost, że winda stała. Każda z nich ma pewność ≤ 0,5,
   a takich odpowiedzi jest 34. Ręczny przegląd tych 34 zgłoszeń wyłapałby na tym zbiorze wszystkie błędy.
4. F1 przekracza próg 0,85, więc nie tworzyliśmy `awaria_v2`. Wynik jest jednak optymistyczny z dwóch powodów.
   Prompt powstał po przejrzeniu części złotego zbioru (25 zgłoszeń z notatkami i etykiety kilku typów notatek).
   Do tego notatki są szablonowe: 573 notatki w złotym zbiorze to tylko 150 różnych treści. Zanim etykieta z LLM
   stanie się celem modelu awarii wind, warto ją sprawdzić na świeżo oznaczonych zgłoszeniach.

## Tabele

### E1. `czy_awaria`: LLM wobec kategorii „awaria” (400 zgłoszeń)

Przedziały 95%: bootstrap zgłoszeń, 2 000 losowań (ziarno 20261116), te same losowania dla obu metod.

| metoda | TP | FP | FN | TN | precision | recall | F1 | F1 95% | recall 95% | trafność |
|---|---|---|---|---|---|---|---|---|---|---|
| kategoria = awaria (baseline) | 55 | 2 | 125 | 218 | 96,5% | 30,6% | 46,4% | 38,8% – 53,9% | 24,3% – 37,2% | 68,2% |
| LLM awaria_v1 | 176 | 0 | 4 | 220 | 100,0% | 97,8% | 98,9% | 97,7% – 99,7% | 95,4% – 99,5% | 99,0% |

Różnice LLM − baseline (sparowane, te same losowania):

| porównanie | miara | różnica | 95% |
|---|---|---|---|
| LLM awaria_v1 − baseline | f1 | +52,5 p.p. | +45,0 p.p. … +60,1 p.p. |
| LLM awaria_v1 − baseline | recall | +67,2 p.p. | +60,1 p.p. … +73,8 p.p. |
| LLM awaria_v1 − baseline | precision | +3,5 p.p. | +0,0 p.p. … +8,6 p.p. |

### E2. Tabele pomyłek

Kategoria „awaria” (baseline):

|  | przewidziano: awaria | przewidziano: brak awarii |
|---|---|---|
| koordynator: awaria | 55 | 125 |
| koordynator: brak awarii | 2 | 218 |

LLM `awaria_v1`:

|  | przewidziano: awaria | przewidziano: brak awarii |
|---|---|---|
| koordynator: awaria | 176 | 4 |
| koordynator: brak awarii | 0 | 220 |

### E3. Wyniki LLM według kategorii Serwisownika

Kategoria nie trafia do wejścia LLM. 125 awarii pominiętych przez etykietę „awaria” leży w kategoriach
„interwencja”, „usterka” i „inne” (60 + 31 + 34). LLM znajduje 122 z nich na podstawie notatek
(59 + 29 + 34).

| kategoria | zgłoszenia | awarie (koordynator) | awarie (LLM) | zgodne | pominięte awarie (FN) | fałszywe alarmy (FP) |
|---|---|---|---|---|---|---|
| konserwacja | 93 | 0 | 0 | 93 | 0 | 0 |
| interwencja | 76 | 60 | 59 | 75 | 1 | 0 |
| usterka | 66 | 31 | 29 | 64 | 2 | 0 |
| awaria | 57 | 55 | 54 | 56 | 1 | 0 |
| inne | 57 | 34 | 34 | 57 | 0 | 0 |
| przegląd | 51 | 0 | 0 | 51 | 0 | 0 |

### E4. Podzespół na prawdziwych awariach (180)

W złotym zbiorze `wandalizm` to osobna wartość, a w schemacie LLM mieści się w `zewnetrzna`. Porównujemy po zamianie
`wandalizm` → `zewnetrzna`.

| prawdziwe awarie | podzespół trafny | trafność | LLM: brak podzespołu | w tym pominięte awarie (FN) | w tym trafione awarie bez podzespołu | LLM nazwał podzespół | trafne wśród nazwanych | trafność wśród nazwanych |
|---|---|---|---|---|---|---|---|---|
| 180 | 157 | 87,2% | 23 | 4 | 19 | 157 | 157 | 100,0% |

Koordynator (wiersze) × LLM (kolumny):

| koordynator \ LLM | brak | drzwi | hamulec_liny | naped | sterownik | zewnetrzna |
|---|---|---|---|---|---|---|
| drzwi | 7 | 68 | 0 | 0 | 0 | 0 |
| hamulec_liny | 1 | 0 | 10 | 0 | 0 | 0 |
| naped | 6 | 0 | 0 | 20 | 0 | 0 |
| sterownik | 5 | 0 | 0 | 0 | 22 | 0 |
| zewnetrzna | 4 | 0 | 0 | 0 | 0 | 37 |

### E5. Notatki trafionych awarii, w których LLM nie podał podzespołu (19 zgłoszeń)

Żadna z tych treści nie nazywa podzespołu. Koordynator znał przyczynę z innego źródła; z jakiego, tego w danych nie
ma. Cyfry zastąpione przez N.

| notatka | notatki | zgłoszenia |
|---|---|---|
| Interwencja — winda nie jeździła, po naprawie OK. | 5 | 5 |
| Po naprawie test OK, przekazano do eksploatacji. | 5 | 5 |
| Uruchomiono, jazdy próbne OK. | 4 | 4 |
| Na miejscu o N:N. Interwencja — winda nie jeździła, po naprawie OK. | 3 | 3 |
| Przyjazd N:N, winda stoi na N. piętrze. Przyjazd na wezwanie, usunięto usterkę, winda w ruchu. | 3 | 3 |
| Winda stała, przyjazd, naprawione, uruchomiono. | 3 | 3 |
| Naprawa zakończona, winda w ruchu. | 2 | 2 |
| Dojazd N:N, zabezpieczenie szybu. Winda stała, przyjazd, naprawione, uruchomiono. | 1 | 1 |
| Na miejscu o N:N. Przyjazd na wezwanie, usunięto usterkę, winda w ruchu. | 1 | 1 |
| Po nparawie test OK, przekazano do eksploatacji. | 1 | 1 |
| Przyjazd N:N, uwolniono N os. Przyjazd na wezwanie, usunięto usterkę, winda w ruchu. | 1 | 1 |
| Przyjazd N:N, winda stoi na N. piętrze. Winda wyłączona z ruchu, naprawa na miejscu, test OK. | 1 | 1 |
| Winda wyłączona z ruchu, naprawa na miejscu, test OK. | 1 | 1 |

Części wymienione w tych zgłoszeniach (`serwis_czesci`) według podzespołu koordynatora:

| podzespol_koordynatora | zgloszenia | z_czesciami | czesci |
|---|---|---|---|
| drzwi | 6 | 3 | Kurtyna świetlna; Operator drzwi; Pasek napędu drzwi; Zamek kabinowy (ZK) |
| hamulec_liny | 1 | 1 | Lina nośna; Wkładki prowadnic |
| naped | 5 | 5 | Enkoder; Falownik; Łożysko silnika |
| sterownik | 3 | 2 | Karta I/O; Płyta sterownika; Zasilacz 24V |
| wandalizm | 1 | 1 | Panel kabiny; Przycisk |
| zewnetrzna | 3 | 3 | Bezpiecznik główny; Czujnik wody |
| RAZEM | 19 | 15 | Bezpiecznik główny; Czujnik wody; Enkoder; Falownik; Karta I/O; Kurtyna świetlna; Lina nośna; Operator drzwi; Panel kabiny; Pasek napędu drzwi; Przycisk; Płyta sterownika; Wkładki prowadnic; Zamek kabinowy (ZK); Zasilacz 24V; Łożysko silnika |

W złotym zbiorze część ma 106 ze 180 awarii i 19 z 220 zgłoszeń bez awarii (zapytanie w sekcji SQL). Nazwa części
„Zamek kabinowy (ZK)” rozwija też skrót ZK, którego w notatkach nikt nie rozpisuje.

### E6. Pewność deklarowana przez LLM a błędy `czy_awaria`

| pewność LLM | zgłoszenia | zgodne | błędne czy_awaria |
|---|---|---|---|
| ≤ 0,5 | 34 | 30 | 4 |
| 0,5–0,8 | 42 | 42 | 0 |
| 0,8–0,95 | 29 | 29 | 0 |
| > 0,95 | 295 | 295 | 0 |

### E7. 10 błędów

Reguła wyboru: najpierw wszystkie pomyłki `czy_awaria` (4, od najwyższej pewności). Potem trafione awarie ze złym
podzespołem, po jednej z każdej grupy podzespołu koordynatora, od najliczniejszej grupy (kolejność w grupie według
md5(id_zgloszenia)).

| # | zgłoszenie | kategoria | koordynator | LLM | pewność | treść zgłoszenia i notatki | objaw (LLM) |
|---|---|---|---|---|---|---|---|
| 1 | Z007050 | usterka | awaria / naped | brak / brak | 0,50 | „Ktoś utknął w windzie”<br>[2024-02-27 11:22] K19 (konserwator): Wymiana łożysk i hamulca silnika, regulacja falownika, test jazdy OK. | Wymieniono łożyska i hamulec silnika oraz wyregulowano falownik; test jazdy OK. |
| 2 | Z000976 | awaria | awaria / sterownik | brak / brak | 0,35 | „Ktoś utknął w windzie”<br>[2023-03-06 19:28] K14 (konserwator): Na miejscu o 19:28. Wymiana karty I/O i aktualizacja konfiguracji, reset ster., test OK. | Zgłoszono uwięzienie osoby; wymieniono kartę I/O i zresetowano sterownik, ale postój niepotwierdzony. |
| 3 | Z002083 | usterka | awaria / sterownik | brak / brak | 0,35 | „Ktoś utknął w windzie”<br>[2023-05-15 08:56] K07 (konserwator): Wymiana zasilacza 24V w szafie ster., po restarcie praca normalna. | Wymieniono zasilacz 24 V w szafie sterownika; po restarcie winda pracowała normalnie. |
| 4 | Z016428 | interwencja | awaria / drzwi | brak / brak | 0,30 | „Winda nie przyjeżdża na wezwanie”<br>[2025-07-23 12:00] K01 (konserwator): Przyjazd na wezwanie, usunięto usterkę, winda w ruchu. | Usunięto usterkę; winda ponownie w ruchu. |
| 5 | Z023494 | awaria | awaria / drzwi | awaria / brak | 0,90 | „Ktoś utknął w windzie”<br>[2026-07-27 04:34] K08 (konserwator): Interwencja — winda nie jeździła, po naprawie OK.<br>[2026-07-28 14:38] K08 (konserwator): Po naprawie test OK, przekazano do eksploatacji. | Winda nie jeździła; po naprawie przekazano ją do eksploatacji. |
| 6 | Z012845 | inne | awaria / naped | awaria / brak | 0,85 | „Winda nie jeździ”<br>[2025-01-14 12:57] K18 (konserwator): Przyjazd 12:57, winda stoi na 4. piętrze. Przyjazd na wezwanie, usunięto usterkę, winda w ruchu.<br>[2025-01-15 01:56] K18 (konserwator): Po nparawie test OK, przekazano do eksploatacji. | Winda stała na 4. piętrze; usterkę usunięto i przywrócono ją do ruchu. |
| 7 | Z011737 | usterka | awaria / sterownik | awaria / brak | 0,80 | „Drzwi windy się nie zamykają”<br>[2024-11-16 18:32] K07 (konserwator): Winda wyłączona z ruchu, naprawa na miejscu, test OK.<br>[2024-11-17 02:25] K07 (konserwator): Naprawa zakończona, winda w ruchu. | Winda wyłączona z ruchu; naprawa zakończona i winda ponownie w ruchu. |
| 8 | Z017241 | usterka | awaria / zewnetrzna | awaria / brak | 0,80 | „Winda szarpie i hałasuje”<br>[2025-09-01 12:40] K04 (konserwator): Interwencja — winda nie jeździła, po naprawie OK. | Winda nie jeździła; po naprawie działa prawidłowo. |
| 9 | Z000932 | awaria | awaria / hamulec_liny | awaria / brak | 1,00 | „Winda nie jeździ”<br>[2023-03-02 13:13] K15 (konserwator): Winda stała, przyjazd, naprawione, uruchomiono.<br>[2023-03-02 17:20] K15 (konserwator): Uruchomiono, jazdy próbne OK. | Winda stała, następnie naprawiona i uruchomiona; przyczyna niepodana. |
| 10 | Z007647 | inne | awaria / wandalizm | awaria / brak | 1,00 | „Ktoś utknął w windzie”<br>[2024-03-31 01:55] K05 (konserwator): Dojazd 01:55, zabezpieczenie szybu. Winda stała, przyjazd, naprawione, uruchomiono. | Winda stała; naprawiono i uruchomiono, przyczyna niepodana. |

Co z tego wynika:

- **1–4 (pominięte awarie).** Zgłaszający pisze „Ktoś utknął w windzie” albo „Winda nie przyjeżdża na wezwanie”,
  a konserwator opisuje tylko naprawę. Prompt mówi, że rozstrzygają notatki, a treść zgłoszenia nie jest
  potwierdzeniem, więc model uznał postój za niepotwierdzony („postój niepotwierdzony”, pewność 0,30–0,50).
  Wymiana łożysk i hamulca silnika, karty I/O czy zasilacza sterownika po zgłoszeniu o uwięzieniu to dla
  koordynatora awaria. W przykładzie 1 koordynator wybrał `naped`, choć notatka wymienia też hamulec silnika,
  więc nawet podzespół jest tu niejednoznaczny.
- **5–10 (awaria bez podzespołu).** Model dobrze rozpoznał postój, ale notatki nie mówią, co się zepsuło
  („Winda stała, przyjazd, naprawione, uruchomiono.”). Zgodnie z promptem odpowiedział `brak`. To nie błąd
  odczytu, tylko brak informacji w notatkach. W przykładzie 10 (wandalizm) dopiero części w `serwis_czesci`
  (przycisk, panel kabiny) sugerują uszkodzenie.

### E8. Zużycie tokenów

Cennika w danych nie ma, więc koszt w PLN: brak w danych.

| wersja | zgłoszenia | tokeny wejścia | w tym z cache OpenAI | tokeny wyjścia | wejście / zgłoszenie | wyjście / zgłoszenie |
|---|---|---|---|---|---|---|
| awaria_v1 | 400 | 990174 | 925010 | 29894 | 2475 | 75 |

### E9. Różnorodność notatek w złotym zbiorze

Notatki są syntetyczne i szablonowe (cyfry zastąpione przez N, białe znaki scalone). Dlatego wynik na tym zbiorze
może być wyższy niż na prawdziwych notatkach.

| koordynator | zgloszenia | notatki | rozne_tresci_cyfry_jako_N |
|---|---|---|---|
| awaria | 180 | 286 | 108 |
| brak awarii | 220 | 287 | 42 |
| RAZEM | 400 | 573 | 150 |

### Propozycja `awaria_v2` (nieuruchomiona, bo F1 ≥ 0,85)

Gdyby wynik trzeba było poprawić, zmiany wynikają wprost z E5–E7:

1. Do wejścia dodać części wymienione w zgłoszeniu (`serwis_czesci.nazwa_czesci`, `kod_czesci`). To podpowiedź
   podzespołu przy 15 z 19 awarii, w których notatki milczą.
2. Zasada: wymiana lub naprawa podzespołu napędu, sterownika, hamulca albo drzwi po zgłoszeniu o postoju lub
   uwięzieniu („utknął”, „nie jeździ”, „nie przyjeżdża”, „wyłączona”) to awaria, nawet gdy notatka nie pisze
   „winda stała”. Dotyczy 4 pominiętych awarii.
3. ZK opisać jako „zamek kabinowy” (nazwa z `serwis_czesci`).
4. `czas_naprawy_h` liczyć w kodzie z godziny przywrócenia windy do ruchu zwracanej przez model. W smoke teście
   jedno z trzech sprawdzonych wyliczeń było błędne o 24 h.

Ryzyko punktu 2: reguła może podnieść liczbę fałszywych alarmów (dziś 0). Sprawdzać ją trzeba na zgłoszeniach spoza
złotego zbioru, bo złoty zbiór posłużył już do ułożenia `awaria_v1`.

## SQL i kod

Powtórzenie (z katalogu głównego repozytorium; ekstrakcja wymaga `OPENAI_API_KEY`, ponowne uruchomienie czyta cache `api/api/ai/llm/cache/`):

```bash
set -a && . ./.env && set +a
cd api && poetry run python -m api.ai.llm.ekstrakcja_awarii --zbior zloty_zbior   # -> ai/features/windy/awarie_llm/awaria_v1_zloty_zbior.parquet
poetry run python -m api.ai.llm.evals.ocena_awarii awaria_v1                         # tabele E1–E9
```

Kod: `api/api/ai/llm/evals/ocena_awarii.py` (testy: `api/tests/test_ocena_awarii.py`), ekstrakcja `api/api/ai/llm/ekstrakcja_awarii.py`, prompt `api/api/ai/llm/prompts/awaria_v1.yaml`, schemat `api/api/ai/llm/schemas/awaria.py`.

### Prawda i baseline (złoty zbiór + kategoria)

```sql
SELECT
    zz.id_zgloszenia,
    zz.czy_awaria AS prawda,
    CASE zz.podzespol WHEN 'wandalizm' THEN 'zewnetrzna' ELSE zz.podzespol END AS podzespol_prawda,
    zz.podzespol AS podzespol_zz,
    z.kategoria,
    z.kategoria = 'awaria' AS kategoria_awaria
FROM serwis_zloty_zbior AS zz
JOIN serwis_zgloszenia AS z USING (id_zgloszenia)
```

Odpowiedzi LLM (`awaria_v1_zloty_zbior.parquet`) łączone po `id_zgloszenia` (`validate='one_to_one'`); zgłoszenie bez odpowiedzi albo z błędem przerywa ocenę (tu: 0 błędów, 400 odpowiedzi).

### Metryki, tabela pomyłek, bootstrap

```python
def tabela_pomylek(prawda: np.ndarray, przewidywanie: np.ndarray) -> dict[str, int]:
    prawda, przewidywanie = np.asarray(prawda, bool), np.asarray(przewidywanie, bool)
    return {
        "tp": int((prawda & przewidywanie).sum()),
        "fp": int((~prawda & przewidywanie).sum()),
        "fn": int((prawda & ~przewidywanie).sum()),
        "tn": int((~prawda & ~przewidywanie).sum()),
    }

def metryki(prawda: np.ndarray, przewidywanie: np.ndarray) -> dict[str, float]:
    """precision, recall, F1, trafność; NaN, gdy mianownik = 0."""
    t = tabela_pomylek(prawda, przewidywanie)
    p = t["tp"] / (t["tp"] + t["fp"]) if t["tp"] + t["fp"] else float("nan")
    r = t["tp"] / (t["tp"] + t["fn"]) if t["tp"] + t["fn"] else float("nan")
    f1 = 2 * t["tp"] / (2 * t["tp"] + t["fp"] + t["fn"]) if t["tp"] + t["fp"] + t["fn"] else float("nan")
    return {"precision": p, "recall": r, "f1": f1, "trafnosc": (t["tp"] + t["tn"]) / sum(t.values())}

def bootstrap(
    prawda: np.ndarray, metody: dict[str, np.ndarray], losowania: int = LOSOWANIA, ziarno: int = ZIARNO
) -> dict[str, pd.DataFrame]:
    """Metoda -> DataFrame (losowanie × precision/recall/f1/trafnosc) na tych samych losowaniach zgłoszeń."""
    rng = np.random.default_rng(ziarno)
    n = len(prawda)
    indeksy = rng.integers(0, n, size=(losowania, n))
    prawda = np.asarray(prawda, bool)
    return {
        nazwa: pd.DataFrame([metryki(prawda[i], np.asarray(przew, bool)[i]) for i in indeksy])
        for nazwa, przew in metody.items()
    }
```

### Podzespół (E4) i pewność (E6)

```python
def podzespoly(df: pd.DataFrame) -> tuple[str, str]:
    """(trafność podzespołu na prawdziwych awariach, macierz prawda × LLM)."""
    a = df[df["prawda"]]
    trafne = a["podzespol"] == a["podzespol_prawda"]
    nazwane = a["podzespol"] != "brak"
    podsum = pd.DataFrame(
        [
            {
                "prawdziwe awarie": len(a),
                "podzespół trafny": int(trafne.sum()),
                "trafność": _proc(trafne.mean()),
                "LLM: brak podzespołu": int((a["podzespol"] == "brak").sum()),
                "w tym pominięte awarie (FN)": int((~a["czy_awaria"]).sum()),
                "w tym trafione awarie bez podzespołu": int((a["czy_awaria"] & (a["podzespol"] == "brak")).sum()),
                "LLM nazwał podzespół": int(nazwane.sum()),
                "trafne wśród nazwanych": int((trafne & nazwane).sum()),
                "trafność wśród nazwanych": _proc((trafne & nazwane).sum() / nazwane.sum()),
            }
        ]
    )
    macierz = pd.crosstab(a["podzespol_prawda"], a["podzespol"]).reset_index()
    macierz = macierz.rename(columns={"podzespol_prawda": "koordynator \\ LLM"})
    macierz.columns.name = None
    return _md(podsum), _md(macierz)

def pewnosc(df: pd.DataFrame) -> str:
    """Pewność deklarowana przez LLM × zgodność czy_awaria z koordynatorem."""
    przedzialy = pd.cut(
        df["pewnosc"], [0, 0.5, 0.8, 0.95, 1.0], include_lowest=True, labels=["≤ 0,5", "0,5–0,8", "0,8–0,95", "> 0,95"]
    )
    g = (
        df.assign(przedzial=przedzialy, zgodne=df["prawda"] == df["czy_awaria"])
        .groupby("przedzial", sort=True, observed=False)
        .agg(zgloszenia=("zgodne", "size"), zgodne=("zgodne", "sum"))
        .reset_index()
    )
    g["błędne czy_awaria"] = g["zgloszenia"] - g["zgodne"]
    return _md(g.rename(columns={"przedzial": "pewność LLM", "zgloszenia": "zgłoszenia"}))
```

### Notatki i części awarii bez podzespołu (E5)

```python
def notatki_bez_podzespolu(con, df: pd.DataFrame) -> str:
    """Treści notatek w prawdziwych awariach, którym LLM nie przypisał podzespołu (cyfry -> N)."""
    ids = df.loc[df["prawda"] & df["czy_awaria"] & (df["podzespol"] == "brak"), "id_zgloszenia"].tolist()
    con.register("ids_bez_podzespolu", pd.DataFrame({"id_zgloszenia": pd.Series(ids, dtype="string")}))
    try:
        wynik = con.execute("""
            SELECT regexp_replace(regexp_replace(tresc, '\\s+', ' ', 'g'), '[0-9]+', 'N', 'g') AS notatka,
                   count(*) AS notatki, count(DISTINCT id_zgloszenia) AS zgloszenia
            FROM serwis_notatki WHERE id_zgloszenia IN (SELECT id_zgloszenia FROM ids_bez_podzespolu)
            GROUP BY 1 ORDER BY notatki DESC, notatka
            """).df()
        wynik = wynik.rename(columns={"zgloszenia": "zgłoszenia"})
    finally:
        con.unregister("ids_bez_podzespolu")
    return _md(wynik)

def czesci_bez_podzespolu(con, df: pd.DataFrame) -> str:
    """Trafione awarie bez podzespołu (LLM) według podzespołu koordynatora: ile ma części w serwis_czesci i jakie."""
    b = df.loc[df["prawda"] & df["czy_awaria"] & (df["podzespol"] == "brak"), ["id_zgloszenia", "podzespol_zz"]]
    con.register("bez_podzespolu", b.astype({"id_zgloszenia": "string", "podzespol_zz": "string"}))
    try:
        wynik = con.execute("""
            SELECT b.podzespol_zz AS podzespol_koordynatora, count(DISTINCT b.id_zgloszenia) AS zgloszenia,
                   count(DISTINCT c.id_zgloszenia) AS z_czesciami,
                   string_agg(DISTINCT c.nazwa_czesci, '; ' ORDER BY c.nazwa_czesci) AS czesci
            FROM bez_podzespolu AS b
            LEFT JOIN serwis_czesci AS c USING (id_zgloszenia)
            GROUP BY ROLLUP (b.podzespol_zz)
            ORDER BY b.podzespol_zz IS NULL, b.podzespol_zz
            """).df()
    finally:
        con.unregister("bez_podzespolu")
    wynik["podzespol_koordynatora"] = wynik["podzespol_koordynatora"].fillna("RAZEM")
    return _md(wynik)
```

Części w złotym zbiorze według etykiety koordynatora (106 / 180 awarii, 19 / 220 bez awarii):

```sql
SELECT zz.czy_awaria, count(DISTINCT zz.id_zgloszenia) AS zgloszenia, count(DISTINCT c.id_zgloszenia) AS z_czesciami
FROM serwis_zloty_zbior AS zz LEFT JOIN serwis_czesci AS c USING (id_zgloszenia)
GROUP BY 1
```

### Wybór 10 błędów (E7)

```python
def wybierz_bledy(df: pd.DataFrame, n: int = LICZBA_BLEDOW) -> pd.DataFrame:
    """Błędy do pokazania: najpierw wszystkie pomyłki czy_awaria (od najwyższej pewności), potem błędny podzespół
    na prawdziwych awariach — po jednym na każdy podzespół koordynatora (w kolejności malejącej liczby takich
    błędów), aż do n. W obrębie grupy kolejność według md5(id_zgloszenia) — powtarzalnie."""
    import hashlib

    df = df.assign(_md5=df["id_zgloszenia"].map(lambda s: hashlib.md5(s.encode()).hexdigest()))
    zle_czy = df[df["prawda"] != df["czy_awaria"]].sort_values(["pewnosc", "_md5"], ascending=[False, True])
    zle_pod = df[df["prawda"] & df["czy_awaria"] & (df["podzespol"] != df["podzespol_prawda"])].sort_values("_md5")
    # po kolei: pierwszy błąd z każdej grupy podzespołu (grupy od najliczniejszej), potem drugi itd.
    grupy = sorted((g for _, g in zle_pod.groupby("podzespol_zz")), key=len, reverse=True)
    po_kolei = [g.iloc[[i]] for i in range(max(map(len, grupy), default=0)) for g in grupy if i < len(g)]
    return pd.concat([zle_czy, *po_kolei]).head(n).drop(columns="_md5")
```

### Różnorodność notatek (E9)

```sql
WITH n AS (
    SELECT n.id_zgloszenia, zz.czy_awaria,
           regexp_replace(regexp_replace(n.tresc, '\s+', ' ', 'g'), '[0-9]+', 'N', 'g') AS wzor
    FROM serwis_notatki AS n
    JOIN serwis_zloty_zbior AS zz USING (id_zgloszenia)
)
SELECT
    coalesce(CASE czy_awaria WHEN true THEN 'awaria' WHEN false THEN 'brak awarii' END, 'RAZEM') AS koordynator,
    count(DISTINCT id_zgloszenia) AS zgloszenia,
    count(*) AS notatki,
    count(DISTINCT wzor) AS rozne_tresci_cyfry_jako_N
FROM n
GROUP BY ROLLUP (czy_awaria)
ORDER BY czy_awaria IS NULL, czy_awaria DESC
```
