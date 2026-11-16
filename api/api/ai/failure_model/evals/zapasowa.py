"""Reguła zapasowa dla wind bez normy (versions/zapasowa_if): sprawdzenie i zapis artefaktu
(docs/b4_dryf_i_fallback.md).

1. B37 i B38 (11 wind Liftar, telemetria od 2024-09-15), dni z mniej niż DNI_BEZ_NORMY dniami telemetrii:
   Isolation Forest uczony na dojrzałych windach tego samego modelu z dni przed 2024-09-15 (bez przecieku czasu);
   wobec modelu v3 na tych samych dniach (UWAGA: 10 z 11 wind było w treningu v3 — wynik v3 jest zawyżony)
   i wobec losowego rankingu (PR-AUC = odsetek dodatnich). Poniedziałki: alarm zapasowy (wynik ≥ próg) i to,
   co dała reguła modelu (3 windy z całej floty, przerwa 7 dni).
2. Symulacja nowej windy poza próbą (test 2026-01-01 – 2026-09-22, wszystkie windy, cechy po korekcie LF-5):
   Isolation Forest uczony na treningu 2023-03 – 2025-06 bez ocenianej windy (każda winda osobno, ten sam model
   windy) wobec v3 z usuniętymi cechami normy (`*_norma`, `*_do_normy_*` = NULL, jak u nowej windy) i v3 z normą.
3. Zapis artefaktu produkcyjnego: Isolation Forest per model windy na treningu 2023-03 – 2025-06 (windy treningu,
   dni dojrzałe), `versions/zapasowa_if/model.joblib` + `metryki.json`.
Uruchomienie: `cd api && poetry run python -m api.ai.failure_model.evals.zapasowa [--zapisz]` (ok. 3–5 min).
"""

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from api.adapters.duckdb_baza import polaczenie
from api.ai.failure_model.base import KATALOG_MODELU, wczytaj_obecny
from api.ai.failure_model.evals.ewaluacja_v2 import TEST, TRENING, ocen, podzial_czas_winda, roznica
from api.ai.failure_model.versions.zapasowa_if.model import DNI_BEZ_NORMY, RegulaZapasowa
from api.ai.features.windy.zbior import wczytaj_zbior
from api.contexts_boundaries.maintenance_bc.alarmy_wind import wczytaj_zalozenia, wybierz_alarmy
from api.contexts_boundaries.maintenance_bc.wyjasnienie import konfiguracja, podzespol_sygnalu

KATALOG = KATALOG_MODELU / "versions" / "zapasowa_if"
NOWE_BUDYNKI = ("B37", "B38")
START_NOWYCH = pd.Timestamp("2024-09-15")


def sygnaly_zapasowe(kolumny) -> list[str]:
    """Sygnały telemetrii ze wskazanym podzespołem (podzespoly.yaml), które mają statystyki okien w cechach."""
    return [s for s in konfiguracja()["sygnaly"] if podzespol_sygnalu(s) and f"{s}_sr_24h" in kolumny]


def udzial_alarmow(con) -> float:
    liczba_wind = con.execute("SELECT count(*) FROM serwis_windy").fetchone()[0]
    return wczytaj_zalozenia()["alarmy_na_tydzien"] / liczba_wind


def wczytaj(tabela_cech: str = "cechy_windy") -> tuple[pd.DataFrame, float]:
    with polaczenie() as con:
        zb, _ = wczytaj_zbior(con, tabela_cech=tabela_cech)
        meta = con.execute("""
            SELECT w.id_windy, w.model AS model_windy, min(t.ts_utc) AS pierwsze_okno
            FROM serwis_windy AS w JOIN telemetra_windy AS t USING (id_windy) GROUP BY ALL""").df()
        cel = con.execute("SELECT id_windy, dzien, podzespol FROM dni_wind").df()
        udzial = udzial_alarmow(con)
    cel["dzien"] = pd.to_datetime(cel["dzien"])
    zb = zb.merge(meta, on="id_windy", how="left", validate="m:1").merge(cel, on=["id_windy", "dzien"], validate="1:1")
    pierwszy_dzien = pd.to_datetime(zb["pierwsze_okno"]).dt.tz_convert("Europe/Warsaw").dt.tz_localize(None)
    zb["dni_telemetrii"] = (zb["dzien"] - pierwszy_dzien.dt.normalize()).dt.days
    return zb, udzial


def b37_b38(zb: pd.DataFrame, udzial: float) -> dict:
    model = wczytaj_obecny()
    nowe = zb["id_windy"].str[:3].isin(NOWE_BUDYNKI)
    modele = sorted(set(zb.loc[nowe, "model_windy"]))
    ucz = zb[~nowe & zb["model_windy"].isin(modele) & (zb["dzien"] < START_NOWYCH)]
    ucz = ucz[ucz["dni_telemetrii"] >= DNI_BEZ_NORMY]
    regula = RegulaZapasowa(sygnaly_zapasowe(zb.columns), udzial).fit(ucz)
    ev = zb[nowe & (zb["dni_telemetrii"] < DNI_BEZ_NORMY)].reset_index(drop=True)
    o = regula.ocen(ev)
    ev = ev.assign(wynik_if=o["wynik"].to_numpy(), alarm_if=o["alarm"].to_numpy(), wynik_v3=model.predict(ev))
    wynik = {
        "uczenie_wiersze": regula.wiersze_,
        "progi": regula.progi_,
        "if": ocen(ev, ev["wynik_if"].to_numpy()),
        "v3_w_probie": ocen(ev, ev["wynik_v3"].to_numpy()),
        "dni_alarmu_if": int(ev["alarm_if"].sum()),
        "dni_alarmu_if_trafne": int((ev["alarm_if"] & (ev["awaria_7d"] == 1)).sum()),
        "awarie": ev.groupby("id_awarii")["podzespol"].first().to_dict(),
        "awarie_z_alarmem_if": sorted(set(ev.loc[ev["alarm_if"] & ev["id_awarii"].notna(), "id_awarii"])),
    }
    # poniedziałki: alarm zapasowy vs reguła modelu na całej flocie (te same dni)
    pon = sorted(d for d in ev["dzien"].unique() if pd.Timestamp(d).day_of_week == 0)
    flota = zb[zb["dzien"].between(pon[0] - pd.Timedelta(days=7), pon[-1])].reset_index(drop=True)
    z = wczytaj_zalozenia()
    al = wybierz_alarmy(
        flota.assign(ryzyko=model.predict(flota)), int(z["alarmy_na_tydzien"]), int(z["przerwa_dni"]), 0
    )
    al = al[al["dzien"].isin(pon)].merge(flota[["id_windy", "dzien", "awaria_7d"]], on=["id_windy", "dzien"])
    al_nowe = al[al["id_windy"].str[:3].isin(NOWE_BUDYNKI)]
    ev_pon = ev[ev["dzien"].isin(pon)]
    wynik["poniedzialki"] = [str(pd.Timestamp(d).date()) for d in pon]
    wynik["pon_if"] = (
        ev_pon.loc[ev_pon["alarm_if"], ["dzien", "id_windy", "awaria_7d", "wynik_if"]].astype(str).to_dict("records")
    )
    wynik["pon_v3_nowe_windy"] = al_nowe[["dzien", "id_windy", "awaria_7d"]].astype(str).to_dict("records")
    wynik["pon_dodatnie_nowe"] = int(ev_pon["awaria_7d"].sum())
    wynik["dni"] = ev[
        ["id_windy", "dzien", "dni_telemetrii", "awaria_7d", "id_awarii", "wynik_if", "alarm_if", "wynik_v3"]
    ]
    return wynik


def symulacja_nowej_windy(zb: pd.DataFrame, udzial: float) -> dict:
    """Test 2026 poza próbą: IF bez ocenianej windy vs v3 bez cech normy vs v3."""
    model = wczytaj_obecny()
    test = zb[zb["dzien"].between(*TEST)].reset_index(drop=True)
    sygnaly = sygnaly_zapasowe(zb.columns)
    ucz_wszystko = zb[zb["dzien"].between(*TRENING) & (zb["dni_telemetrii"] >= DNI_BEZ_NORMY)]
    wynik_if = np.full(len(test), np.nan)
    for w, grupa in test.groupby("id_windy"):
        ucz = ucz_wszystko[
            (ucz_wszystko["model_windy"] == grupa["model_windy"].iloc[0]) & (ucz_wszystko["id_windy"] != w)
        ]
        regula = RegulaZapasowa(sygnaly, udzial).fit(ucz)
        wynik_if[grupa.index] = regula.ocen(grupa)["wynik"].to_numpy()
    bez_normy = test.copy()
    kol_normy = [c for c in model.cechy if c.endswith("_norma") or "_do_normy_" in c]
    bez_normy[kol_normy] = np.nan
    v3_bez = model.predict(bez_normy)
    return {
        "kolumny_normy": len(kol_normy),
        "if_bez_windy": ocen(test, wynik_if),
        "v3_bez_normy": ocen(test, v3_bez),
        "v3_z_norma": ocen(test, model.predict(test)),
        "if_minus_v3_bez_normy": roznica(test, wynik_if, v3_bez),
    }


def zapisz_artefakt(zb: pd.DataFrame, udzial: float) -> dict:
    maski, _ = podzial_czas_winda(zb)
    ucz = zb[maski["trening"] & (zb["dni_telemetrii"] >= DNI_BEZ_NORMY).to_numpy()]
    regula = RegulaZapasowa(sygnaly_zapasowe(zb.columns), udzial).fit(ucz)
    KATALOG.mkdir(parents=True, exist_ok=True)
    joblib.dump(regula, KATALOG / "model.joblib")
    metryki = {
        "wersja": regula.wersja,
        "uczenie": f"trening {TRENING[0]} – {TRENING[1]}, windy treningu v2b, "
        f"dni z >= {DNI_BEZ_NORMY} dniami telemetrii",
        "udzial_alarmow": udzial,
        "sygnaly": list(regula.sygnaly),
        "wiersze": regula.wiersze_,
        "progi": regula.progi_,
    }
    (KATALOG / "metryki.json").write_text(json.dumps(metryki, ensure_ascii=False, indent=1), encoding="utf-8")
    return metryki


def _krotko(m: dict) -> dict:
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in m.items()}


if __name__ == "__main__":
    zb, udzial = wczytaj()
    w = b37_b38(zb, udzial)
    print("udział alarmów", udzial)
    for k in ("uczenie_wiersze", "progi", "dni_alarmu_if", "dni_alarmu_if_trafne", "awarie", "awarie_z_alarmem_if"):
        print(k, w[k])
    print("IF", _krotko(w["if"]))
    print("v3 (w próbie)", _krotko(w["v3_w_probie"]))
    print("poniedziałki", w["poniedzialki"], "dodatnie dni-poniedziałki nowych wind", w["pon_dodatnie_nowe"])
    print("alarmy IF w poniedziałki", w["pon_if"])
    print("alarmy v3 dla nowych wind", w["pon_v3_nowe_windy"])
    w["dni"].to_csv(Path("/tmp") / "b37_b38_zapasowa.csv", index=False)
    zk, _ = wczytaj("cechy_windy_korekta_lf5")
    for k, v in symulacja_nowej_windy(zk, udzial).items():
        print(k, _krotko(v) if isinstance(v, dict) else v)
    if "--zapisz" in sys.argv:
        print(zapisz_artefakt(zb, udzial))
