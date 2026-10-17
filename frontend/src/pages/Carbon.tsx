import { Placeholder } from "./Placeholder";

export function Component() {
  return (
    <Placeholder
      path="/carbon"
      planned={[
        "Residual emissions by strategy on the test period",
        "The on-chain emissions proof",
        "Forecast against actual grid intensity for the run's week",
        "Intensity heatmap with the planned load shift",
        "Caveats",
      ]}
    />
  );
}
