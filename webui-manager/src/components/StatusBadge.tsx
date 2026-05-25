import { useI18n } from "@/i18n";

const STATUS_COLORS: Record<string, string> = {
  running: "bg-green-100 text-green-800",
  stopped: "bg-gray-100 text-gray-800",
  error: "bg-red-100 text-red-800",
  creating: "bg-yellow-100 text-yellow-800",
};

export default function StatusBadge({ status }: { status: string }) {
  const { t } = useI18n();
  const label = t(`status.${status}` as `status.${string}`);
  return (
    <span
      className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_COLORS[status] || "bg-gray-100 text-gray-800"}`}
    >
      {label.includes(".") ? status : label}
    </span>
  );
}
