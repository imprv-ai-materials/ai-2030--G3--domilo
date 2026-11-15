// Odczyty z API wyceny (api/api/main.py). Wywołania po stronie serwera Next.js, bez pamięci podręcznej:
// panel ma pokazywać stan po ostatnim przebiegu zadania nocnego.

export const API_URL = process.env.API_URL ?? "http://localhost:8101";

export type Rodzaj = "lokal" | "oferta";

export type PozycjaKolejki = {
  rodzaj: Rodzaj;
  id_obiektu: string;
  miasto: string | null;
  dzielnica: string | null;
  metraz: number | null;
  cena_ofertowa: number | null;
  powod: string | null;
  czas_przebiegu: string;
};

export type OfertaPonizejP10 = {
  id_obiektu: string;
  miasto: string | null;
  dzielnica: string | null;
  metraz: number | null;
  cena_ofertowa: number;
  p10: number;
  p50: number;
  p90: number;
  cena_do_p10: number;
  czas_przebiegu: string;
};

export type Czynnik = { cecha: string; opis: string; wplyw_pln: number };

export type KartaWyceny = {
  rodzaj: Rodzaj;
  id_obiektu: string;
  miasto: string | null;
  dzielnica: string | null;
  metraz: number | null;
  wersja_modelu: string;
  czas_przebiegu: string;
  dzien_wyceny: string | null;
  p10: number | null;
  p50: number | null;
  p90: number | null;
  odmowa: boolean;
  powod: string | null;
  cena_ofertowa: number | null;
  wartosc_bazowa: number | null;
  czynniki: Czynnik[];
  historia: { czas_przebiegu: string; p10: number | null; p50: number | null; p90: number | null; odmowa: boolean }[];
};

export class BladApi extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function pobierz<T>(sciezka: string): Promise<T> {
  let odp: Response;
  try {
    odp = await fetch(`${API_URL}${sciezka}`, { cache: "no-store" });
  } catch {
    throw new BladApi(0, `Brak połączenia z API wyceny (${API_URL}). Uruchom: cd api && poetry run uvicorn api.main:app --port 8101`);
  }
  if (!odp.ok) {
    throw new BladApi(odp.status, `API wyceny zwróciło ${odp.status} dla ${sciezka}`);
  }
  return (await odp.json()) as T;
}

export const kolejkaNieWiem = () => pobierz<PozycjaKolejki[]>("/valuation/kolejka-nie-wiem");
export const ofertyPonizejP10 = () => pobierz<OfertaPonizejP10[]>("/valuation/oferty-ponizej-p10");
export const kartaWyceny = (rodzaj: string, id: string) =>
  pobierz<KartaWyceny>(`/valuation/karta/${encodeURIComponent(rodzaj)}/${encodeURIComponent(id)}`);

const zl = new Intl.NumberFormat("pl-PL", { maximumFractionDigits: 0 });
const m2 = new Intl.NumberFormat("pl-PL", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const proc = new Intl.NumberFormat("pl-PL", { maximumFractionDigits: 1 });

export const fmtZl = (x: number | null | undefined) => (x == null ? "—" : `${zl.format(x)} zł`);
export const fmtM2 = (x: number | null | undefined) => (x == null ? "—" : `${m2.format(x)} m²`);
export const fmtProc = (x: number) => `${proc.format(x)}%`;
export const fmtCzas = (iso: string) =>
  new Date(iso).toLocaleString("pl-PL", { timeZone: "Europe/Warsaw", dateStyle: "short", timeStyle: "short" });
