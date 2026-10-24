import { Link } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";

export function NotFoundPage() {
  const { t } = useTranslation();
  return (
    <section className="mx-auto max-w-xl p-8">
      <h1 className="font-display text-xl font-bold">{t("notFound.title")}</h1>
      <Link to="/" className="mt-4 inline-block underline">
        {t("notFound.back")}
      </Link>
    </section>
  );
}
