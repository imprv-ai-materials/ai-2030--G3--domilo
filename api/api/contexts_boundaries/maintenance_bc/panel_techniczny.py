"""Dane tablicy Grafana dla działu technicznego (dev/grafana/, docs/b4_panel_techniczny.md).

Grafana czyta dane wtyczką motherduck-duckdb-datasource 0.4.6 (DuckDB 1.5.6), która nie otwiera domilo.duckdb
(format pliku 2.0), a otwarty plik blokowałby zapis zadaniom. Dlatego panel czyta pliki Parquet z
`dev/grafana/dane/<tabela>.parquet`; źródło danych Grafany to DuckDB w pamięci z widokami `read_parquet` (initSql,
dev/grafana/provisioning/datasources/duckdb.yaml). Plik powstaje obok i podmienia stary jednym `os.replace`.

Tabele (źródło: domilo.duckdb, stan po zadaniu `ryzyko-wind` albo symulacji wstecz `ryzyko_wstecz.py`):
- `windy_ryzyko`: najnowsza ocena każdej windy (ryzyko_wind) z budynkiem, współrzędnymi do mapy i opisem; windy
  budynku rozstawione na okręgu o promieniu `PROMIEN_STOPNIE` wokół punktu budynku (pms_budynki.lat / lon), żeby
  każda była widoczna na mapie;
- `ryzyko_historia`: ryzyko (P awarii w 7 dni) i ranga każdej windy w każdym dniu oceny;
- `sygnaly_30d`: godzinne średnie `LICZBA_SYGNALOW` najważniejszych sygnałów z 30 dni przed odcięciem najnowszego dnia
  oceny (te same pliki SQL rodzin co cechy modelu: features/windy/sql/, bez okien serwisowych, definicja bledy_drzwi
  według current.yaml) + norma windy z cech tego dnia (`<sygnał>_norma`). Najważniejsze = największy udział w
  ważności (gain) modelu bazowego, zsumowany po cechach sygnału (maintenance_bc/wyjasnienie.sygnal_cechy);
- `alerty`: alarmy_wind z opisem, wskazanym podzespołem, wynikiem i oceną koordynatora (alerty_ocena):
  wynik `trafny` = start awarii tej windy (awarie_odtworzone; start z telemetrii albo pierwsze zgłoszenie) w
  (06:00 dnia alarmu; 06:00 + 7 dni], jak `dni_wind.awaria_7d`; `w toku` = okno jeszcze się nie zamknęło względem
  stanu danych o awariach i awarii w nim jeszcze nie ma; inaczej `fałszywy`. Stan danych o awariach = najpóźniejsze
  `serwis_zgloszenia.utworzono` (czas lokalny). `wyprzedzenie_h` = godziny od alarmu do startu awarii (trafne);
- `podsumowanie_8_tyg`: alarmy z ostatnich 8 tygodni (dni alarmu w (ostatni dzień alarmu − 56 dni; ostatni dzień
  alarmu]): liczby wyników, precyzja na zamkniętych oknach, mediana wyprzedzenia w godzinach;
- `panel_info`: kiedy odświeżono, dzień oceny, stan danych, wersja modelu, próg opłacalności wizyty p* (w %, z
  maintenance_bc/zalozenia.yaml: koszt_wizyty / (skutecznosc × koszt_awarii_ponad_planowa), wartosc_alarmow.ekonomia)
  — granica kolorów ryzyka na tablicy (`powyzej_progu` w windy_ryzyko).
Uruchomienie: `pypyr grafana` (dane + Grafana) albo
`cd api && poetry run python -m api.contexts_boundaries.maintenance_bc.panel_techniczny`.
"""

import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from api.adapters import alerty_ocena, ryzyko_wind, telemetra
from api.adapters.duckdb_baza import KATALOG_REPO, SCIEZKA_BAZY, polaczenie
from api.ai.failure_model.base import ustawienia_cech, wczytaj_obecny
from api.ai.features.windy.cechy import RODZINY, odciecie_s, przygotuj, sql_pliku, sygnaly
from api.contexts_boundaries.maintenance_bc.alarmy_wind import wczytaj_zalozenia
from api.contexts_boundaries.maintenance_bc.cechy_dzienne import KATALOG_DZIENNY, plik_cech
from api.contexts_boundaries.maintenance_bc.wartosc_alarmow import ekonomia
from api.contexts_boundaries.maintenance_bc.wyjasnienie import katalog_sygnalow, konfiguracja, sygnal_cechy

STREFA = ZoneInfo("Europe/Warsaw")
KATALOG_PANELU = KATALOG_REPO / "dev" / "grafana" / "dane"
LICZBA_SYGNALOW = 6  # tyle wykresów sygnałów na tablicy (wybór prezentacyjny)
DNI_SYGNALOW = 30
TYGODNIE_PODSUMOWANIA = 8
PROMIEN_STOPNIE = 0.0004  # rozstawienie wind budynku na mapie (ok. 30–45 m; tylko prezentacja)
OKNO_ALARMU = timedelta(days=7)


# --- przekształcenia (bez plików) ------------------------------------------------------------------------------------


def rozstaw_windy(df: pd.DataFrame) -> pd.DataFrame:
    """lat / lon każdej windy: punkty na okręgu wokół budynku (jedna winda = punkt budynku)."""
    df = df.sort_values(["id_budynku", "id_windy"]).reset_index(drop=True)
    nr = df.groupby("id_budynku").cumcount()
    n = df.groupby("id_budynku")["id_windy"].transform("count")
    kat = 2 * np.pi * nr / n
    promien = np.where(n > 1, PROMIEN_STOPNIE, 0.0)
    df["lat_windy"] = df["lat"] + promien * np.sin(kat)
    df["lon_windy"] = df["lon"] + promien * np.cos(kat) / np.cos(np.radians(df["lat"]))
    return df


def wyniki_alertow(alarmy: pd.DataFrame, awarie: pd.DataFrame, stan_danych: pd.Timestamp) -> pd.DataFrame:
    """alarmy: dzien, id_windy (+ inne); awarie: id_awarii, id_windy, podzespol, start_tz (moment).
    Dodaje: moment_alarmu, koniec_okna, wynik (trafny / fałszywy / w toku), id_awarii, podzespol_awarii,
    wyprzedzenie_h."""
    al = alarmy.copy()
    al["moment_alarmu"] = [
        pd.Timestamp(d).normalize().tz_localize(None).tz_localize(STREFA) + pd.Timedelta(hours=6) for d in al["dzien"]
    ]
    al["koniec_okna"] = [
        (pd.Timestamp(d).normalize() + OKNO_ALARMU).tz_localize(STREFA) + pd.Timedelta(hours=6) for d in al["dzien"]
    ]
    aw = awarie.copy()
    aw["start_tz"] = pd.to_datetime(aw["start_tz"]).dt.tz_convert(STREFA)
    para = al.reset_index(names="_nr").merge(aw, on="id_windy", how="inner")
    para = para[(para["start_tz"] > para["moment_alarmu"]) & (para["start_tz"] <= para["koniec_okna"])]
    pierwsza = para.sort_values("start_tz").groupby("_nr").first()
    al["id_awarii"] = pierwsza["id_awarii"].reindex(al.index)
    al["podzespol_awarii"] = pierwsza["podzespol"].reindex(al.index)
    start = pierwsza["start_tz"].reindex(al.index)
    al["wyprzedzenie_h"] = [
        (s.timestamp() - m.timestamp()) / 3600 if pd.notna(s) else np.nan for s, m in zip(start, al["moment_alarmu"])
    ]
    zamkniete = al["koniec_okna"] <= stan_danych
    al["wynik"] = np.where(al["id_awarii"].notna(), "trafny", np.where(zamkniete, "fałszywy", "w toku"))
    return al


def podsumowanie(alerty: pd.DataFrame, tygodnie: int = TYGODNIE_PODSUMOWANIA) -> pd.DataFrame:
    """Jeden wiersz: alarmy z ostatnich `tygodnie` tygodni (względem ostatniego dnia alarmu)."""
    if alerty.empty:
        return pd.DataFrame([{"alarmy": 0}])
    do = pd.Timestamp(max(alerty["dzien"]))
    od = do - pd.Timedelta(weeks=tygodnie)
    a = alerty[pd.to_datetime(alerty["dzien"]) > od]
    trafne, falszywe = int((a["wynik"] == "trafny").sum()), int((a["wynik"] == "fałszywy").sum())
    w = a.loc[a["wynik"] == "trafny", "wyprzedzenie_h"].dropna()
    oceny = a["ocena_koordynatora"].notna()
    return pd.DataFrame(
        [
            {
                "od_dnia": (od + pd.Timedelta(days=1)).date(),
                "do_dnia": do.date(),
                "alarmy": len(a),
                "trafne": trafne,
                "falszywe": falszywe,
                "w_toku": int((a["wynik"] == "w toku").sum()),
                "precyzja_zamkniete": trafne / (trafne + falszywe) if trafne + falszywe else np.nan,
                "mediana_wyprzedzenia_h": float(w.median()) if len(w) else np.nan,
                "trafne_z_wyprzedzeniem": len(w),
                "ocenione_przez_koordynatora": int(oceny.sum()),
                "ocena_zgodna_z_wynikiem": int(
                    (
                        oceny
                        & (
                            ((a["ocena_koordynatora"] == "trafny") & (a["wynik"] == "trafny"))
                            | ((a["ocena_koordynatora"] == "falszywy") & (a["wynik"] == "fałszywy"))
                        )
                    ).sum()
                ),
            }
        ]
    )


def najwazniejsze_sygnaly(model, n: int = LICZBA_SYGNALOW) -> list[str]:
    """Sygnały telemetrii (ze statystykami okien) o największym łącznym udziale w ważności (gain) modelu."""
    bazowy = getattr(model, "model_bazowy", model)
    w = bazowy.waznosc_cech()
    w["sygnal"] = w["cecha"].map(sygnal_cechy)
    w = w[w["sygnal"].isin(konfiguracja()["sygnaly"]) & w["sygnal"].isin(katalog_sygnalow())]
    w = w[~w["sygnal"].isin(["wibracje_czujnik", "sterownik_firmware"])]
    return list(w.groupby("sygnal")["udzial"].sum().sort_values(ascending=False).head(n).index)


# --- dane z bazy ------------------------------------------------------------------------------------------------------


def _ostatni_dzien(con) -> date:
    d = con.execute(f"SELECT max(dzien) FROM {ryzyko_wind.TABELA_RYZYKA}").fetchone()[0]
    if d is None:
        raise LookupError("ryzyko_wind jest pusta: uruchom zadanie ryzyko-wind albo ryzyko_wstecz.py")
    return d


def windy_ryzyko(con, dzien: date) -> pd.DataFrame:
    df = con.execute(
        f"""
        SELECT r.id_windy, w.id_budynku, b.nazwa AS budynek, b.miasto, b.adres, b.lat, b.lon, w.producent,
            w.model AS model_windy, r.dzien, r.p_awarii_7d, r.wynik, r.ranga, r.stoi,
            coalesce(r.tryb_oceny, 'model') AS tryb_oceny, r.dni_telemetrii, r.opis, r.podzespoly,
            r.ostatnie_okno, r.okna_24h, a.pozycja AS pozycja_alarmu, r.wersja_modelu
        FROM {ryzyko_wind.TABELA_RYZYKA} AS r
        JOIN serwis_windy AS w USING (id_windy)
        JOIN pms_budynki AS b ON b.id_budynku = w.id_budynku
        LEFT JOIN {ryzyko_wind.TABELA_ALARMOW} AS a USING (dzien, id_windy)
        WHERE r.dzien = ?
        """,
        [dzien],
    ).df()
    df["podzespol_1"] = [(json.loads(p) or [{}])[0].get("podzespol") if p else None for p in df["podzespoly"]]
    df["ryzyko_proc"] = (100 * df["p_awarii_7d"]).round(1)
    df["alarm"] = df["pozycja_alarmu"].notna()
    return rozstaw_windy(df.drop(columns="podzespoly"))


def ryzyko_historia(con) -> pd.DataFrame:
    return con.execute(f"""
        SELECT r.dzien, r.moment_oceny AS czas, r.id_windy, r.p_awarii_7d, round(100 * r.p_awarii_7d, 1) AS ryzyko_proc,
            r.wynik, r.ranga, coalesce(r.tryb_oceny, 'model') AS tryb_oceny
        FROM {ryzyko_wind.TABELA_RYZYKA} AS r ORDER BY r.dzien, r.id_windy""").df()


def sygnaly_30d(con, dzien: date, nazwy: list[str], katalog_dzienny: Path = KATALOG_DZIENNY) -> pd.DataFrame:
    """Godzinne średnie sygnałów `nazwy` z DNI_SYGNALOW dni przed odcięciem dnia `dzien` + norma z cech dnia."""
    zrodlo = telemetra.utworz_widok_zrodla(con, telemetra.MagazynTelemetrii())
    model = wczytaj_obecny()
    przygotuj(
        con,
        bool(getattr(model, "bez_serwisu", True)),
        zrodlo,
        (dzien.isoformat(), dzien.isoformat()),
        bool(ustawienia_cech()["korekta_bledow_drzwi_lf5"]),
    )
    koniec = odciecie_s(dzien)
    czesci = []
    for rodzina in RODZINY:
        wybrane = [s for s in sygnaly(con, rodzina) if s in nazwy]
        if not wybrane:
            continue
        kol = ", ".join(f"avg(CAST({s} AS DOUBLE)) AS {s}" for s in wybrane)
        df = con.execute(
            f"""
            SELECT id_windy, to_timestamp(CAST(floor((epoch(ts_utc) + 540) / 3600) * 3600 + 3000 AS BIGINT)) AS czas,
                {kol}
            FROM ({sql_pliku(rodzina)})
            WHERE ts_utc > to_timestamp(?) AND ts_utc <= to_timestamp(?)
            GROUP BY ALL
            """,
            [koniec - DNI_SYGNALOW * 86400, koniec],
        ).df()
        czesci.append(df.melt(id_vars=["id_windy", "czas"], var_name="sygnal", value_name="wartosc"))
    dlugie = pd.concat(czesci, ignore_index=True)
    opisy = konfiguracja()["sygnaly"]
    dlugie["nazwa"] = dlugie["sygnal"].map(lambda s: opisy[s]["nazwa"])
    dlugie["jednostka"] = dlugie["sygnal"].map(lambda s: str(katalog_sygnalow()[s].get("jednostka")))
    dlugie["kolejnosc"] = dlugie["sygnal"].map({s: i + 1 for i, s in enumerate(nazwy)})
    dlugie["etykieta"] = dlugie["nazwa"] + " [" + dlugie["jednostka"] + "]"
    plik = plik_cech(dzien.isoformat(), katalog_dzienny)
    if plik.exists():
        cechy = pd.read_parquet(plik, columns=["id_windy", *[f"{s}_norma" for s in nazwy]])
        normy = cechy.melt(id_vars="id_windy", var_name="sygnal", value_name="norma")
        normy["sygnal"] = normy["sygnal"].str.removesuffix("_norma")
        dlugie = dlugie.merge(normy, on=["id_windy", "sygnal"], how="left")
    else:
        dlugie["norma"] = np.nan
    return dlugie.sort_values(["id_windy", "kolejnosc", "czas"]).reset_index(drop=True)


def alerty(con) -> tuple[pd.DataFrame, pd.Timestamp]:
    al = con.execute(f"""
        SELECT a.dzien, a.pozycja, a.id_windy, w.id_budynku, b.nazwa AS budynek, b.miasto,
            coalesce(a.tryb_oceny, 'model') AS tryb_oceny, a.p_awarii_7d, a.id_zgloszenia, r.opis, r.podzespoly
        FROM {ryzyko_wind.TABELA_ALARMOW} AS a
        JOIN serwis_windy AS w USING (id_windy)
        JOIN pms_budynki AS b ON b.id_budynku = w.id_budynku
        LEFT JOIN {ryzyko_wind.TABELA_RYZYKA} AS r USING (dzien, id_windy)
        ORDER BY a.dzien DESC, a.pozycja""").df()
    awarie = con.execute("""
        SELECT id_awarii, id_windy, podzespol,
            coalesce(start_awarii_tz, timezone('Europe/Warsaw', pierwsze_zgloszenie)) AS start_tz
        FROM awarie_odtworzone""").df()
    stan = con.execute("SELECT timezone('Europe/Warsaw', max(utworzono)) FROM serwis_zgloszenia").fetchone()[0]
    stan = pd.Timestamp(stan).tz_convert(STREFA)
    al = wyniki_alertow(al, awarie, stan)
    al["podzespol_wskazany"] = [(json.loads(p) or [{}])[0].get("podzespol") if p else None for p in al["podzespoly"]]
    oc = alerty_ocena.oceny(con)
    oc = oc.rename(
        columns={
            "ocena": "ocena_koordynatora",
            "podzespol": "podzespol_koordynatora",
            "komentarz": "komentarz_koordynatora",
        }
    )
    kol_oc = ["dzien", "id_windy", "ocena_koordynatora", "podzespol_koordynatora", "komentarz_koordynatora"]
    al = al.drop(columns="podzespoly").merge(oc[kol_oc], on=["dzien", "id_windy"], how="left")
    al["ryzyko_proc"] = (100 * al["p_awarii_7d"]).round(1)
    al["wyprzedzenie_h"] = al["wyprzedzenie_h"].round(1)
    return al, stan


# --- zapis ------------------------------------------------------------------------------------------------------------


def _zapisz(df: pd.DataFrame, katalog: Path, nazwa: str) -> None:
    katalog.mkdir(parents=True, exist_ok=True)
    tymczasowy = katalog / f".{nazwa}.parquet.tmp"
    df.to_parquet(tymczasowy, index=False)
    os.replace(tymczasowy, katalog / f"{nazwa}.parquet")


def zbuduj_panel(
    sciezka: Path = SCIEZKA_BAZY, katalog: Path = KATALOG_PANELU, katalog_dzienny: Path = KATALOG_DZIENNY
) -> dict[str, int]:
    """Zapisuje pliki Parquet panelu; zwraca liczby wierszy."""
    model = wczytaj_obecny()
    with polaczenie(sciezka=sciezka) as con:
        dzien = _ostatni_dzien(con)
        nazwy = najwazniejsze_sygnaly(model)
        tabele = {
            "windy_ryzyko": windy_ryzyko(con, dzien),
            "ryzyko_historia": ryzyko_historia(con),
            "sygnaly_30d": sygnaly_30d(con, dzien, nazwy, katalog_dzienny),
        }
        tabele["alerty"], stan = alerty(con)
    prog = float(ekonomia(wczytaj_zalozenia())["prog"])
    tabele["windy_ryzyko"]["powyzej_progu"] = tabele["windy_ryzyko"]["p_awarii_7d"] >= prog
    tabele["podsumowanie_8_tyg"] = podsumowanie(tabele["alerty"])
    tabele["panel_info"] = pd.DataFrame(
        [
            {
                "odswiezono": datetime.now(STREFA).isoformat(timespec="seconds"),
                "dzien_oceny": dzien,
                "stan_danych_awarii": stan.isoformat(),
                "wersja_modelu": model.wersja,
                "sygnaly": ", ".join(nazwy),
                "korekta_bledow_drzwi_lf5": bool(ustawienia_cech()["korekta_bledow_drzwi_lf5"]),
                "prog_oplacalnosci_proc": round(100 * prog, 2),
            }
        ]
    )
    for nazwa, df in tabele.items():
        _zapisz(df, Path(katalog), nazwa)
    return {k: len(v) for k, v in tabele.items()}


if __name__ == "__main__":
    for tabela, n in zbuduj_panel().items():
        print(f"{tabela:20} {n:>8,}".replace(",", " "))
