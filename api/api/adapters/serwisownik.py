"""Serwisownik (zgłoszenia techniczne, notatki, części, windy) -> tabele serwis_* w domilo.duckdb.

`zbuduj_baze()` (`pypyr baza`) wczytuje pliki z data/serwis/ przez `wczytaj()`. Samo przeładowanie tabel Serwisownika
w istniejącej bazie: `cd api && python -m api.adapters.serwisownik`.

Konwencje źródła (data/README.md, „Konwencje systemów”):
- czas lokalny Europe/Warsaw bez strefy, z dokładnością do minuty. W Parquecie to TIMESTAMP_NS; w bazie TIMESTAMP
  (mikrosekundy) z tą samą godziną lokalną. Godzina 02:00–03:00 w dniu 2025-10-26 występuje dwa razy i baza tego
  nie rozstrzyga;
- `serwis_czesci.koszt_netto` to tekst z eksportu: spacja tysięcy i przecinek dziesiętny (`1 234,50`). W bazie
  DECIMAL(12, 2). Tekst w innym formacie przerywa wczytywanie (ValueError), zamiast cicho dać NULL albo złą liczbę.

Zapis do Serwisownika (`KlientSerwisownika`): alert o ryzyku awarii windy jako zgłoszenie
(zadanie `ryzyko-wind`, maintenance_bc/ryzyko_dzienne.py). Atrapa: dev/serwisownik_mock/ (`pypyr serwisownik_mock`).
Kontrakt (przyjęty w tej pracy, do potwierdzenia z zespołem Serwisownika; atrapa zachowuje się tak samo):
- `POST {SERWISOWNIK_URL}/api/zgloszenia`: pola jak w serwis_zgloszenia (`id_budynku`, `id_urzadzenia` = id windy,
  `typ_urzadzenia` = `winda`, `zrodlo` = `model_awarii`, `kategoria` = `przegląd`, `priorytet` = `normalny`,
  `tresc_zgloszenia` = opis alertu jednym zdaniem, `firma_serwisowa`) + `alarm` (dzień, pozycja, ryzyko, sygnały,
  podejrzane podzespoły z wkładami, wersja modelu) + `klucz_idempotencji`.
- `klucz_idempotencji` = `{id_windy}:{data_alarmu}` (winda + data alarmu). Serwisownik zakłada zgłoszenie tylko
  przy pierwszym kluczu. Ten sam klucz i ta sama treść: 200 z tym samym `id_zgloszenia` i `utworzono = false`. Ten
  sam klucz i inna treść: 409 (`KonfliktIdempotencji`; ponowienie nic nie da). Odpowiedź 200:
  `{"id_zgloszenia": "...", "utworzono": true|false}`. Inne błędy HTTP i sieci przechodzą dalej jako wyjątki httpx,
  więc Inngest ponawia krok wysyłki.
- Adres `SERWISOWNIK_URL` (domyślnie atrapa http://127.0.0.1:8103); opcjonalny `SERWISOWNIK_TOKEN` (Bearer).
"""

import os
from pathlib import Path

import duckdb
import httpx

# Tabela -> kolumny czasu lokalnego (TIMESTAMP_NS w Parquecie -> TIMESTAMP).
KOLUMNY_CZASU: dict[str, tuple[str, ...]] = {
    "serwis_zgloszenia": ("utworzono", "zamknieto"),
    "serwis_notatki": ("data_czas",),
    "serwis_czesci": (),
    "serwis_windy": ("czujnik_wibracji_od",),
    "serwis_harmonogram": ("data_plan", "data_wykonania"),
    "serwis_zloty_zbior": ("start_awarii",),
}
TABELE = tuple(KOLUMNY_CZASU)

# '88,39', '1 234,50', '-12,00'; spacja co trzy cyfry.
WZORZEC_KOSZTU = r"^-?[0-9]{1,3}( [0-9]{3})*,[0-9]{2}$"
SQL_KOSZTU = "CAST(replace(replace(koszt_netto, ' ', ''), ',', '.') AS DECIMAL(12, 2))"


def select_tabeli(nazwa: str, plik: str) -> str:
    """SELECT wczytujący plik Parquet tabeli Serwisownika z typami bazy."""
    zamiany = [f"CAST({kol} AS TIMESTAMP) AS {kol}" for kol in KOLUMNY_CZASU[nazwa]]
    if nazwa == "serwis_czesci":
        zamiany.append(f"{SQL_KOSZTU} AS koszt_netto")
    replace = f" REPLACE ({', '.join(zamiany)})" if zamiany else ""
    return f"SELECT *{replace} FROM read_parquet('{plik}')"


def sprawdz_koszty(con: duckdb.DuckDBPyConnection, plik: str) -> None:
    """ValueError, gdy któryś niepusty `koszt_netto` nie ma formatu eksportu (`1 234,50`)."""
    zle, przyklady = con.execute(
        f"SELECT count(*), list(DISTINCT koszt_netto)[1:5] FROM read_parquet('{plik}') "
        f"WHERE koszt_netto IS NOT NULL AND NOT regexp_matches(koszt_netto, '{WZORZEC_KOSZTU}')"
    ).fetchone()
    if zle:
        raise ValueError(f"serwis_czesci.koszt_netto: {zle} wartości w nieznanym formacie, np. {przyklady} ({plik})")


def wczytaj(con: duckdb.DuckDBPyConnection, pliki: dict[str, Path | str]) -> dict[str, int]:
    """Tworzy (od nowa) tabele Serwisownika obecne w `pliki` (nazwa tabeli -> Parquet); zwraca liczby wierszy.

    Ścieżki względne są liczone przez DuckDB od `file_search_path` (polacz() ustawia katalog repozytorium).
    Tabele spoza Serwisownika w `pliki` są pomijane.
    """
    liczby: dict[str, int] = {}
    for nazwa in TABELE:
        if nazwa not in pliki:
            continue
        plik = Path(pliki[nazwa]).as_posix()
        if nazwa == "serwis_czesci":
            sprawdz_koszty(con, plik)
        con.execute(f"CREATE OR REPLACE TABLE {nazwa} AS {select_tabeli(nazwa, plik)}")
        liczby[nazwa] = con.execute(f"SELECT count(*) FROM {nazwa}").fetchone()[0]
    return liczby


# --- zapis: alert o ryzyku awarii windy -> zgłoszenie ----------------------------------------------------------------

URL_DOMYSLNY = "http://127.0.0.1:8103"
SCIEZKA_ZGLOSZEN = "/api/zgloszenia"
LIMIT_CZASU_S = 30.0


class KonfliktIdempotencji(RuntimeError):
    """Serwisownik ma już zgłoszenie z tym kluczem, ale z inną treścią."""


def klucz_idempotencji(id_windy: str, data_alarmu: str) -> str:
    return f"{id_windy}:{data_alarmu}"


class KlientSerwisownika:
    def __init__(self, url: str | None = None, http: httpx.Client | None = None, token: str | None = None):
        self.url = (url or os.environ.get("SERWISOWNIK_URL") or URL_DOMYSLNY).rstrip("/")
        self._http = http
        self.token = token if token is not None else os.environ.get("SERWISOWNIK_TOKEN")

    def zglos_alarm(self, zgloszenie: dict) -> dict:
        """Wysyła zgłoszenie (pola w opisie modułu, z `alarm.id_windy` i `alarm.dzien`); zwraca odpowiedź 200."""
        alarm = zgloszenie["alarm"]
        tresc = {**zgloszenie, "klucz_idempotencji": klucz_idempotencji(alarm["id_windy"], alarm["dzien"])}
        naglowki = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        klient = self._http or httpx.Client(timeout=LIMIT_CZASU_S)
        try:
            odp = klient.post(f"{self.url}{SCIEZKA_ZGLOSZEN}", json=tresc, headers=naglowki)
        finally:
            if self._http is None:
                klient.close()
        if odp.status_code == 409:
            raise KonfliktIdempotencji(odp.text[:500])
        odp.raise_for_status()
        wynik = odp.json()
        return {"id_zgloszenia": str(wynik["id_zgloszenia"]), "utworzono": bool(wynik["utworzono"])}


if __name__ == "__main__":
    from api.adapters.duckdb_baza import KATALOG_REPO, pliki_tabel, polaczenie

    pliki_wzgledne = {n: p.relative_to(KATALOG_REPO) for n, p in pliki_tabel().items()}
    with polaczenie(tylko_odczyt=False) as polaczenie_bazy:
        for tabela, n in wczytaj(polaczenie_bazy, pliki_wzgledne).items():
            print(f"{tabela:24} {n:>10,}".replace(",", " "))
