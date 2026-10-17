/**
 * Runtime schemas for the JSON API (hourproof/server.py; the hosted site serves the exported snapshot of the same
 * handlers). Only the fields the UI reads are declared; unknown fields pass through. A response that does not match
 * fails loudly in the page's error state instead of rendering a wrong or empty figure.
 */
import { z } from "zod";

export const RunStatus = z.enum(["running", "done", "failed"]).or(z.string());

export const DemoState = z
  .object({
    run_id: z.string(),
    network: z.string(),
    status: RunStatus,
    mode: z.string().optional(),
    zk_mode: z.string().optional(),
    started_utc: z.string().optional(),
    finished_utc: z.string().nullish(),
  })
  .passthrough();

export const StaticSnapshot = z
  .object({
    run_id: z.string(),
    network: z.string(),
    verification: z.string(),
    evidence: z.string(),
    exported_utc: z.string(),
  })
  .passthrough();

export const Overview = z
  .object({
    running: z.boolean(),
    demo: DemoState.nullable(),
    static_snapshot: StaticSnapshot.optional(),
  })
  .passthrough();

export type Overview = z.infer<typeof Overview>;
export type DemoState = z.infer<typeof DemoState>;
