/**
 * Runtime schemas for the JSON API (hourproof/server.py; the hosted site serves the exported snapshot of the same
 * handlers). Only the fields the UI reads are declared; unknown fields pass through. A response that does not match
 * fails loudly in the page's error state instead of rendering a wrong or empty figure.
 */
import { z } from "zod";

export const Tx = z
  .object({
    hash: z.string(),
    label: z.string(),
    gas: z.number(),
    url: z.string().nullish(),
    block: z.number().nullish(),
    role: z.string().nullish(),
  })
  .passthrough();

export const Step = z
  .object({
    id: z.string(),
    title: z.string(),
    status: z.string(),
    seconds: z.number().nullish(),
    detail: z.string().nullish(),
    metrics: z.record(z.unknown()).default({}),
    txs: z.array(Tx).default([]),
  })
  .passthrough();

export const Attack = z
  .object({
    id: z.string(),
    title: z.string(),
    expected: z.string().nullish(),
    observed: z.string().nullish(),
    status: z.string(),
    note: z.string().nullish(),
  })
  .passthrough();

export const DemoState = z
  .object({
    run_id: z.string(),
    network: z.string(),
    status: z.string(),
    mode: z.string().optional(),
    zk_mode: z.string().optional(),
    started_utc: z.string().optional(),
    finished_utc: z.string().nullish(),
    steps: z.array(Step).default([]),
    attacks: z.array(Attack).default([]),
    summary: z.record(z.unknown()).nullish(),
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

export const Dataset = z
  .object({
    hourly_match_of_100pct_annual_wind: z.number(),
    buyer_label: z.string().nullish(),
    year: z.number().nullish(),
    hours: z.number().nullish(),
    source: z.string().nullish(),
  })
  .passthrough();

export const Overview = z
  .object({
    running: z.boolean(),
    demo: DemoState.nullable(),
    dataset: Dataset.nullable(),
    annual_match: z.number().nullable(),
    backtest: z.record(z.unknown()).nullable(),
    static_snapshot: StaticSnapshot.optional(),
  })
  .passthrough();

const series = z.array(z.number());
export const Week = z.union([
  z.object({ available: z.literal(false) }),
  z
    .object({
      available: z.literal(true),
      source: z.string(),
      window_start_utc: z.string(),
      hours: z.array(z.string()),
      base_mwh: series,
      topup_mwh: series,
      private_agent_load_mwh: series,
      private_naive_load_mwh: series,
      coverage_naive: z.number(),
      coverage_agent: z.number(),
    })
    .passthrough(),
]);

export const RunLog = z
  .object({
    log: z.string(),
    running: z.boolean(),
    recorded: z.boolean().optional(), // the hosted snapshot: the verified run's recorded console output
    run_id: z.string().optional(),
    source: z.string().optional(),
  })
  .passthrough();

export const Carbon = z.union([
  z.object({ available: z.literal(false) }),
  z
    .object({
      available: z.literal(true),
      test_period: z.tuple([z.string(), z.string()]),
      test_hours: z.number(),
      mae: z.record(z.number()),
      improvement_vs_best_persistence: z.number(),
      strategies: z.array(
        z
          .object({
            id: z.string(),
            label: z.string(),
            reference: z.boolean(),
            emissions_t: z.number(),
            residual_unmatched_t: z.number(),
            coverage: z.number(),
          })
          .passthrough(),
      ),
      robustness: z.record(z.record(z.unknown())),
      frozen_config: z.object({ flex_share: z.number(), flex_cap: z.number() }),
      caveats: z.array(z.string()),
      week: z
        .object({
          source: z.string(),
          hours: z.array(z.string()),
          intensity: z.array(z.number()),
          forecast: z.array(z.number()),
          shift_mwh: z.array(z.number()),
          mae: z.record(z.number()).nullish(),
        })
        .optional(),
      proof: z.record(z.unknown()).optional(),
    })
    .passthrough(),
]);

export type RunLog = z.infer<typeof RunLog>;
export type Carbon = z.infer<typeof Carbon>;
export type CarbonData = Extract<Carbon, { available: true }>;
export type Overview = z.infer<typeof Overview>;
export type DemoState = z.infer<typeof DemoState>;
export type Step = z.infer<typeof Step>;
export type Tx = z.infer<typeof Tx>;
export type Week = z.infer<typeof Week>;
export type WeekData = Extract<Week, { available: true }>;
