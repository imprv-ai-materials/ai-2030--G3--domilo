"""Ryzyko i spodziewany czas do odejścia dla jednego najmu (GET /risk/{id_najmu}), model v2_przezycie_cox.

Model v2 przewiduje przeżycie w obrębie jednego okresu umowy (czas od jego początku, cechy v1 na data_od okresu).
Krzywą najemcy od dnia oceny składamy z okresów:
1. reszta bieżącego okresu: S_0(e + u) / S_0(e), gdzie e = miesiące, które już minęły (najem trwa do dnia oceny);
2. kolejne przedłużenia po 12 miesięcy (warstwa 12): S = P(przetrwania poprzednich okresów) × S_k(u - początek_k).
Cechy przyszłych okresów (ZALOZENIA_KRZYWEJ): jak w bieżącym okresie, z wyjątkiem stażu (rośnie o długość okresów)
i indeksacji > 6% (= 0, tak jak w niemal wszystkich przedłużeniach z 2026 r.: docs/przezycie.md, tabela
„Rok początku ostatniego przedłużenia”). To założenie wykonawcy, nie wynik danych.
Mediana = pierwszy moment, w którym S <= 0,5 (None, gdy nie w horyzoncie 60 mies.); RMST60 = pole pod S do 60 mies.
(średnia liczba miesięcy najmu w ciągu najbliższych 5 lat). Siatka: 1/30 miesiąca (ok. 1 dzień).
Dzień oceny: dzień eksportu danych (2026-09-30), bo baza nie ma nowszych zdarzeń.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import duckdb
import joblib
import numpy as np
import pandas as pd
from api.ai.churn_model.versions.v2_przezycie_cox.model import ModelCox
from api.ai.churn_model.versions.v3_uplift_tlearner.model import ModelUpliftT
from api.ai.features.najemcy.cechy_okresow import cechy_okresow, okresy_umow
from api.contexts_boundaries.retention_bc.oferta_najmu import oferta_najmu
from dateutil.relativedelta import relativedelta

SCIEZKA_MODELU = (
    Path(__file__).resolve().parents[2] / "ai" / "churn_model" / "versions" / "v2_przezycie_cox" / "model.joblib"
)
DZIEN_OCENY = date(2026, 9, 30)
HORYZONT_MIES = 60.0
KROK_MIES = 1 / 30
DLUGOSC_PRZEDLUZENIA = 12.0
INDEKSACJA_PRZYSZLA = 0.0
ZALOZENIA_KRZYWEJ = (
    "Krzywa składa się z reszty bieżącego okresu i kolejnych przedłużeń po 12 miesięcy (model v2 liczy przeżycie "
    "w jednym okresie).",
    "Cechy przyszłych okresów jak w bieżącym okresie; staż rośnie o długość okresów.",
    "W przyszłych przedłużeniach indeksacja <= 6% (założenie wykonawcy, nie dane).",
    "Dzień oceny to dzień eksportu danych 2026-09-30.",
    "Przeżycie z bazą Kalbfleischa-Prentice'a (zgodne z Kaplanem-Meierem przy końcach umów w jednym dniu).",
    "B2B: model zawyża przeżycie przedłużeń (S(12) 0,41 wobec 0,22 wg Kaplana-Meiera na treningu) i nowych najmów od "
    "2025 (0,29 wobec 0,15), więc mediana i RMST60 dla B2B są zawyżone (docs/przezycie_cox.md, „Kalibracja”).",
    "W B2C model słabo rozróżnia najemców (C-index 0,501 na teście, docs/przezycie_cox.md): wynik dla B2C jest bliski "
    "średniej dla podobnych umów.",
)


class NajemNieznany(LookupError):
    pass


class NajemPozaModelem(ValueError):
    pass


class NajemZakonczony(ValueError):
    pass


def miesiace_kalendarzowe(od: date, do_wylacznie: date) -> float:
    """Pełne miesiące kalendarzowe od `od` do `do_wylacznie` + ułamek kolejnego (jak w czas_najmu.sql)."""
    roznica = relativedelta(do_wylacznie, od)
    pelne = roznica.years * 12 + roznica.months
    poczatek = od + relativedelta(months=pelne)
    koniec = od + relativedelta(months=pelne + 1)
    return pelne + (do_wylacznie - poczatek).days / (koniec - poczatek).days


@dataclass
class KrzywaNajmu:
    czasy: np.ndarray  # miesiące od dnia oceny
    przezycie: np.ndarray  # S(u): szansa, że najem trwa dłużej niż u
    p_konca_biezacego_okresu: float

    def mediana(self) -> float | None:
        ponizej = np.flatnonzero(self.przezycie <= 0.5)
        return float(self.czasy[ponizej[0]]) if len(ponizej) else None

    def rmst(self, horyzont: float = HORYZONT_MIES) -> float:
        maska = self.czasy < horyzont
        return float(np.sum(self.przezycie[maska] * np.diff(np.append(self.czasy[maska], horyzont))))

    def przezycie_po(self, miesiace: float) -> float:
        return float(self.przezycie[np.searchsorted(self.czasy, miesiace, side="right") - 1])


def krzywa_pozostala(
    model: ModelCox,
    X0: pd.DataFrame,
    miesiecy_umowy: float,
    minelo: float,
    opoznienie: float = 0.0,
    horyzont: float = HORYZONT_MIES,
    krok: float = KROK_MIES,
    indeksacja_przyszla: float = INDEKSACJA_PRZYSZLA,
) -> KrzywaNajmu:
    """S(u) od dnia oceny dla jednego najmu. X0: jeden wiersz cech po `model.macierz` (bieżący okres).

    minelo: miesiące bieżącego okresu przed dniem oceny (0, gdy okres zaczyna się później: wtedy `opoznienie` to
    miesiące do jego początku, w których najem na pewno trwa, bo umowa jest podpisana)."""
    L0 = float(miesiecy_umowy)
    e = min(float(minelo), L0 - krok)
    u = np.arange(0.0, horyzont + krok / 2, krok)
    S = np.ones_like(u)

    def przezycie(X: pd.DataFrame, t) -> np.ndarray:
        return np.exp(-model.skumulowany_hazard(X, t)[0])

    S_e = przezycie(X0, [e])[0]
    koniec = opoznienie + (L0 - e)
    maska = (u >= opoznienie) & (u <= koniec)
    S[maska] = przezycie(X0, e + (u[maska] - opoznienie)) / S_e
    P = przezycie(X0, [L0])[0] / S_e
    p_konca = 1.0 - P
    staz0, k = float(X0["staz_lat"].iloc[0]), 1
    while koniec < horyzont:
        Xk = X0.copy()
        Xk["staz_lat"] = staz0 + (L0 + DLUGOSC_PRZEDLUZENIA * (k - 1)) / 12
        Xk["indeksacja_powyzej_6"] = indeksacja_przyszla
        if "miesiecy_umowy" in Xk:
            Xk["miesiecy_umowy"] = DLUGOSC_PRZEDLUZENIA
        maska = (u > koniec) & (u <= koniec + DLUGOSC_PRZEDLUZENIA)
        S[maska] = P * przezycie(Xk, u[maska] - koniec)
        P *= przezycie(Xk, [DLUGOSC_PRZEDLUZENIA])[0]
        koniec += DLUGOSC_PRZEDLUZENIA
        k += 1
    return KrzywaNajmu(czasy=u, przezycie=S, p_konca_biezacego_okresu=float(p_konca))


def krzywa_od_dnia_oceny(
    model: ModelCox, X0: pd.DataFrame, data_od: date, miesiecy_umowy: float, dzien_oceny: date
) -> tuple[KrzywaNajmu, float]:
    """Krzywa S(u) od dnia oceny dla bieżącego okresu zaczętego `data_od` i miesiące okresu przed dniem oceny."""
    jutro = dzien_oceny + timedelta(days=1)
    if data_od > dzien_oceny:
        minelo, opoznienie = 0.0, miesiace_kalendarzowe(jutro, data_od)
    else:
        minelo, opoznienie = miesiace_kalendarzowe(data_od, jutro), 0.0
    return krzywa_pozostala(model, X0, miesiecy_umowy, minelo, opoznienie), minelo


def ryzyko_okresow(
    con: duckdb.DuckDBPyConnection, okresy: pd.DataFrame, model: ModelCox, dzien_oceny: date = DZIEN_OCENY
) -> pd.DataFrame:
    """Wsadowo to samo co `ryzyko_najmu` (bez części `oferta`) dla bieżących okresów z `okresy_umow`.

    Kolumny: id_umowy, ryzyko (= P(koniec najmu w bieżącym okresie) od dnia oceny), ryzyko_12_od_poczatku_okresu,
    przezycie_12_mies, mediana_do_odejscia_mies (NaN = powyżej horyzontu 60 mies.), rmst60_mies."""
    cechy = cechy_okresow(con, okresy).drop(columns=["linia", "miesiecy_umowy", "nr_okresu"])
    wiersze = okresy.merge(cechy, on="id_umowy", how="left", validate="1:1").reset_index(drop=True)
    if wiersze.empty:
        return pd.DataFrame(columns=KOLUMNY_RYZYKA_OKRESOW)
    X = model.macierz(wiersze).reset_index(drop=True)
    ryzyko_12 = model.ryzyko(wiersze)
    wyniki = []
    for i, w in wiersze.iterrows():
        krzywa, _ = krzywa_od_dnia_oceny(
            model, X.iloc[[i]], pd.Timestamp(w["data_od"]).date(), float(w["miesiecy_umowy"]), dzien_oceny
        )
        mediana = krzywa.mediana()
        wyniki.append(
            {
                "id_umowy": str(w["id_umowy"]),
                "ryzyko": krzywa.p_konca_biezacego_okresu,
                "ryzyko_12_od_poczatku_okresu": float(ryzyko_12[i]),
                "przezycie_12_mies": krzywa.przezycie_po(12),
                "mediana_do_odejscia_mies": np.nan if mediana is None else round(mediana, 2),
                "rmst60_mies": round(krzywa.rmst(HORYZONT_MIES), 2),
            }
        )
    return pd.DataFrame(wyniki, columns=KOLUMNY_RYZYKA_OKRESOW)


KOLUMNY_RYZYKA_OKRESOW = [
    "id_umowy",
    "ryzyko",
    "ryzyko_12_od_poczatku_okresu",
    "przezycie_12_mies",
    "mediana_do_odejscia_mies",
    "rmst60_mies",
]


SQL_NAJEM = """
SELECT id_najmu, linia, data_wprowadzenia::DATE AS od, data_wyprowadzenia::DATE AS do
FROM pms_najmy
WHERE id_najmu = ?
"""


def wczytaj_model(sciezka: Path = SCIEZKA_MODELU) -> ModelCox:
    model = joblib.load(sciezka)
    if not isinstance(model, ModelCox):
        raise TypeError(f"{sciezka} nie zawiera modelu v2_przezycie_cox")
    return model


def ryzyko_najmu(
    con: duckdb.DuckDBPyConnection,
    id_najmu: str,
    model: ModelCox,
    dzien_oceny: date = DZIEN_OCENY,
    model_uplift: ModelUpliftT | None = None,
) -> dict:
    """Ryzyko, mediana czasu do odejścia i RMST60 dla aktywnego najmu B2C / B2B (słownik pól OdpowiedzRyzyka);
    z `model_uplift` także oferta: uplift, EV i zalecana akcja (oferta_najmu.py)."""
    najem = con.execute(SQL_NAJEM, [id_najmu]).fetchone()
    if najem is None:
        raise NajemNieznany(f"Brak najmu {id_najmu} w PMS")
    _, linia, _, wyprowadzka = najem
    if linia not in ("B2C", "B2B"):
        raise NajemPozaModelem(f"Najem {id_najmu} to linia {linia}: model obejmuje tylko umowy roczne B2C i B2B")
    if wyprowadzka is not None and wyprowadzka <= dzien_oceny:
        raise NajemZakonczony(f"Najem {id_najmu} zakończył się {wyprowadzka}")

    okresy = okresy_umow(con, "2100-12-31")  # także przedłużenia podpisane na okres po dniu oceny
    okresy = okresy[okresy["id_najmu"] == id_najmu].reset_index(drop=True)
    biezacy = okresy.loc[[okresy["nr_okresu"].idxmax()]].reset_index(drop=True)
    cechy = cechy_okresow(con, biezacy).drop(columns=["linia", "miesiecy_umowy", "nr_okresu"])
    wiersz = biezacy.merge(cechy, on="id_umowy", how="left", validate="1:1")
    X0 = model.macierz(wiersz)

    data_od = pd.Timestamp(wiersz["data_od"].iloc[0]).date()
    krzywa, minelo = krzywa_od_dnia_oceny(model, X0, data_od, float(wiersz["miesiecy_umowy"].iloc[0]), dzien_oceny)
    mediana = krzywa.mediana()
    return {
        "id_najmu": id_najmu,
        "linia": linia,
        "dzien_oceny": dzien_oceny,
        "wersja_modelu": model.wersja,
        "okres": {
            "id_umowy": str(wiersz["id_umowy"].iloc[0]),
            "nr_okresu": int(wiersz["nr_okresu"].iloc[0]),
            "data_od": data_od,
            "data_do": pd.Timestamp(wiersz["data_do"].iloc[0]).date(),
            "miesiecy_umowy": int(wiersz["miesiecy_umowy"].iloc[0]),
            "minelo_miesiecy": round(minelo, 2),
        },
        "ryzyko_12_od_poczatku_okresu": float(model.ryzyko(wiersz)[0]),
        "p_konca_w_biezacym_okresie": krzywa.p_konca_biezacego_okresu,
        "przezycie_12_mies": krzywa.przezycie_po(12),
        "przezycie_24_mies": krzywa.przezycie_po(24),
        "mediana_do_odejscia_mies": None if mediana is None else round(mediana, 2),
        "mediana_powyzej_horyzontu": mediana is None,
        "rmst60_mies": round(krzywa.rmst(HORYZONT_MIES), 2),
        "horyzont_mies": HORYZONT_MIES,
        "zalozenia": list(ZALOZENIA_KRZYWEJ),
        "oferta": None if model_uplift is None else oferta_najmu(con, biezacy, model_uplift, dzien_oceny),
    }
