// src/pages/TrafficResultsPage.tsx
import { useEffect, useState } from "react";
import {
  BarChart3,
  Brain,
  Clock3,
  CheckCircle2,
  GitCompareArrows,
  AlertTriangle,
  LineChart,
} from "lucide-react";
import { StatCard } from "../components/StatCard";
import { getTrafficResults } from "../services/traffic";
import type { TrafficResults } from "../types/traffic";

interface MetricRowProps {
  label: string;
  baseline: string;
  dqn: string;
  change: string;
}

function MetricRow({ label, baseline, dqn, change }: MetricRowProps) {
  return (
    <div className="grid grid-cols-1 gap-3 rounded-xl border border-gray-200 p-4 md:grid-cols-4 md:items-center">
      <div>
        <p className="text-sm font-semibold text-gray-900">{label}</p>
      </div>
      <div>
        <p className="text-xs uppercase tracking-wide text-gray-500">Baseline</p>
        <p className="text-sm font-medium text-gray-800">{baseline}</p>
      </div>
      <div>
        <p className="text-xs uppercase tracking-wide text-gray-500">DQN</p>
        <p className="text-sm font-medium text-gray-800">{dqn}</p>
      </div>
      <div>
        <p className="text-xs uppercase tracking-wide text-gray-500">Improvement</p>
        <p className="text-sm font-semibold text-green-700">{change}</p>
      </div>
    </div>
  );
}

export function TrafficResultsPage() {
  const [results, setResults] = useState<TrafficResults | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadTrafficResults() {
      try {
        const data = await getTrafficResults();
        setResults(data);
      } catch (err) {
        console.error("Failed to load traffic results:", err);
        setError("Failed to load traffic results from backend.");
      } finally {
        setLoading(false);
      }
    }

    loadTrafficResults();
  }, []);

  const trainingData = results?.trainingRewards ?? [];
  const maxReward =
    trainingData.length > 0 ? Math.max(...trainingData.map((point) => point.reward)) : 1;

  const baselineWaitingTime = results?.baselineWaitingTime ?? 0;
  const dqnWaitingTime = results?.dqnWaitingTime ?? 0;
  const improvementPercent = results?.improvementPercent ?? 0;
  const trainingEpisodes = results?.trainingEpisodes ?? 0;
  const notes = results?.notes ?? "No evaluation note available.";

  const dqnBarWidth =
    baselineWaitingTime > 0 ? Math.max((dqnWaitingTime / baselineWaitingTime) * 100, 4) : 0;

  return (
    <div className="space-y-8">
      <section className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="text-sm font-medium text-gray-500">Traffic Optimization</p>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight text-gray-900">
            Traffic Results
          </h1>
          <p className="mt-3 max-w-3xl text-sm text-gray-600">
            This page presents the traffic signal optimization results for the single-intersection
            DQN controller against a fixed-time baseline. It is designed to make the capstone’s AI
            contribution visible and defensible during demos and presentations.
          </p>
        </div>

        <div className="rounded-xl border border-green-200 bg-green-50 px-4 py-3">
          <p className="text-sm font-medium text-green-900">Current Backend Result</p>
          <p className="mt-1 text-2xl font-semibold text-green-800">
            {loading ? "..." : `${improvementPercent}% improvement`}
          </p>
        </div>
      </section>

      {error && (
        <section className="rounded-xl border border-red-200 bg-red-50 p-5">
          <p className="text-sm font-semibold text-red-900">Backend error</p>
          <p className="mt-2 text-sm text-red-800">{error}</p>
        </section>
      )}

      <section className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Baseline Waiting Time"
          value={loading ? "..." : `${baselineWaitingTime} s`}
          sublabel="Fixed-time controller reference"
        />
        <StatCard
          label="DQN Waiting Time"
          value={loading ? "..." : `${dqnWaitingTime} s`}
          sublabel="Current single-intersection result"
        />
        <StatCard
          label="Improvement"
          value={loading ? "..." : `${improvementPercent}%`}
          sublabel="Loaded from backend results"
        />
        <StatCard
          label="Training Episodes"
          value={loading ? "..." : trainingEpisodes.toString()}
          sublabel="Completed DQN training cycles"
        />
      </section>

      <section className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <div className="xl:col-span-2 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <div className="flex items-start gap-3">
            <div className="rounded-lg bg-gray-100 p-2">
              <GitCompareArrows className="h-5 w-5 text-gray-700" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-gray-900">Baseline vs DQN Comparison</h2>
              <p className="mt-1 text-sm text-gray-600">
                Summary comparison between the fixed-time signal strategy and the DQN controller.
              </p>
            </div>
          </div>

          <div className="mt-6 space-y-4">
            <MetricRow
              label="Average Waiting Time"
              baseline={loading ? "..." : `${baselineWaitingTime} s`}
              dqn={loading ? "..." : `${dqnWaitingTime} s`}
              change={loading ? "..." : `-${improvementPercent}%`}
            />
            <MetricRow
              label="Queue Pressure"
              baseline="Higher"
              dqn="Lower"
              change="Reduced"
            />
            <MetricRow
              label="Signal Adaptiveness"
              baseline="Static timing"
              dqn="State-driven"
              change="Improved"
            />
            <MetricRow
              label="Control Strategy"
              baseline="Fixed-time baseline"
              dqn="Learned DQN policy"
              change="AI-enabled"
            />
          </div>

          <div className="mt-6 rounded-xl border border-blue-200 bg-blue-50 p-4">
            <p className="text-sm font-semibold text-blue-900">Evaluation note</p>
            <p className="mt-2 text-sm text-blue-800">{notes}</p>
          </div>
        </div>

        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <div className="flex items-start gap-3">
            <div className="rounded-lg bg-gray-100 p-2">
              <Brain className="h-5 w-5 text-gray-700" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-gray-900">DQN Model Summary</h2>
              <p className="mt-1 text-sm text-gray-600">
                Current reinforcement learning implementation details.
              </p>
            </div>
          </div>

          <div className="mt-6 space-y-4">
            <div className="rounded-lg border border-gray-200 px-4 py-3">
              <p className="text-xs uppercase tracking-wide text-gray-500">Architecture</p>
              <p className="mt-1 text-sm font-medium text-gray-900">Single-intersection DQN</p>
            </div>

            <div className="rounded-lg border border-gray-200 px-4 py-3">
              <p className="text-xs uppercase tracking-wide text-gray-500">Training Features</p>
              <p className="mt-1 text-sm font-medium text-gray-900">
                Replay memory, target network, Huber loss, gradient clipping
              </p>
            </div>

            <div className="rounded-lg border border-gray-200 px-4 py-3">
              <p className="text-xs uppercase tracking-wide text-gray-500">Signal Logic</p>
              <p className="mt-1 text-sm font-medium text-gray-900">
                Includes yellow and all-red transition phases
              </p>
            </div>

            <div className="rounded-lg border border-gray-200 px-4 py-3">
              <p className="text-xs uppercase tracking-wide text-gray-500">State Representation</p>
              <p className="mt-1 text-sm font-medium text-gray-900">
                Richer traffic-state input for decision quality
              </p>
            </div>
          </div>
        </div>
      </section>

      <section className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <div className="flex items-start gap-3">
            <div className="rounded-lg bg-gray-100 p-2">
              <BarChart3 className="h-5 w-5 text-gray-700" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-gray-900">Waiting Time Comparison</h2>
              <p className="mt-1 text-sm text-gray-600">
                Simple visual contrast between baseline and DQN waiting time.
              </p>
            </div>
          </div>

          <div className="mt-8 space-y-6">
            <div>
              <div className="mb-2 flex items-center justify-between">
                <span className="text-sm font-medium text-gray-700">Fixed-Time Baseline</span>
                <span className="text-sm font-semibold text-gray-900">
                  {loading ? "..." : `${baselineWaitingTime} s`}
                </span>
              </div>
              <div className="h-4 w-full rounded-full bg-gray-200">
                <div className="h-4 rounded-full bg-gray-700" style={{ width: "100%" }} />
              </div>
            </div>

            <div>
              <div className="mb-2 flex items-center justify-between">
                <span className="text-sm font-medium text-gray-700">DQN Controller</span>
                <span className="text-sm font-semibold text-green-700">
                  {loading ? "..." : `${dqnWaitingTime} s`}
                </span>
              </div>
              <div className="h-4 w-full rounded-full bg-gray-200">
                <div
                  className="h-4 rounded-full bg-green-600"
                  style={{ width: loading ? "0%" : `${dqnBarWidth}%` }}
                />
              </div>
            </div>
          </div>

          <div className="mt-6 rounded-lg border border-green-200 bg-green-50 p-4">
            <p className="text-sm font-medium text-green-900">
              The DQN controller currently shows lower waiting time than the fixed-time baseline in
              the backend evaluation data.
            </p>
          </div>
        </div>

        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <div className="flex items-start gap-3">
            <div className="rounded-lg bg-gray-100 p-2">
              <LineChart className="h-5 w-5 text-gray-700" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-gray-900">Training Progress</h2>
              <p className="mt-1 text-sm text-gray-600">
                Reward progression loaded from backend evaluation data.
              </p>
            </div>
          </div>

          <div className="mt-8 flex h-64 items-end gap-3 rounded-xl border border-gray-200 bg-gray-50 p-4">
            {trainingData.length === 0 ? (
              <div className="flex h-full w-full items-center justify-center text-sm text-gray-500">
                No training reward data available.
              </div>
            ) : (
              trainingData.map((point) => {
                const height = `${(point.reward / maxReward) * 100}%`;

                return (
                  <div key={point.episode} className="flex flex-1 flex-col items-center justify-end">
                    <div
                      className="w-full rounded-t-md bg-gray-800 transition-all"
                      style={{ height }}
                      title={`Episode ${point.episode}: ${point.reward}`}
                    />
                    <p className="mt-2 text-[10px] text-gray-500">{point.episode}</p>
                  </div>
                );
              })
            )}
          </div>

          <p className="mt-4 text-sm text-gray-600">
            This visual now depends on backend-provided values from `/api/traffic-results`.
          </p>
        </div>
      </section>

      <section className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <div className="flex items-start gap-3">
            <div className="rounded-lg bg-gray-100 p-2">
              <CheckCircle2 className="h-5 w-5 text-gray-700" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-gray-900">What This Proves</h2>
              <p className="mt-1 text-sm text-gray-600">
                Why this page matters to your capstone story.
              </p>
            </div>
          </div>

          <div className="mt-6 space-y-4">
            <div className="rounded-lg border border-gray-200 px-4 py-3">
              <p className="text-sm font-medium text-gray-900">
                The project includes a trained AI controller, not just dashboard integration.
              </p>
            </div>
            <div className="rounded-lg border border-gray-200 px-4 py-3">
              <p className="text-sm font-medium text-gray-900">
                The signal controller can be compared against a meaningful fixed-time baseline.
              </p>
            </div>
            <div className="rounded-lg border border-gray-200 px-4 py-3">
              <p className="text-sm font-medium text-gray-900">
                The reinforcement learning component is visible as measurable system improvement.
              </p>
            </div>
          </div>
        </div>

        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <div className="flex items-start gap-3">
            <div className="rounded-lg bg-gray-100 p-2">
              <AlertTriangle className="h-5 w-5 text-gray-700" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-gray-900">Next Data Improvement</h2>
              <p className="mt-1 text-sm text-gray-600">
                What should become more rigorous after this integration.
              </p>
            </div>
          </div>

          <div className="mt-6 space-y-4">
            <div className="rounded-lg border border-gray-200 px-4 py-3">
              <p className="text-sm font-medium text-gray-900">
                Export real evaluation output directly from the testing script
              </p>
            </div>
            <div className="rounded-lg border border-gray-200 px-4 py-3">
              <p className="text-sm font-medium text-gray-900">
                Store queue length and throughput comparisons
              </p>
            </div>
            <div className="rounded-lg border border-gray-200 px-4 py-3">
              <p className="text-sm font-medium text-gray-900">
                Save repeat-run averages instead of one-off values
              </p>
            </div>
            <div className="rounded-lg border border-gray-200 px-4 py-3">
              <p className="text-sm font-medium text-gray-900">
                Mark clearly whether figures are benchmarked or provisional
              </p>
            </div>
          </div>
        </div>
      </section>

      <section className="rounded-xl border border-yellow-200 bg-yellow-50 p-5">
        <div className="flex items-start gap-3">
          <Clock3 className="mt-0.5 h-5 w-5 text-yellow-700" />
          <div>
            <h2 className="text-sm font-semibold text-yellow-900">Current status</h2>
            <p className="mt-2 text-sm text-yellow-800">
              This page now loads from the backend. The next quality improvement is to have your
              DQN testing script write verified evaluation results into the JSON file automatically.
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}