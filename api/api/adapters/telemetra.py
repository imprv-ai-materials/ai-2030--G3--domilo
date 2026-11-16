"""Telemetra (czujniki wind): pobieranie nowych okien 10-min i magazyn okien bieżących w Parquet.

Zadanie Inngest `telemetra-okna` (co 10 minut, maintenance_bc/telemetria_biezaca.py) pobiera okna ze źródła
i dopisuje je do magazynu. Cechy dnia (`cechy-wind`, 05:50) czytają eksport z data/ razem z magazynem
(`utworz_widok_zrodla`), tymi samymi plikami SQL co trening.

Źródła okien (`zrodlo_okien()`):
- `KlientTelemetry` — API Telemetry: `GET {TELEMETRA_URL}/okna?od=<ISO 8601>&do=<ISO 8601>` zwraca
  `{"okna": [{kolumny SCHEMAT}, ...]}` z oknami o `ts_utc` (koniec okna, UTC) w (od; do]. Opcjonalny token
  `TELEMETRA_TOKEN` (Authorization: Bearer). Kontrakt API przyjęty w tej pracy (do potwierdzenia z dostawcą).
- `ZrodloEksportu` — atrapa do pracy lokalnej: te same okna z eksportu data/telemetra/telemetra_windy/ (tylko do
  odczytu). Gdy `TELEMETRA_URL` nie jest ustawione albo = `eksport`. Po dniu eksportu nie zwraca nic.

Magazyn (`MagazynTelemetrii`, katalog `TELEMETRA_MAGAZYN`, domyślnie telemetra_biezaca/ w katalogu głównym, poza
gitem): `telemetra_windy/rok=RRRR/miesiac=MM/okna.parquet` (miesiąc według `ts_utc` w UTC, jak w eksporcie),
schemat jak eksport (bez kolumn partycji). Zapis jest idempotentny po kluczu (id_windy, ts_utc): okno już zapisane
z tą samą treścią to powtórzenie, z inną treścią to konflikt — zostaje pierwsza wersja (jak w eksporcie), a konflikt
jest liczony i zwracany w wyniku. Plik miesiąca jest zastępowany atomowo (os.replace), więc czytelnik widzi starą
albo nową wersję. Jeden zapisujący naraz: funkcja Inngest ma concurrency 1.
Odrzucane (liczone, nie zapisywane): okna bez id_windy / ts_utc i okna, których ts_utc nie jest pełnym 10-minutowym
znacznikiem.
"""

import os
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol

import duckdb
import httpx
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from api.adapters.duckdb_baza import KATALOG_DANYCH, KATALOG_REPO

KATALOG_EKSPORTU = KATALOG_DANYCH / "telemetra" / "telemetra_windy"
KATALOG_MAGAZYNU = KATALOG_REPO / "telemetra_biezaca"
PODKATALOG = "telemetra_windy"
NAZWA_PLIKU = "okna.parquet"
WIDOK_ZRODLA = "telemetra_windy_biezaca"
KLUCZ = ("id_windy", "ts_utc")
OKNO = timedelta(minutes=10)
LIMIT_CZASU_S = 60.0

# Schemat okna = schemat eksportu data/telemetra/telemetra_windy (bez kolumn partycji rok, miesiac).
SCHEMAT = pa.schema(
    [
        ("id_windy", pa.string()),
        ("ts_utc", pa.timestamp("ms", tz="UTC")),
        ("kursy", pa.int16()),
        ("otwarcia_drzwi", pa.int16()),
        ("ponowne_otwarcia", pa.int16()),
        ("czas_zamykania_drzwi_sr_s", pa.float32()),
        ("czas_zamykania_drzwi_max_s", pa.float32()),
        ("prad_silnika_sr_a", pa.float32()),
        ("prad_silnika_max_a", pa.float32()),
        ("temp_silnika_c", pa.float32()),
        ("temp_maszynowni_c", pa.float32()),
        ("wibracje_rms_mg", pa.float32()),
        ("blad_poziomowania_sr_mm", pa.float32()),
        ("bledy_drzwi", pa.int8()),
        ("bledy_napedu", pa.int8()),
        ("bledy_sterownika", pa.int8()),
        ("kody_bledow", pa.string()),
        ("tryb", pa.string()),
        ("firmware", pa.string()),
    ]
)
KOLUMNY = tuple(SCHEMAT.names)


class ZrodloOkien(Protocol):
    def pobierz_okna(self, od: datetime, do: datetime) -> pd.DataFrame:
        """Okna z ts_utc w (od; do] (kolumny KOLUMNY)."""


def _iso(t: datetime) -> str:
    return pd.Timestamp(t).tz_convert("UTC").isoformat()


class KlientTelemetry:
    """API Telemetry (kontrakt w opisie modułu)."""

    def __init__(self, url: str, http: httpx.Client | None = None, token: str | None = None):
        self.url = url.rstrip("/")
        self._http = http
        self.token = token if token is not None else os.environ.get("TELEMETRA_TOKEN")

    def pobierz_okna(self, od: datetime, do: datetime) -> pd.DataFrame:
        naglowki = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        klient = self._http or httpx.Client(timeout=LIMIT_CZASU_S)
        try:
            odp = klient.get(f"{self.url}/okna", params={"od": _iso(od), "do": _iso(do)}, headers=naglowki)
        finally:
            if self._http is None:
                klient.close()
        odp.raise_for_status()
        okna = pd.DataFrame(odp.json()["okna"])
        if okna.empty:
            return pd.DataFrame(columns=list(KOLUMNY))
        okna["ts_utc"] = pd.to_datetime(okna["ts_utc"], utc=True)
        return okna


class ZrodloEksportu:
    """Atrapa Telemetry: okna z eksportu data/ (tylko do odczytu) w (od; do]."""

    def __init__(self, katalog: Path = KATALOG_EKSPORTU):
        self.katalog = Path(katalog)

    def pobierz_okna(self, od: datetime, do: datetime) -> pd.DataFrame:
        con = duckdb.connect()
        try:
            con.execute("SET TimeZone = 'UTC'")
            return con.execute(
                f"""
                SELECT {', '.join(KOLUMNY)}
                FROM read_parquet('{self.katalog.as_posix()}/*/*/*.parquet', hive_partitioning = false)
                WHERE ts_utc > ? AND ts_utc <= ?
                ORDER BY ts_utc, id_windy
                """,
                [pd.Timestamp(od).tz_convert("UTC"), pd.Timestamp(do).tz_convert("UTC")],
            ).df()
        finally:
            con.close()


def zrodlo_okien() -> ZrodloOkien:
    """`TELEMETRA_URL` -> KlientTelemetry; brak albo `eksport` -> ZrodloEksportu (atrapa)."""
    url = os.environ.get("TELEMETRA_URL", "").strip()
    return ZrodloEksportu() if url in ("", "eksport") else KlientTelemetry(url)


def ujednolic(okna: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Okna w schemacie SCHEMAT (kolumny, typy, ts_utc w UTC); zwraca (poprawne bez duplikatów klucza, odrzucone)."""
    brak = [k for k in KOLUMNY if k not in okna.columns]
    if brak:
        raise ValueError(f"Telemetra: brak kolumn {', '.join(brak)}")
    df = okna[list(KOLUMNY)].copy()
    df["ts_utc"] = pd.to_datetime(df["ts_utc"], utc=True)
    ok = df["id_windy"].notna() & df["ts_utc"].notna() & (df["ts_utc"].dt.floor(OKNO) == df["ts_utc"])
    odrzucone = int((~ok).sum())
    df = df[ok].drop_duplicates(list(KLUCZ), keep="first")
    tabela = pa.Table.from_pandas(df, schema=SCHEMAT, preserve_index=False, safe=False)
    return tabela.to_pandas(), odrzucone


def _rowne(a: pd.DataFrame, b: pd.DataFrame) -> pd.Series:
    """Czy wiersze a i b (ten sam indeks, kolumny poza kluczem) mają tę samą treść (NaN = NaN)."""
    rowne = pd.Series(True, index=a.index)
    for k in KOLUMNY:
        if k in KLUCZ:
            continue
        x, y = a[k], b[k]
        rowne &= (x == y) | (x.isna() & y.isna())
    return rowne


class MagazynTelemetrii:
    """Okna bieżące w Parquet (rok=/miesiac=/okna.parquet), idempotentnie po (id_windy, ts_utc)."""

    def __init__(self, katalog: Path | str | None = None):
        bazowy = Path(katalog or os.environ.get("TELEMETRA_MAGAZYN") or KATALOG_MAGAZYNU)
        self.katalog = bazowy / PODKATALOG

    def plik_miesiaca(self, rok: int, miesiac: int) -> Path:
        return self.katalog / f"rok={rok}" / f"miesiac={miesiac:02d}" / NAZWA_PLIKU

    def pliki(self) -> list[Path]:
        return sorted(self.katalog.glob(f"rok=*/miesiac=*/{NAZWA_PLIKU}"))

    def wczytaj_miesiac(self, rok: int, miesiac: int) -> pd.DataFrame:
        plik = self.plik_miesiaca(rok, miesiac)
        if not plik.exists():
            return SCHEMAT.empty_table().to_pandas()
        return pq.read_table(plik, schema=SCHEMAT).to_pandas()

    def dopisz(self, okna: pd.DataFrame) -> dict:
        """Dopisuje okna; zwraca liczby: pobrane, nowe, powtorzenia, konflikty, odrzucone (+ przyklady_konfliktow)."""
        df, odrzucone = ujednolic(okna)
        wynik = {"pobrane": len(okna), "nowe": 0, "powtorzenia": 0, "konflikty": 0, "odrzucone": odrzucone}
        przyklady: list[str] = []
        if df.empty:
            return {**wynik, "przyklady_konfliktow": przyklady}
        miesiace = df["ts_utc"].dt.tz_convert("UTC")
        for (rok, miesiac), czesc in df.groupby([miesiace.dt.year, miesiace.dt.month], sort=True):
            stare = self.wczytaj_miesiac(int(rok), int(miesiac))
            para = czesc.merge(stare, on=list(KLUCZ), how="left", suffixes=("", "_stare"), indicator=True)
            znane = para["_merge"] == "both"
            nowe = czesc[~znane.to_numpy()]
            if znane.any():
                z = para[znane]
                stare_z = z[[f"{k}_stare" if k not in KLUCZ else k for k in KOLUMNY]]
                stare_z.columns = list(KOLUMNY)
                rowne = _rowne(z[list(KOLUMNY)], stare_z)
                wynik["powtorzenia"] += int(rowne.sum())
                wynik["konflikty"] += int((~rowne).sum())
                przyklady += [f"{w}:{_iso(t)}" for w, t in zip(z.loc[~rowne, "id_windy"], z.loc[~rowne, "ts_utc"])]
            if nowe.empty:
                continue
            calosc = pd.concat([stare, nowe], ignore_index=True).sort_values(["ts_utc", "id_windy"])
            self._zapisz_atomowo(self.plik_miesiaca(int(rok), int(miesiac)), calosc)
            wynik["nowe"] += len(nowe)
        return {**wynik, "przyklady_konfliktow": przyklady[:20]}

    @staticmethod
    def _zapisz_atomowo(plik: Path, df: pd.DataFrame) -> None:
        plik.parent.mkdir(parents=True, exist_ok=True)
        tymczasowy = plik.with_suffix(".tmp")
        pq.write_table(pa.Table.from_pandas(df, schema=SCHEMAT, preserve_index=False), tymczasowy)
        os.replace(tymczasowy, plik)

    def ostatnie_okno(self) -> datetime | None:
        """Najpóźniejszy ts_utc w magazynie (None = pusty)."""
        pliki = self.pliki()
        if not pliki:
            return None
        return max(pq.read_table(p, columns=["ts_utc"]).column("ts_utc").to_pandas().max() for p in pliki)


def ostatnie_okno_eksportu(katalog: Path = KATALOG_EKSPORTU) -> datetime | None:
    if not any(Path(katalog).glob("*/*/*.parquet")):
        return None
    con = duckdb.connect()
    try:
        wynik = con.execute(
            f"SELECT max(ts_utc) FROM read_parquet('{Path(katalog).as_posix()}/*/*/*.parquet', "
            "hive_partitioning = false)"
        ).fetchone()[0]
    finally:
        con.close()
    return None if wynik is None else pd.Timestamp(wynik).tz_convert("UTC").to_pydatetime()


def sql_zrodla(magazyn: MagazynTelemetrii, z_eksportem: bool = True, katalog_eksportu: Path = KATALOG_EKSPORTU) -> str:
    """SELECT okien: eksport (data/, tylko do odczytu) + okna magazynu, których klucza nie ma w eksporcie.
    Eksport ma pierwszeństwo dla swojego okresu (jak zasada „pierwsza wersja zostaje” w magazynie)."""
    kolumny = ", ".join(KOLUMNY)
    czesci = []
    eksport = f"read_parquet('{Path(katalog_eksportu).as_posix()}/*/*/*.parquet', hive_partitioning = false)"
    if z_eksportem:
        czesci.append(f"SELECT {kolumny} FROM {eksport}")
    if magazyn.pliki():
        biezace = f"read_parquet('{magazyn.katalog.as_posix()}/*/*/{NAZWA_PLIKU}', hive_partitioning = false)"
        if z_eksportem:
            czesci.append(f"""
                SELECT {', '.join(f'b.{k}' for k in KOLUMNY)}
                FROM {biezace} AS b
                ANTI JOIN (SELECT id_windy, ts_utc FROM {eksport}
                           WHERE ts_utc >= (SELECT min(ts_utc) FROM {biezace})) AS e
                    USING (id_windy, ts_utc)""")
        else:
            czesci.append(f"SELECT {kolumny} FROM {biezace}")
    if not czesci:
        raise FileNotFoundError("Brak okien telemetrii: ani eksportu, ani magazynu")
    return "\nUNION ALL\n".join(czesci)


def utworz_widok_zrodla(
    con: duckdb.DuckDBPyConnection,
    magazyn: MagazynTelemetrii | None = None,
    z_eksportem: bool = True,
    katalog_eksportu: Path = KATALOG_EKSPORTU,
    nazwa: str = WIDOK_ZRODLA,
) -> str:
    """Tymczasowy widok okien (eksport + magazyn) o kolumnach telemetra_windy bez partycji; zwraca jego nazwę."""
    sql = sql_zrodla(magazyn or MagazynTelemetrii(), z_eksportem, katalog_eksportu)
    con.execute(f"CREATE OR REPLACE TEMP VIEW {nazwa} AS {sql}")
    return nazwa


def podziel_zakres(od: datetime, do: datetime, krok: timedelta) -> Iterable[tuple[datetime, datetime]]:
    """(od; do] w kawałkach najwyżej `krok` (kolejne zapytania do API)."""
    poczatek = od
    while poczatek < do:
        koniec = min(poczatek + krok, do)
        yield poczatek, koniec
        poczatek = koniec


def teraz_utc() -> datetime:
    return datetime.now(timezone.utc)
