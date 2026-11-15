"""Zadanie nocne wyceny (valuation_bc): lokale Domilo, nowe oferty, raport kwartalny dla banku.

Kroki funkcji Inngest `wyceny-nocne` (inngest_app.py) wołają `przebieg_lokali`, `przebieg_ofert`
i `przebieg_raportu`. Każdy krok zapisuje wynik w domilo.duckdb (wyceny_historia) albo w docs/bank/
i zwraca krótkie podsumowanie (JSON). Ręczne uruchomienie całości bez Inngest (z katalogu api/):
    poetry run python -m api.contexts_boundaries.valuation_bc.nocne

- Lokale: 7 200 lokali z pms_lokale; cechy otoczenia i sąsiedztwa liczone raz na budynek na dzień przebiegu,
  cechy z opisu z features/wycena/cechy_llm/opisy_domilo.parquet (opis bez czynszu, prompt cechy_lokalu_v1).
- Nowe oferty: oferty z ostatnich OKNO_NOWYCH_OFERT_DNI dni danych (licząc od najnowszej publikacji przed dniem
  przebiegu), jeszcze niewycenione w innym przebiegu. Cechy z opisu (bez kwot) odczytuje LLM; odpowiedzi trafiają
  do cache klienta, więc ponowienie kroku nie płaci drugi raz.
- Połączenie z bazą trzymamy tylko na czas zapytań, a nie podczas wywołań LLM (duckdb_baza.polaczenie).
"""

import sys
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from api.adapters import wyceny_historia
from api.adapters.duckdb_baza import KATALOG_REPO, SCIEZKA_BAZY, polaczenie
from api.adapters.llm_client import KlientLLM
from api.ai.features.wycena.cechy_llm import KOLUMNY_LLM, cechy_do_modelu, wyciagnij
from api.ai.features.wycena.ceny_w_opisie import bez_kwot
from api.ai.features.wycena.ekstrakcja_llm import KATALOG_WYNIKOW, PROMPT_OPISU
from api.ai.llm.prompty import wczytaj_prompt
from api.ai.valuation_model.base import ModelWyceny
from api.ai.valuation_model.obecny import wczytaj_obecny
from api.contexts_boundaries.valuation_bc import raport_bank
from api.contexts_boundaries.valuation_bc.schematy import STREFA
from api.contexts_boundaries.valuation_bc.wycena import cechy_punktow, wycen

OKNO_NOWYCH_OFERT_DNI = 30
KATALOG_RAPORTOW = KATALOG_REPO / "docs" / "bank"
PLIK_CECH_DOMILO = KATALOG_WYNIKOW / "opisy_domilo.parquet"

SQL_LOKALE = """
SELECT l.id_lokalu, l.id_budynku, b.miasto, b.dzielnica, b.lat, b.lon, l.metraz, l.pokoje, l.pietro,
       CAST(b.rok_oddania AS DOUBLE) AS rok_budowy
FROM pms_lokale l JOIN pms_budynki b USING (id_budynku)
ORDER BY l.id_lokalu
"""
SQL_OFERTY = f"""
SELECT id_oferty, miasto, dzielnica, lat, lon, metraz, pokoje, pietro, CAST(rok_budowy AS DOUBLE) AS rok_budowy,
       CAST(cena_ofertowa AS DOUBLE) AS cena_ofertowa, data_publikacji, opis
FROM radar_oferty
WHERE data_publikacji < $koniec
  AND data_publikacji > (SELECT max(data_publikacji) FROM radar_oferty WHERE data_publikacji < $koniec)
                        - INTERVAL {OKNO_NOWYCH_OFERT_DNI} DAY
ORDER BY data_publikacji, id_oferty
"""

Ekstraktor = Callable[[pd.DataFrame], pd.DataFrame]


# --- lokale Domilo --------------------------------------------------------------------------------------------------


def cechy_lokali(con: duckdb.DuckDBPyConnection, dzien: date) -> pd.DataFrame:
    lokale = con.execute(SQL_LOKALE).df()
    budynki = lokale.drop_duplicates("id_budynku")[["id_budynku", "miasto", "dzielnica", "lat", "lon"]]
    punkty = budynki.rename(columns={"id_budynku": "id"}).assign(dzien_wyceny=dzien)
    otoczenie = cechy_punktow(con, punkty).drop(columns=["miasto", "dzielnica", "lat", "lon", "dzien_wyceny"])
    X = lokale.merge(
        otoczenie.rename(columns={"id": "id_budynku"}), on="id_budynku", how="left", validate="many_to_one"
    )
    opisy = cechy_do_modelu(pd.read_parquet(PLIK_CECH_DOMILO)).rename(columns={"id": "id_lokalu"})
    X = X.merge(opisy, on="id_lokalu", how="left", validate="one_to_one")
    return X.assign(dzien_wyceny=dzien)


def _wyceny(X: pd.DataFrame, w: pd.DataFrame, id_kol: str, cena: pd.Series | None) -> pd.DataFrame:
    wyj = pd.DataFrame(
        {
            "id_obiektu": X[id_kol].to_numpy(),
            "miasto": X["miasto"].to_numpy(),
            "dzielnica": X["dzielnica"].to_numpy(),
            "metraz": X["metraz"].to_numpy(dtype=float),
            "dzien_wyceny": X["dzien_wyceny"].to_numpy(),
            "cena_ofertowa": np.nan if cena is None else cena.to_numpy(dtype=float),
        }
    )
    for k in ("p10", "p50", "p90", "odmowa", "powod", "wartosc_bazowa", "czynniki"):
        wyj[k] = w[k].to_numpy()
    wyj["odmowa"] = wyj["odmowa"].astype(bool)
    return wyj[list(wyceny_historia.KOLUMNY_WYCEN)]


def wycen_lokale(con: duckdb.DuckDBPyConnection, model: ModelWyceny, dzien: date) -> pd.DataFrame:
    X = cechy_lokali(con, dzien)
    return _wyceny(X, wycen(model, X), "id_lokalu", None)


# --- nowe oferty ----------------------------------------------------------------------------------------------------


def nowe_oferty(con: duckdb.DuckDBPyConnection, dzien: date, wycenione: set[str]) -> pd.DataFrame:
    koniec = datetime.combine(dzien + timedelta(days=1), datetime.min.time())
    oferty = con.execute(SQL_OFERTY, {"koniec": koniec}).df()
    return oferty[~oferty["id_oferty"].isin(wycenione)].reset_index(drop=True)


def ekstraktor_llm(rekordy: pd.DataFrame) -> pd.DataFrame:
    """id + KOLUMNY_LLM z opisów (LLM, cache klienta); odczyt nieudany = braki (oferta wyceniona bez cech opisu)."""
    surowe = wyciagnij(KlientLLM(), rekordy, wczytaj_prompt(PROMPT_OPISU), watki=16, postep=500)
    return pd.DataFrame({"id": rekordy["id"]}).merge(cechy_do_modelu(surowe), on="id", how="left")


def wycen_oferty(
    con: duckdb.DuckDBPyConnection, model: ModelWyceny, dzien: date, oferty: pd.DataFrame, ekstraktor: Ekstraktor
) -> pd.DataFrame:
    if oferty.empty:
        return pd.DataFrame(columns=list(wyceny_historia.KOLUMNY_WYCEN))
    rekordy = pd.DataFrame({"id": oferty["id_oferty"], "tekst": oferty["opis"].map(bez_kwot)})
    cechy_opisu = ekstraktor(rekordy)[["id", *KOLUMNY_LLM]].rename(columns={"id": "id_oferty"})
    punkty = oferty.drop(columns=["opis"]).rename(columns={"id_oferty": "id"}).assign(dzien_wyceny=dzien)
    X = cechy_punktow(con, punkty).rename(columns={"id": "id_oferty"})
    X = X.merge(cechy_opisu, on="id_oferty", how="left", validate="one_to_one")
    return _wyceny(X, wycen(model, X), "id_oferty", X["cena_ofertowa"])


# --- kroki zadania (zapis do bazy / docs) ---------------------------------------------------------------------------


def _dzien(czas_iso: str) -> tuple[datetime, date]:
    czas = datetime.fromisoformat(czas_iso)
    return czas, czas.astimezone(STREFA).date()


def przebieg_lokali(id_przebiegu: str, czas_iso: str, sciezka: Path = SCIEZKA_BAZY) -> dict:
    czas, dzien = _dzien(czas_iso)
    obecny = wczytaj_obecny()
    with polaczenie(sciezka=sciezka) as con:
        w = wycen_lokale(con, obecny.model, dzien)
    with polaczenie(tylko_odczyt=False, sciezka=sciezka) as con:
        n = wyceny_historia.zapisz(con, id_przebiegu, czas, obecny.wersja, "lokal", w)
    return {"lokale": n, "odmowy": int(w["odmowa"].sum()), "suma_p50_pln": float(w["p50"].sum())}


def przebieg_ofert(
    id_przebiegu: str, czas_iso: str, ekstraktor: Ekstraktor = ekstraktor_llm, sciezka: Path = SCIEZKA_BAZY
) -> dict:
    czas, dzien = _dzien(czas_iso)
    obecny = wczytaj_obecny()
    with polaczenie(sciezka=sciezka) as con:
        wycenione = wyceny_historia.wycenione(con, "oferta", poza_przebiegiem=id_przebiegu)
        oferty = nowe_oferty(con, dzien, wycenione)
    if oferty.empty:
        return {"oferty": 0, "odmowy": 0, "ponizej_p10": 0}
    # LLM poza połączeniem z bazą; wynik podajemy dalej gotowy.
    cechy = ekstraktor(pd.DataFrame({"id": oferty["id_oferty"], "tekst": oferty["opis"].map(bez_kwot)}))
    with polaczenie(sciezka=sciezka) as con:
        w = wycen_oferty(con, obecny.model, dzien, oferty, lambda _: cechy)
    with polaczenie(tylko_odczyt=False, sciezka=sciezka) as con:
        n = wyceny_historia.zapisz(con, id_przebiegu, czas, obecny.wersja, "oferta", w)
    ponizej = (~w["odmowa"]) & (w["cena_ofertowa"] < w["p10"])
    return {"oferty": n, "odmowy": int(w["odmowa"].sum()), "ponizej_p10": int(ponizej.sum())}


def przebieg_raportu(
    czas_iso: str, katalog: Path = KATALOG_RAPORTOW, sciezka: Path = SCIEZKA_BAZY, nadpisz: bool = False
) -> dict:
    """Raport za ostatni pełny kwartał, jeśli jeszcze go nie ma (albo `nadpisz`)."""
    czas, dzien = _dzien(czas_iso)
    kwartal = raport_bank.ostatni_kwartal(dzien)
    plik = Path(katalog) / f"raport_{kwartal[0]}Q{kwartal[1]}.md"
    if plik.exists() and not nadpisz:
        return {"raport": str(plik), "utworzono": False}
    with polaczenie(sciezka=sciezka) as con:
        tekst = raport_bank.raport(con, kwartal, czas_raportu=czas)
    plik.parent.mkdir(parents=True, exist_ok=True)
    plik.write_text(tekst, encoding="utf-8")
    return {"raport": str(plik), "utworzono": True}


def main(argv: list[str]) -> None:
    czas = datetime.now(timezone.utc).isoformat()
    id_przebiegu = f"reczny-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}"
    print("lokale:", przebieg_lokali(id_przebiegu, czas), flush=True)
    print("oferty:", przebieg_ofert(id_przebiegu, czas), flush=True)
    print("raport:", przebieg_raportu(czas, nadpisz="--nadpisz-raport" in argv), flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
