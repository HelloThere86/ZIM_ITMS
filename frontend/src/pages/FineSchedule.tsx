import { useEffect, useState } from "react";
import { AlertCircle, Loader2, ShieldCheck } from "lucide-react";
import { fetchJson } from "../services/api";

interface Fine {
  violation_name: string;
  legal_code?: string | null;
  fine_amount: number;
  currency?: string | null;
}

type LoadState = "loading" | "error" | "ready";

function formatViolationName(name: string): string {
  return name.replaceAll("_", " ").toUpperCase();
}

export function FineSchedule() {
  const [fines, setFines] = useState<Fine[]>([]);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [errorMsg, setErrorMsg] = useState("");

  useEffect(() => {
    fetchJson<Fine[]>("/fines")
      .then((data) => {
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
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Fine Schedule</h1>
          <p className="text-sm text-gray-500">
            Official ZRP Traffic Fine Regulations (S.I. 121 of 2024)
          </p>
        </div>
        <div className="flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 px-4 py-2 text-green-700">
          <ShieldCheck className="h-5 w-5" />
          <span className="text-sm font-semibold">Legally Validated</span>
        </div>
      </div>

      {loadState === "loading" && (
        <div className="flex items-center justify-center gap-2 py-16 text-gray-400">
          <Loader2 className="h-5 w-5 animate-spin" />
          <span className="text-sm">Loading fine schedule...</span>
        </div>
      )}

      {loadState === "error" && (
        <div className="flex items-center gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-red-700">
          <AlertCircle className="h-5 w-5 shrink-0" />
          <span className="text-sm">
            Failed to load fine schedule:{" "}
            <span className="font-medium">{errorMsg}</span>
          </span>
        </div>
      )}

      {loadState === "ready" && (
        <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
          <table className="w-full">
            <thead className="border-b border-gray-200 bg-gray-50">
              <tr>
                <th className="px-6 py-4 text-left text-xs font-bold uppercase text-gray-500">
                  Violation Type
                </th>
                <th className="px-6 py-4 text-left text-xs font-bold uppercase text-gray-500">
                  Legal Code
                </th>
                <th className="px-6 py-4 text-right text-xs font-bold uppercase text-gray-500">
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
                fines.map((fine, index) => (
                  <tr key={index} className="transition-colors hover:bg-gray-50">
                    <td className="px-6 py-4 text-sm font-medium text-gray-900">
                      {formatViolationName(fine.violation_name)}
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-500">
                      {fine.legal_code ?? "-"}
                    </td>
                    <td className="px-6 py-4 text-right text-sm font-bold text-gray-900">
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
