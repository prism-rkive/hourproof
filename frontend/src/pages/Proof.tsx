import { Placeholder } from "./Placeholder";

export function Component() {
  return (
    <Placeholder
      path="/proof"
      planned={[
        "Run header: run ID, network, transactions, gas, status and the run buttons",
        "Every step of the run, with its transactions on the block explorer",
        "The independent verification step",
        "Recorded log of the run",
      ]}
    />
  );
}
