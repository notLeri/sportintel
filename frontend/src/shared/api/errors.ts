// Единая ошибка API (CONV §5.2). Компоненты не разбирают Response сами (CONV §11).

export interface FieldError {
  field: string;
  code: string;
  message: string;
}

interface AppErrorInit {
  status: number;
  code: string;
  title: string;
  detail?: string;
  requestId?: string;
  fieldErrors?: FieldError[];
  current?: unknown;
  retryAfterS?: number;
}

const isRecord = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null;

/** `Retry-After`: секунды или HTTP-дата → секунды (≥ 0). */
export function parseRetryAfter(header: string | null, now = Date.now()): number | undefined {
  if (!header) return undefined;
  const seconds = Number(header);
  if (Number.isFinite(seconds)) return Math.max(0, Math.round(seconds));
  const at = Date.parse(header);
  return Number.isNaN(at) ? undefined : Math.max(0, Math.round((at - now) / 1000));
}

export class AppError extends Error {
  readonly status: number;
  readonly code: string;
  readonly title: string;
  readonly requestId?: string;
  readonly fieldErrors: FieldError[];
  readonly current?: unknown;
  readonly retryAfterS?: number;

  constructor(init: AppErrorInit) {
    super(init.detail ?? init.title);
    this.name = "AppError";
    this.status = init.status;
    this.code = init.code;
    this.title = init.title;
    this.requestId = init.requestId;
    this.fieldErrors = init.fieldErrors ?? [];
    this.current = init.current;
    this.retryAfterS = init.retryAfterS;
  }

  /** Тело problem+json → AppError; не-JSON (502 от прокси) → common.internal. */
  static fromProblem(
    problem: unknown,
    status: number,
    extra: { requestId?: string; retryAfterS?: number } = {},
  ): AppError {
    if (!isRecord(problem) || typeof problem.code !== "string") {
      return new AppError({
        status,
        code: "common.internal",
        title: "Internal error",
        requestId: extra.requestId,
        retryAfterS: extra.retryAfterS,
      });
    }
    const fieldErrors = Array.isArray(problem.errors)
      ? problem.errors.filter(isRecord).map((e) => ({
          field: String(e.field ?? ""),
          code: String(e.code ?? ""),
          message: String(e.message ?? ""),
        }))
      : [];
    return new AppError({
      status,
      code: problem.code,
      title: typeof problem.title === "string" ? problem.title : problem.code,
      detail: typeof problem.detail === "string" ? problem.detail : undefined,
      requestId: typeof problem.request_id === "string" ? problem.request_id : extra.requestId,
      fieldErrors,
      current: problem.current ?? undefined,
      retryAfterS: extra.retryAfterS,
    });
  }

  static async fromResponse(response: Response): Promise<AppError> {
    const requestId = response.headers.get("x-request-id") ?? undefined;
    const retryAfterS = parseRetryAfter(response.headers.get("retry-after"));
    let body: unknown = null;
    if ((response.headers.get("content-type") ?? "").includes("json")) {
      body = await response.json().catch(() => null);
    }
    return AppError.fromProblem(body, response.status, { requestId, retryAfterS });
  }

  static network(cause?: unknown): AppError {
    const err = new AppError({ status: 0, code: "network.offline", title: "Network error" });
    if (cause !== undefined) Object.defineProperty(err, "cause", { value: cause });
    return err;
  }
}

export function isAppError(err: unknown): err is AppError {
  return err instanceof AppError;
}
