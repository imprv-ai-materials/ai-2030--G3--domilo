# Kolejka zapytań: jedno zdanie uzasadnienia z top 3 cech SHAP (2026-11-15)

## Wnioski

1. Przy każdym zapytaniu w kolejce doradca może zobaczyć jedno krótkie zdanie, które mówi, co najbardziej podnosi
   wynik modelu, np. „Wprowadzenie za 23 dni, budżet 4 550 zł (165% mediany w mieście) i konkretne pytania
   w wiadomości”. Zdanie ułożone przez LLM korzysta wyłącznie z trzech faktów, a każde jest sprawdzane automatycznie.
2. Na 495 zapytaniach z LLM wszystkie zdania mają ≤ 140 znaków (najdłuższe 139, mediana 92). 494 przeszły kontrolę
   „tylko fakty z top 3”. Jedno odrzuciła ona niesłusznie (słowo „oferty” w zwrocie „roczna oferta B2C”) i zastąpiło
   je zdanie z szablonu. W żadnym z dwóch przebiegów kontrola nie znalazła faktu spoza top 3, który LLM naprawdę
   by dopisał. Ręczny przegląd 25 zdań też nie znalazł takiego faktu.
3. Zdanie tłumaczy szansę na umowę (p), a nie całą pozycję w kolejce według pieniędzy. Pierwsze zapytanie w kolejce
   D03 jest pierwsze głównie dlatego, że dotyczy 4 lokali B2B w Warszawie. Liczby lokali nie ma jednak w top 3 SHAP,
   więc zdanie jej nie wymienia.
4. Model najczęściej wskazuje termin wprowadzenia, budżet względem mediany, linię i źródło zapytania. Częste są też
   fakty „negatywne”, np. „zapytanie zgodne z ofertą” (brak sygnału niedopasowania): to prawda, ale mówi doradcy
   niewiele.

## Jak to działa

| Krok | Gdzie | Co robi |
|---|---|---|
| SHAP | `ai/lead_model/uzasadnienie.top_wklady` | Wkłady cech w log-szansę z zapisanego `v2b_lgbm_ipw` (`explain`, LightGBM `pred_contrib`). Bierze najwyżej 3 cechy o wkładzie > 0, malejąco. |
| Fakty | `ai/features/leady/fakty.py` | Jedna cecha → jeden fakt, ≤ 40 znaków, np. „relokacja: Altakom”, „2 lokale: Altakom”, „budżet 3 500 zł, 150% mediany w mieście”. Kontekst to tylko pola formularza: `budzet_max` i nazwa firmy B2B. Fakty nie zawierają treści wiadomości ani imienia. Każdy fakt ma kotwice, czyli słowa, po których widać go w zdaniu. |
| Zdanie | `ai/llm/prompts/uzasadnienie_v1.yaml`, `ai/llm/schemas/uzasadnienie.py` | LLM (`gpt-6-luna`, reasoning `none`, temperatura 0, cache w `ai/llm/cache`) dostaje tylko listę faktów top 3. Schemat ma `maxLength` 140 i `extra="forbid"`. |
| Kontrola | `uzasadnienie.sprawdz_zdanie` | Sprawdza, czy zdanie ma ≤ 140 znaków, czy wszystkie liczby pochodzą z faktów top 3 i czy żadna kotwica faktu spoza top 3 nie występuje na początku słowa. Gdy zdanie nie przejdzie kontroli albo API zwróci błąd, wstawiane jest zdanie z szablonu „Za zapytaniem: fakt1; fakt2; fakt3.”. |

- **Zakres:** SHAP, top 3 i fakty liczyłem dla każdego zapytania zwykłego testu (15 217 zapytań, 2026-03 – 2026-06).
  Zdania z LLM powstały dla 495 zapytań: wszystkich 196 z 2026-06-15 i losowych 300 z testu (ziarno 42; jedno jest
  w obu grupach).
- **Model:** zapisany `v2b_lgbm_ipw`, uczony na danych do 2026-02, więc test jest dla niego danymi spoza uczenia.
  Kalibracja izotoniczna (kalibracja.md) nie zmienia kolejności, więc wyjaśnia tę samą kolejność. EV w kolejce
  liczę z p tego modelu (`leasing_bc/wartosc.py`). Na obsłużonych zapytaniach testu ten model był już prawie
  skalibrowany (ECE 0,70 pp, kalibracja.md T2).
- **Kolejka D03 z 2026-06-15:** zapytania utworzone tego dnia (czas warszawski) z `crm_leady.id_doradcy = 'D03'`
  (23 zapytania), według EV malejąco. `id_doradcy` to stan na dzień eksportu (przypisany doradca). Służy tylko do
  wyboru przykładu i nie jest cechą modelu.
- **Ograniczenie kontroli:** kotwice wyłapią nazwę, liczbę lub słowo kluczowe innego faktu, ale nie omówienie
  (np. „stolica” zamiast „Warszawa”). Dlatego dodatkowo przejrzałem ręcznie 25 losowych zdań i wszystkie wiernie
  oddają fakty.

## Wyniki

### T1. 20 pierwszych zapytań w kolejce D03, 2026-06-15 (z 23; według EV)

W nawiasie przy fakcie: wkład SHAP w log-szansę. Kolumna „umowa” pokazuje faktyczny wynik po 45 dniach (`umowa_45d`)
i nie była znana w chwili ułożenia kolejki.

| # | Zapytanie | Godz. | Linia | Źródło | p | EV | Fakty top 3 (wkład) | Zdanie dla doradcy | Umowa |
|---:|---|---|---|---|---:|---:|---|---|---:|
| 1 | L145834 | 10:34 | B2B | relokacja_b2b | 8,9% | 18 254 zł | źródło: program relokacji B2B (+0,72)<br>użyty kalkulator na stronie (+0,27)<br>konkretne pytania w wiadomości (+0,17) | Zapytanie pochodzi z programu relokacji B2B, użyto kalkulatora na stronie i zawiera konkretne pytania w wiadomości. | 0 |
| 2 | L145832 | 10:31 | B2C | lokum24 | 12,9% | 6 189 zł | 4 wizyty na stronie (+0,39)<br>najem roczny B2C (+0,32)<br>wprowadzenie za 39 dni (+0,31) | Zapytanie ma 4 wizyty na stronie, dotyczy najmu rocznego B2C, a wprowadzenie jest za 39 dni. | 1 |
| 3 | L145882 | 15:16 | B2B | relokacja_b2b | 11,0% | 5 624 zł | źródło: program relokacji B2B (+0,85)<br>najem firmowy B2B (+0,18)<br>1 lokal: Orbinet (+0,14) | Zapytanie pochodzi z programu relokacji B2B, dotyczy najmu firmowego B2B i obejmuje 1 lokal: Orbinet. | 0 |
| 4 | L145880 | 14:58 | MID | www | 21,4% | 3 613 zł | budżet 4 200 zł, 152% mediany w mieście (+0,54)<br>źródło: strona Domilo (+0,50)<br>4 wizyty na stronie (+0,28) | Budżet wynosi 4 200 zł, czyli 152% mediany w mieście; źródłem jest strona Domilo, a zapytanie miało 4 wizyty na stronie. | 0 |
| 5 | L145873 | 13:40 | B2C | lokum24 | 7,3% | 3 500 zł | wprowadzenie za 29 dni (+0,45)<br>konkretne pytania w wiadomości (+0,22)<br>wiadomość 179 znaków (+0,09) | Wprowadzenie za 29 dni, konkretne pytania w wiadomości i wiadomość o długości 179 znaków. | 0 |
| 6 | L145868 | 13:07 | MID | lokum24 | 15,6% | 2 632 zł | wprowadzenie za 23 dni (+0,61)<br>budżet 4 550 zł, 165% mediany w mieście (+0,57)<br>konkretne pytania w wiadomości (+0,21) | Wprowadzenie za 23 dni, budżet 4 550 zł (165% mediany w mieście) i konkretne pytania w wiadomości. | 0 |
| 7 | L145931 | 20:33 | B2C | lokum24 | 4,9% | 2 359 zł | wprowadzenie za 15 dni (+0,42)<br>budżet 4 550 zł, 165% mediany w mieście (+0,34)<br>konkretne pytania w wiadomości (+0,18) | Wprowadzenie za 15 dni, budżet 4 550 zł, 165% mediany w mieście i konkretne pytania w wiadomości. | 0 |
| 8 | L145798 | 05:40 | B2C | lokum24 | 4,1% | 1 985 zł | budżet 3 100 zł, 112% mediany w mieście (+0,36)<br>wiadomość 23 znaki (+0,25)<br>najem roczny B2C (+0,22) | Budżet wynosi 3 100 zł, czyli 112% mediany w mieście; wiadomość ma 23 znaki, a najem jest roczny B2C. | 0 |
| 9 | L145790 | 03:22 | B2C | lokum24 | 3,7% | 1 763 zł | wprowadzenie za 29 dni (+0,44)<br>obejrzany spacer 3D (+0,41)<br>4 wizyty na stronie (+0,27) | Wprowadzenie za 29 dni, obejrzany spacer 3D i 4 wizyty na stronie. | 0 |
| 10 | L145956 | 21:59 | B2C | lokum24 | 3,2% | 1 558 zł | wprowadzenie za 30 dni (+0,39)<br>najem roczny B2C (+0,16)<br>pilny termin (+0,04) | Wprowadzenie za 30 dni, najem roczny B2C i pilny termin. | 0 |
| 11 | L145836 | 10:34 | MID | www | 7,0% | 1 182 zł | obejrzany spacer 3D (+0,43)<br>źródło: strona Domilo (+0,41)<br>wprowadzenie za 54 dni (+0,10) | Obejrzany spacer 3D, źródło: strona Domilo, wprowadzenie za 54 dni. | 0 |
| 12 | L145838 | 10:38 | MID | domteraz | 6,8% | 1 147 zł | budżet 5 150 zł, 187% mediany w mieście (+0,56)<br>obejrzany spacer 3D (+0,44)<br>konkretne pytania w wiadomości (+0,09) | Budżet wynosi 5 150 zł, czyli 187% mediany w mieście; obejrzano spacer 3D i zadano konkretne pytania w wiadomości. | 0 |
| 13 | L145810 | 08:04 | B2C | lokum24 | 2,3% | 1 094 zł | użyty kalkulator na stronie (+0,23)<br>najem roczny B2C (+0,16)<br>zapytanie zgodne z ofertą (+0,07) | Użyto kalkulatora na stronie, zapytanie dotyczy najmu rocznego B2C i jest zgodne z ofertą. | 0 |
| 14 | L145784 | 01:12 | MID | domteraz | 5,4% | 915 zł | wprowadzenie za 15 dni (+0,57)<br>użyty kalkulator na stronie (+0,16)<br>budżet 3 250 zł, 118% mediany w mieście (+0,11) | Wprowadzenie za 15 dni, użyty kalkulator na stronie, budżet 3 250 zł, 118% mediany w mieście. | 0 |
| 15 | L145806 | 07:36 | MID | social | 4,7% | 784 zł | budżet 4 100 zł, 149% mediany w mieście (+0,45)<br>obejrzany spacer 3D (+0,28)<br>użyty kalkulator na stronie (+0,16) | Budżet wynosi 4 100 zł, czyli 149% mediany w mieście; obejrzano spacer 3D i użyto kalkulatora na stronie. | 0 |
| 16 | L145789 | 03:06 | B2C | www | 1,4% | 690 zł | źródło: strona Domilo (+0,34)<br>konkretne pytania w wiadomości (+0,18)<br>najem roczny B2C (+0,08) | Zapytanie pochodzi ze strony Domilo, zawiera konkretne pytania w wiadomości i dotyczy najmu rocznego B2C. | 0 |
| 17 | L145930 | 20:31 | MID | lokum24 | 4,0% | 681 zł | wprowadzenie za 31 dni (+0,29)<br>budżet 3 500 zł, 127% mediany w mieście (+0,17)<br>miasto: Warszawa (+0,06) | Wprowadzenie za 31 dni, budżet 3 500 zł, 127% mediany w mieście, Warszawa. | 0 |
| 18 | L145851 | 11:54 | MID | lokum24 | 3,6% | 602 zł | budżet 4 400 zł, 159% mediany w mieście (+0,50)<br>konkretne pytania w wiadomości (+0,30)<br>wiadomość 421 znaków (+0,19) | Budżet 4 400 zł, 159% mediany w mieście, konkretne pytania w wiadomości i wiadomość o długości 421 znaków. | 0 |
| 19 | L145949 | 21:49 | MID | lokum24 | 3,4% | 568 zł | konkretne pytania w wiadomości (+0,34)<br>wiadomość 334 znaki (+0,15)<br>budżet 3 200 zł, 116% mediany w mieście (+0,14) | Wiadomość zawiera konkretne pytania, ma 334 znaki, a budżet wynosi 3 200 zł, czyli 116% mediany w mieście. | 0 |
| 20 | L145833 | 10:33 | MID | domteraz | 2,8% | 479 zł | wprowadzenie za 41 dni (+0,18)<br>budżet 3 200 zł, 116% mediany w mieście (+0,06)<br>zapytanie zgodne z ofertą (+0,06) | Wprowadzenie za 41 dni, budżet 3 200 zł (116% mediany w mieście) i zapytanie zgodne z ofertą. | 0 |

Zapytanie 1: EV = 0,0889 × 3 110 zł (mediana B2B, Warszawa) × 16,5 mies. × 4 lokale. Liczba lokali (4) nie ma
dodatniego wkładu w top 3 SHAP, więc nie ma jej w zdaniu, choć to ona stawia zapytanie na początku kolejki.

### T2. Zdania z LLM (495 zapytań)

| Miara | Wartość |
|---|---|
| zdania ≤ 140 znaków | 495 z 495 (min 48, mediana 92, maks. 139) |
| zdanie z LLM przyjęte przez kontrolę | 494 |
| zdanie z szablonu | 1: LLM napisał „rocznej oferty B2C”, kotwica „ofert” należy do faktu spoza top 3 (fałszywy alarm) |
| różnych zdań | 470 (identyczne fakty → to samo zdanie z cache) |
| wywołania API | 469 (26 z 495 to identyczne wejście, odczyt z cache) |
| tokeny na 1 000 wywołań | 444 861 wejścia (0 z cache promptu OpenAI), 47 789 wyjścia; kwota: brak cennika w `leasing_bc/zalozenia.yaml` |
| pierwszy przebieg (przed poprawkami) | 321 z LLM, 174 z szablonu, wszystkie przez fałszywe alarmy kontroli: 152 to kotwica „pytani” w słowie „zapytanie”, a 22 to ogólne słowo „osoba” (np. „osoba użyła kalkulatora”), w 20 z nich także „pytani”. Poprawki: kotwica tylko na początku słowa, liczbę osób sprawdzają formy „osób”/„osoby” i kontrola liczb, prompt każe użyć wszystkich faktów (LLM gubił fakty 2–3). Wpisy cache z pierwszego przebiegu usunięte. |

### T3. Które cechy trafiają do top 3 (15 217 zapytań testu)

Liczba dodatnich wkładów: 3 u 15 180 zapytań, 2 u 32, 1 u 4, 0 u 1 (to zapytanie dostaje zdanie „Żadna cecha tego
zapytania nie podnosi jego wyniku.”).

| Cecha | W top 3 | Na 1. miejscu |
|---|---:|---:|
| termin_dni | 7 177 | 4 328 |
| budzet_do_mediany | 6 688 | 2 660 |
| linia | 5 840 | 1 219 |
| zrodlo | 5 140 | 4 157 |
| syg_konkretne_pytania | 3 606 | 718 |
| syg_niedopasowanie_oferty („zgodne z ofertą” lub „spoza oferty”) | 3 206 | 136 |
| www_spacer_3d | 2 675 | 854 |
| www_liczba_sesji | 2 652 | 319 |
| www_kalkulator | 2 132 | 468 |
| dlugosc_wiadomosci | 2 125 | 232 |
| miasto | 1 586 | 85 |
| liczba_osob | 856 | 22 |
| liczba_lokali | 579 | 7 |
| syg_pilny_termin | 519 | 1 |
| umowa_ramowa | 386 | 3 |
| zwierze | 239 | 1 |
| syg_budzet_niski | 129 | 0 |
| syg_relokacja | 38 | 5 |
| syg_brak_informacji | 35 | 1 |

## SQL i kod

```bash
pypyr baza
set -a && . ./.env && set +a
cd api && poetry run python -m api.ai.lead_model.evals.uzasadnienia          # [--bez-llm]: tylko SHAP i fakty
poetry run pytest api/tests/test_uzasadnienie.py
```

Wyniki: `api/api/ai/lead_model/evals/wyniki/uzasadnienia.parquet` (każde zapytanie testu: p, EV, top 3 z wkładami,
fakty top 3 i pozostałe z kotwicami, zdanie, źródło zdania, problemy) i `uzasadnienia.json` (T2, T3, 20 przykładów
z T1). Test `test_kazde_wygenerowane_zdanie_ma_najwyzej_140_znakow_i_tylko_fakty_top3` czyta ten plik i sprawdza
każde zdanie: długość ≤ 140 i `sprawdz_zdanie(...) == []`.

**Kontekst faktów** (`SQL_KONTEKST` w `features/leady/fakty.py`; pola formularza znane w chwili zapytania):

```sql
SELECT l.id_leada, l.budzet_max, f.nazwa AS firma
FROM crm_leady AS l
LEFT JOIN crm_firmy_b2b AS f ON f.id_firmy = l.id_firmy_b2b;
```

**Wybór kolejki D03** (w `uzasadnienia.py`, na zapytaniach testu z `podzial_v2`):

```sql
SELECT id_leada, id_doradcy FROM crm_leady;   -- potem: dzień utworzenia (Europe/Warsaw) = 2026-06-15 i id_doradcy = 'D03'
```

**Top 3 i kontrola zdania** (fragmenty `ai/lead_model/uzasadnienie.py`):

```python
def top_wklady(wklady, n=3):
    w = wklady.drop(labels=["wklad_staly"], errors="ignore")
    w = w[w > 0].sort_values(ascending=False, kind="mergesort").head(n)
    return [(k.removeprefix("wklad_"), float(v)) for k, v in w.items()]

def sprawdz_zdanie(zdanie, top, pozostale):
    problemy = []
    if len(zdanie) > 140: problemy.append("długość")
    tekst_top = " ".join(f.tekst for f in top)
    if _liczby(zdanie) - _liczby(tekst_top): problemy.append("liczby spoza top 3")   # B2B/B2C/3D/lokum24 to nie liczby; 3 500 = 3500
    for f in pozostale:   # kotwica faktu spoza top 3 na początku słowa, której nie ma w tekście top 3
        if any(k not in tekst_top.lower() and re.search(r"(?<!\w)" + re.escape(k), zdanie.lower()) for k in f.kotwice):
            problemy.append(f"fakt spoza top 3: {f.cecha}")
    return problemy
```

Prompt: [`api/api/ai/llm/prompts/uzasadnienie_v1.yaml`](../api/api/ai/llm/prompts/uzasadnienie_v1.yaml). Wejście
LLM to tylko lista „1. fakt / 2. fakt / 3. fakt” (`wejscie_llm`), która jest też kluczem cache.
