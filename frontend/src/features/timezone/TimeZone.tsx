import { ClockIcon } from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { useMe, useSetTimeZone } from "@/entities/user";
import { deviceTimeZone, sameOffset, zoneLabel, zoneOffset } from "@/shared/lib/datetime";
import { Button, HelpTip, toast } from "@/shared/ui";

const keepKey = (userId: string) => `tz-keep:${userId}`;

function readKeep(userId: string): string | null {
  try {
    return localStorage.getItem(keepKey(userId));
  } catch {
    return null;
  }
}

/** Пояс профиля не совпадает с часами устройства — предупредить, пока человек не выбрал.
 * Пояс устройства — из системных часов, а не по IP: VPN его не меняет. */
export function TimeZoneBanner() {
  const { t } = useTranslation(["common", "hints"]);
  const me = useMe();
  const set = useSetTimeZone();
  const device = deviceTimeZone();
  const pair = `${me.timezone}|${device}`;
  const [kept, setKept] = useState(() => readKeep(me.id));
  if (sameOffset(me.timezone, device) || kept === pair) return null;
  const keep = () => {
    try {
      localStorage.setItem(keepKey(me.id), pair);
    } catch {
      /* без хранилища — просто скрыть до перезагрузки */
    }
    setKept(pair);
  };
  return (
    <div
      role="status"
      className="bg-attention text-attention-foreground flex flex-wrap items-center gap-3 px-4 py-2 text-sm"
    >
      <ClockIcon aria-hidden className="size-4 shrink-0" />
      <span>
        {t("tz.mismatch", { profile: zoneLabel(me.timezone), device: zoneLabel(device) })}
        <HelpTip text={t("hints:tz.mismatch")} />
      </span>
      <span className="ml-auto flex gap-2">
        <Button
          size="sm"
          disabled={set.isPending}
          onClick={() =>
            set.mutate(device, {
              onSuccess: () => toast.success(t("tz.changed", { zone: zoneLabel(device) })),
              onError: () => toast.error(t("tz.change_failed")),
            })
          }
        >
          {t("tz.use_device", { zone: zoneLabel(device) })}
        </Button>
        <Button size="sm" variant="ghost" onClick={keep}>
          {t("tz.keep", { zone: zoneLabel(me.timezone) })}
        </Button>
      </span>
    </div>
  );
}

/** Часовой пояс профиля: «как на устройстве» первым, остальные — по смещению. */
export function TimeZoneSelect({ id }: { id?: string }) {
  const { t } = useTranslation(["common", "hints"]);
  const me = useMe();
  const set = useSetTimeZone();
  const device = deviceTimeZone();
  const zones = useMemo(() => {
    const all = Intl.supportedValuesOf("timeZone");
    if (!all.includes(me.timezone)) all.push(me.timezone);
    const minutes = (z: string) => {
      const m = /GMT([+−])?(\d+)?(?::(\d+))?/.exec(zoneOffset(z));
      const v = Number(m?.[2] ?? 0) * 60 + Number(m?.[3] ?? 0);
      return m?.[1] === "−" ? -v : v;
    };
    return all
      .map((z) => ({ z, m: minutes(z) }))
      .sort((a, b) => a.m - b.m || a.z.localeCompare(b.z));
  }, [me.timezone]);
  return (
    <span className="inline-flex items-center gap-1">
      <label htmlFor={id ?? "tz-select"} className="text-muted-foreground text-xs">
        {t("tz.label")}
      </label>
      <select
        id={id ?? "tz-select"}
        className="border-input h-7 max-w-[15rem] rounded-md border bg-transparent px-1 text-xs"
        value={me.timezone}
        disabled={set.isPending}
        onChange={(e) =>
          set.mutate(e.target.value, {
            onSuccess: () => toast.success(t("tz.changed", { zone: zoneLabel(e.target.value) })),
            onError: () => toast.error(t("tz.change_failed")),
          })
        }
      >
        {device !== me.timezone ? (
          <option value={device}>{t("tz.device_option", { zone: zoneLabel(device) })}</option>
        ) : null}
        {zones.map(({ z }) => (
          <option key={z} value={z}>
            {zoneOffset(z)} · {z.replace(/_/g, " ")}
          </option>
        ))}
      </select>
      <HelpTip text={t("hints:tz.select")} />
    </span>
  );
}
