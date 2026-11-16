"""Reguła alarmu o awariach wind (punkt pracy modelu; wyniki: docs/b4_punkt_pracy.md).

Reguła (`wybierz_alarmy`): w dzień alarmu (`dzien_alarmu`, poniedziałek) o 06:00 Europe/Warsaw alarm dostaje
`alarmy_na_tydzien` wind o najwyższym ryzyku (remis: id_windy rosnąco). Winda z alarmem w dniu t nie dostaje
kolejnego w dniach t+1 … t+`przerwa_dni` (przy 7 dniach: nie w następny poniedziałek). Winda bez wiersza
w danym dniu (w `dni_wind`: stoi o 06:00 z powodu awarii) nie dostaje alarmu. Stałe: zalozenia.yaml (od użytkownika).

Ocena (`ocen_alarmy`): alarm jest trafny, gdy start awarii tej windy wypada w (06:00 t; 06:00 t+7] — to samo okno
co `dni_wind.awaria_7d` (docs/b4_target.md). Czułość liczymy na awariach (nie na dniach): awaria ze startem
w (06:00 pierwszego poniedziałku; 06:00 tydzień po ostatnim] jest złapana, gdy jej start wypada w oknie alarmu
tej samej windy. „Z sygnałem” = podzespół drzwi, napęd, hamulec/liny, sterownik (bez `zewnetrzna` i `brak`).
Wyprzedzenie = godziny od alarmu (06:00) do startu pierwszej awarii w oknie, tylko dla trafnych alarmów.
"""

from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

PLIK_ZALOZEN = Path(__file__).with_name("zalozenia.yaml")
STREFA = "Europe/Warsaw"
GODZINA_ALARMU = 6
OKNO = pd.Timedelta(days=7)
PODZESPOLY_Z_SYGNALEM = ("drzwi", "naped", "hamulec_liny", "sterownik")


def wczytaj_zalozenia(plik: Path = PLIK_ZALOZEN) -> dict[str, int]:
    """{nazwa: wartosc} z zalozenia.yaml; brak wartości = błąd (liczby tylko od użytkownika)."""
    z = yaml.safe_load(plik.read_text(encoding="utf-8"))
    wyj = {k: v["wartosc"] for k, v in z.items()}
    brak = [k for k, v in wyj.items() if v is None]
    if brak:
        raise ValueError(f"maintenance_bc/zalozenia.yaml: brak wartości {', '.join(brak)}")
    return wyj


def moment(dzien: pd.Timestamp) -> pd.Timestamp:
    """06:00 czasu Warszawy w danym dniu jako moment (TIMESTAMPTZ); zmiana czasu jest o 02:00–03:00."""
    return (pd.Timestamp(dzien).normalize() + pd.Timedelta(hours=GODZINA_ALARMU)).tz_localize(STREFA)


def wybierz_alarmy(ryzyko: pd.DataFrame, limit: int, przerwa_dni: int, dzien_alarmu: int = 0) -> pd.DataFrame:
    """ryzyko: kolumny id_windy, dzien, ryzyko (wiersz = winda × dzień oceny o 06:00).
    Zwraca alarmy: dzien, pozycja (1 = najwyższe ryzyko), id_windy, ryzyko."""
    r = ryzyko[["id_windy", "dzien", "ryzyko"]].copy()
    r["dzien"] = pd.to_datetime(r["dzien"]).dt.normalize()
    r = r[r["dzien"].dt.day_of_week == dzien_alarmu]
    ostatni: dict[str, pd.Timestamp] = {}
    wyj = []
    for dzien, grupa in r.groupby("dzien", sort=True):
        granica = dzien - pd.Timedelta(days=przerwa_dni)
        wolne = grupa[[not (w in ostatni and ostatni[w] >= granica) for w in grupa["id_windy"]]]
        wybrane = wolne.sort_values(["ryzyko", "id_windy"], ascending=[False, True]).head(limit)
        for poz, (w, ryz) in enumerate(zip(wybrane["id_windy"], wybrane["ryzyko"], strict=True), start=1):
            ostatni[w] = dzien
            wyj.append((dzien, poz, w, float(ryz)))
    return pd.DataFrame(wyj, columns=["dzien", "pozycja", "id_windy", "ryzyko"])


def ocen_alarmy(alarmy: pd.DataFrame, awarie: pd.DataFrame, poniedzialki: Sequence[pd.Timestamp]) -> dict:
    """alarmy: wynik `wybierz_alarmy`; awarie: id_awarii, id_windy, podzespol, start_tz (moment startu);
    poniedzialki: wszystkie dni alarmu w okresie (także bez alarmu), wyznaczają tygodnie i zakres czułości.
    Zwraca {"alarmy": alarm × wynik, "awarie": awaria × złapana, "tygodnie": tydzień × liczby, "ogolem": dict}."""
    tygodnie = pd.DataFrame({"tydzien": sorted(pd.to_datetime(list(poniedzialki)).normalize())})
    tygodnie["od"] = [moment(d) for d in tygodnie["tydzien"]]
    tygodnie["do"] = [moment(d + OKNO) for d in tygodnie["tydzien"]]

    aw = awarie[["id_awarii", "id_windy", "podzespol", "start_tz"]].copy()
    aw["start_tz"] = pd.to_datetime(aw["start_tz"]).dt.tz_convert(STREFA)
    aw["sygnal"] = aw["podzespol"].isin(PODZESPOLY_Z_SYGNALEM)
    zakres_od, zakres_do = tygodnie["od"].min(), tygodnie["do"].max()
    aw = aw[(aw["start_tz"] > zakres_od) & (aw["start_tz"] <= zakres_do)].copy()
    # tydzień awarii = poniedziałek, w którego oknie (06:00; 06:00 + 7 dni] wypada start
    aw["tydzien"] = [
        tygodnie.loc[(tygodnie["od"] < s) & (s <= tygodnie["do"]), "tydzien"].iloc[0] for s in aw["start_tz"]
    ]

    al = alarmy.copy()
    al["dzien"] = pd.to_datetime(al["dzien"]).dt.normalize()
    al["od"] = [moment(d) for d in al["dzien"]]
    al["do"] = [moment(d + OKNO) for d in al["dzien"]]
    para = al.reset_index(names="nr_alarmu").merge(aw, on="id_windy", how="inner", suffixes=("", "_awarii"))
    para = para[(para["start_tz"] > para["od"]) & (para["start_tz"] <= para["do"])]
    pierwsza = para.sort_values("start_tz").groupby("nr_alarmu").first()
    al["trafny"] = al.index.isin(pierwsza.index)
    al["podzespol"] = pierwsza["podzespol"].reindex(al.index)
    al["wyprzedzenie_h"] = ((pierwsza["start_tz"] - pierwsza["od"]).dt.total_seconds() / 3600).reindex(al.index)
    aw["zlapana"] = aw["id_awarii"].isin(set(para["id_awarii"]))

    tyg = tygodnie[["tydzien"]].set_index("tydzien")
    tyg["alarmy"] = al.groupby("dzien").size()
    tyg["trafne"] = al.groupby("dzien")["trafny"].sum()
    tyg["awarie"] = aw.groupby("tydzien").size()
    tyg["zlapane"] = aw.groupby("tydzien")["zlapana"].sum()
    tyg["awarie_sygnal"] = aw[aw["sygnal"]].groupby("tydzien").size()
    tyg["zlapane_sygnal"] = aw[aw["sygnal"]].groupby("tydzien")["zlapana"].sum()
    tyg = tyg.fillna(0).astype(int).reset_index()

    return {"alarmy": al, "awarie": aw, "tygodnie": tyg, "ogolem": podsumuj(tyg, al["wyprzedzenie_h"])}


def podsumuj(tyg: pd.DataFrame, wyprzedzenie_h: pd.Series) -> dict:
    s = tyg[["alarmy", "trafne", "awarie", "zlapane", "awarie_sygnal", "zlapane_sygnal"]].sum()
    w = wyprzedzenie_h.dropna()
    return {
        **{k: int(v) for k, v in s.items()},
        "precyzja": s["trafne"] / s["alarmy"] if s["alarmy"] else np.nan,
        "czulosc": s["zlapane"] / s["awarie"] if s["awarie"] else np.nan,
        "czulosc_sygnal": s["zlapane_sygnal"] / s["awarie_sygnal"] if s["awarie_sygnal"] else np.nan,
        "mediana_wyprzedzenia_h": float(w.median()) if len(w) else np.nan,
    }
