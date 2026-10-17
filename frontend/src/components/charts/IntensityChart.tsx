/** Hourly grid CO₂ intensity: the actual (posted on-chain) and the agent's day-ahead forecast. Loaded on demand. */
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useChartColors } from "@/hooks/useChartColors";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { dayLabel, weekday } from "@/lib/format";

export type IntensityChartProps = {
  hours: string[];
  actual: number[];
  forecast: number[];
  shift?: number[];
  height?: number;
};

export default function IntensityChart({ hours, actual, forecast, shift, height = 240 }: IntensityChartProps) {
  const c = useChartColors();
  const wide = useMediaQuery("(min-width: 640px)");
  const data = hours.map((h, i) => ({ i, hour: h, actual: actual[i], forecast: forecast[i], shift: shift?.[i] }));
  const oneDay = hours.length <= 24;
  const ticks = data
    .filter((d) => (oneDay ? Number(d.hour.slice(11, 13)) % 3 === 0 : d.hour.slice(11, 13) === "00"))
    .map((d) => d.i);
  return (
    <>
      <p className="mb-1 text-xs text-subtle-foreground">g/kWh</p>
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid vertical={false} stroke={c.grid} />
          <XAxis
            dataKey="i"
            type="number"
            domain={["dataMin", "dataMax"]}
            ticks={ticks}
            interval={0}
            tickFormatter={(i: number) => {
              const h = data.find((d) => d.i === i)?.hour ?? "";
              if (oneDay) return h.slice(11, 16);
              return wide ? dayLabel(h, true) : weekday(h);
            }}
            tick={{ fill: c.subtle, fontSize: 11 }}
            tickLine={false}
            axisLine={{ stroke: c.grid }}
          />
          <YAxis width={40} tick={{ fill: c.subtle, fontSize: 11 }} tickLine={false} axisLine={false} />
          <Tooltip
            isAnimationActive={false}
            cursor={{ stroke: c.subtle, strokeWidth: 1 }}
            content={({ active, payload }) => {
              const p = active && payload?.[0]?.payload;
              if (!p) return null;
              const sh = p.shift as number | undefined;
              return (
                <div className="rounded-lg border border-border bg-popover px-3 py-2 text-xs shadow-md">
                  <p className="font-medium text-foreground">
                    {dayLabel(p.hour)}, {String(p.hour).slice(11, 16)} UTC
                  </p>
                  <p className="tabular mt-1 text-muted-foreground">
                    Actual: <span className="text-foreground">{Math.round(p.actual)} g/kWh</span>
                  </p>
                  <p className="tabular text-muted-foreground">
                    Forecast: <span className="text-foreground">{Math.round(p.forecast)} g/kWh</span>
                  </p>
                  {sh !== undefined && Math.abs(sh) > 0.05 && (
                    <p className="tabular text-muted-foreground">
                      Plan: {sh > 0 ? "+" : "−"}
                      {Math.abs(sh).toFixed(1)} MWh {sh > 0 ? "moved in" : "deferred"}
                    </p>
                  )}
                </div>
              );
            }}
          />
          <Line
            dataKey="forecast"
            name="Agent's day-ahead forecast"
            stroke={c.series2}
            strokeWidth={2}
            strokeDasharray="5 3"
            dot={false}
            isAnimationActive={false}
          />
          <Line
            dataKey="actual"
            name="Actual"
            stroke={c.foreground}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 3.5 }}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </>
  );
}
