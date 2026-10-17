import { Placeholder } from "./Placeholder";

export function Component() {
  return (
    <Placeholder
      path="/security"
      planned={[
        "How many attacks were refused, computed from the run",
        "Each attack: what it tried, what refused it, and whether a transaction exists",
      ]}
    />
  );
}
