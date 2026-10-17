import type { z } from "zod";
import { Overview, Week } from "./schemas";

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

async function getJSON<S extends z.ZodTypeAny>(path: string, schema: S): Promise<z.infer<S>> {
  let res: Response;
  try {
    res = await fetch(path, { headers: { Accept: "application/json" } });
  } catch {
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

/**
 * One request per endpoint per page load, shared by the shell and every page (the files are static snapshots on the
 * host). `fresh` re-fetches, for the live local server while a run is in progress.
 */
const cache = new Map<string, Promise<unknown>>();
function cached<S extends z.ZodTypeAny>(path: string, schema: S, fresh = false): Promise<z.infer<S>> {
  if (fresh || !cache.has(path)) {
    const p = getJSON(path, schema);
    p.catch(() => cache.delete(path)); // a failed request is retried next time
    cache.set(path, p);
  }
  return cache.get(path) as Promise<z.infer<S>>;
}

export const getOverview = (fresh = false) => cached("/api/overview", Overview, fresh);
export const getWeek = (fresh = false) => cached("/api/week", Week, fresh);

export function clearApiCache() {
  cache.clear();
}
