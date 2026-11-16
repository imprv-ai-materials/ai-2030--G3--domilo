# CLAUDE.md — Domilo S.A.

## Firma

Domilo S.A. to operator najmu instytucjonalnego: wynajmuje mieszkania w budynkach, które sam posiada i obsługuje.
Dane są syntetyczne (firmy, osoby i adresy fikcyjne), przygotowane do kursu „Zostań praktykiem modeli predykcyjnych”.

Skala według danych (sprawdzone 2026-11-15 na `pms_budynki`, `pms_lokale`, `serwis_windy`):

| Miasto | Budynki | Lokale | Windy |
|---|---:|---:|---:|
| Warszawa | 14 | 2 900 | 52 |
| Kraków | 7 | 1 300 | 26 |
| Wrocław | 6 | 1 100 | 22 |
| Poznań | 4 | 700 | 14 |
| Gdańsk | 4 | 650 | 15 |
| Łódź | 3 | 550 | 11 |
| **Razem** | **38** | **7 200** | **140** |

Systemy źródłowe: PMS (lokale, najmy, umowy, płatności), CRM (zapytania, doradcy, www), portal najemcy,
serwisownik (zgłoszenia techniczne, windy), Telemetra (czujniki wind i ciepła), Radar (rynek: oferty, transakcje RCN,
operaty, zdjęcia), FK (koszty), dane zewnętrzne (POI, dzielnice GUS). Opis tabel: [data/README.md](data/README.md).

## Cztery modele

| Model | Pytanie biznesowe | Główne źródła |
|---|---|---|
| Wycena lokali z przedziałem | Ile wart jest czynsz / lokal i z jaką niepewnością? | `radar/`, `zewnetrzne/`, `pms_lokale` |
| Kolejka zapytań dla doradców | Którym zapytaniem doradca ma zająć się najpierw? | `crm/` |
| Lista retencyjna najemców | Którzy najemcy nie przedłużą umowy i komu dać ofertę? | `pms_umowy`, `portal/`, `retencja_decyzje`, `fk_rabaty` |
| Alerty o awariach wind | Która winda wkrótce się zepsuje? | `serwis/`, `telemetra/telemetra_windy` |

## Zasady (obowiązują zawsze)

1. **`data/` jest tylko do odczytu.** Nie zapisuj, nie przenoś, nie usuwaj i nie nadpisuj niczego w `data/`.
   Bazy (`domilo.duckdb`), wyniki pośrednie, modele i raporty zapisuj poza tym katalogiem.
2. **Liczby tylko z danych.** Każda liczba w raporcie, kodzie, komentarzu i odpowiedzi pochodzi z zapytania lub
   obliczenia wykonanego na `data/` (albo na artefakcie z niego zbudowanym), a zapytanie jest pokazane obok.
   Nie podawaj liczb z pamięci, wiedzy ogólnej ani szacunków „na oko”. Jeśli danych brakuje, napisz „brak w danych”.
   Założenia biznesowe (np. koszt utraconego najemcy) podawaj tylko od użytkownika i oznaczaj jako założenie.
3. **Każdy model ma punkt odniesienia (baseline)** zapisany w [evals/porownanie.md](evals/porownanie.md):
   prosta reguła lub obecny sposób działania firmy, liczony na tym samym podziale danych i tymi samymi metrykami co model.
   Bez porównania z baseline nie piszemy, że model „działa” ani że jest „lepszy”.
4. **Raporty w `docs/`** (Markdown) mają stały układ:
   1. 3–5 zdań wniosków (co z tego wynika dla Domilo, bez żargonu);
   2. tabele z wynikami;
   3. SQL i kod, którymi wyniki policzono (tak, by dało się je powtórzyć).
5. **Odpowiedź w czacie kończ** listą zmienionych plików i pytaniami do użytkownika.

## Pułapki w danych (ważne dla modeli)

- **Dzień eksportu: 2026-09-30 23:59 Europe/Warsaw.** Dane zdarzeniowe 2023-01-01 – 2026-09-30.
- **Stan na dzień eksportu ≠ historia:** `pms_lokale.status`, `pms_lokale.czynsz_katalogowy`, `crm_leady.status`
  opisują stan na koniec eksportu. Cechy do modelu bierz z historii (`crm_historia_statusow`, `pms_umowy`, …)
  według stanu na moment predykcji, inaczej przeciek przyszłości.
- **Importy i migracje:** PMS od 2019-04, rekordy sprzed 2023-03-01 to import (puste `data_podpisania`,
  puste `zrodlo`); CRM sprzed 2025-03-03 to migracja z poprzedniego systemu.
- **Opóźnienie RCN:** `rcn_transakcje` kończy się 2026-06-30 (publikacja z opóźnieniem 60–120 dni).
- **Czas:** CRM — tekst ISO 8601 z przesunięciem; serwisownik — czas lokalny bez strefy (2025-10-26 02:00–03:00
  występuje dwa razy); Telemetra — `ts_utc` w UTC, koniec okna 10 min. Czas biznesowy: Europe/Warsaw.
- **Formaty:** `serwis_czesci.koszt_netto` to tekst z przecinkiem dziesiętnym (`1 234,50`);
  `wibracje_rms_mg` puste przed montażem czujnika (`serwis_windy.czujnik_wibracji_od`).
- Najmy z `data_wprowadzenia` po dniu eksportu to umowy już podpisane (lokal ma jeszcze status „wolny”).
- `portal_logowania_mies` to agregat za **cały** miesiąc kalendarzowy — uważaj na miesiąc predykcji.

## Mapa folderów

```
data/                         # dane źródłowe Domilo — TYLKO DO ODCZYTU
domilo.duckdb                 # baza budowana z data/ (pypyr baza), w .gitignore
docs/                         # raporty (wnioski → tabele → SQL i kod)
├── bank/                     # raporty kwartalne dla banku (zadanie nocne, raport_RRRRQn.md)
evals/porownanie.md           # model vs baseline, wszystkie cztery modele
dev/                          # pipeline'y pypyr (m.in. baza.yaml, kolejka.yaml, mock_lejek.yaml)
├── mock_lejek/               # atrapa CRM dla webhooka kolejek (port 8102, stan w stan.json poza gitem)
├── metabase/                 # Metabase 0.63.17 + sterownik DuckDB 1.5.6.0 (port 3300; pypyr metabase): panel kampanii
│                             # dla marketingu; czyta Parquet z dane/ (DuckDB :memory: + widoki read_parquet), bo
│                             # sterownik (DuckDB 1.5) nie otwiera domilo.duckdb; plugins/, stan/, dane/, .env poza gitem
api/api/                      # kod Pythona (src_dir pypyr; testy w api/tests/)
├── main.py                   # FastAPI: /valuation, /leads/next, /leads/skips, /team/dashboard, /risk/{id_najmu}, Inngest (pypyr api)
├── inngest_app.py            # Inngest: wyceny-nocne (02:00; pypyr nocne), kolejka-doradcow (05:30; pypyr kolejka),
│                             # lista-retencyjna (pon. 07:00; pypyr lista_retencyjna)
├── adapters/                 # połączenia z systemami zewnętrznymi
│   ├── duckdb_baza.py        # polacz(), polaczenie() (blokada procesu) i zbuduj_baze() dla domilo.duckdb
│   ├── serwisownik.py        # wczytanie serwis_* (TIMESTAMP lokalny, koszt_netto '1 234,50' -> DECIMAL z kontrolą formatu)
│   ├── wyceny_historia.py    # tabela wyceny_historia w domilo.duckdb (przenoszona przy przebudowie bazy)
│   ├── kolejka_doradcow.py   # tabela kolejka_doradcow (dzień × zapytanie; przenoszona przy przebudowie bazy)
│   ├── kolejka_ranking.py    # tabela kolejka_ranking: pełny ranking dnia (zadanie / symulacja wstecz), dla panelu
│   ├── kolejka_pominiecia.py # tabela kolejka_pominiecia: pominięcia z CRM z powodem (POST /leads/skips)
│   ├── kolejka_historia.py   # tabela kolejka_historia: pozycje kolejek z wariantem eksperymentu i flagą losowa (5%)
│   ├── crm_lejek.py          # webhook kolejek do CRM, idempotentny po (id_leada, data_kolejki); atrapa: dev/mock_lejek/
│   └── lista_retencyjna.py   # tabela lista_retencyjna: umowy za 60–66 dni z ryzykiem, upliftem, akcją i grupą kampanii
├── contexts_boundaries/      # konteksty biznesowe (bounded contexts)
│   ├── valuation_bc/         # wycena lokali
│   ├── leasing_bc/           # zapytania i doradcy (najem); kolejka_dzienna.py: kroki zadania kolejka-doradcow;
│   │                         # kolejka_wstecz.py (ranking wstecz), panel.py (GET /team/dashboard), pominiecia.py,
│   │                         # eksperyment.py (switchback: plan w parach, wariant dnia, 5% pozycji losowych;
│   │                         # plan aktywny, gdy istnieje eksperyment_plan.yaml)
│   ├── retention_bc/         # retencja najemców; ryzyko_najmu.py: GET /risk (v2_przezycie_cox, mediana i RMST60)
│   │                         # oferta_najmu.py: część `oferta` w /risk (uplift v3, EV, akcja rabat / bez rabatu /
│   │                         # nie budzić + uzasadnienie z 3 cech; poza zakresem treningu v3 -> bez rabatu;
│   │                         # docs/ryzyko_oferta.md), przeglad_ofert.py: akcje dla aktywnych najmów i przykłady
│   │                         # polityka_rabatow.py: EV oferty (uplift v3 × R − D × P − k, zalozenia.yaml)
│   │                         # i polityki rabatów na rok (docs/polityka_rabatow.md)
│   │                         # lista_retencyjna.py: kroki zadania lista-retencyjna (current.yaml listy, grupa =
│   │                         # md5_number(id_umowy:kampania) % 100 < 20 -> kontrola; docs/lista_retencyjna.md)
│   │                         # panel_kampanii.py: tabele panelu Metabase (lista tygodnia, wynik kampanii Q3) jako
│   │                         # Parquet w dev/metabase/dane/; ostatni krok zadania lista-retencyjna (docs/panel_kampanii.md)
│   └── maintenance_bc/       # serwis i windy; alarmy_wind.py: reguła alarmu (pon. 06:00, 3 windy o najwyższym
│                             # ryzyku, przerwa 7 dni; zalozenia.yaml), punkt_pracy.py: ocena na teście v2b
│                             # (precyzja, czułość, wyprzedzenie tydzień po tygodniu; docs/b4_punkt_pracy.md);
│                             # wartosc_alarmow.py: PLN alarmów (trafny = skuteczność × koszt awarii − wizyta), p*
│                             # na ryzyku skalibrowanym izotonią na walidacji, krzywa wartości, koszt limitu
│       └── zalozenia.yaml    # (w każdym bc) stałe ekonomiczne — tylko od użytkownika, z opisem źródła
├── data_platform/            # wspólne definicje metryk (raport = eksperyment)
│   ├── dbt/                  # projekt dbt: modele schematu metryki w domilo.duckdb + testy (docs/kolejka_metryki.md)
│   ├── dbt_uruchom.py        # dbt build/test na domilo.duckdb (3. krok pypyr baza)
│   └── eksperyment_kolejki.py # moc/MDE i analiza eksperymentu kolejki (docs/kolejka_eksperyment.md)
└── ai/
    ├── features/             # budowa cech per model
    │   ├── wycena/
    │   ├── leady/
    │   ├── najemcy/
    │   └── windy/            # zgloszenia_wind.sql/.py: zgłoszenia wind z ustaloną windą (docs/b4_historia_awarii.md);
    │                         # awarie_odtworzone.sql/.py + serie_przestoju.sql: awarie z LLM i startem z telemetrii;
    │                         # dni_wind.sql/.py: target awaria_7d (docs/b4_target.md); cechy.py + sql/: cechy_windy
    │                         # (docs/b4_cechy.md); tsfresh_cechy.py: cechy_windy_tsfresh (docs/b4_tsfresh.md);
    │                         # katalog.yaml: opis wszystkich cech wind
    ├── valuation_model/      # wycena lokali z przedziałem
    ├── lead_model/           # kolejka zapytań dla doradców
    ├── churn_model/          # lista retencyjna najemców
    ├── failure_model/        # alerty o awariach wind
    │   ├── base.py           # (w każdym modelu) wspólny interfejs / definicja modelu; wind: ModelWind,
    │   │                     # KOLUMNY_ZAKAZANE (target, przyszła awaria, id_windy / id_budynku / dzien)
    │   ├── versions/         # kolejne wersje modelu (wind: v2_lgbm_losowy = przestroga, v2b_lgbm_czas_winda)
    │   ├── evals/            # ewaluacje wersji (failure_model/evals/historia_awarii.py: docs/b4_historia_awarii.md;
    │   │                     # ewaluacja_v2.py + porownanie.md: losowy podział vs czas + 28 wind poza treningiem)
    │   └── current.yaml      # wskazanie wersji używanej obecnie
    └── llm/
        ├── ekstrakcja_awarii.py # awaria windy z notatek (prompt awaria_v1, schemat schemas/awaria.py): wejście =
        │                     # zgłoszenie + wszystkie notatki, bez kategorii; wynik features/windy/awarie_llm/*.parquet
        ├── evals/            # m.in. ocena_awarii.py: ekstrakcja awarii wobec serwis_zloty_zbior i kategorii „awaria”
        │                     # (precision / recall / F1 z bootstrapem, podzespół; docs/b4_ekstrakcja.md)
        ├── prompts/          # prompty
        ├── schemas/          # schematy odpowiedzi
        └── cache/            # cache odpowiedzi LLM (poza gitem; klucz sha256(wersja promptu + wejście),
                              # klient adapters/llm_client.py)
ui/                           # Next.js (port 3100; pnpm --dir ui dev): panel rzeczoznawcy i /zespol (kierownik najmu)
```

Powiązania: `valuation_bc` ↔ `features/wycena` ↔ `valuation_model`; `leasing_bc` ↔ `features/leady` ↔ `lead_model`;
`retention_bc` ↔ `features/najemcy` ↔ `churn_model`; `maintenance_bc` ↔ `features/windy` ↔ `failure_model`.

## Baza domilo.duckdb

- Budowa: `pypyr baza`, czyli `api.adapters.duckdb_baza.zbuduj_baze()`. Trwa kilka sekund, a bazę zawsze buduje
  od zera z `data/`. W kodzie łącz się przez `polacz()`, nie przez `duckdb.connect()` bezpośrednio.
- **Tabele:** po jednej na każdy plik Parquet z `data/`, nazwa = nazwa pliku bez rozszerzenia (39 tabel, w tym
  `metadane` ze `zdjecia/metadane.parquet` oraz `telemetra_firmware` i `telemetra_urzadzenia_ciepla`). Zdjęć JPEG
  nie wczytujemy.
- **Tabele pochodne** (drugi krok `pypyr baza`, po przebudowie): `leady_cel` — target kolejki zapytań `umowa_45d`
  (`api/api/ai/features/leady/leady_cel.sql`, opis i liczby w `docs/kolejka_target.md`); `migawki_najemcy` —
  target listy retencyjnej `odejdzie`: umowa roczna B2C/B2B z `data_do` 2023-03-01 – 2026-09-30, migawka 60 dni
  przed `data_do` (`api/api/ai/features/najemcy/migawki.sql`, opis i liczby w `docs/target_najemcy.md`);
  `cechy_najemcy` — cechy na dzień migawki, tylko ze zdarzeń < `data_migawki`, jeden plik SQL na rodzinę
  (`api/api/ai/features/najemcy/sql/`: umowa, platnosci, relacja, budynek; `cechy.py`). `portal_logowania_mies`
  tylko z pełnych miesięcy przed miesiącem migawki, zamiast `czynsz_katalogowy` czynsz nowych umów podobnych lokali
  sprzed migawki; bez `rok_urodzenia` i `jezyk_kontaktu` (`features/najemcy/wykluczone.yaml`). Przecieki:
  `docs/przecieki_najemcy.md`.
  `czas_najmu` — analiza przeżycia: najem B2C/B2B z `pms_najmy` (wprowadzenie do 2026-09-30), `miesiace` (miesiące
  kalendarzowe z ułamkiem) do wyprowadzki albo do 2026-09-30, `zdarzenie` = 1 zakończony, 0 cenzura
  (`api/api/ai/features/najemcy/czas_najmu.sql`; Kaplan-Meier: `churn_model/evals/przezycie.py`, `docs/przezycie.md`).
  `zgloszenia_wind` — zgłoszenia Serwisownika dotyczące wind (`id_urzadzenia` = winda albo puste i typ `winda`),
  `id_windy` z `id_urzadzenia`, a gdy puste — jedyna winda budynku, inaczej `ustalenie_windy = 'nieustalona'`
  (`api/api/ai/features/windy/zgloszenia_wind.sql`). To nie jest target: kategoria `awaria` nie oznacza faktycznej
  awarii (złoty zbiór, notatki: `docs/b4_historia_awarii.md`).
  `awarie_odtworzone` — awaria windy = zgłoszenia z `czy_awaria` z LLM (`awaria_v1`, plik
  `features/windy/awarie_llm/awaria_v1_windy.parquet`; bez niego krok jest pomijany) tej samej windy, każde do 24 h
  po poprzednim; `podzespol` = najczęstszy różny od `brak`; `start_awarii` (lokalny Europe/Warsaw, `*_tz` = moment)
  = koniec ostatniego okna z kursami > 0 przed serią ≥ 3 okien bez kursów / `tryb = wylaczona`, zaczętą do 24 h
  przed pierwszym zgłoszeniem; `zrodlo_startu` = telemetria / brak_serii / brak_telemetrii; `czas_awarii` = start
  albo pierwsze zgłoszenie (`api/api/ai/features/windy/awarie_odtworzone.sql`, `docs/b4_historia_awarii.md` R10–R14).
  `dni_wind` — target modelu wind: winda × dzień 2023-03-01 – 2026-09-22 (w zakresie telemetrii windy), predykcja
  o 06:00 Europe/Warsaw, `awaria_7d` = start awarii z `awarie_odtworzone` w (06:00 t; 06:00 t+7]; bez dni, w których
  o 06:00 winda stoi z powodu awarii; `id_awarii`, `podzespol`, `liczba_awarii_7d`, `godziny_do_startu` to przyszłość,
  nie cechy (`api/api/ai/features/windy/dni_wind.sql`, `docs/b4_target.md`). Różnice godzin licz jako
  `epoch(a) − epoch(b)`: `TIMESTAMPTZ − TIMESTAMPTZ` w DuckDB 2.0 daje dni kalendarzowe (zmiana czasu = ±1 h błędu).
  `cechy_windy` — cechy z telemetrii dla wierszy `dni_wind`: tylko okna zakończone do 05:50 dnia oceny, bez
  `tryb = 'serwis'`; rodziny w `api/api/ai/features/windy/sql/` (drzwi, naped, wibracje, sterownik, uzycie; plik =
  sygnały z okien 10-min), statystyki generuje `features/windy/cechy.py`: średnia / max z 24 h, 3 i 7 dni (dokładne
  godziny), norma = mediana średnich dobowych z dni 15–44 (≥ 20 dni), stosunek do normy, trend 7 dni; wibracje przed
  montażem NULL + `ma_czujnik_wibracji`; `firmware_dni_od_zmiany`, `firmware_zmiana_glowna_44d`. **Pułapka:**
  Liftar LF-5 od 2025-11-17 raportuje błąd drzwi parą `E07|E17` (błędy ×2–3 bez wzrostu awarii;
  `docs/b4_cechy.md`).
  `cechy_windy_tsfresh` — tsfresh 0.21 z 168 godzinnych średnich przed 05:50 (czas zamykania drzwi, prąd, wibracje):
  RMS, kurtoza, energia, udziały pasm FFT (k 1–6 / 7 = doba / 8–14 / 15–84); puste godziny interpolowane, < 84 h
  z wartością -> NULL (`features/windy/tsfresh_cechy.py`, ok. 1,5 min; `extract_features` z `n_jobs=0` — szybsze
  niż procesy i działa ze skryptem ze stdin). Selekcja tylko na treningu 2023-03 – 2025-06 -> `tsfresh_wybrane.yaml`;
  opis wszystkich cech wind: `features/windy/katalog.yaml` (spójność: `tests/test_katalog_windy.py`).
  Porównanie (`failure_model/evals/tsfresh_porownanie.py`, `docs/b4_tsfresh.md`, MLflow `windy`): test od 2025-07-08
  (przerwa 7 dni po treningu = okno targetu).
  Model wind (`features/windy/zbior.py` składa dni_wind + cechy): **v2b_lgbm_czas_winda** (trening 2023-03 – 2025-06,
  walidacja 2025-07 – 12, test 2026-01-01 – 09-22, 28 wind poza treningiem) test PR-AUC 0,352, ROC AUC 0,773;
  `v2_lgbm_losowy` (losowe wiersze 80/20) 0,763 / 0,968 to **przeciek** (te same awarie w treningu i teście) —
  nigdy nie oceniaj modelu wind losowym podziałem wierszy (`failure_model/evals/porownanie.md`). `current.yaml` pusty.
- **Metryki dbt** (trzeci krok `pypyr baza`: `dbt build` z testami): schemat `metryki` — `umowa_45d`, `obsluzony`
  (oba z `leady_cel`), `wartosc_umowy` (podpisanie; ramowa = jeden wiersz), `przychod_na_godzine_doradcy`
  (tydzień / kwartał). Raporty i eksperymenty o wyniku zespołu czytają te tabele, nie liczą po swojemu
  (`api/api/data_platform/dbt/`, opis i liczby w `docs/kolejka_metryki.md`). Panel kierownika (`models/panel`,
  widoki poza `pierwszy_kontakt`): `ranking_dzien`, `pierwszy_kontakt`, `adopcja_dzien`, `kolejka_zapytania`,
  `pominiecia`, `panel_tydzien` (`docs/kolejka_panel.md`). Eksperyment kolejki (`docs/kolejka_eksperyment.md`):
  `przychod_z_kontaktow` (metryka główna: przychód z kontaktów tygodnia na godzinę, umowa do `vars.limit_wartosci_umowy`)
  i widok `eksperyment_tydzien` (wariant tygodnia z `kolejka_historia`).
- **Tabele trwałe aplikacji** (nie z `data/`; przebudowa je przenosi, a brakujące tworzy puste):
  `wyceny_historia`, `kolejka_doradcow`, `kolejka_ranking` (`zrodlo_kolejki`: `zadanie` albo `symulacja_wstecz`,
  `pypyr kolejka_wstecz`), `kolejka_pominiecia`, `kolejka_historia`, `lista_retencyjna` (klucz data_listy × id_umowy).
- **Kolejka a eksperyment:** 5% pozycji każdej kolejki doradcy (40 → 2) jest losowych, z ziarnem `dzień:miasto:wariant`
  (ten sam dzień = ta sama kolejka, webhook idempotentny); ranga zawsze według EV. Nie zmieniaj w trakcie
  eksperymentu modelu, założeń EV, 5%, limitu wartości umowy ani zmiennych korekty.
- **Widoki:** `telemetra_windy` i `telemetra_cieplo` czytają partycje `rok=/miesiac=` (kolumny `rok`, `miesiac`
  jako INTEGER). Mają ścieżki względne `data/...`: `polacz()` ustawia `file_search_path` na katalog repozytorium,
  a w CLI uruchamiaj zapytania z katalogu głównego.
- **Czas:** `polacz()` ustawia `TimeZone = 'Europe/Warsaw'`.
  - CRM (`crm_*.utworzono|data_statusu|data_czas`, `www_sesje.data_czas`): TIMESTAMPTZ, czyli dokładny moment.
  - Serwisownik (`serwis_*`, `api.adapters.serwisownik`): TIMESTAMP bez strefy = czas lokalny Warszawy, ta sama
    godzina co w źródle (Parquet: TIMESTAMP_NS, dokładność do minuty). Godziny
    2025-10-26 02:00–03:00 baza nie rozstrzyga.
  - Telemetra (`ts_utc`): TIMESTAMPTZ, tak jak w Parquecie.
  - Porównanie TIMESTAMP z TIMESTAMPTZ traktuje TIMESTAMP jako czas warszawski, co jest poprawne dla Serwisownika,
    PMS i portalu. Bez `polacz()` (np. w CLI) najpierw wykonaj `SET TimeZone = 'Europe/Warsaw'`.
- `serwis_czesci.koszt_netto` jest w bazie liczbą DECIMAL(12,2) (w źródle tekst `1 234,50`); inny format tekstu
  przerywa budowę bazy (`serwisownik.sprawdz_koszty`).
- Testy: `api/tests/test_duckdb_baza.py` sprawdza liczby wierszy względem Parquetów, typy czasu i widoki.

## Narzędzia

- Python 3.12 + Poetry (`poetry install`, `poetry run pypyr install`); zadania: `pypyr format|lint|test`.
- Biblioteki: duckdb 2.0, pandas 3.1, pyarrow 26, scikit-learn 1.9, lightgbm 4.7, pytz (`pyproject.toml`).
  lifelines 0.30.3 deklaruje `pandas < 3`, więc nie ma jej w `pyproject.toml` (są jej zależności): instaluje ją
  `pypyr install` przez `pip install --no-deps lifelines==0.30.3`.
  `pytz` jest potrzebny, bo bez niego DuckDB nie zwraca do Pythona kolumn TIMESTAMPTZ.
  tsfresh 0.21.2 (cechy przebiegów wind, `features/windy/tsfresh_cechy.py`).
  causalml 0.18 (S-learner `BaseSClassifier` w ewaluacji uplift); jej `get_qini` nie obsługuje remisów, więc krzywe
  Qini liczy `churn_model/evals/metryki_uplift.py`.
  dbt-core 1.12 + dbt-duckdb 1.11 (grupa dev); profil w `api/api/data_platform/dbt/profiles.yml` ustawia
  `TimeZone = 'Europe/Warsaw'`, ścieżkę bazy podaje `dbt_uruchom.py`. dbt otwiera bazę do zapisu, więc nie uda się,
  gdy inny proces ma ją w tej chwili otwartą (blokada pliku DuckDB).
- Dane czytamy przez `polacz()` (baza) albo DuckDB/pandas wprost z Parquetu.
  **DuckDB 2.0:** relacja z `duckdb.sql(...)` nie ma `fetchone()` — używaj `.fetchall()` albo
  `con.execute(...).fetchone()`. CLI `duckdb` 1.5 na hoście **nie otworzy** `domilo.duckdb` (format pliku 2.0),
  ale wciąż czyta pliki Parquet.
- MLflow 3.18: eksperymenty w `mlflow.db` + `mlartifacts/` (katalog główny, w .gitignore), połączenie przez
  `api.adapters.mlflow_rejestr.ustaw_eksperyment()`; wycena loguje się do eksperymentu `wycena`
  (`valuation_model/evals/ewaluacja.py`), kolejka zapytań do eksperymentu `leady` (`lead_model/evals/ewaluacja.py`: v0/v1 w oknie migracji; `ewaluacja_v2.py`: v2 na teście i w oknie; `ewaluacja_v2b.py`: v2b z wagami IPW; `ewaluacja_v3.py`: `v3_ev_kalibracja`, obecna w `current.yaml`), model wind do eksperymentu `windy` (`failure_model/evals/tsfresh_porownanie.py`, `ewaluacja_v2.py`), lista retencyjna do eksperymentu `najemcy` (`churn_model/evals/ewaluacja_v1.py`: `v1_ryzyko` wobec `score_polityki` i reguły „B2B najpierw”; kontrakt w `churn_model/base.py`; `current.yaml` od 2026-11-16: `ryzyko` = v2_przezycie_cox, `uplift` = v3_uplift_tlearner, wczytuje `base.wczytaj_obecny()`, wpis do potwierdzenia; `ewaluacja_v2.py`: `v2_przezycie_cox`, model Coxa na okresach umów, cechy v1 na `data_od` okresu z `features/najemcy/cechy_okresow.py`, C-index wobec reguły „B2B najpierw”, `docs/przezycie_cox.md`; `evals/uplift.py`: `v3_uplift_tlearner` (T-learner, 2 × LightGBM) i S-learner z causalml na losowym `test_2025` 70 / 30 według id_umowy, wobec reguły „górne 35% `score_polityki`”, miary Qini / AUUC w `evals/metryki_uplift.py`, raport `churn_model/evals/uplift.md`). Cechy chronione wykluczone z modelu kolejki i z promptów (`jezyk`, `imie`, `rok_urodzenia`): `api/api/ai/features/leady/wykluczone.yaml`, pilnuje test `api/tests/test_cechy_wykluczone.py`. Podgląd: `poetry run mlflow ui --backend-store-uri sqlite:///mlflow.db`.
- Skille procesu pracy: `.claude/skills/` (m.in. `use-sw-development-workflow`, `sw-test-driven-development`).
