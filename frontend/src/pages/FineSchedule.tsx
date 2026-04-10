import { useEffect, useState } from "react";
import { ShieldCheck, AlertCircle, Loader2 } from "lucide-react";

interface Fine {
  violation_name: string;
  legal_code: string;   // should come from your /api/fines response
  fine_amount: number;
}

type LoadState = "loading" | "error" | "ready";

function formatViolationName(name: string): string {
  return name.replaceAll("_", " ").toUpperCase();
}

export function FineSchedule() {
  const [fines, setFines]       = useState<Fine[]>([]);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [errorMsg, setErrorMsg]  = useState<string>("");

  useEffect(() => {
    fetch("http://127.0.0.1:8000/api/fines")
      .then((res) => {
        if (!res.ok) throw new Error(`Server returned ${res.status}`);
        return res.json();
      })
      .then((data: Fine[]) => {
        setFines(data);
        setLoadState("ready");
      })
      .catch((err: Error) => {
        setErrorMsg(err.message);
        setLoadState("error");
      });
  }, []);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Fine Schedule</h1>
          <p className="text-sm text-gray-500">
            Official ZRP Traffic Fine Regulations (S.I. 121 of 2024)
          </p>
        </div>
        <div className="bg-green-50 text-green-700 px-4 py-2 rounded-lg border border-green-200 flex items-center gap-2">
          <ShieldCheck className="w-5 h-5" />
          <span className="text-sm font-semibold">Legally Validated</span>
        </div>
      </div>

      {/* Loading */}
      {loadState === "loading" && (
        <div className="flex items-center justify-center py-16 text-gray-400 gap-2">
          <Loader2 className="w-5 h-5 animate-spin" />
          <span className="text-sm">Loading fine schedule…</span>
        </div>
      )}

      {/* Error */}
      {loadState === "error" && (
        <div className="flex items-center gap-3 bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
          <AlertCircle className="w-5 h-5 shrink-0" />
          <span className="text-sm">
            Failed to load fine schedule: <span className="font-medium">{errorMsg}</span>
          </span>
        </div>
      )}

      {/* Table */}
      {loadState === "ready" && (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-6 py-4 text-left text-xs font-bold text-gray-500 uppercase">
                  Violation Type
                </th>
                <th className="px-6 py-4 text-left text-xs font-bold text-gray-500 uppercase">
                  Legal Code
                </th>
                <th className="px-6 py-4 text-right text-xs font-bold text-gray-500 uppercase">
                  Fine (USD)
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {fines.length === 0 ? (
                <tr>
                  <td colSpan={3} className="px-6 py-10 text-center text-sm text-gray-400">
                    No fines found.
                  </td>
                </tr>
              ) : (
                fines.map((fine, i) => (
                  <tr key={i} className="hover:bg-gray-50 transition-colors">
                    <td className="px-6 py-4 text-sm font-medium text-gray-900">
                      {formatViolationName(fine.violation_name)}
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-500">
                      {fine.legal_code ?? "—"}
                    </td>
                    <td className="px-6 py-4 text-sm font-bold text-gray-900 text-right">
                      ${fine.fine_amount.toFixed(2)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}