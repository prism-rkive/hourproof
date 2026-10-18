import type { z } from "zod";
import type * as Schemas from "./schemas";

/** The response schemas by name. They (and zod) load on the first request, which never happens during hydration. */
type SchemaName = "Overview" | "Week" | "Carbon" | "RunLog";
type Parsed<K extends SchemaName> = z.infer<(typeof Schemas)[K]>;

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

async function getJSON<K extends SchemaName>(path: string, name: K): Promise<Parsed<K>> {
  let res: Response;
  try {
    res = await fetch(path, { headers: { Accept: "application/json" } });
  } catch {
    throw new ApiError(`Could not reach ${path}`, path);
  }
  if (!res.ok) throw new ApiError(`${path} answered HTTP ${res.status}`, path, res.status);
  const [body, schemas] = await Promise.all([res.json(), import("./schemas")]);
  const parsed = (schemas[name] as z.ZodTypeAny).safeParse(body);
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
function cached<K extends SchemaName>(path: string, name: K, fresh = false): Promise<Parsed<K>> {
  if (fresh || !cache.has(path)) {
    const p = getJSON(path, name);
    p.catch(() => cache.delete(path)); // a failed request is retried next time
    cache.set(path, p);
  }
  return cache.get(path) as Promise<Parsed<K>>;
}

export const getOverview = (fresh = false) => cached("/api/overview", "Overview", fresh);
export const getWeek = (fresh = false) => cached("/api/week", "Week", fresh);
export const getCarbon = (fresh = false) => cached("/api/carbon", "Carbon", fresh);
export const getLog = (fresh = false) => cached("/api/demo/log", "RunLog", fresh);

/** Start a run on the local server (the hosted snapshot cannot). Same request as the original dashboard. */
export async function startRun(network: "local" | "base-sepolia"): Promise<string | null> {
  const r = await fetch("/api/demo/run", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ network, zk_mode: "real", mode: "carbon" }),
  });
  if (r.ok) return null;
  const e = (await r.json().catch(() => ({}))) as { error?: string };
  return e.error || `Could not start the run (HTTP ${r.status}).`;
}

export function clearApiCache() {
  cache.clear();
}
