import type { Me } from "@/entities/user";

export interface TransitionOption {
  to: string;
  minRole: string;
}

/** Ключ подписи по паре from→to (FE-T3.3 §7). */
export function labelKey(from: string, to: string): string {
  if (from === "REVIEWING" && to === "NEW") return "workflow.return";
  if (from === "READY" && to === "DRAFT") return "workflow.back_to_edit";
  if (from === "REJECTED" && to === "NEW") return "workflow.restore";
  return `workflow.to.${to}`;
}

export const HOTKEYS: Record<string, string> = { REVIEWING: "t", SELECTED: "s", REJECTED: "r" };

/** Доступные переходы из /me.allowed_transitions; SELECTED → DRAFT вручную не показывается. */
export function availableTransitions(me: Me, status: string): TransitionOption[] {
  const all = (me.allowed_transitions[status] ?? []) as { to: string; min_role: string }[];
  return all
    .filter((o) => !(status === "SELECTED" && o.to === "DRAFT"))
    .map((o) => ({ to: o.to, minRole: o.min_role }));
}
