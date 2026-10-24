import { useTranslation } from "react-i18next";

import { parseRationale } from "./rationale-parse";

const signed = (n: number) => (n > 0 ? `+${n}` : `−${Math.abs(n)}`);

/** «Почему важно» на языке интерфейса: сработавшие сигналы с баллами и поправки уровня. */
export function RelevanceRationale({ text }: { text: string }) {
  const { t } = useTranslation("event");
  if (!text) return <p className="text-sm">—</p>;
  const r = parseRationale(text);
  const total = r.parts.reduce((s, p) => s + p.points, 0);
  return (
    <div className="space-y-1 text-sm">
      {r.raw ? <p>{r.raw}</p> : null}
      {r.base ? <p>{t(`rationale.${r.base}`)}</p> : null}
      {r.parts.length ? (
        <ul aria-label={t("rationale.signals")} className="space-y-0.5">
          {r.parts.map((p, i) => (
            <li key={i} className="flex justify-between gap-3">
              <span className="min-w-0">
                {p.kind === "rule"
                  ? p.name
                  : t(`rationale.${p.kind}${p.name ? "" : "_plain"}`, { name: p.name })}
              </span>
              <span className="shrink-0 tabular-nums">{signed(p.points)}</span>
            </li>
          ))}
          <li className="text-muted-foreground flex justify-between gap-3 border-t pt-0.5">
            <span>{t("rationale.total")}</span>
            <span className="tabular-nums">{total}</span>
          </li>
        </ul>
      ) : null}
      {r.mods.map((m) => (
        <p key={m} className="text-muted-foreground text-xs">
          {t(`rationale.mod.${m}`)}
        </p>
      ))}
    </div>
  );
}
