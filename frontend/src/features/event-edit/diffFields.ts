import type { EventDetail } from "@/entities/event";

export interface EditValues {
  title: string;
  summary: string;
  sport_id: string;
  competition_id: string;
  team_ids: string[];
  player_ids: string[];
}

export function valuesOf(e: EventDetail): EditValues {
  return {
    title: e.title,
    summary: e.summary?.text ?? "",
    sport_id: e.sport_id ?? "",
    competition_id: e.competition?.id ?? "",
    team_ids: e.teams.map((x) => x.id),
    player_ids: e.players.map((x) => x.id),
  };
}

const same = (a: unknown, b: unknown) =>
  Array.isArray(a) && Array.isArray(b) ? [...a].sort().join() === [...b].sort().join() : a === b;

/** Изменённые пользователем поля → тело PATCH (null для очищенных). */
export function changedPatch(base: EditValues, mine: EditValues): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const k of Object.keys(mine) as (keyof EditValues)[]) {
    if (same(base[k], mine[k])) continue;
    const v = mine[k];
    out[k] = Array.isArray(v) ? v : v === "" && k !== "title" ? null : v;
  }
  return out;
}

export interface DiffRow {
  field: keyof EditValues;
  base: unknown;
  mine: unknown;
  theirs: unknown;
}

/** Поля, изменённые другим пользователем после входа в режим правки (FE-T3.5 §7). */
export function diffFields(base: EditValues, mine: EditValues, theirs: EventDetail): DiffRow[] {
  const t = valuesOf(theirs);
  return (Object.keys(base) as (keyof EditValues)[])
    .filter((k) => !same(base[k], t[k]))
    .map((k) => ({ field: k, base: base[k], mine: mine[k], theirs: t[k] }));
}
