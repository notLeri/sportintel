import { useId } from "react";

import { cn } from "@/shared/lib/utils";

/** Контуры знака «Si» (вектор логотипа SportIntel); точка «i» — отдельно, чтобы анимировать её появление. */
export const LOGO_S =
  "M757 322 678 415H488Q472 418 478 432L668 516C705 532 728 562 728 600 728 655 685 693 620 693H343L420 603H592Q610 598 597 588L425 509C390 494 365 470 365 440 365 375 420 322 485 322Z";
export const LOGO_I_DOT =
  "M804 322H874Q898 322 898 346V396Q898 420 874 420H804Q780 420 780 396V346Q780 322 804 322Z";
export const LOGO_I_STEM =
  "M790 456H874Q896 456 896 478V671Q896 695 872 695H804Q780 695 780 671V466Q780 456 790 456Z";

/**
 * Знак SportIntel: «S» цветом текста, «i» — акцентом текущей палитры (--brand-bright).
 * Рассчитан на тёмный фон (полоса навигации, панель входа).
 */
export function BrandMark({ className, animated }: { className?: string; animated?: boolean }) {
  // useId содержит «:»/«»» — в url(#…) безопаснее только латиница и цифры.
  const id = "logo" + useId().replace(/[^\w-]/g, "");
  return (
    <svg
      viewBox="336 314 568 386"
      aria-hidden
      className={cn("h-7 w-auto shrink-0", animated && "logo-in", className)}
    >
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="1" y2="1">
          <stop
            offset="0"
            style={{ stopColor: "color-mix(in oklab, var(--brand-bright), white 30%)" }}
          />
          <stop offset="1" style={{ stopColor: "var(--brand-bright)" }} />
        </linearGradient>
      </defs>
      <path className="logo-s" d={LOGO_S} fill="currentColor" />
      <path className="logo-i" d={LOGO_I_STEM} fill={`url(#${id})`} />
      <path className="logo-dot" d={LOGO_I_DOT} fill={`url(#${id})`} />
    </svg>
  );
}

/** Знак + надпись «SportIntel» («Intel» — акцентом), для панели входа. */
export function BrandLogo({ className, animated }: { className?: string; animated?: boolean }) {
  return (
    <span className={cn("inline-flex items-center gap-3", className)}>
      <BrandMark animated={animated} className="h-[1.6em]" />
      <span className="font-display leading-none font-extrabold tracking-tight">
        Sport<span className="text-brand-bright">Intel</span>
      </span>
    </span>
  );
}
