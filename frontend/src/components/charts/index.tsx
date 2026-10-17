import { lazy, Suspense } from "react";
import type { HourlyChartProps } from "./HourlyChart";

const HourlyChartImpl = lazy(() => import("./HourlyChart"));

/** Reserves the chart's height while the charting code loads, so nothing jumps. */
function ChartSkeleton({ height }: { height: number }) {
  return <div className="animate-pulse rounded-md bg-muted" style={{ height }} aria-hidden />;
}

export function HourlyChart(props: HourlyChartProps & { ariaLabel: string }) {
  const height = props.height ?? 200;
  return (
    <figure role="img" aria-label={props.ariaLabel} className="m-0">
      <Suspense fallback={<ChartSkeleton height={height} />}>
        <HourlyChartImpl {...props} />
      </Suspense>
    </figure>
  );
}
