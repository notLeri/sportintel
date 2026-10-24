import { useTranslation } from "react-i18next";

/** Заглушка экрана до его задачи (FE-T0.8). */
export function Placeholder({ title }: { title: string }) {
  const { t } = useTranslation();
  return (
    <section aria-labelledby="page-title" className="mx-auto max-w-3xl p-8">
      <h1 id="page-title" className="font-display text-2xl font-bold">
        {title}
      </h1>
      <p className="text-muted-foreground mt-2">
        {t("placeholder.title")} — {t("placeholder.body")}
      </p>
    </section>
  );
}
