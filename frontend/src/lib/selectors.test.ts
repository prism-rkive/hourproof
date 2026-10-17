import { snapshot } from "@/test/snapshot";
import { Overview } from "./schemas";
import { lastRunLine, runStatus } from "./selectors";

const raw = snapshot("overview") as Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
const o = Overview.parse(raw);

describe("runStatus", () => {
  it("reads the verified run from the snapshot", () => {
    const s = runStatus(o);
    expect(s.tone).toBe("success");
    expect(s.runId).toBe(raw.demo.run_id);
    expect(s.full).toBe(`Last run ${raw.demo.run_id} on Base Sepolia: passed`);
    expect(raw.static_snapshot.run_id).toBe(raw.demo.run_id);
  });

  it("follows the original dashboard's rules", () => {
    expect(runStatus({ ...o, running: true }).short).toBe("Run in progress");
    expect(runStatus({ ...o, demo: { ...o.demo!, status: "failed" } }).tone).toBe("danger");
    expect(runStatus({ ...o, demo: null }).short).toBe("No run yet");
  });
});

describe("lastRunLine", () => {
  it("uses the run's own finish time, in UTC", () => {
    const d = new Date(raw.demo.finished_utc);
    expect(lastRunLine(o)).toContain(`${d.getUTCFullYear()}`);
    expect(lastRunLine(o)).toMatch(/UTC on Base Sepolia$/);
  });
});
