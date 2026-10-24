import { Hint } from "@/shared/ui";

import { sourceInitials } from "./sourceInitials";

/**
 * Квадрат слева от события: инициалы самого надёжного источника, +N — остальные.
 * Полные имена — в подсказке (top — до трёх лучших по уровню доверия).
 */
export function SourceMark({ top, total }: { top: { name: string }[]; total: number }) {
  const names = top.map((s) => s.name);
  const [first] = names;
  if (!first) return <span aria-hidden className="size-10" />;
  const more = total - names.length;
  const label = more > 0 ? `${names.join(", ")} +${more}` : names.join(", ");
  return (
    <Hint text={label}>
      <span className="bg-secondary text-foreground relative flex size-10 rounded-md shrink-0 items-center justify-center text-xs font-bold tracking-tight">
        <span aria-hidden>{sourceInitials(first)}</span>
        <span className="sr-only">{label}</span>
        {total > 1 ? (
          <span
            aria-hidden
            className="bg-foreground text-background ring-background absolute -right-1.5 -bottom-1.5 min-w-4 rounded-full px-1 ring-2 text-center text-[10px] leading-4"
          >
            +{total - 1}
          </span>
        ) : null}
      </span>
    </Hint>
  );
}
