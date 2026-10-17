/**
 * One week of hourly values: bars (certificates) and, optionally, a line (the buyer's load). Loaded on demand so the
 * charting library is not part of the first page load.
 */
import { Bar, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useChartColors } from "@/hooks/useChartColors";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { dayLabel, int, weekday } from "@/lib/format";

export type HourlyChartProps = {
  hours: string[];
  bars: number[];
  barLabel: string;
  line?: number[];
  lineLabel?: string;
  height?: number;
};

export default function HourlyChart({ hours, bars, barLabel, line, lineLabel, height = 200 }: HourlyChartProps) {
  const c = useChartColors();
  const wide = useMediaQuery("(min-width: 640px)"); // narrow screens: weekday only, so the labels never overlap
  const data = hours.map((h, i) => ({ i, hour: h, bar: bars[i] ?? 0, line: line?.[i] }));
  const dayTicks = hours.map((_, i) => i).filter((i) => i % 24 === 0);
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }} barCategoryGap={0.5}>
        <CartesianGrid vertical={false} stroke={c.grid} />
        <XAxis
          dataKey="i"
          ticks={dayTicks}
          interval={0}
          tickFormatter={(i: number) => (wide ? dayLabel(hours[i] ?? "", true) : weekday(hours[i] ?? ""))}
          tick={{ fill: c.subtle, fontSize: 11 }}
          tickLine={false}
          axisLine={{ stroke: c.grid }}
        />
        <YAxis
          width={44}
          tickFormatter={(v: number) => int(v)}
          tick={{ fill: c.subtle, fontSize: 11 }}
          tickLine={false}
          axisLine={false}
        />
        <Tooltip
          cursor={{ fill: c.grid, opacity: 0.6 }}
          isAnimationActive={false}
          content={({ active, payload }) => {
            const p = active && payload?.[0]?.payload;
            if (!p) return null;
            return (
              <div className="rounded-lg border border-border bg-popover px-3 py-2 text-xs shadow-md">
                <p className="font-medium text-foreground">
                  {dayLabel(p.hour)}, {String(p.hour).slice(11, 16)} UTC
                </p>
                <p className="tabular mt-1 text-muted-foreground">
                  {barLabel}: <span className="text-foreground">{int(p.bar)} MWh</span>
                </p>
                {line && (
                  <p className="tabular text-muted-foreground">
                    {lineLabel}: <span className="text-foreground">{int(p.line ?? 0)} MWh</span>
                  </p>
                )}
              </div>
            );
          }}
        />
        <Bar dataKey="bar" name={barLabel} fill={c.brand} fillOpacity={line ? 0.45 : 0.9} isAnimationActive={false} />
        {line && (
          <Line
            dataKey="line"
            name={lineLabel}
            type="linear"
            stroke={c.foreground}
            strokeWidth={1.75}
            dot={false}
            activeDot={{ r: 3 }}
            isAnimationActive={false}
          />
        )}
      </ComposedChart>
    </ResponsiveContainer>
  );
}
