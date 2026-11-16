"""Zadanie `ryzyko-wind` (Inngest codziennie o 06:00 Europe/Warsaw): ryzyko awarii każdej windy, reguła alarmu
i zgłoszenia alarmów w Serwisowniku.

Kroki (ctx.step.run):
1. `parametry`: dzień oceny (z wywołania albo dziś w Europe/Warsaw), katalog przebiegu
   `windy_dzienne/<dzien>/<id_przebiegu>/` (poza gitem), plik cech z zadania `cechy-wind`.
2. `ryzyko`: aktywna wersja z failure_model/current.yaml (`base.wczytaj_obecny()`): `predict` = wynik rankingu,
   `prawdopodobienstwo` = P(awaria w 7 dni) (gdy wersja je ma), `explain` -> 3 najsilniejsze sygnały i podejrzane
   podzespoły (maintenance_bc/wyjasnienie.py). Brak pliku cech: RetryAfterError do `CZEKAJ_NA_CECHY` po 06:00 dnia
   oceny (zadanie `cechy-wind` mogło jeszcze czekać na okna), potem błąd.
3. `zapis-ryzyka`: tabela ryzyko_wind (zastępuje dzień).
4. `alarmy`: reguła alarmu maintenance_bc/alarmy_wind.wybierz_alarmy ze stałymi z zalozenia.yaml (poniedziałek,
   3 windy o najwyższym `predict`, przerwa 7 dni liczona także z alarmów zapisanych wcześniej w alarmy_wind). Windy,
   które o 05:50 stoją (`tryb = 'wylaczona'`), alarmu nie dostają — w treningu taki dzień nie ma wiersza w dni_wind
   (docs/b4_ryzyko_dzienne.md). Zapis w alarmy_wind; pierwsza decyzja dnia zostaje (adapters/ryzyko_wind.py).
5. `serwisownik-<id_windy>`: osobny krok na każdy alarm — zgłoszenie w Serwisowniku (adapters/serwisownik.py,
   idempotentne po windzie i dniu), potem `id_zgloszenia` w alarmy_wind.

Ręcznie: `cd api && poetry run python -m api.contexts_boundaries.maintenance_bc.ryzyko_dzienne [RRRR-MM-DD]`
(wymaga atrapy Serwisownika `pypyr serwisownik_mock` albo SERWISOWNIK_URL, gdy dzień jest dniem alarmu).
"""

import json
import sys
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import inngest
import numpy as np
import pandas as pd
from api.adapters import ryzyko_wind, serwisownik
from api.adapters.duckdb_baza import SCIEZKA_BAZY, polaczenie
from api.ai.failure_model.base import wczytaj_obecny
from api.contexts_boundaries.maintenance_bc import alarmy_wind
from api.contexts_boundaries.maintenance_bc.cechy_dzienne import KATALOG_DZIENNY, STREFA, dzis, plik_cech
from api.contexts_boundaries.maintenance_bc.wyjasnienie import wyjasnij_ramke

CZEKAJ_NA_CECHY = timedelta(minutes=30)
PONOW_PO = timedelta(minutes=2)

Krok = Callable[..., Any]


class BrakCech(RuntimeError):
    """Nie ma pliku cech dnia (zadanie cechy-wind nie przeszło)."""


def moment_oceny(dzien: date) -> pd.Timestamp:
    return alarmy_wind.moment(pd.Timestamp(dzien))


def _plik(katalog: str, nazwa: str) -> Path:
    return Path(katalog) / f"{nazwa}.parquet"


def krok_parametry(dzien: str | None, id_przebiegu: str, katalog_bazowy: str) -> dict:
    d = date.fromisoformat(dzien) if dzien else dzis()
    katalog = Path(katalog_bazowy) / d.isoformat() / id_przebiegu
    katalog.mkdir(parents=True, exist_ok=True)
    return {
        "dzien": d.isoformat(),
        "moment_oceny": moment_oceny(d).isoformat(),
        "katalog": str(katalog),
        "plik_cech": str(plik_cech(d.isoformat(), katalog_bazowy)),
        "id_przebiegu": id_przebiegu,
    }


def ocen(model, cechy: pd.DataFrame) -> pd.DataFrame:
    """Wynik, P(awaria 7 dni), ranga i wyjaśnienie dla wierszy cech (logika bez plików)."""
    model.sprawdz_kolumny(cechy)
    wynik = np.asarray(model.predict(cechy), dtype=float)
    p = np.asarray(model.prawdopodobienstwo(cechy), dtype=float) if hasattr(model, "prawdopodobienstwo") else None
    wyj = wyjasnij_ramke(cechy, model.explain(cechy), cechy["okna_24h"])
    df = cechy[["id_windy", "dzien", "stoi", "ostatnie_okno", "okna_24h"]].copy()
    df["wynik"] = wynik.round(8)
    df["p_awarii_7d"] = p.round(6) if p is not None else np.nan
    # remis: id_windy rosnąco (jak w regule alarmu)
    df = df.sort_values(["wynik", "id_windy"], ascending=[False, True], kind="mergesort").reset_index(drop=True)
    df["ranga"] = np.arange(1, len(df) + 1)
    kolejnosc = {w: i for i, w in enumerate(cechy["id_windy"])}
    df["sygnaly"] = [json.dumps(wyj[kolejnosc[w]]["sygnaly"], ensure_ascii=False) for w in df["id_windy"]]
    df["podzespoly"] = [json.dumps(wyj[kolejnosc[w]]["podzespoly"], ensure_ascii=False) for w in df["id_windy"]]
    df["opis"] = [wyj[kolejnosc[w]]["opis"] for w in df["id_windy"]]
    return df


def krok_ryzyko(katalog: str, dzien: str, plik_cech_dnia: str, teraz: str | None = None) -> dict:
    d = date.fromisoformat(dzien)
    if not Path(plik_cech_dnia).exists():
        chwila = pd.Timestamp(teraz).to_pydatetime() if teraz else datetime.now(STREFA)
        if d == chwila.astimezone(STREFA).date() and chwila < moment_oceny(d).to_pydatetime() + CZEKAJ_NA_CECHY:
            raise inngest.RetryAfterError(f"Brak cech dnia {dzien} (zadanie cechy-wind)", retry_after=PONOW_PO)
        raise BrakCech(f"Brak cech dnia {dzien}: {plik_cech_dnia} (uruchom zadanie cechy-wind)")
    model = wczytaj_obecny()
    cechy = pd.read_parquet(plik_cech_dnia)
    if bool(cechy["bez_serwisu"].iloc[0]) != bool(getattr(model, "bez_serwisu", True)):
        raise BrakCech(f"Cechy dnia {dzien} liczone w innym wariancie okien serwisowych niż model {model.wersja}")
    df = ocen(model, cechy)
    df["moment_oceny"] = moment_oceny(d)
    df["wersja_modelu"] = model.wersja
    df.to_parquet(_plik(katalog, "ryzyko"), index=False)
    return {
        "wersja_modelu": model.wersja,
        "windy": len(df),
        "stoi": int(df["stoi"].sum()),
        "najwyzsze": df.head(3)[["id_windy", "wynik", "p_awarii_7d"]].to_dict("records"),
    }


def krok_zapis_ryzyka(katalog: str, dzien: str, id_przebiegu: str, sciezka: Path = SCIEZKA_BAZY) -> dict:
    df = pd.read_parquet(_plik(katalog, "ryzyko")).assign(id_przebiegu=id_przebiegu)
    df["dzien"] = pd.to_datetime(df["dzien"]).dt.date
    with polaczenie(tylko_odczyt=False, sciezka=sciezka) as con:
        n = ryzyko_wind.zapisz_ryzyko(con, date.fromisoformat(dzien), df)
    return {"zapisane": n}


def wybierz_alarmy_dnia(ryzyko: pd.DataFrame, poprzednie: pd.DataFrame, zalozenia: dict) -> pd.DataFrame:
    """Reguła alarmu dla jednego dnia (logika bez bazy): windy, które stoją, nie dostają alarmu."""
    kandydaci = ryzyko.loc[~ryzyko["stoi"].astype(bool)].rename(columns={"wynik": "ryzyko"})
    wybrane = alarmy_wind.wybierz_alarmy(
        kandydaci,
        limit=int(zalozenia["alarmy_na_tydzien"]),
        przerwa_dni=int(zalozenia["przerwa_dni"]),
        dzien_alarmu=int(zalozenia["dzien_alarmu"]),
        poprzednie=poprzednie,
    )
    return wybrane.rename(columns={"ryzyko": "wynik"})


def krok_alarmy(katalog: str, dzien: str, id_przebiegu: str, sciezka: Path = SCIEZKA_BAZY) -> dict:
    d = date.fromisoformat(dzien)
    z = alarmy_wind.wczytaj_zalozenia()
    ryzyko = pd.read_parquet(_plik(katalog, "ryzyko"))
    with polaczenie(tylko_odczyt=False, sciezka=sciezka) as con:
        poprzednie = ryzyko_wind.alarmy(con, d - timedelta(days=int(z["przerwa_dni"])), d - timedelta(days=1))
        wybrane = wybierz_alarmy_dnia(ryzyko, poprzednie, z)
        nowe = wybrane.merge(ryzyko[["id_windy", "p_awarii_7d", "wersja_modelu"]], on="id_windy", how="left")
        nowe = nowe.assign(dzien=d, id_przebiegu=id_przebiegu)
        zapisane, teraz_zapisane = ryzyko_wind.zapisz_alarmy(con, d, nowe)
    wiersze = zapisane.assign(dzien=pd.to_datetime(zapisane["dzien"]).dt.date.astype(str))
    return {
        "dzien_alarmu": bool(pd.Timestamp(d).day_of_week == int(z["dzien_alarmu"])),
        "zapisano_teraz": teraz_zapisane,
        "windy_stoja": int(ryzyko["stoi"].sum()),
        "w_przerwie": sorted(set(poprzednie["id_windy"])) if len(poprzednie) else [],
        "alarmy": wiersze[["dzien", "pozycja", "id_windy", "wynik", "p_awarii_7d", "id_zgloszenia"]]
        .replace({np.nan: None})
        .to_dict("records"),
    }


def zgloszenie_alarmu(alarm: dict, ocena: dict, winda: dict) -> dict:
    """Treść zgłoszenia do Serwisownika (deterministyczna: ten sam alarm = ta sama treść = ten sam klucz).
    `tresc_zgloszenia` = opis alertu jednym zdaniem (wyjasnienie.opis_alertu); szczegóły w `alarm`."""
    return {
        "id_budynku": winda["id_budynku"],
        "id_urzadzenia": alarm["id_windy"],
        "typ_urzadzenia": "winda",
        "zrodlo": "model_awarii",
        "kategoria": "przegląd",
        "priorytet": "normalny",
        "firma_serwisowa": winda["firma_serwisowa"],
        "tresc_zgloszenia": ocena["opis"],
        "alarm": {
            "id_windy": alarm["id_windy"],
            "dzien": alarm["dzien"],
            "pozycja": int(alarm["pozycja"]),
            "wynik": alarm["wynik"],
            "p_awarii_7d": alarm.get("p_awarii_7d"),
            "wersja_modelu": ocena["wersja_modelu"],
            "podejrzane_podzespoly": ocena["podzespoly"],
            "sygnaly": ocena["sygnaly"],
        },
    }


def krok_serwisownik(
    alarm: dict, sciezka: Path = SCIEZKA_BAZY, klient: serwisownik.KlientSerwisownika | None = None
) -> dict:
    d = date.fromisoformat(alarm["dzien"])
    with polaczenie(sciezka=sciezka) as con:
        ocena = ryzyko_wind.ocena_windy(con, alarm["id_windy"], d)
        winda = con.execute(
            "SELECT id_budynku, firma_serwisowa FROM serwis_windy WHERE id_windy = ?", [alarm["id_windy"]]
        ).df()
    if ocena is None or winda.empty:
        raise inngest.NonRetriableError(f"Brak oceny albo windy {alarm['id_windy']} z dnia {alarm['dzien']}")
    odp = (klient or serwisownik.KlientSerwisownika()).zglos_alarm(
        zgloszenie_alarmu(alarm, ocena, winda.iloc[0].to_dict())
    )
    with polaczenie(tylko_odczyt=False, sciezka=sciezka) as con:
        ryzyko_wind.oznacz_wyslany(con, d, alarm["id_windy"], odp["id_zgloszenia"])
    return {"id_windy": alarm["id_windy"], **odp}


def wykonaj_ryzyko_wind(
    krok: Krok,
    id_przebiegu: str,
    dzien: str | None = None,
    sciezka: Path = SCIEZKA_BAZY,
    katalog_bazowy: Path = KATALOG_DZIENNY,
    klient: serwisownik.KlientSerwisownika | None = None,
) -> dict:
    """Kolejność kroków; `krok(id, handler, *args)` = ctx.step.run w Inngest (w testach i CLI: wywołanie wprost)."""
    par = krok("parametry", krok_parametry, dzien, id_przebiegu, str(katalog_bazowy))
    kat, d = par["katalog"], par["dzien"]
    wynik: dict[str, Any] = {"parametry": par}
    wynik["ryzyko"] = krok("ryzyko", krok_ryzyko, kat, d, par["plik_cech"])
    wynik["zapis"] = krok("zapis-ryzyka", krok_zapis_ryzyka, kat, d, id_przebiegu, sciezka)
    wynik["alarmy"] = krok("alarmy", krok_alarmy, kat, d, id_przebiegu, sciezka)
    wynik["serwisownik"] = [
        krok(f"serwisownik-{a['id_windy']}", krok_serwisownik, a, sciezka, *([klient] if klient else []))
        for a in wynik["alarmy"]["alarmy"]
    ]
    return wynik


def _krok_wprost(id_kroku: str, handler: Callable, *args):
    wynik = handler(*args)
    print(f"[{id_kroku}] {json.dumps(wynik, ensure_ascii=False, default=str)}", flush=True)
    return wynik


if __name__ == "__main__":
    argumenty = [a for a in sys.argv[1:] if a]
    przebieg = f"reczny-{datetime.now(timezone.utc):%Y%m%dT%H%M%S%f}"
    wykonaj_ryzyko_wind(_krok_wprost, przebieg, argumenty[0] if argumenty else None)
