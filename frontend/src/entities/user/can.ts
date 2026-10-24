import type { Me, Permission } from "./types";

/** Только UX-подсказка: сервер проверяет права сам (FE-T0.18 §15). */
export function can(me: Pick<Me, "permissions"> | null | undefined, perm: Permission): boolean {
  return Boolean(me?.permissions.includes(perm));
}
