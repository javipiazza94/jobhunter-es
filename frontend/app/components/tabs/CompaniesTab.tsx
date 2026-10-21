import { ChevronRight } from "lucide-react";
import type { Company } from "@/lib/types";

interface Props {
  companies: Company[];
  countryFilter: string;
  onCountryFilterChange: (country: string) => void;
  onSelectCompany: (c: Company) => void;
}

const COUNTRY_NAMES: Record<string, string> = { ES: "España", US: "USA", UK: "UK" };

/** Pestaña «Empresas». */
export function CompaniesTab({ companies, countryFilter, onCountryFilterChange, onSelectCompany }: Props) {
  // Los países del desplegable salen de los datos: antes solo se podía elegir ES, US y UK.
  const countries = Array.from(new Set(companies.map(c => c.country).filter(Boolean))).sort();
  const visible = countryFilter ? companies.filter(c => c.country === countryFilter) : companies;
  return (
    <div className="glass-card overflow-hidden animate-fade-in">
      <div className="p-4 border-b border-white/5 bg-black/20 flex items-center gap-3">
        <span className="text-sm font-medium text-gray-500 uppercase tracking-wider">País:</span>
        <select
          value={countryFilter}
          onChange={(e) => onCountryFilterChange(e.target.value)}
          className="bg-[#16161f] border border-white/10 text-gray-300 text-sm rounded-lg px-3 py-1.5 focus:ring-2 focus:ring-indigo-500/50 outline-none"
        >
          <option value="">Todos</option>
          {countries.map(code => (
            <option key={code} value={code}>{COUNTRY_NAMES[code] ?? code}</option>
          ))}
        </select>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm text-left">
          <thead className="text-xs text-gray-400 uppercase bg-black/40 border-b border-white/5 tracking-wider">
            <tr>
              <th className="px-6 py-4 font-semibold">Empresa</th>
              <th className="px-6 py-4 font-semibold">Sector</th>
              <th className="px-6 py-4 font-semibold">País</th>
              <th className="px-6 py-4 font-semibold text-right">Ofertas</th>
              <th className="px-6 py-4 font-semibold text-right">Enviadas</th>
              <th className="px-6 py-4 font-semibold">Empleos</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {visible.map((c, idx) => (
              <tr key={c.id} onClick={() => onSelectCompany(c)} className="hover:bg-white/[0.03] cursor-pointer transition-colors stagger-row" style={{ animationDelay: `${idx * 0.02}s` }}>
                <td className="px-6 py-4 font-semibold text-gray-200">{c.name}</td>
                <td className="px-6 py-4">
                  <span className="bg-blue-500/10 text-blue-400 border border-blue-500/20 px-2 py-0.5 rounded-full text-[10px] uppercase font-bold tracking-wider">{c.sector}</span>
                </td>
                <td className="px-6 py-4 text-gray-400">{c.country}</td>
                <td className="px-6 py-4 text-right text-gray-300 tabular-nums font-mono">{c.offer_count}</td>
                <td className="px-6 py-4 text-right tabular-nums font-mono">
                  <span className={c.application_count > 0 ? "text-emerald-400 font-semibold" : "text-gray-600"}>
                    {c.application_count}
                  </span>
                </td>
                <td className="px-6 py-4">
                  {c.careers_url && (
                    <a href={c.careers_url} target="_blank" rel="noopener noreferrer"
                      className="text-indigo-400 hover:text-indigo-300 hover:underline text-xs font-medium inline-flex items-center gap-1">Ver <ChevronRight className="w-3 h-3" /></a>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
