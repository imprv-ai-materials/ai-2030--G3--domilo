import { BladApi } from "@/lib/api";

export default function BladApiKomunikat({ blad }: { blad: unknown }) {
  const tekst = blad instanceof BladApi ? blad.message : "Nieoczekiwany błąd przy pobieraniu danych z API wyceny.";
  return (
    <div className="blad" role="alert">
      {tekst}
    </div>
  );
}
