import { lazy, Suspense } from "react";
import { useIsClient } from "@/hooks/useIsClient";
import { useNearViewport } from "@/hooks/useNearViewport";
import type { HourlyChartProps } from "./HourlyChart";
import type { IntensityChartProps } from "./IntensityChart";

const HourlyChartImpl = lazy(() => import("./HourlyChart"));
const IntensityChartImpl = lazy(() => import("./IntensityChart"));

/** Reserves the chart's height while the charting code loads, so nothing jumps. */
function ChartSkeleton({ height }: { height: number }) {
  return <div className="animate-pulse rounded-md bg-muted" style={{ height }} aria-hidden />;
}

export function HourlyChart(props: HourlyChartProps & { ariaLabel: string }) {
  const height = props.height ?? 200;
  const client = useIsClient();
  const [ref, near] = useNearViewport<HTMLElement>();
  return (
    <figure ref={ref} role="img" aria-label={props.ariaLabel} className="m-0">
      {client && near ? (
        <Suspense fallback={<ChartSkeleton height={height} />}>
          <HourlyChartImpl {...props} />
        </Suspense>
      ) : (
        <ChartSkeleton height={height} /> // prerendered HTML, or not yet near the viewport
      )}
    </figure>
  );
}

export function IntensityChart(props: IntensityChartProps & { ariaLabel: string }) {
  const height = props.height ?? 240;
  const client = useIsClient();
  const [ref, near] = useNearViewport<HTMLElement>();
  return (
    <figure ref={ref} role="img" aria-label={props.ariaLabel} className="m-0">
      {client && near ? (
        <Suspense fallback={<ChartSkeleton height={height} />}>
          <IntensityChartImpl {...props} />
        </Suspense>
      ) : (
        <ChartSkeleton height={height} /> // prerendered HTML, or not yet near the viewport
      )}
    </figure>
  );
}
