import { cn } from "@/shared/lib/utils";

/** Полоса прогресса. value 0…1; null — сколько осталось, неизвестно (бегущая полоса). */
export function Progress({
  value,
  label,
  className,
}: {
  value: number | null;
  label: string;
  className?: string;
}) {
  const pct = value === null ? null : Math.round(Math.min(1, Math.max(0, value)) * 100);
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={pct ?? undefined}
      className={cn("bg-muted h-1.5 w-full overflow-hidden rounded-full", className)}
    >
      <div
        className={cn(
          "bg-primary h-full rounded-full transition-[width] duration-700 ease-out",
          pct === null && "w-1/3 animate-pulse",
        )}
        style={pct === null ? undefined : { width: `${pct}%` }}
      />
    </div>
  );
}
