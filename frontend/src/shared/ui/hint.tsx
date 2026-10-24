import type { ReactElement, ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "./tooltip";

/** Подсказка при наведении и фокусе. Ребёнок должен принимать ref и props (span, button, Badge). */
export function Hint({ text, children }: { text?: ReactNode; children: ReactElement }) {
  if (!text) return children;
  // Свой Provider: подсказка работает и вне AppProviders (изолированные виджеты, тесты).
  return (
    <TooltipProvider delayDuration={300}>
      <Tooltip>
        <TooltipTrigger asChild>{children}</TooltipTrigger>
        <TooltipContent className="max-w-xs">{text}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

/** Значок «?» рядом с заголовком: объясняет, что это и зачем. Текст читается как описание кнопки. */
export function HelpTip({ text }: { text: string }) {
  const { t } = useTranslation();
  return (
    <Hint text={text}>
      <button
        type="button"
        aria-label={t("help")}
        className="ml-1 inline-flex size-4 cursor-help items-center justify-center rounded-full border align-middle text-[10px] leading-none font-normal text-muted-foreground"
      >
        ?
      </button>
    </Hint>
  );
}
