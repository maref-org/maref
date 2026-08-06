/**
 * MAREF Frontend OpenTelemetry Instrumentation
 *
 * Provides trace context injection for all API requests,
 * allowing end-to-end tracing from Frontend → Backend → Sidecar → Governance.
 */

let _currentTraceId: string | null = null;
let _otelInitialized = false;

export interface TraceContext {
  traceId: string | null;
  spanId?: string;
  parentSpanId?: string;
}

export function initOtel(serviceName = "maref-frontend", version = "0.26.0"): void {
  if (_otelInitialized) return;
  _otelInitialized = true;

  if (typeof window !== "undefined") {
    console.log(`[MAREF OTel] Frontend instrumentation initialized: ${serviceName}@${version}`);
  }
}

export function generateTraceId(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return Array.from(bytes)
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export function startTrace(operationName: string, attributes?: Record<string, string>): TraceContext {
  const traceId = generateTraceId();
  _currentTraceId = traceId;

  if (typeof window !== "undefined" && import.meta.env.DEV) {
    console.debug(`[MAREF OTel] start_trace: ${operationName} trace_id=${traceId}`, attributes);
  }

  return { traceId };
}

export function getCurrentTraceId(): string | null {
  return _currentTraceId;
}

export function injectTraceHeaders(headers: HeadersInit = {}): HeadersInit {
  const traceId = _currentTraceId;
  if (!traceId) return headers;

  const newHeaders: Record<string, string> = {
    ...(headers as Record<string, string>),
    "X-Trace-ID": traceId,
    "X-Client-Name": "maref-frontend",
    "X-Client-Version": "0.26.0",
  };

  return newHeaders;
}

export function endTrace(context?: TraceContext): void {
  _currentTraceId = null;

  if (typeof window !== "undefined" && import.meta.env.DEV) {
    console.debug("[MAREF OTel] end_trace", context);
  }
}

export async function traceRequest<T>(
  operationName: string,
  fetchFn: () => Promise<Response>,
  attributes?: Record<string, string>,
): Promise<T> {
  const traceCtx = startTrace(operationName, attributes);

  try {
    const response = await fetchFn();
    const serverTraceId = response.headers.get("X-Trace-ID");

    if (serverTraceId) {
      _currentTraceId = serverTraceId;
    }

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    const data = await response.json();
    endTrace(traceCtx);
    return data as T;
  } catch (error) {
    if (typeof window !== "undefined") {
      console.error(`[MAREF OTel] trace_error: ${operationName}`, error);
    }
    endTrace(traceCtx);
    throw error;
  }
}

export function createTracedFetch(baseUrl: string): typeof fetch {
  return async function tracedFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
    const url = typeof input === "string" && input.startsWith("/") ? `${baseUrl}${input}` : input;
    const traceId = generateTraceId();
    _currentTraceId = traceId;

    const mergedInit: RequestInit = {
      ...init,
      headers: {
        "Content-Type": "application/json",
        "X-Trace-ID": traceId,
        "X-Client-Name": "maref-frontend",
        ...((init?.headers as Record<string, string>) || {}),
      },
    };

    const response = await fetch(url, mergedInit);

    const serverTraceId = response.headers.get("X-Trace-ID");
    if (serverTraceId) {
      _currentTraceId = serverTraceId;
    }

    return response;
  };
}
