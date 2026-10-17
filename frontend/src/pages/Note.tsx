import { Placeholder } from "./Placeholder";

export function Component() {
  return (
    <Placeholder
      path="/note"
      planned={[
        "Outcome: KPI met or missed, and the coupon it set",
        "Term sheet: KPI, target, proven value, coupon, notes and amount paid",
        "Settlement transactions",
      ]}
    />
  );
}
