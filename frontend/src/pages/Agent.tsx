import { Placeholder } from "./Placeholder";

export function Component() {
  return (
    <Placeholder
      path="/agent"
      planned={[
        "Hourly coverage by strategy, with perfect foresight as a reference",
        "Forecast skill of the agent's models",
        "How the walk-forward test works",
      ]}
    />
  );
}
