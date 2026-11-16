"""Zadanie `cechy-wind` (Inngest codziennie o 05:50 Europe/Warsaw): cechy modelu wind na dzień oceny.

Te same pliki SQL i funkcje co trening (features/windy/cechy.py: `cechy_dnia`, tsfresh_cechy.py:
`cechy_tsfresh_dnia`), tylko dla jednego dnia i ze źródła = eksport data/ + okna dopisane przez zadanie
`telemetra-okna` (adapters/telemetra.py, widok `telemetra_windy_biezaca`). Odcięcie: okno kończące się o 05:50
(cechy.ODCIECIE). Wariant okien serwisowych (`bez_serwisu`) bierzemy z aktywnej wersji modelu (current.yaml).

Kroki (ctx.step.run):
1. `parametry`: dzień oceny (z wywołania albo dziś w Europe/Warsaw) i plik wyniku
   `windy_dzienne/<dzien>/cechy.parquet` (poza gitem; ponowny przebieg go zastępuje).
2. `kompletnosc`: ile wind z serwis_windy ma okno kończące się o 05:50. Gdy części brakuje, jest dzień oceny
   i nie minęło jeszcze `CZEKAJ_DO` po odcięciu, krok zgłasza RetryAfterError (Inngest ponowi go za
   `PONOW_PO`), bo okno 05:40–05:50 mogło jeszcze nie przyjść (zadanie `telemetra-okna` też rusza o 05:50).
   Po tym czasie liczymy cechy z tym, co jest, a liczba wind bez okna trafia do wyniku.
3. `cechy`: cechy ręczne + tsfresh + stan telemetrii windy (ostatnie okno przed odcięciem, liczba okien z 24 h,
   tryb ostatniego okna, `stoi` = tryb `wylaczona` o 05:50) -> plik Parquet.
`CZEKAJ_DO` i `PONOW_PO` to parametry techniczne przyjęte w tej pracy (nie z danych).

Ręcznie: `cd api && poetry run python -m api.contexts_boundaries.maintenance_bc.cechy_dzienne [RRRR-MM-DD]`.
"""

import json
import sys
from collections.abc import Callable
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import inngest
import pandas as pd
from api.adapters import telemetra
from api.adapters.duckdb_baza import KATALOG_REPO, SCIEZKA_BAZY, polaczenie
from api.ai.failure_model.base import wczytaj_obecny
from api.ai.features.windy.cechy import ODCIECIE, cechy_dnia, odciecie_s
from api.ai.features.windy.tsfresh_cechy import cechy_tsfresh_dnia

STREFA = ZoneInfo("Europe/Warsaw")
KATALOG_DZIENNY = KATALOG_REPO / "windy_dzienne"
CZEKAJ_DO = timedelta(minutes=8)
PONOW_PO = timedelta(minutes=1)

Krok = Callable[..., Any]


def dzis() -> date:
    return datetime.now(STREFA).date()


def plik_cech(dzien: str, katalog_bazowy: Path | str = KATALOG_DZIENNY) -> Path:
    return Path(katalog_bazowy) / dzien / "cechy.parquet"


def moment_odciecia(dzien: date) -> datetime:
    return datetime.fromtimestamp(odciecie_s(dzien), tz=STREFA)


def stan_telemetrii(con, dzien: date, zrodlo: str) -> pd.DataFrame:
    """Winda (z serwis_windy) × stan okien przed odcięciem: ostatnie_okno, okna_24h, tryb_ostatniego, okno_odciecia."""
    odciecie = odciecie_s(dzien)
    return con.execute(
        f"""
        WITH t AS (
            SELECT id_windy, ts_utc, tryb
            FROM {zrodlo}
            WHERE ts_utc > to_timestamp(? - 86400) AND ts_utc <= to_timestamp(?)
        )
        SELECT
            w.id_windy,
            max(t.ts_utc) AS ostatnie_okno,
            count(t.ts_utc) AS okna_24h,
            arg_max(t.tryb, t.ts_utc) AS tryb_ostatniego,
            coalesce(bool_or(t.ts_utc = to_timestamp(?)), false) AS okno_odciecia
        FROM serwis_windy AS w
        LEFT JOIN t USING (id_windy)
        GROUP BY w.id_windy
        ORDER BY w.id_windy
        """,
        [odciecie, odciecie, odciecie],
    ).df()


def krok_parametry(dzien: str | None, katalog_bazowy: str) -> dict:
    d = date.fromisoformat(dzien) if dzien else dzis()
    return {
        "dzien": d.isoformat(),
        "odciecie": moment_odciecia(d).isoformat(),
        "plik": str(plik_cech(d.isoformat(), katalog_bazowy)),
    }


def krok_kompletnosc(
    dzien: str, katalog_magazynu: str | None, sciezka: Path = SCIEZKA_BAZY, teraz: str | None = None
) -> dict:
    d = date.fromisoformat(dzien)
    with polaczenie(sciezka=sciezka) as con:
        zrodlo = telemetra.utworz_widok_zrodla(con, telemetra.MagazynTelemetrii(katalog_magazynu))
        stan = stan_telemetrii(con, d, zrodlo)
    brak = stan.loc[~stan["okno_odciecia"], "id_windy"].tolist()
    chwila = pd.Timestamp(teraz).to_pydatetime() if teraz else datetime.now(STREFA)
    if brak and d == chwila.astimezone(STREFA).date() and chwila < moment_odciecia(d) + CZEKAJ_DO:
        raise inngest.RetryAfterError(
            f"{len(brak)} z {len(stan)} wind bez okna {ODCIECIE} dnia {dzien}; czekam na Telemetrę",
            retry_after=PONOW_PO,
        )
    return {"windy": len(stan), "bez_okna_odciecia": len(brak), "przyklady_bez_okna": brak[:10]}


def krok_cechy(dzien: str, plik: str, katalog_magazynu: str | None, sciezka: Path = SCIEZKA_BAZY) -> dict:
    d = date.fromisoformat(dzien)
    bez_serwisu = bool(getattr(wczytaj_obecny(), "bez_serwisu", True))
    with polaczenie(sciezka=sciezka) as con:
        zrodlo = telemetra.utworz_widok_zrodla(con, telemetra.MagazynTelemetrii(katalog_magazynu))
        reczne = cechy_dnia(con, d, zrodlo=zrodlo, bez_serwisu=bez_serwisu)
        ts = cechy_tsfresh_dnia(con, d, zrodlo=zrodlo, bez_serwisu=bez_serwisu)
        stan = stan_telemetrii(con, d, zrodlo)
    df = (
        stan.merge(reczne, on="id_windy", how="inner", validate="1:1")
        .merge(ts.drop(columns="dzien"), on="id_windy", how="left", validate="1:1")
        .assign(stoi=lambda x: x["tryb_ostatniego"].eq("wylaczona"), bez_serwisu=bez_serwisu)
    )
    Path(plik).parent.mkdir(parents=True, exist_ok=True)
    tymczasowy = Path(plik).with_suffix(".tmp")
    df.to_parquet(tymczasowy, index=False)
    tymczasowy.replace(plik)
    return {
        "windy": len(df),
        "kolumny": df.shape[1],
        "stoi": int(df["stoi"].sum()),
        "bez_okna_odciecia": int((~df["okno_odciecia"]).sum()),
        "bez_serwisu": bez_serwisu,
    }


def wykonaj_cechy_wind(
    krok: Krok,
    dzien: str | None = None,
    katalog_magazynu: str | None = None,
    sciezka: Path = SCIEZKA_BAZY,
    katalog_bazowy: Path = KATALOG_DZIENNY,
) -> dict:
    """Kolejność kroków; `krok(id, handler, *args)` = ctx.step.run w Inngest (w testach i CLI: wywołanie wprost)."""
    par = krok("parametry", krok_parametry, dzien, str(katalog_bazowy))
    kompletnosc = krok("kompletnosc", krok_kompletnosc, par["dzien"], katalog_magazynu, sciezka)
    cechy = krok("cechy", krok_cechy, par["dzien"], par["plik"], katalog_magazynu, sciezka)
    return {"parametry": par, "kompletnosc": kompletnosc, "cechy": cechy}


def _krok_wprost(id_kroku: str, handler: Callable, *args):
    wynik = handler(*args)
    print(f"[{id_kroku}] {json.dumps(wynik, ensure_ascii=False, default=str)}", flush=True)
    return wynik


if __name__ == "__main__":
    argumenty = [a for a in sys.argv[1:] if a]
    wykonaj_cechy_wind(_krok_wprost, argumenty[0] if argumenty else None)
