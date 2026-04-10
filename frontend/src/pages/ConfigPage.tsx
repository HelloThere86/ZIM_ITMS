import { useEffect, useState } from "react";
import {
  Settings,
  Camera,
  Shield,
  Save,
  RotateCcw,
  SlidersHorizontal,
  RefreshCw,
} from "lucide-react";
import { getConfig, updateConfig } from "../services/config";

const DEFAULTS = {
  clipDuration: "15s",
  imageQuality: "High",
  autoFlagThreshold: 85,
  reviewThreshold: 75,
};

function configArrayToMap(items: { key: string; value: string }[]) {
  return Object.fromEntries(items.map((item) => [item.key, item.value]));
}

export function ConfigPage() {
  const [clipDuration, setClipDuration] = useState(DEFAULTS.clipDuration);
  const [imageQuality, setImageQuality] = useState(DEFAULTS.imageQuality);
  const [autoFlagThreshold, setAutoFlagThreshold] = useState(DEFAULTS.autoFlagThreshold);
  const [reviewThreshold, setReviewThreshold] = useState(DEFAULTS.reviewThreshold);

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  function applyDefaults() {
    setClipDuration(DEFAULTS.clipDuration);
    setImageQuality(DEFAULTS.imageQuality);
    setAutoFlagThreshold(DEFAULTS.autoFlagThreshold);
    setReviewThreshold(DEFAULTS.reviewThreshold);
  }

  async function loadConfig() {
    try {
      setLoading(true);
      setError(null);
      setSuccessMessage(null);

      const items = await getConfig();
      const map = configArrayToMap(items);

      setClipDuration(map.clip_duration ?? DEFAULTS.clipDuration);
      setImageQuality(map.image_quality ?? DEFAULTS.imageQuality);
      setAutoFlagThreshold(Number(map.auto_flag_threshold ?? DEFAULTS.autoFlagThreshold));
      setReviewThreshold(Number(map.review_threshold ?? DEFAULTS.reviewThreshold));
    } catch (err) {
      console.error("Failed to load config:", err);
      setError("Failed to load configuration from backend. Default values are being shown.");
      applyDefaults();
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadConfig();
  }, []);

  function handleReset() {
    applyDefaults();
    setSuccessMessage(null);
    setError(null);
  }

  async function handleSave() {
    try {
      setSaving(true);
      setError(null);
      setSuccessMessage(null);

      const updates = [
        updateConfig("clip_duration", clipDuration, "Updated clip duration"),
        updateConfig("image_quality", imageQuality, "Updated image quality"),
        updateConfig(
          "auto_flag_threshold",
          String(autoFlagThreshold),
          "Updated auto-flag threshold"
        ),
        updateConfig(
          "review_threshold",
          String(reviewThreshold),
          "Updated review threshold"
        ),
      ];

      await Promise.all(updates);
      setSuccessMessage("Configuration saved successfully.");
    } catch (err) {
      console.error("Failed to save config:", err);
      setError("Failed to save one or more configuration values.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-8">
      <section className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="text-sm font-medium text-gray-500">Operational Parameters</p>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight text-gray-900">
            Detection & Capture Configuration
          </h1>
          <p className="mt-3 max-w-3xl text-sm text-gray-600">
            Manage the configurable parameters that affect evidence capture and automated
            detection behavior. This page is limited to operational settings that are
            intended to be adjusted by an administrator.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={loadConfig}
            className="inline-flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition hover:bg-gray-50"
          >
            <RefreshCw className="h-4 w-4" />
            Refresh
          </button>

          <div className="rounded-xl border border-green-200 bg-green-50 px-4 py-3">
            <p className="text-sm font-medium text-green-900">Configuration State</p>
            <p className="mt-1 text-lg font-semibold text-green-800">
              {loading ? "Loading..." : "Backend Synced"}
            </p>
          </div>
        </div>
      </section>

      {error && (
        <section className="rounded-xl border border-red-200 bg-red-50 p-4">
          <p className="text-sm font-semibold text-red-900">Backend issue</p>
          <p className="mt-1 text-sm text-red-800">{error}</p>
        </section>
      )}

      {successMessage && (
        <section className="rounded-xl border border-green-200 bg-green-50 p-4">
          <p className="text-sm font-semibold text-green-900">Saved</p>
          <p className="mt-1 text-sm text-green-800">{successMessage}</p>
        </section>
      )}

      <section className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
          <p className="text-sm font-medium text-gray-500">Auto-Flag Threshold</p>
          <p className="mt-2 text-3xl font-semibold text-gray-900">
            {loading ? "..." : `${autoFlagThreshold}%`}
          </p>
          <p className="mt-1 text-sm text-gray-500">Current detection trigger</p>
        </div>

        <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
          <p className="text-sm font-medium text-gray-500">Review Threshold</p>
          <p className="mt-2 text-3xl font-semibold text-gray-900">
            {loading ? "..." : `${reviewThreshold}%`}
          </p>
          <p className="mt-1 text-sm text-gray-500">Manual review boundary</p>
        </div>

        <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
          <p className="text-sm font-medium text-gray-500">Clip Duration</p>
          <p className="mt-2 text-3xl font-semibold text-gray-900">
            {loading ? "..." : clipDuration}
          </p>
          <p className="mt-1 text-sm text-gray-500">Recorded evidence length</p>
        </div>

        <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
          <p className="text-sm font-medium text-gray-500">Image Quality</p>
          <p className="mt-2 text-3xl font-semibold text-gray-900">
            {loading ? "..." : imageQuality}
          </p>
          <p className="mt-1 text-sm text-gray-500">Snapshot capture profile</p>
        </div>
      </section>

      <section className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <div className="xl:col-span-2 space-y-6">
          <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
            <div className="flex items-start gap-3">
              <div className="rounded-lg bg-gray-100 p-2">
                <Camera className="h-5 w-5 text-gray-700" />
              </div>
              <div>
                <h2 className="text-lg font-semibold text-gray-900">Capture Settings</h2>
                <p className="mt-1 text-sm text-gray-600">
                  Configure evidence clip length and stored image quality.
                </p>
              </div>
            </div>

            <div className="mt-6 grid grid-cols-1 gap-5 md:grid-cols-2">
              <div>
                <label className="mb-2 block text-sm font-medium text-gray-700">
                  Clip Duration
                </label>
                <select
                  value={clipDuration}
                  onChange={(e) => setClipDuration(e.target.value)}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 outline-none transition focus:border-gray-400"
                >
                  <option value="10s">10s</option>
                  <option value="15s">15s</option>
                  <option value="20s">20s</option>
                  <option value="30s">30s</option>
                </select>
                <p className="mt-2 text-xs text-gray-500">Length of recorded evidence clips.</p>
              </div>

              <div>
                <label className="mb-2 block text-sm font-medium text-gray-700">
                  Image Quality
                </label>
                <select
                  value={imageQuality}
                  onChange={(e) => setImageQuality(e.target.value)}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 outline-none transition focus:border-gray-400"
                >
                  <option value="Low">Low</option>
                  <option value="Medium">Medium</option>
                  <option value="High">High</option>
                  <option value="Ultra">Ultra</option>
                </select>
                <p className="mt-2 text-xs text-gray-500">Capture quality for stored snapshots.</p>
              </div>
            </div>
          </div>

          <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
            <div className="flex items-start gap-3">
              <div className="rounded-lg bg-gray-100 p-2">
                <Shield className="h-5 w-5 text-gray-700" />
              </div>
              <div>
                <h2 className="text-lg font-semibold text-gray-900">Detection Thresholds</h2>
                <p className="mt-1 text-sm text-gray-600">
                  Define how aggressively the system flags cases and routes them for review.
                </p>
              </div>
            </div>

            <div className="mt-6 grid grid-cols-1 gap-5 md:grid-cols-2">
              <div>
                <label className="mb-2 block text-sm font-medium text-gray-700">
                  Auto-Flag Threshold
                </label>
                <input
                  type="number"
                  min={0}
                  max={100}
                  value={autoFlagThreshold}
                  onChange={(e) => setAutoFlagThreshold(Number(e.target.value))}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 outline-none transition focus:border-gray-400"
                />
                <p className="mt-2 text-xs text-gray-500">
                  Confidence level required for automatic flagging.
                </p>
              </div>

              <div>
                <label className="mb-2 block text-sm font-medium text-gray-700">
                  Review Threshold
                </label>
                <input
                  type="number"
                  min={0}
                  max={100}
                  value={reviewThreshold}
                  onChange={(e) => setReviewThreshold(Number(e.target.value))}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 outline-none transition focus:border-gray-400"
                />
                <p className="mt-2 text-xs text-gray-500">
                  Cases below this level should be routed for human verification.
                </p>
              </div>
            </div>
          </div>
        </div>

        <div className="space-y-6">
          <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
            <div className="flex items-start gap-3">
              <div className="rounded-lg bg-gray-100 p-2">
                <SlidersHorizontal className="h-5 w-5 text-gray-700" />
              </div>
              <div>
                <h2 className="text-lg font-semibold text-gray-900">Current Parameter Summary</h2>
                <p className="mt-1 text-sm text-gray-600">
                  Snapshot of the stored operational parameters.
                </p>
              </div>
            </div>

            <div className="mt-6 space-y-4">
              <div className="rounded-lg border border-gray-200 px-4 py-3">
                <p className="text-xs uppercase tracking-wide text-gray-500">Detection Mode</p>
                <p className="mt-1 text-sm font-medium text-gray-900">
                  Auto-flag at {autoFlagThreshold}%, review below {reviewThreshold}%
                </p>
              </div>

              <div className="rounded-lg border border-gray-200 px-4 py-3">
                <p className="text-xs uppercase tracking-wide text-gray-500">Capture Profile</p>
                <p className="mt-1 text-sm font-medium text-gray-900">
                  {clipDuration} clips · {imageQuality} quality
                </p>
              </div>
            </div>
          </div>

          <div className="rounded-xl border border-blue-200 bg-blue-50 p-5">
            <div className="flex items-start gap-3">
              <Settings className="mt-0.5 h-5 w-5 text-blue-700" />
              <div>
                <h2 className="text-sm font-semibold text-blue-900">Current status</h2>
                <p className="mt-2 text-sm text-blue-800">
                  This page stores only operational parameters that are intended to affect
                  evidence capture and detection behavior.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">Save Configuration</h2>
            <p className="mt-1 text-sm text-gray-600">
              These values persist through the backend and should appear in the audit trail.
            </p>
          </div>

          <div className="flex gap-3">
            <button
              onClick={handleReset}
              disabled={saving}
              className="inline-flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-5 py-2 text-sm font-medium text-gray-700 transition hover:bg-gray-50 disabled:opacity-50"
            >
              <RotateCcw className="h-4 w-4" />
              Reset
            </button>

            <button
              onClick={handleSave}
              disabled={saving || loading}
              className="inline-flex items-center gap-2 rounded-lg bg-gray-800 px-5 py-2 text-sm font-medium text-white transition hover:bg-gray-900 disabled:opacity-50"
            >
              <Save className="h-4 w-4" />
              {saving ? "Saving..." : "Save Changes"}
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}