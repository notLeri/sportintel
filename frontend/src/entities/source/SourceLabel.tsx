import { Badge } from "@/shared/ui";

export function SourceLabel({ name, tier }: { name: string; tier: string | null | undefined }) {
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
      <span>{name}</span>
      {tier ? <Badge variant="outline">{tier}</Badge> : null}
    </span>
  );
}
