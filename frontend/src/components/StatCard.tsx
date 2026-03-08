// src/components/StatCard.tsx
interface StatCardProps {
  label: string;
  value: string;
  sublabel: string;
}

export function StatCard({ label, value, sublabel }: StatCardProps) {
  return (
    <div className="bg-white p-6 rounded-lg border border-gray-200 shadow-sm">
      <p className="text-sm font-medium text-gray-500">{label}</p>
      <p className="mt-1 text-3xl font-semibold text-gray-900">{value}</p>
      <p className="text-sm text-gray-500">{sublabel}</p>
    </div>
  );
}