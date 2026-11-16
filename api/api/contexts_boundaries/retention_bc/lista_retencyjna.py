"""Cotygodniowa lista retencyjna: umowy kończące się za 60–66 dni -> ryzyko i czas -> uplift i akcja -> grupa
kampanii z hasha -> zapis (tabela lista_retencyjna). Opis i wyniki: docs/lista_retencyjna.md.

Funkcja Inngest `lista-retencyjna` (inngest_app.py, poniedziałek 07:00 czasu warszawskiego) wywołuje
`wykonaj_liste_retencyjna`, a każdy krok idzie przez `ctx.step.run` (po awarii Inngest ponawia tylko krok, który
padł). Kroki przekazują sobie dane przez pliki Parquet w katalogu przebiegu
(`lista_retencyjna/<data_listy>/<id_przebiegu>/`, poza gitem), a zwracają krótkie podsumowanie (JSON).

- Dzień listy (`data_listy`): z wywołania albo dzisiejsza data w Europe/Warsaw (krok `parametry`, zapamiętany).
- Stan danych: dzień listy, ale nie później niż dzień eksportu 2026-09-30 (późniejszych zdarzeń w danych nie ma).
- Umowy: bieżący (ostatni podpisany) okres aktywnego najmu B2C / B2B (`features/najemcy/okresy_umow.sql`: umowy
  `pierwsza` i `przedłużenie`), który kończy się (`data_do`) od dzień listy + 60 do dzień listy + 66 dni włącznie.
  Lista co poniedziałek pokrywa więc każdy dzień końca umowy dokładnie raz. Aktywny = bez wyprowadzki do dnia stanu.
- Modele: churn_model/current.yaml przez `base.wczytaj_obecny()`: część `ryzyko` (v2_przezycie_cox: ryzyko =
  P(koniec najmu w bieżącym okresie) od dnia stanu, mediana, RMST60; ryzyko_najmu.ryzyko_okresow, to samo co
  GET /risk) i część `uplift` (v3_uplift_tlearner: szanse przedłużenia, uplift, EV i akcja; oferta_najmu, cechy na
  dzień decyzji = min(data_do − 60 dni, dzień stanu), budżet rabatów z zalozenia.yaml, gdy jest ustalony).
- Grupa: `reszta_hasha` = md5(`id_umowy:kampania`) czytane jako liczba little-endian mod 100, czyli to samo co
  `md5_number(id_umowy || ':' || kampania) % 100` w DuckDB (docs/kampania_2026q4_plan.md); reszta < 20 ->
  `kontrola` (20%, bez oferty niezależnie od akcji), inaczej `polityka`. `wyslac_oferte` = polityka i akcja rabat.
  Grupa zależy tylko od id_umowy i nazwy kampanii, więc każdy przebieg (i każdy tydzień) daje tej umowie tę samą.
- Kampania: z wywołania albo `kampania_RRRRqN` według kwartału miesiąca końca umowy minus 2 miesiące (oferta idzie
  45 dni przed końcem): końce 2026-12 – 2027-02 -> kampania_2026q4, 2027-03 – 2027-05 -> kampania_2027q1 itd.
- Zapis: tabela lista_retencyjna, zastępuje cały dzień listy (adapters/lista_retencyjna.py).

Ręcznie (bez Inngest): `pypyr lista_retencyjna [data=RRRR-MM-DD] [kampania=...]` albo
`cd api && poetry run python -m api.contexts_boundaries.retention_bc.lista_retencyjna [RRRR-MM-DD] [kampania]`.
"""

import hashlib
import json
import sys
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
from api.adapters import lista_retencyjna
from api.adapters.duckdb_baza import KATALOG_REPO, SCIEZKA_BAZY, polaczenie
from api.ai.churn_model.base import wczytaj_obecny
from api.ai.features.najemcy.cechy_okresow import okresy_umow
from api.contexts_boundaries.retention_bc.oferta_najmu import (
    decyzja,
    miesci_sie_w_budzecie,
    oferty_okresow,
    populacja_budzetu,
)
from api.contexts_boundaries.retention_bc.ryzyko_najmu import ryzyko_okresow
from api.contexts_boundaries.retention_bc.zalozenia import budzet_rabatow, zalozenia_oferty
from dateutil.relativedelta import relativedelta

STREFA = ZoneInfo("Europe/Warsaw")
KONIEC_DANYCH = date(2026, 9, 30)  # dzień eksportu (CLAUDE.md)
DNI_OD, DNI_DO = 60, 66
UDZIAL_KONTROLI = 0.20  # 20% umów w kontroli (docs/kampania_2026q4_plan.md, polecenie użytkownika)
KATALOG_PRZEBIEGOW = KATALOG_REPO / "lista_retencyjna"

Krok = Callable[..., Any]

SQL_WYPOWIEDZENIA = """
SELECT id_najmu, coalesce(wypowiedzenie_data::DATE <= $stan, false) AS wypowiedzenie_zlozone
FROM pms_najmy
"""


# --- logika (bez plików i Inngest) ---------------------------------------------------------------------------------


def stan_danych_na(data_listy: date) -> date:
    """Dzień, według którego liczymy cechy i ryzyko: dzień listy, najpóźniej dzień eksportu."""
    return min(data_listy, KONIEC_DANYCH)


def okno_konca(data_listy: date) -> tuple[date, date]:
    """Pierwszy i ostatni dzień końca umowy (włącznie) na liście z dnia `data_listy`."""
    return data_listy + timedelta(days=DNI_OD), data_listy + timedelta(days=DNI_DO)


def nazwa_kampanii(data_do: date) -> str:
    """kampania_RRRRqN: kwartał miesiąca końca umowy cofniętego o 2 miesiące (miesiąc wysłania oferty)."""
    m = date(data_do.year, data_do.month, 1) - relativedelta(months=2)
    return f"kampania_{m.year}q{(m.month - 1) // 3 + 1}"


def reszta_hasha(id_umowy: str, kampania: str) -> int:
    """md5(`id_umowy:kampania`) jako liczba little-endian mod 100 (= DuckDB md5_number(...) % 100)."""
    skrot = hashlib.md5(f"{id_umowy}:{kampania}".encode("utf-8")).digest()
    return int.from_bytes(skrot, "little") % 100


def grupa_kampanii(id_umowy: str, kampania: str, udzial_kontroli: float = UDZIAL_KONTROLI) -> str:
    return "kontrola" if reszta_hasha(id_umowy, kampania) < round(100 * udzial_kontroli) else "polityka"


def umowy_w_oknie(con, data_listy: date, stan: date) -> pd.DataFrame:
    """Bieżące okresy aktywnych najmów B2C / B2B z końcem w oknie 60–66 dni (kolumny okresy_umow + id_najemcy,
    wypowiedzenie_zlozone), posortowane po id_umowy."""
    okresy = okresy_umow(con, "2100-12-31")  # także przedłużenia podpisane na okres po dniu stanu
    biezace = okresy.loc[okresy.groupby("id_najmu")["nr_okresu"].idxmax()]
    od, do = okno_konca(data_listy)
    dzien_stanu = pd.Timestamp(stan)
    wybrane = biezace[
        biezace["linia"].isin(["B2C", "B2B"])
        & (biezace["data_wyprowadzenia"].isna() | (biezace["data_wyprowadzenia"] > dzien_stanu))
        & biezace["data_do"].between(pd.Timestamp(od), pd.Timestamp(do))
    ]
    wyp = con.execute(SQL_WYPOWIEDZENIA, {"stan": stan}).df()
    wybrane = wybrane.merge(wyp, on="id_najmu", how="left", validate="1:1")
    wybrane["wypowiedzenie_zlozone"] = wybrane["wypowiedzenie_zlozone"].fillna(False).astype(bool)
    return wybrane.sort_values("id_umowy", kind="mergesort").reset_index(drop=True)


# --- kroki (każdy czyta pliki poprzednich kroków z katalogu przebiegu i zapisuje swój) ----------------------------


def _plik(katalog: str, nazwa: str) -> Path:
    return Path(katalog) / f"{nazwa}.parquet"


def _liczniki(s: pd.Series) -> dict[str, int]:
    return {str(k): int(v) for k, v in s.value_counts().sort_index().items()}


def krok_parametry(data_listy: str | None, id_przebiegu: str, katalog_bazowy: str, kampania: str | None) -> dict:
    dzien = date.fromisoformat(data_listy) if data_listy else datetime.now(STREFA).date()
    katalog = Path(katalog_bazowy) / dzien.isoformat() / id_przebiegu
    katalog.mkdir(parents=True, exist_ok=True)
    od, do = okno_konca(dzien)
    return {
        "data_listy": dzien.isoformat(),
        "stan_danych_na": stan_danych_na(dzien).isoformat(),
        "koniec_umowy_od": od.isoformat(),
        "koniec_umowy_do": do.isoformat(),
        "kampania": kampania,
        "katalog": str(katalog),
        "id_przebiegu": id_przebiegu,
    }


def krok_umowy(katalog: str, data_listy: str, stan: str, sciezka: Path = SCIEZKA_BAZY) -> dict:
    with polaczenie(sciezka=sciezka) as con:
        umowy = umowy_w_oknie(con, date.fromisoformat(data_listy), date.fromisoformat(stan))
    umowy.to_parquet(_plik(katalog, "umowy"), index=False)
    return {
        "umowy": len(umowy),
        "linie": _liczniki(umowy["linia"]),
        "z_wypowiedzeniem": int(umowy["wypowiedzenie_zlozone"].sum()),
    }


def krok_ryzyko(katalog: str, stan: str, sciezka: Path = SCIEZKA_BAZY) -> dict:
    """Ryzyko i czas do odejścia z części `ryzyko` current.yaml (to samo co GET /risk)."""
    obecny = wczytaj_obecny()
    umowy = pd.read_parquet(_plik(katalog, "umowy"))
    with polaczenie(sciezka=sciezka) as con:
        ryzyko = ryzyko_okresow(con, umowy, obecny.ryzyko, date.fromisoformat(stan))
    ryzyko.to_parquet(_plik(katalog, "ryzyko"), index=False)
    return {
        "wersja_modelu": obecny.wersja_ryzyka,
        "umowy": len(ryzyko),
        "ryzyko_srednie": round(float(ryzyko["ryzyko"].mean()), 6) if len(ryzyko) else None,
    }


def krok_uplift(katalog: str, stan: str, sciezka: Path = SCIEZKA_BAZY) -> dict:
    """Szanse przedłużenia, uplift, EV i akcja z części `uplift` current.yaml (reguła z oferta_najmu.py)."""
    obecny = wczytaj_obecny()
    z = zalozenia_oferty()
    budzet = budzet_rabatow()
    dzien = date.fromisoformat(stan)
    umowy = pd.read_parquet(_plik(katalog, "umowy"))
    kolumny = [
        "id_umowy", "p_przedluzy_z_oferta", "p_przedluzy_bez_oferty", "uplift", "ev_pln", "data_decyzji",
        "poza_zakresem_modelu", "akcja", "uzasadnienie",
    ]  # fmt: skip
    if umowy.empty:
        pd.DataFrame(columns=kolumny).to_parquet(_plik(katalog, "uplift"), index=False)
        return {"wersja_modelu": obecny.wersja_upliftu, "umowy": 0, "akcje": {}}
    with polaczenie(sciezka=sciezka) as con:
        wynik, wklady, wartosci = oferty_okresow(con, umowy, obecny.uplift, z, dzien)
        pop = populacja_budzetu(con, obecny.uplift, z, dzien) if budzet is not None else None
    wiersze = []
    for i in wynik.index:
        w = wynik.loc[i]
        w_budzecie = None
        if pop is not None:
            w_budzecie = miesci_sie_w_budzecie(pop["ev"], pop["koszt_rabatu"], i, budzet) if i in pop.index else None
        d = decyzja(
            float(w["uplift"]), float(w["ev"]), float(w["p_oferta"]), wklady.drop(columns="wklad_staly").loc[i],
            wartosci.loc[i], list(w["poza_zakresem"]), w_budzecie, pd.Timestamp(w["migawka"]).date(), dzien,
        )  # fmt: skip
        wiersze.append(
            {
                "id_umowy": str(i),
                "p_przedluzy_z_oferta": float(w["p_oferta"]),
                "p_przedluzy_bez_oferty": float(w["p_bez_oferty"]),
                "uplift": float(w["uplift"]),
                "ev_pln": float(w["ev"]),
                "data_decyzji": pd.Timestamp(w["data_migawki"]).date(),
                "poza_zakresem_modelu": [str(c) for c in w["poza_zakresem"]],
                "akcja": d["akcja"],
                "uzasadnienie": d["uzasadnienie"],
            }
        )
    uplift = pd.DataFrame(wiersze, columns=kolumny)
    uplift.to_parquet(_plik(katalog, "uplift"), index=False)
    return {
        "wersja_modelu": obecny.wersja_upliftu,
        "umowy": len(uplift),
        "akcje": _liczniki(uplift["akcja"]),
        "poza_zakresem_modelu": int((uplift["poza_zakresem_modelu"].map(len) > 0).sum()),
        "budzet_rabatow_rok": budzet,
    }


def krok_grupy(katalog: str, kampania: str | None) -> dict:
    """Grupa kampanii z hasha (id_umowy, kampania); kampania z wywołania albo z miesiąca końca umowy."""
    umowy = pd.read_parquet(_plik(katalog, "umowy"), columns=["id_umowy", "data_do"])
    kampanie = [kampania or nazwa_kampanii(pd.Timestamp(d).date()) for d in umowy["data_do"]]
    reszty = [reszta_hasha(str(i), k) for i, k in zip(umowy["id_umowy"], kampanie)]
    grupy = pd.DataFrame(
        {
            "id_umowy": umowy["id_umowy"].astype(str),
            "kampania": kampanie,
            "reszta_hasha": pd.array(reszty, dtype="int32"),
            "grupa": [grupa_kampanii(str(i), k) for i, k in zip(umowy["id_umowy"], kampanie)],
        }
    )
    grupy.to_parquet(_plik(katalog, "grupy"), index=False)
    return {
        "umowy": len(grupy),
        "kampanie": _liczniki(grupy["kampania"]),
        "grupy": _liczniki(grupy["grupa"]),
    }


def krok_zapis(
    katalog: str,
    data_listy: str,
    stan: str,
    wersja_ryzyka: str,
    wersja_upliftu: str,
    id_przebiegu: str,
    sciezka: Path = SCIEZKA_BAZY,
) -> dict:
    """Lista dnia do tabeli lista_retencyjna (zastępuje cały dzień); kopia zapisanych wierszy w lista.parquet."""
    umowy = pd.read_parquet(_plik(katalog, "umowy"))
    df = (
        umowy[["id_umowy", "id_najmu", "id_najemcy", "linia", "data_do", "wypowiedzenie_zlozone"]]
        .merge(pd.read_parquet(_plik(katalog, "ryzyko")), on="id_umowy", how="left", validate="1:1")
        .merge(pd.read_parquet(_plik(katalog, "uplift")), on="id_umowy", how="left", validate="1:1")
        .merge(pd.read_parquet(_plik(katalog, "grupy")), on="id_umowy", how="left", validate="1:1")
    )
    dzien = date.fromisoformat(data_listy)
    df = df.assign(
        data_listy=dzien,
        data_do=pd.to_datetime(df["data_do"]).dt.date,
        dni_do_konca=(pd.to_datetime(df["data_do"]) - pd.Timestamp(dzien)).dt.days.astype("int32"),
        stan_danych_na=date.fromisoformat(stan),
        data_decyzji=pd.to_datetime(df["data_decyzji"]).dt.date,
        poza_zakresem_modelu=df["poza_zakresem_modelu"].map(list),
        wyslac_oferte=(df["grupa"] == "polityka") & (df["akcja"] == "rabat"),
        wersja_modelu_ryzyka=wersja_ryzyka,
        wersja_modelu_upliftu=wersja_upliftu,
        id_przebiegu=id_przebiegu,
    )
    for k in ("ryzyko", "ryzyko_12_od_poczatku_okresu", "przezycie_12_mies", "p_przedluzy_z_oferta"):
        df[k] = df[k].astype(float).round(6)
    df["p_przedluzy_bez_oferty"] = df["p_przedluzy_bez_oferty"].astype(float).round(6)
    df["uplift"] = df["uplift"].astype(float).round(6)
    df["ev_pln"] = df["ev_pln"].astype(float).round(2)
    df = df[list(lista_retencyjna.KOLUMNY)].sort_values("id_umowy", kind="mergesort").reset_index(drop=True)
    with polaczenie(tylko_odczyt=False, sciezka=sciezka) as con:
        n = lista_retencyjna.zapisz(con, dzien, df)
    df.to_parquet(_plik(katalog, "lista"), index=False)
    return {
        "zapisane": n,
        "grupy": _liczniki(df["grupa"]),
        "akcje": _liczniki(df["akcja"]),
        "wyslac_oferte": int(df["wyslac_oferte"].sum()),
    }


# --- przebieg -------------------------------------------------------------------------------------------------------


def wykonaj_liste_retencyjna(
    krok: Krok,
    id_przebiegu: str,
    data_listy: str | None = None,
    kampania: str | None = None,
    sciezka: Path = SCIEZKA_BAZY,
    katalog_bazowy: Path = KATALOG_PRZEBIEGOW,
) -> dict:
    """Kolejność kroków; `krok(id, handler, *args)` = ctx.step.run w Inngest (w testach i CLI: wywołanie wprost)."""
    par = krok("parametry", krok_parametry, data_listy, id_przebiegu, str(katalog_bazowy), kampania)
    kat, dzien, stan = par["katalog"], par["data_listy"], par["stan_danych_na"]
    wynik: dict[str, Any] = {"parametry": par}
    wynik["umowy"] = krok("umowy-w-oknie", krok_umowy, kat, dzien, stan, sciezka)
    wynik["ryzyko"] = krok("ryzyko-i-czas", krok_ryzyko, kat, stan, sciezka)
    wynik["uplift"] = krok("uplift-i-akcja", krok_uplift, kat, stan, sciezka)
    wynik["grupy"] = krok("grupy-kampanii", krok_grupy, kat, par["kampania"])
    wersje = (wynik["ryzyko"]["wersja_modelu"], wynik["uplift"]["wersja_modelu"])
    wynik["zapis"] = krok("zapis-listy", krok_zapis, kat, dzien, stan, *wersje, id_przebiegu, sciezka)
    return wynik


def _krok_wprost(id_kroku: str, handler: Callable, *args):
    wynik = handler(*args)
    print(f"[{id_kroku}] {json.dumps(wynik, ensure_ascii=False, default=str)}", flush=True)
    return wynik


if __name__ == "__main__":
    # argumenty: data listy (RRRR-MM-DD) i / albo nazwa kampanii, w dowolnej kolejności (puste pomijamy)
    argumenty = [a for a in sys.argv[1:] if a]
    daty = [a for a in argumenty if len(a) == 10 and a[4] == "-" and a[7] == "-"]
    inne = [a for a in argumenty if a not in daty]
    przebieg = f"reczny-{datetime.now(timezone.utc):%Y%m%dT%H%M%S%f}"
    wykonaj_liste_retencyjna(_krok_wprost, przebieg, daty[0] if daty else None, inne[0] if inne else None)
