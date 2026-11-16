"""Przegląd zaleceń GET /risk (część `oferta`) dla wszystkich aktywnych najmów i 10 przykładów do raportu.

Uruchomienie (wymaga domilo.duckdb i modeli v2_przezycie_cox oraz v3_uplift_tlearner):
    cd api && poetry run python -m api.contexts_boundaries.retention_bc.przeglad_ofert

Populacja: najmy B2C / B2B aktywne w dniu oceny (2026-09-30: bez wyprowadzki albo z wyprowadzką później), bieżący
okres = ostatni podpisany (jak w /risk). Akcja jak w oferta_najmu.zalecana_akcja przy obecnych założeniach.
Przykłady: po 3 z każdej akcji (najmy na 25., 50. i 75. percentylu EV w danej akcji, a nie skrajne, bo v3 zawyża
skrajne uplifty) i jeden graniczny (najem, którego EV jest najbliższe zera); wszystkie spośród najmów w zakresie
danych uczących v3 (poza zakresem akcja to zawsze „bez rabatu, decyzja w dniu migawki”).
Każdy przykład liczy pełna funkcja endpointu (ryzyko_najmu), więc w raporcie jest dokładnie to, co zwraca API.
Zapis: retention_bc/wyniki/oferty_aktywnych.parquet, retention_bc/wyniki/przyklady_oferty.json.
"""

import json

import numpy as np
import pandas as pd
from api.adapters.duckdb_baza import polacz
from api.ai.features.najemcy.cechy_okresow import okresy_umow
from api.contexts_boundaries.retention_bc.oferta_najmu import (
    AKCJE,
    oferty_okresow,
    wczytaj_model_uplift,
    wiersz_z_wkladami,
    zalecana_akcja,
)
from api.contexts_boundaries.retention_bc.polityka_rabatow import KATALOG_WYNIKOW
from api.contexts_boundaries.retention_bc.ryzyko_najmu import DZIEN_OCENY, ryzyko_najmu, wczytaj_model
from api.contexts_boundaries.retention_bc.zalozenia import budzet_rabatow, zalozenia_oferty

PERCENTYLE_PRZYKLADOW = (25, 50, 75)


def aktywne_okresy(con, dzien_oceny=DZIEN_OCENY) -> pd.DataFrame:
    okresy = okresy_umow(con, "2100-12-31")
    biezace = okresy.loc[okresy.groupby("id_najmu")["nr_okresu"].idxmax()]
    dzien = pd.Timestamp(dzien_oceny)
    return biezace[biezace["data_wyprowadzenia"].isna() | (biezace["data_wyprowadzenia"] > dzien)].reset_index(
        drop=True
    )


def wybierz_przyklady(tabela: pd.DataFrame) -> list[tuple[str, str]]:
    """(id_najmu, powód wyboru): po 3 na akcję (percentyle EV w akcji) i 1 graniczny (|EV| najmniejsze)."""
    wybrane = []
    tabela = tabela[tabela["poza_zakresem"].map(len) == 0]  # przykłady tylko z najmów w zakresie modelu
    for akcja in AKCJE:
        grupa = tabela[tabela["akcja"] == akcja].sort_values("ev", kind="stable").reset_index(drop=True)
        for p in PERCENTYLE_PRZYKLADOW:
            i = int(round(p / 100 * (len(grupa) - 1)))
            wybrane.append((grupa.at[i, "id_najmu"], f"{akcja}: {p}. percentyl EV w tej akcji"))
    pozostale = tabela[~tabela["id_najmu"].isin([w[0] for w in wybrane])]
    graniczny = pozostale.loc[pozostale["ev"].abs().idxmin(), "id_najmu"]
    wybrane.append((graniczny, "graniczny: EV najbliższe zera"))
    return wybrane


def main() -> dict:
    z = zalozenia_oferty()
    model_v3, model_v2 = wczytaj_model_uplift(), wczytaj_model()
    with polacz() as con:
        okresy = aktywne_okresy(con)
        wynik, wklady, wartosci = oferty_okresow(con, okresy, model_v3, z, DZIEN_OCENY)
        opisy = wiersz_z_wkladami(wklady, wartosci, wynik, DZIEN_OCENY)
        tabela = wynik.join(opisy).reset_index(drop=True)
        tabela["linia"] = okresy.set_index("id_umowy").loc[tabela["id_umowy"], "linia"].to_numpy()
        tabela["dni_do_konca"] = (tabela["data_do"] - pd.Timestamp(DZIEN_OCENY)).dt.days
        przyklady = []
        for id_najmu, powod in wybierz_przyklady(tabela):
            odp = ryzyko_najmu(con, id_najmu, model_v2, model_uplift=model_v3)
            przyklady.append({"powod_wyboru": powod, "id_najmu": id_najmu, "linia": odp["linia"]} | odp["oferta"])

    w_roku = tabela["dni_do_konca"].between(1, 365)
    podsumowanie = {}
    for nazwa, maska in (("wszystkie_aktywne", np.ones(len(tabela), dtype=bool)), ("koniec_w_365_dni", w_roku)):
        t = tabela[maska]
        poza = t["poza_zakresem"].map(len) > 0
        cechy_poza = pd.Series([c for lista in t.loc[poza, "poza_zakresem"] for c in lista]).value_counts()
        podsumowanie[nazwa] = {
            "najmy": int(len(t)),
            "poza_zakresem_modelu": int(poza.sum()),
            "poza_zakresem_wg_cechy": {k: int(v) for k, v in cechy_poza.head(8).items()},
            "decyzja_w_przyszlosci": int((t["migawka"] > pd.Timestamp(DZIEN_OCENY)).sum()),
            "akcje_w_zakresie": {a: int(((t["akcja"] == a) & ~poza).sum()) for a in AKCJE},
            "akcje": {a: int((t["akcja"] == a).sum()) for a in AKCJE},
            "akcje_wg_linii": {
                linia: {a: int(((t["akcja"] == a) & (t["linia"] == linia)).sum()) for a in AKCJE}
                for linia in ("B2C", "B2B")
            },
            "ev_suma_rabat": float(t.loc[t["akcja"] == "rabat", "ev"].sum()),
            "koszt_rabatow_rabat": float(t.loc[t["akcja"] == "rabat", "koszt_rabatu"].sum()),
            "uplift_mediana": {a: float(t.loc[t["akcja"] == a, "uplift"].median()) for a in AKCJE},
            "ev_mediana": {a: float(t.loc[t["akcja"] == a, "ev"].median()) for a in AKCJE},
        }
    # Spójność: akcja z przeglądu = akcja z endpointu dla przykładów (budżet nieustalony)
    zgodne = all(p["zalecana_akcja"] == zalecana_akcja(p["uplift"], p["ev_pln"], p["w_budzecie"]) for p in przyklady)
    wyj = {
        "dzien_oceny": str(DZIEN_OCENY),
        "zalozenia": {"R": z.R, "D": z.D, "k": z.k, "budzet_rabatow_rok": budzet_rabatow()},
        "podsumowanie": podsumowanie,
        "przyklady": przyklady,
        "przyklady_zgodne_z_regula": zgodne,
    }
    KATALOG_WYNIKOW.mkdir(exist_ok=True)
    tabela.to_parquet(KATALOG_WYNIKOW / "oferty_aktywnych.parquet", index=False)
    (KATALOG_WYNIKOW / "przyklady_oferty.json").write_text(
        json.dumps(wyj, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    return wyj


if __name__ == "__main__":
    w = main()
    print(json.dumps(w["podsumowanie"], ensure_ascii=False, indent=1))
    print("zgodne:", w["przyklady_zgodne_z_regula"])
    for p in w["przyklady"]:
        print(f"\n[{p['powod_wyboru']}] {p['id_najmu']} ({p['linia']}), koniec {p['koniec_okresu']}")
        print(
            f"  decyzja {p['data_decyzji']}, p_o={p['p_przedluzy_z_oferta']:.3f}, p_k={p['p_przedluzy_bez_oferty']:.3f}"
        )
        print(f"  uplift={p['uplift']:+.4f}, EV={p['ev_pln']:.0f} -> {p['zalecana_akcja']}")
        print("  " + p["uzasadnienie"])
        print("  ", [(c["cecha"], c["wklad_pp"]) for c in p["najwazniejsze_cechy"]])
        print("  uwagi:", [u for u in p["uwagi"][3:]], "| poza:", p["poza_zakresem_modelu"])
