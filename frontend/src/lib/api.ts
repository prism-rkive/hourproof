import type { z } from "zod";
import { Overview } from "./schemas";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly path: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function getJSON<S extends z.ZodTypeAny>(path: string, schema: S, signal?: AbortSignal): Promise<z.infer<S>> {
  let res: Response;
  try {
    res = await fetch(path, { signal, headers: { Accept: "application/json" } });
  } catch (e) {
    if (signal?.aborted) throw e;
    throw new ApiError(`Could not reach ${path}`, path);
  }
  if (!res.ok) throw new ApiError(`${path} answered HTTP ${res.status}`, path, res.status);
  const parsed = schema.safeParse(await res.json());
  if (!parsed.success) {
    const issue = parsed.error.issues[0];
    throw new ApiError(
      `${path} returned unexpected data (${issue?.path.join(".") || "root"}: ${issue?.message})`,
      path,
    );
  }
  return parsed.data;
}

export const fetchOverview = (signal?: AbortSignal) => getJSON("/api/overview", Overview, signal);
