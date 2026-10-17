/** The committed snapshot of the verified run: the same files the hosted site serves. Tests read them as-is. */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const DIR = resolve(__dirname, "..", "..", "..", "deploy", "snapshot");

export function snapshot(name: "overview" | "week" | "carbon" | "log"): unknown {
  return JSON.parse(readFileSync(resolve(DIR, `${name}.json`), "utf-8"));
}
