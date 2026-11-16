"""Ocena ekstrakcji awarii (ai/llm/ekstrakcja_awarii.py) na złotym zbiorze koordynatora: docs/b4_ekstrakcja.md.

Prawda: `serwis_zloty_zbior.czy_awaria` i `podzespol` (400 zgłoszeń wind). W złotym zbiorze `wandalizm` jest osobnym
podzespołem, a w schemacie LLM to `zewnetrzna` — porównujemy po zamianie `wandalizm` -> `zewnetrzna`.
Punkt odniesienia: etykieta Serwisownika `kategoria = 'awaria'` na tych samych zgłoszeniach.

Wejście: `ai/features/windy/awarie_llm/<wersja>_zloty_zbior.parquet` z `python -m api.ai.llm.ekstrakcja_awarii`.
Uruchomienie (z katalogu api/): `python -m api.ai.llm.evals.ocena_awarii [awaria_v1 awaria_v2 ...]`
— wypisuje tabele Markdown. Przedziały 95% z bootstrapu zgłoszeń (LOSOWANIA, ZIARNO; te same losowania dla
wszystkich metod, więc różnice są sparowane).
"""

import sys
from collections.abc import Sequence

import numpy as np
import pandas as pd
from api.ai.llm.ekstrakcja_awarii import KATALOG_WYNIKOW, zgloszenia

LOSOWANIA = 2000
ZIARNO = 20261116
LICZBA_BLEDOW = 10

SQL_PRAWDA = """
SELECT
    zz.id_zgloszenia,
    zz.czy_awaria AS prawda,
    CASE zz.podzespol WHEN 'wandalizm' THEN 'zewnetrzna' ELSE zz.podzespol END AS podzespol_prawda,
    zz.podzespol AS podzespol_zz,
    z.kategoria,
    z.kategoria = 'awaria' AS kategoria_awaria
FROM serwis_zloty_zbior AS zz
JOIN serwis_zgloszenia AS z USING (id_zgloszenia)
"""


def wczytaj(con, wersja: str) -> pd.DataFrame:
    """Złoty zbiór + odpowiedzi LLM danej wersji (jeden wiersz na zgłoszenie złotego zbioru)."""
    llm = pd.read_parquet(KATALOG_WYNIKOW / f"{wersja}_zloty_zbior.parquet")
    prawda = con.execute(SQL_PRAWDA).df()
    df = prawda.merge(llm, on="id_zgloszenia", how="left", validate="one_to_one")
    if df["czy_awaria"].isna().any() or df["blad"].notna().any():
        brak = int(df["czy_awaria"].isna().sum())
        raise ValueError(f"{wersja}: {brak} zgłoszeń złotego zbioru bez odpowiedzi LLM (błąd albo brak w pliku)")
    df["czy_awaria"] = df["czy_awaria"].astype(bool)
    df["prawda"] = df["prawda"].astype(bool)
    df["kategoria_awaria"] = df["kategoria_awaria"].astype(bool)
    return df


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


def _proc(x: float) -> str:
    return "brak" if pd.isna(x) else f"{100 * x:.1f}%".replace(".", ",")


def _przedzial(s: pd.Series) -> str:
    return f"{_proc(s.quantile(0.025))} – {_proc(s.quantile(0.975))}"


def _md(df: pd.DataFrame) -> str:
    kol = [str(k) for k in df.columns]
    linie = ["| " + " | ".join(kol) + " |", "|" + "---|" * len(kol)]
    for w in df.itertuples(index=False):
        linie.append("| " + " | ".join("" if pd.isna(x) else str(x).replace("|", "\\|") for x in w) + " |")
    return "\n".join(linie)


def tabela_metryk(df_wersji: dict[str, pd.DataFrame]) -> tuple[str, str]:
    """(metryki z przedziałami, różnice F1 / recall względem kategorii) dla wszystkich wersji i baseline."""
    pierwsza = next(iter(df_wersji.values()))
    prawda = pierwsza["prawda"].to_numpy()
    metody = {"kategoria = awaria (baseline)": pierwsza["kategoria_awaria"].to_numpy()}
    for wersja, df in df_wersji.items():
        assert (df["id_zgloszenia"].to_numpy() == pierwsza["id_zgloszenia"].to_numpy()).all()
        metody[f"LLM {wersja}"] = df["czy_awaria"].to_numpy()
    boot = bootstrap(prawda, metody)
    wiersze = []
    for nazwa, przew in metody.items():
        t, m = tabela_pomylek(prawda, przew), metryki(prawda, przew)
        wiersze.append(
            {
                "metoda": nazwa,
                **{k.upper(): v for k, v in t.items()},
                "precision": _proc(m["precision"]),
                "recall": _proc(m["recall"]),
                "F1": _proc(m["f1"]),
                "F1 95%": _przedzial(boot[nazwa]["f1"]),
                "recall 95%": _przedzial(boot[nazwa]["recall"]),
                "trafność": _proc(m["trafnosc"]),
            }
        )
    baseline = "kategoria = awaria (baseline)"
    roznice = []
    for nazwa in metody:
        if nazwa == baseline:
            continue
        for miara in ("f1", "recall", "precision"):
            d = boot[nazwa][miara] - boot[baseline][miara]
            roznice.append(
                {
                    "porównanie": f"{nazwa} − baseline",
                    "miara": miara,
                    "różnica": _pp(metryki(prawda, metody[nazwa])[miara] - metryki(prawda, metody[baseline])[miara]),
                    "95%": f"{_pp(d.quantile(0.025))} … {_pp(d.quantile(0.975))}",
                }
            )
    return _md(pd.DataFrame(wiersze)), _md(pd.DataFrame(roznice))


def _pp(x: float) -> str:
    return f"{100 * x:+.1f} p.p.".replace(".", ",", 1)


def tabela_pomylek_md(df: pd.DataFrame, kolumna: str) -> str:
    t = tabela_pomylek(df["prawda"], df[kolumna])
    return _md(
        pd.DataFrame(
            [
                {"": "koordynator: awaria", "przewidziano: awaria": t["tp"], "przewidziano: brak awarii": t["fn"]},
                {"": "koordynator: brak awarii", "przewidziano: awaria": t["fp"], "przewidziano: brak awarii": t["tn"]},
            ]
        )
    )


def wedlug_kategorii(df: pd.DataFrame) -> str:
    """Kategoria Serwisownika × prawda × odpowiedź LLM."""
    g = (
        df.groupby("kategoria")
        .apply(
            lambda x: pd.Series(
                {
                    "zgłoszenia": len(x),
                    "awarie (koordynator)": int(x["prawda"].sum()),
                    "awarie (LLM)": int(x["czy_awaria"].sum()),
                    "zgodne": int((x["prawda"] == x["czy_awaria"]).sum()),
                    "pominięte awarie (FN)": int((x["prawda"] & ~x["czy_awaria"]).sum()),
                    "fałszywe alarmy (FP)": int((~x["prawda"] & x["czy_awaria"]).sum()),
                }
            ),
            include_groups=False,
        )
        .reset_index()
        .sort_values("zgłoszenia", ascending=False)
    )
    return _md(g)


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


def bledy_md(con, df: pd.DataFrame) -> str:
    b = wybierz_bledy(df)
    teksty = zgloszenia(con, list(b["id_zgloszenia"])).set_index("id_zgloszenia")["tekst"]

    def notatki(id_):
        linie = teksty[id_].splitlines()
        tresc = linie[2].removeprefix("Treść zgłoszenia: ")
        return f"„{tresc}”<br>" + "<br>".join(linie[4:] if len(linie) > 4 else linie[3:])

    wiersze = [
        {
            "#": i,
            "zgłoszenie": r.id_zgloszenia,
            "kategoria": r.kategoria,
            "koordynator": f"{'awaria' if r.prawda else 'brak'} / {r.podzespol_zz}",
            "LLM": f"{'awaria' if r.czy_awaria else 'brak'} / {r.podzespol}",
            "pewność": f"{r.pewnosc:.2f}".replace(".", ","),
            "treść zgłoszenia i notatki": notatki(r.id_zgloszenia),
            "objaw (LLM)": r.objaw,
        }
        for i, r in enumerate(b.itertuples(index=False), start=1)
    ]
    return _md(pd.DataFrame(wiersze))


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


SQL_ROZNORODNOSC = """
WITH n AS (
    SELECT n.id_zgloszenia, zz.czy_awaria,
           regexp_replace(regexp_replace(n.tresc, '\\s+', ' ', 'g'), '[0-9]+', 'N', 'g') AS wzor
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
"""


def roznorodnosc(con) -> str:
    """Ile różnych treści notatek (cyfry -> N, białe znaki scalone) jest w złotym zbiorze."""
    return _md(con.execute(SQL_ROZNORODNOSC).df())


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


def tokeny(df_wersji: dict[str, pd.DataFrame]) -> str:
    return _md(
        pd.DataFrame(
            [
                {
                    "wersja": w,
                    "zgłoszenia": len(df),
                    "tokeny wejścia": int(df["tokeny_wejscia"].sum()),
                    "w tym z cache OpenAI": int(df["tokeny_wejscia_z_cache"].sum()),
                    "tokeny wyjścia": int(df["tokeny_wyjscia"].sum()),
                    "wejście / zgłoszenie": round(df["tokeny_wejscia"].mean()),
                    "wyjście / zgłoszenie": round(df["tokeny_wyjscia"].mean()),
                }
                for w, df in df_wersji.items()
            ]
        )
    )


def main(wersje: Sequence[str]) -> None:
    from api.adapters.duckdb_baza import polacz

    con = polacz()
    df_wersji = {w: wczytaj(con, w).sort_values("id_zgloszenia").reset_index(drop=True) for w in wersje}
    met, roz = tabela_metryk(df_wersji)
    print(f"### E1 metryki\n\n{met}\n\n### E1b różnice\n\n{roz}\n")
    pierwsza = next(iter(df_wersji.values()))
    print(f"### E2 baseline\n\n{tabela_pomylek_md(pierwsza, 'kategoria_awaria')}\n")
    for w, df in df_wersji.items():
        print(f"### E2 {w}\n\n{tabela_pomylek_md(df, 'czy_awaria')}\n")
        print(f"### E3 {w}\n\n{wedlug_kategorii(df)}\n")
        podsum, macierz = podzespoly(df)
        print(f"### E4 {w}\n\n{podsum}\n\n### E4b {w}\n\n{macierz}\n")
        print(f"### E5 {w}\n\n{notatki_bez_podzespolu(con, df)}\n")
        print(f"### E5b {w}\n\n{czesci_bez_podzespolu(con, df)}\n")
        print(f"### E6 {w}\n\n{pewnosc(df)}\n")
        print(f"### E7 {w}\n\n{bledy_md(con, df)}\n")
    print(f"### E8 tokeny\n\n{tokeny(df_wersji)}\n")
    print(f"### E9 roznorodnosc\n\n{roznorodnosc(con)}\n")


if __name__ == "__main__":
    main(sys.argv[1:] or ["awaria_v1"])
