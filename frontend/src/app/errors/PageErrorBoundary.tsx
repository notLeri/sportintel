import { Component, type ErrorInfo, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { isAppError } from "@/shared/api";
import { Button } from "@/shared/ui";

import { captureException } from "../telemetry";

const CHUNK_ERROR_RE =
  /Failed to fetch dynamically imported module|Importing a module script failed/i;

export function ErrorFallback({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const { t } = useTranslation("errors");
  const isChunk = error instanceof Error && CHUNK_ERROR_RE.test(error.message);
  return (
    <section role="alert" className="mx-auto max-w-xl p-8">
      <h1 className="font-display text-xl font-bold">{t("page.title")}</h1>
      <p className="text-muted-foreground mt-2">{isChunk ? t("page.chunk") : t("page.body")}</p>
      {isAppError(error) && error.requestId ? (
        <p className="text-muted-foreground mt-2 font-mono text-sm">
          {t("page.requestId", { id: error.requestId })}
        </p>
      ) : null}
      {onRetry && !isChunk ? (
        <Button className="mt-4" onClick={onRetry}>
          {t("page.retry")}
        </Button>
      ) : (
        <Button className="mt-4" onClick={() => window.location.reload()}>
          {t("page.reload")}
        </Button>
      )}
    </section>
  );
}

interface Props {
  children: ReactNode;
}

interface State {
  error: unknown;
}

export class PageErrorBoundary extends Component<Props, State> {
  override state: State = { error: null };

  static getDerivedStateFromError(error: unknown): State {
    return { error };
  }

  override componentDidCatch(error: unknown, info: ErrorInfo): void {
    captureException(error, { route: window.location.pathname });
    console.error("page error", error, info.componentStack);
  }

  override render() {
    return this.state.error ? <ErrorFallback error={this.state.error} /> : this.props.children;
  }
}
