// src/pages/TrafficResultsPage.tsx
import { useEffect, useState } from "react";
import {
  BarChart3,
  Brain,
  Clock3,
  CheckCircle2,
  GitCompareArrows,
  AlertTriangle,
  TrendingDown,
  Trophy,
  Network,
  Cpu,
} from "lucide-react";
import { StatCard } from "../components/StatCard";
import { getTrafficResults } from "../services/traffic";
import type { TrafficResults, ModelResult } from "../types/traffic";

// ─── Model metadata ──────────────────────────────────────────────────────────

const MODEL_META: Record<
  string,
  { label: string; shortLabel: string; color: string; bar: string; description: string }
> = {
  fixed_timer: {
    label: "Fixed Timer (Baseline)",
    shortLabel: "Fixed Timer",
    color: "text-gray-700",
    bar: "bg-gray-500",
    description: "Traditional fixed-cycle signal timing — no learning",
  },
  individual_dqn: {
    label: "Individual MARL DQN",
    shortLabel: "Individual DQN",
    color: "text-blue-700",
    bar: "bg-blue-500",
    description: "Each agent optimises its own intersection independently",
  },
  coop_dqn: {
    label: "Cooperative MARL DQN",
    shortLabel: "Coop DQN",
    color: "text-purple-700",
    bar: "bg-purple-500",
    description: "Agents share neighbour state for joint situational awareness",
  },
  qmix: {
    label: "QMIX (CTDE)",
    shortLabel: "QMIX",
    color: "text-emerald-700",
    bar: "bg-emerald-500",
    description: "Centralised training, decentralised execution via mixing network",
  },
};

const MODEL_ORDER = ["fixed_timer", "individual_dqn", "coop_dqn", "qmix"];

// ─── Sub-components ───────────────────────────────────────────────────────────

function AlgorithmBadge({ modelKey }: { modelKey: string }) {
  const meta = MODEL_META[modelKey];
  const colours: Record<string, string> = {
    fixed_timer:    "bg-gray-100 text-gray-700 border-gray-200",
    individual_dqn: "bg-blue-50 text-blue-700 border-blue-200",
    coop_dqn:       "bg-purple-50 text-purple-700 border-purple-200",
    qmix:           "bg-emerald-50 text-emerald-700 border-emerald-200",
  };
  return (
    <span className={`inline-flex rounded-full border px-2.5 py-0.5 text-xs font-medium ${colours[modelKey]}`}>
      {meta?.shortLabel ?? modelKey}
    </span>
  );
}

interface ComparisonRowProps {
  rank: number;
  modelKey: string;
  result: ModelResult;
  baseline: ModelResult | null;
  isBest: boolean;
}

function ComparisonRow({ rank, modelKey, result, baseline, isBest }: ComparisonRowProps) {
  const meta = MODEL_META[modelKey];
  const improvement =
    baseline && baseline.avgWaitPerStep > 0
      ? (((baseline.avgWaitPerStep - result.avgWaitPerStep) / baseline.avgWaitPerStep) * 100).toFixed(1)
      : null;

  return (
    <tr className={`border-b border-gray-100 transition-colors hover:bg-gray-50 ${isBest ? "bg-emerald-50/40" : ""}`}>
      <td className="px-5 py-4 text-sm font-medium text-gray-500">
        {isBest ? <Trophy className="h-4 w-4 text-emerald-600" /> : rank}
      </td>
      <td className="px-5 py-4">
        <div>
          <p className={`text-sm font-semibold ${meta?.color ?? "text-gray-900"}`}>
            {meta?.label ?? modelKey}
          </p>
          <p className="mt-0.5 text-xs text-gray-500">{meta?.description}</p>
        </div>
      </td>
      <td className="px-5 py-4 text-sm font-medium text-gray-900">
        {result.avgWaitPerStep.toFixed(2)}
        <span className="ml-1 text-xs text-gray-400">s</span>
      </td>
      <td className="px-5 py-4 text-sm text-gray-700">{result.avgQueuePerStep.toFixed(2)}</td>
      <td className="px-5 py-4 text-sm text-gray-700">{result.throughput.toLocaleString()}</td>
      <td className="px-5 py-4 text-sm">
        {improvement !== null && parseFloat(improvement) > 0 ? (
          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2.5 py-0.5 text-xs font-semibold text-emerald-700">
            <TrendingDown className="h-3 w-3" />
            {improvement}% less wait
          </span>
        ) : improvement !== null && parseFloat(improvement) < 0 ? (
          <span className="inline-flex rounded-full bg-red-50 px-2.5 py-0.5 text-xs font-semibold text-red-700">
            +{Math.abs(parseFloat(improvement))}% worse
          </span>
        ) : (
          <span className="text-xs text-gray-400">Baseline</span>
        )}
      </td>
    </tr>
  );
}

interface WaitBarProps {
  modelKey: string;
  value: number;
  max: number;
  loading: boolean;
}

function WaitBar({ modelKey, value, max, loading }: WaitBarProps) {
  const meta = MODEL_META[modelKey];
  const pct = max > 0 ? Math.max((value / max) * 100, 2) : 0;
  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <AlgorithmBadge modelKey={modelKey} />
        </div>
        <span className="text-sm font-semibold text-gray-900">
          {loading ? "..." : `${value.toFixed(2)}s`}
        </span>
      </div>
      <div className="h-3 w-full overflow-hidden rounded-full bg-gray-100">
        <div
          className={`h-3 rounded-full transition-all duration-700 ${meta?.bar ?? "bg-gray-400"}`}
          style={{ width: loading ? "0%" : `${pct}%` }}
        />
      </div>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export function TrafficResultsPage() {
  const [results, setResults] = useState<TrafficResults | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getTrafficResults()
      .then((data) => { setResults(data); })
      .catch((err) => {
        console.error("Failed to load traffic results:", err);
        setError("Failed to load traffic results from backend.");
      })
      .finally(() => setLoading(false));
  }, []);

  const models = results?.models ?? {};
  const baseline = models["fixed_timer"] ?? null;

  // Best-performing RL model by avg wait
  const rlKeys = ["individual_dqn", "coop_dqn", "qmix"];
  const bestKey = rlKeys.reduce<string | null>((best, key) => {
    if (!models[key]) return best;
    if (!best || models[key].avgWaitPerStep < models[best].avgWaitPerStep) return key;
    return best;
  }, null);

  const bestImprovement =
    bestKey && baseline && baseline.avgWaitPerStep > 0
      ? (((baseline.avgWaitPerStep - models[bestKey].avgWaitPerStep) / baseline.avgWaitPerStep) * 100).toFixed(1)
      : null;

  const maxWait = Math.max(...MODEL_ORDER.map((k) => models[k]?.avgWaitPerStep ?? 0));

  const trainingData = results?.trainingRewards ?? [];
  const maxReward = trainingData.length > 0 ? Math.max(...trainingData.map((p) => p.reward)) : 1;

  return (
    <div className="space-y-8">

      {/* ── Header ── */}
      <section className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="text-sm font-medium text-gray-500">Traffic Optimisation</p>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight text-gray-900">
            Traffic Results
          </h1>
          <p className="mt-3 max-w-3xl text-sm text-gray-600">
            Four-algorithm comparison across Fixed Timer baseline, Independent MARL DQN,
            Cooperative MARL DQN, and QMIX (centralised training, decentralised execution).
            Each model was evaluated over 5 runs on the same SUMO traffic scenario.
          </p>
        </div>

        <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3">
          <p className="text-sm font-medium text-emerald-900">Best RL improvement</p>
          <p className="mt-1 text-2xl font-semibold text-emerald-800">
            {loading ? "..." : bestImprovement ? `${bestImprovement}% less wait` : "—"}
          </p>
          {bestKey && !loading && (
            <p className="mt-0.5 text-xs text-emerald-700">
              via {MODEL_META[bestKey]?.shortLabel}
            </p>
          )}
        </div>
      </section>

      {/* ── Error ── */}
      {error && (
        <section className="rounded-xl border border-red-200 bg-red-50 p-5">
          <p className="text-sm font-semibold text-red-900">Backend error</p>
          <p className="mt-2 text-sm text-red-800">{error}</p>
        </section>
      )}

      {/* ── Stat cards ── */}
      <section className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Baseline Wait"
          value={loading ? "..." : `${baseline?.avgWaitPerStep.toFixed(2) ?? "—"} s`}
          sublabel="Fixed-timer reference"
        />
        <StatCard
          label="Best RL Wait"
          value={loading || !bestKey ? "..." : `${models[bestKey].avgWaitPerStep.toFixed(2)} s`}
          sublabel={bestKey ? MODEL_META[bestKey]?.shortLabel : "—"}
        />
        <StatCard
          label="Best Improvement"
          value={loading ? "..." : bestImprovement ? `${bestImprovement}%` : "—"}
          sublabel="Reduction in avg wait vs fixed timer"
        />
        <StatCard
          label="Algorithms Tested"
          value="4"
          sublabel="Fixed Timer · Ind DQN · Coop DQN · QMIX"
        />
      </section>

      {/* ── Full comparison table ── */}
      <section className="rounded-xl border border-gray-200 bg-white shadow-sm overflow-hidden">
        <div className="flex items-start gap-3 border-b border-gray-100 px-6 py-5">
          <div className="rounded-lg bg-gray-100 p-2">
            <GitCompareArrows className="h-5 w-5 text-gray-700" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-gray-900">Four-Algorithm Comparison</h2>
            <p className="mt-1 text-sm text-gray-600">
              Ranked by average wait per step. Lower is better. Improvement calculated against
              fixed-timer baseline.
            </p>
          </div>
        </div>

        {loading ? (
          <div className="px-6 py-10 text-sm text-gray-500">Loading results...</div>
        ) : Object.keys(models).length === 0 ? (
          <div className="px-6 py-10 text-sm text-gray-500">No results available from backend.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full">
              <thead className="bg-gray-50 text-xs font-semibold uppercase tracking-wider text-gray-500">
                <tr>
                  <th className="px-5 py-3 text-left w-10">#</th>
                  <th className="px-5 py-3 text-left">Algorithm</th>
                  <th className="px-5 py-3 text-left">Avg Wait / Step</th>
                  <th className="px-5 py-3 text-left">Avg Queue / Step</th>
                  <th className="px-5 py-3 text-left">Throughput</th>
                  <th className="px-5 py-3 text-left">vs Baseline</th>
                </tr>
              </thead>
              <tbody>
                {MODEL_ORDER.filter((k) => models[k]).map((key, idx) => (
                  <ComparisonRow
                    key={key}
                    rank={idx + 1}
                    modelKey={key}
                    result={models[key]}
                    baseline={baseline}
                    isBest={key === bestKey}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* ── Wait bar chart + model summary ── */}
      <section className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <div className="xl:col-span-2 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <div className="flex items-start gap-3">
            <div className="rounded-lg bg-gray-100 p-2">
              <BarChart3 className="h-5 w-5 text-gray-700" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-gray-900">Wait Time by Algorithm</h2>
              <p className="mt-1 text-sm text-gray-600">
                Proportional bars — shorter bar means less average waiting time.
              </p>
            </div>
          </div>

          <div className="mt-8 space-y-5">
            {MODEL_ORDER.filter((k) => models[k] || loading).map((key) => (
              <WaitBar
                key={key}
                modelKey={key}
                value={models[key]?.avgWaitPerStep ?? 0}
                max={maxWait}
                loading={loading}
              />
            ))}
          </div>
        </div>

        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <div className="flex items-start gap-3">
            <div className="rounded-lg bg-gray-100 p-2">
              <Brain className="h-5 w-5 text-gray-700" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-gray-900">Architecture Summary</h2>
              <p className="mt-1 text-sm text-gray-600">Key design decisions per algorithm.</p>
            </div>
          </div>

          <div className="mt-6 space-y-3">
            {MODEL_ORDER.map((key) => {
              const meta = MODEL_META[key];
              return (
                <div key={key} className="rounded-lg border border-gray-200 px-4 py-3">
                  <div className="flex items-center gap-2 mb-1">
                    <AlgorithmBadge modelKey={key} />
                  </div>
                  <p className="text-xs text-gray-600">{meta?.description}</p>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* ── Training reward chart + findings ── */}
      <section className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <div className="flex items-start gap-3">
            <div className="rounded-lg bg-gray-100 p-2">
              <Network className="h-5 w-5 text-gray-700" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-gray-900">Training Reward Curve</h2>
              <p className="mt-1 text-sm text-gray-600">
                Episode reward progression from backend evaluation data.
              </p>
            </div>
          </div>

          <div className="mt-8 flex h-64 items-end gap-1 rounded-xl border border-gray-200 bg-gray-50 p-4">
            {trainingData.length === 0 ? (
              <div className="flex h-full w-full items-center justify-center text-sm text-gray-500">
                No training reward data available.
              </div>
            ) : (
              trainingData.map((point) => (
                <div
                  key={point.episode}
                  className="flex flex-1 flex-col items-center justify-end"
                >
                  <div
                    className="w-full rounded-t-sm bg-gray-800 transition-all"
                    style={{ height: `${(point.reward / maxReward) * 100}%` }}
                    title={`Episode ${point.episode}: ${point.reward}`}
                  />
                  <p className="mt-2 text-[10px] text-gray-500">{point.episode}</p>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <div className="flex items-start gap-3">
            <div className="rounded-lg bg-gray-100 p-2">
              <CheckCircle2 className="h-5 w-5 text-gray-700" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-gray-900">Key Findings</h2>
              <p className="mt-1 text-sm text-gray-600">
                What the four-algorithm comparison demonstrates.
              </p>
            </div>
          </div>

          <div className="mt-6 space-y-3">
            <div className="rounded-lg border border-gray-200 px-4 py-3">
              <p className="text-sm font-medium text-gray-900">
                All RL algorithms outperform the fixed-timer baseline on wait time
              </p>
            </div>
            <div className="rounded-lg border border-gray-200 px-4 py-3">
              <p className="text-sm font-medium text-gray-900">
                Cooperative DQN narrows the gap over individual DQN through neighbour state sharing
              </p>
            </div>
            <div className="rounded-lg border border-gray-200 px-4 py-3">
              <p className="text-sm font-medium text-gray-900">
                QMIX's monotonicity constraint may limit performance on asymmetric traffic topologies
              </p>
            </div>
            <div className="rounded-lg border border-gray-200 px-4 py-3">
              <p className="text-sm font-medium text-gray-900">
                Gridlock cascade events persist across DQN variants — motivates future QMIX tuning
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ── Status banner ── */}
      <section className="rounded-xl border border-yellow-200 bg-yellow-50 p-5">
        <div className="flex items-start gap-3">
          <Clock3 className="mt-0.5 h-5 w-5 text-yellow-700" />
          <div>
            <h2 className="text-sm font-semibold text-yellow-900">Evaluation methodology</h2>
            <p className="mt-2 text-sm text-yellow-800">
              Each model was evaluated across 5 identical runs on the same SUMO scenario with
              exploration disabled. Results represent the best checkpoint saved during training.
              The <code className="rounded bg-yellow-100 px-1 text-xs">AvgWait(cmp)</code> metric
              uses lane-sum waiting time divided by steps — consistent across all four algorithms.
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}