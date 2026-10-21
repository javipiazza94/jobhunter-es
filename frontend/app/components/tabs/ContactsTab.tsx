import { Users, ChevronRight } from "lucide-react";
import type { Contact } from "@/lib/types";

/** Pestaña «Contactos»: emails y formularios extraídos, con las ofertas relevantes de cada empresa. */
export function ContactsTab({ contacts, onSelectContact }: { contacts: Contact[]; onSelectContact: (c: Contact) => void }) {
  return (
    <div className="glass-card overflow-hidden animate-fade-in">
      {contacts.length === 0 ? (
        <div className="p-16 text-center border-dashed border-white/10">
          <div className="w-16 h-16 rounded-full bg-white/5 flex items-center justify-center mx-auto mb-4">
            <Users className="w-8 h-8 text-gray-500" />
          </div>
          <h3 className="text-lg font-medium text-gray-300 mb-2">Sin contactos aún</h3>
          <p className="text-sm text-gray-500">Pulsa &quot;Contactos&quot; en la barra superior para extraer emails de las webs de empresas.</p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="text-xs text-gray-400 uppercase bg-black/40 border-b border-white/5 tracking-wider">
              <tr>
                <th className="px-6 py-4 font-semibold">Contacto</th>
                <th className="px-6 py-4 font-semibold">Empresa</th>
                <th className="px-6 py-4 font-semibold">Ofertas relevantes</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {contacts.map((ct, idx) => (
                <tr key={ct.id} onClick={() => onSelectContact(ct)} className="hover:bg-white/[0.03] cursor-pointer transition-colors align-top stagger-row" style={{ animationDelay: `${idx * 0.02}s` }}>
                  <td className="px-6 py-4">
                    <div className="font-mono text-sm text-indigo-400 mb-1">{ct.value}</div>
                    <span className="bg-white/5 text-gray-400 border border-white/10 px-1.5 py-0.5 rounded text-[10px] uppercase font-bold tracking-wider">{ct.type || "email"}</span>
                  </td>
                  <td className="px-6 py-4 text-gray-400 text-sm">
                    <div className="font-medium text-gray-200 mb-1">{ct.company_name || "—"}</div>
                    {ct.company_website && <a href={ct.company_website} target="_blank" rel="noopener noreferrer" className="text-indigo-400 hover:text-indigo-300 hover:underline text-xs inline-flex items-center gap-1">Web <ChevronRight className="w-3 h-3" /></a>}
                  </td>
                  <td className="px-6 py-4">
                    {ct.offers.length === 0 ? (
                      <span className="text-xs text-gray-500 italic">Sin ofertas activas</span>
                    ) : (
                      <div className="flex flex-col gap-2">
                        {ct.offers.slice(0, 4).map(o => (
                          <div key={o.id} className="flex items-center gap-3">
                            {o.url ? (
                              <a href={o.url} target="_blank" rel="noopener noreferrer" className="text-sm text-gray-300 hover:text-indigo-400 hover:underline truncate max-w-xs font-medium">{o.title}</a>
                            ) : (
                              <span className="text-sm text-gray-300 truncate max-w-xs font-medium">{o.title}</span>
                            )}
                            <span className="text-xs text-gray-500 shrink-0 bg-black/20 px-2 py-0.5 rounded-md border border-white/5">{o.location || "Remoto"}</span>
                            <span className={`text-[10px] font-bold tracking-wider px-2 py-0.5 rounded shrink-0 border ${o.relevance_score >= 0.8 ? "bg-green-500/10 text-green-400 border-green-500/20" : "bg-gray-500/10 text-gray-400 border-gray-500/20"}`}>
                              {(o.relevance_score * 100).toFixed(0)}%
                            </span>
                          </div>
                        ))}
                        {ct.offers.length > 4 && <span className="text-xs text-indigo-400/80 font-medium ml-1">+{ct.offers.length - 4} más</span>}
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
