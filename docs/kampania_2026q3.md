# Kampania retencyjna Q3 2026: czy oferta z rabatem zarabia

**Dla Moniki: nie wiemy, że kampania zarabia. Przy założeniach R, D i k z `zalozenia.yaml` najpewniej straciła
około 207 tys. zł (95% przedział: od 405 tys. zł straty do mniej więcej zera), bo rabat dostają głównie najemcy,
którzy przedłużyliby umowę i bez niego.**

Stan: 2026-11-16. Wszystkie liczby liczy
[`retention_bc/kampania_2026q3.py`](../api/api/contexts_boundaries/retention_bc/kampania_2026q3.py) na `domilo.duckdb`
i zapisuje w `api/api/contexts_boundaries/retention_bc/wyniki/kampania_2026q3.json`. Testy:
`api/tests/test_kampania_2026q3.py`.

## Wnioski

1. **Z ofertą przedłużyło 49,3% najemców, bez oferty 39,6%.** To +9,7 p.p., czyli około 43 dodatkowe przedłużenia
   na 444 wysłane oferty. Grupa bez oferty jest jednak mała (111 umów), więc przedział jest szeroki: od 0 do
   +20 p.p. Na samej kampanii nie da się nawet rozstrzygnąć, czy oferta w ogóle zatrzymuje najemców.
2. **Pieniądze liczą się prościej niż efekt.** 43 dodatkowe przedłużenia są warte 212 tys. zł (43 × 4 920 zł),
   a kampania kosztuje 419 tys. zł: 392 tys. zł rabatów dla 218 przedłużających (1 800 zł rocznie każdy) i 27 tys. zł
   kontaktu. Wynik netto to −207 tys. zł, a ROI −50%. Jedno dodatkowe przedłużenie kosztuje 9 745 zł, a odejście
   najemcy 4 920 zł.
3. **Żeby kampania wyszła na zero, oferta musiałaby podnosić przedłużenia o 19,2 p.p.** To górna granica tego, co
   pokazują dane. W 976 na 1 000 losowań bootstrap wynik jest ujemny. Kierunek nie zmienia się przy losowaniu po
   najemcach ani przy rabacie liczonym jak w FK (1 950 zł). Zmienia się tylko górna granica: gdyby kontakt nic nie
   kosztował (k = 0 zamiast szacunku 60 zł), sięga +27 tys. zł.
4. **Wynik zgadza się z losowym testem 2025.** Tam w tej samej grupie (`kwalifikuje`) oferta dała +16,1 p.p.,
   a przy tym efekcie kampania Q3 też by straciła (−66 tys. zł). Zarobiłaby dopiero przy górnej granicy efektu
   z 2025 roku (+20,8 p.p.). To samo mówi [polityka_rabatow.md](polityka_rabatow.md): rabat 1 800 zł rocznie się nie
   opłaca, także w górnych 35% ryzyka.
5. **Losowanie grupy kontrolnej wygląda na udane.** Kontrola to dokładnie 20,0% kwalifikujących się umów, a grupy nie
   różnią się score, udziałem B2B, wcześniejszymi wypowiedzeniami ani miesiącem końca umowy. Klienci firmowi (B2B)
   prawie nie przedłużają, z ofertą czy bez (3,4% i 4,2%), więc dla nich oferta jest czystym kosztem.

## Wyniki

### Założenia (podane przez użytkownika, `retention_bc/zalozenia.yaml`)

| Symbol | Wartość | Co oznacza | Źródło | Odpowiedzialny |
|---|---:|---|---|---|
| R | 4 920 zł | koszt odejścia najemcy (wartość jednego dodatkowego przedłużenia) | FinKs i PMS 2025 | Monika Lis |
| D | 1 800 zł | roczny rabat dla każdego, kto przedłuży z ofertą | FinKs | Joanna Michalak |
| k | 60 zł | koszt kontaktu (jedna wysłana oferta) | szacunek | Joanna Michalak |

**Wynik netto = dodatkowe przedłużenia × R − rabaty × D − oferty × k**, gdzie dodatkowe przedłużenia =
(% przedłużeń z ofertą − % w kontroli) × liczba ofert. ROI = wynik netto / (rabaty × D + oferty × k).

### Populacja i definicje

- **Umowy:** `retencja_decyzje.okres = 'kampania_2026q3'`, końce umów od 2026-07-01 do 2026-09-30. Ofertę mogło
  dostać 555 umów z flagą `kwalifikuje` (stara reguła: górne 35% `score_polityki`, score 0,5078–0,9754). 444 dostały
  ofertę (`grupa = 'oferta'`), a 111 losowo nie (`grupa = 'kontrola'`). 1 031 umów bez flagi (`brak_oferty`,
  score do 0,5228) jest poza porównaniem. Każda z 555 umów ma wiersz w `migawki_najemcy`, więc złączenie nie gubi
  żadnej.
- **Wynik:** przedłużenie = 1 − `migawki_najemcy.odejdzie` (kolejny okres umowy albo przeprowadzka do innego lokalu
  Domilo). Dla umów kończących się do 2026-09-30 wynik jest znany w dniu eksportu
  ([target_najemcy.md](target_najemcy.md)). W kampanii nie było żadnej przeprowadzki.
- **Oferta:** zawsze 45 dni przed końcem umowy (444 z 444). Otworzyło ją 265 najemców (59,7%). Liczymy efekt
  *wysłania* oferty, nie jej przyjęcia.
- **Rabaty:** przedłużenie z ofertą, którego następna umowa ma pozycje w `fk_rabaty`. Liczymy je po D = 1 800 zł,
  czyli za cały rok nowej umowy. FK księguje rabat co miesiąc i do dnia eksportu (`fk_rabaty` kończy się na 2026-09)
  zaksięgowało dopiero część: 453 pozycje × 150 zł = 67 950 zł. Reszta przyjdzie w kolejnych miesiącach.
- **Przedziały 95%:** bootstrap percentylowy, 1 000 losowań (ziarno 42). Umowy losujemy ze zwracaniem osobno
  w grupie z ofertą i w kontroli, bo przydział był losowy na poziomie umowy. Sprawdzenie: losowanie najemców
  z wszystkimi ich umowami (546 najemców, 2 z nich mają umowy w obu grupach). Dla efektu podajemy też przedział Walda.

### 1. Przedłużenia

| Grupa | Umowy | Przedłużenia | % przedłużeń | 95% bootstrap |
|---|---:|---:|---:|---:|
| oferta | 444 | 219 | 49,3 | 44,6 – 53,8 |
| kontrola | 111 | 44 | 39,6 | 30,6 – 48,6 |
| **Różnica (efekt oferty)** | | | **+9,7 p.p.** | **0,0 – +20,1** (Wald: −0,5 – +19,9) |

### 2. Wynik w złotówkach

| Pozycja | Wartość | 95% bootstrap |
|---|---:|---:|
| Dodatkowe przedłużenia (9,7 p.p. × 444 oferty) | 43,0 | 0,0 – 89,0 |
| Korzyść: dodatkowe przedłużenia × R | 211 560 zł | |
| Rabaty: 218 przedłużeń z rabatem × D | 392 400 zł | |
| Koszt kontaktu: 444 oferty × k | 26 640 zł | |
| Koszt razem (rabaty + kontakt) | 419 040 zł | 381 240 – 455 040 zł |
| **Wynik netto** | **−207 480 zł** | **−405 402 – −117 zł** |
| **ROI** (wynik netto / koszt) | **−49,5%** | **−100,0% – −0,03%** |
| Losowania z dodatnim wynikiem netto | 24 z 1 000 (2,4%) | |
| Efekt potrzebny, by wyjść na zero (koszt / R / oferty) | +19,2 p.p. | |
| Koszt jednego dodatkowego przedłużenia (koszt / 43,0) | 9 745 zł | |

Rabat ma 218 z 219 przedłużeń z ofertą. W grupie kontrolnej rabatu nie dostał nikt.

### 3. Wrażliwość

| Wariant | Efekt (p.p.) | Wynik netto | 95% przedział | ROI | 95% przedział | Losowania z wynikiem > 0 |
|---|---:|---:|---:|---:|---:|---:|
| Główny (bootstrap w grupach) | +9,7 | −207 480 zł | −405 402 – −117 zł | −49,5% | −100,0% – −0,03% | 2,4% |
| Bootstrap po najemcach | +9,7 | −207 480 zł | −428 281 – −7 320 zł | −49,5% | −105,5% – −1,7% | 2,1% |
| D = 1 950 zł (rabat jak w FK: 13 × 150 zł) | +9,7 | −240 180 zł | −434 618 – −33 538 zł | −53,2% | −100,0% – −7,3% | 0,9% |
| k = 0 zł (kontakt bez kosztu) | +9,7 | −180 840 zł | −378 762 – +26 523 zł | −46,1% | −100,0% – +6,6% | 4,8% |

Przy k = 0 efekt potrzebny, by wyjść na zero, wynosi +18,0 p.p.

**Efekt z losowego testu 2025** (grupa `kwalifikuje`, [test_rabatu_2025.md](test_rabatu_2025.md)) zamiast efektu
z kampanii, przy tych samych 444 ofertach i 218 rabatach:

| Efekt z testu 2025 | Dodatkowe przedłużenia | Wynik netto | ROI |
|---|---:|---:|---:|
| dolna granica: +11,5 p.p. | 50,9 | −168 780 zł | −40,3% |
| punktowo: +16,1 p.p. | 71,7 | −66 487 zł | −15,9% |
| górna granica: +20,8 p.p. | 92,4 | +35 806 zł | +8,5% |

### 4. Czy grupa kontrolna jest porównywalna

| Cecha (znana przed ofertą) | Oferta | Kontrola | p |
|---|---:|---:|---:|
| Udział kontroli (test dwumianowy wobec 20%) | | 20,0% (111 z 555) | 1,000 |
| Średni `score_polityki` (test Welcha) | 0,679 | 0,665 | 0,210 |
| Udział B2B (test Fishera) | 19,8% | 21,6% | 0,692 |
| Wypowiedzenie przed migawką (test Fishera) | 17,6% | 15,3% | 0,673 |
| Miesiąc końca 2026-07 / 08 / 09 (χ²) | 150 / 142 / 152 | 37 / 36 / 38 | 0,995 |

### 5. Segmenty (tylko opis: w kontroli po 24–87 umów)

| Segment | Umowy: oferta | Umowy: kontrola | % przedłużeń: oferta | % przedłużeń: kontrola | Efekt (p.p.) | 95% Wald | Wynik netto |
|---|---:|---:|---:|---:|---:|---:|---:|
| koniec 2026-07 | 150 | 37 | 56,0 | 37,8 | +18,2 | +0,6 – +35,7 | −26 163 zł |
| koniec 2026-08 | 142 | 36 | 48,6 | 44,4 | +4,1 | −14,0 – +22,3 | −103 747 zł |
| koniec 2026-09 | 152 | 38 | 43,4 | 36,8 | +6,6 | −10,7 – +23,8 | −76 920 zł |
| B2C | 356 | 87 | 60,7 | 49,4 | +11,2 | −0,4 – +22,9 | −211 334 zł |
| B2B | 88 | 24 | 3,4 | 4,2 | −0,8 | −9,6 – +8,1 | −13 960 zł |

Wynik netto segmentu liczymy tym samym wzorem na umowach segmentu. Wyniki B2C i B2B nie sumują się do wyniku
całości, bo efekt w całości nie jest średnią efektów segmentów ważoną liczbą ofert (różne udziały kontroli).

## SQL i kod

Uruchomienie (wymaga `domilo.duckdb` z tabelą `migawki_najemcy`, czyli `pypyr baza`):

```bash
cd api && poetry run python -m api.contexts_boundaries.retention_bc.kampania_2026q3
cd api && poetry run pytest -q tests/test_kampania_2026q3.py
```

Zbiór analizy (`SQL_KAMPANII` w skrypcie):

```sql
SELECT r.id_umowy, r.data_konca::DATE AS data_konca, date_trunc('month', r.data_konca)::DATE AS miesiac_konca,
       r.score_polityki, r.kwalifikuje, r.grupa, r.grupa = 'oferta' AS oferta, r.data_oferty::DATE AS data_oferty,
       r.czy_otwarta, m.id_najemcy, m.linia, m.wypowiedzenie_przed_migawka, m.przeprowadzka,
       1 - m.odejdzie AS przedluzona,
       f.id_umowy IS NOT NULL AS rabat,
       coalesce(f.pozycje, 0) AS rabat_pozycje_do_eksportu,
       coalesce(f.suma, 0) AS rabat_zaksiegowany_pln
FROM retencja_decyzje AS r
JOIN migawki_najemcy AS m USING (id_umowy)
LEFT JOIN (SELECT id_umowy, count(*) AS pozycje, sum(kwota_rabatu) AS suma FROM fk_rabaty GROUP BY id_umowy) AS f
    ON f.id_umowy = m.id_umowy_nastepnej
WHERE r.okres = 'kampania_2026q3' AND r.grupa IN ('oferta', 'kontrola')
ORDER BY r.id_umowy;
```

Sprawdzenia:

```sql
-- Grupy kampanii: brak_oferty 1 031, kontrola 111, oferta 444 (końce 2026-07-01 – 2026-09-30)
SELECT grupa, kwalifikuje, count(*) AS umowy, min(data_konca)::DATE AS od, max(data_konca)::DATE AS do_,
       count(data_oferty) AS z_data_oferty, min(score_polityki) AS score_min, max(score_polityki) AS score_max
FROM retencja_decyzje WHERE okres = 'kampania_2026q3' GROUP BY ALL ORDER BY ALL;

-- Oferta zawsze 45 dni przed końcem umowy (444 umowy)
SELECT date_diff('day', data_oferty, data_konca) AS dni, count(*) AS umowy
FROM retencja_decyzje WHERE okres = 'kampania_2026q3' AND grupa = 'oferta' GROUP BY 1 ORDER BY 1;

-- Ostatni miesiąc w fk_rabaty (2026-09): rabaty roczne są dopiero w trakcie księgowania
SELECT max(miesiac) AS ostatni_miesiac FROM fk_rabaty;
```

Obliczenia (funkcje w `kampania_2026q3.py`):

- `wynik_kampanii`: p_oferta, p_kontrola, efekt = p_oferta − p_kontrola, dodatkowe = efekt × oferty,
  rabaty = przedłużenia z ofertą z pozycją w `fk_rabaty`, wynik netto = dodatkowe × R − rabaty × D − oferty × k,
  ROI = wynik netto / (rabaty × D + oferty × k), próg zera = (rabaty × D + oferty × k) / R / oferty;
- `bootstrap_wyniku`: 1 000 losowań ze zwracaniem osobno w grupie oferta i kontrola (ziarno 42); z `klastry =
  "id_najemcy"` losowani są najemcy ze wszystkimi umowami; `przedzial`: percentyle 2,5 i 97,5;
- `ate_wald`: efekt ± 1,96 · √(pₒ(1−pₒ)/nₒ + pₖ(1−pₖ)/nₖ);
- `balans`: test dwumianowy udziału kontroli wobec 20%, test Welcha dla score, test Fishera dla B2B i wypowiedzeń,
  χ² miesiąc × grupa;
- `wynik_przy_ate`: wynik netto przy efekcie z testu 2025 (`eksperyment_rabatu_2025.json`,
  `efekty_wg_kwalifikuje.kwalifikuje`), przy tych samych ofertach i rabatach;
- wrażliwość: `replace(z, D=1950)` (13 pozycji × 150 zł w FK, `polityka_rabatow.SQL_D_Z_FK`) i `replace(z, k=0)`.
