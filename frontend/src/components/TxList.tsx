import { ExternalLink } from "lucide-react";
import { int, shortHash } from "@/lib/format";
import type { Tx } from "@/lib/schemas";
import { cn } from "@/lib/utils";
import { CopyButton } from "./CopyButton";

/** Explorer name from a transaction URL, for link labels ("BaseScan"). */
function explorer(url: string): string {
  try {
    const host = new URL(url).hostname;
    return host.includes("basescan") ? "BaseScan" : host;
  } catch {
    return "the block explorer";
  }
}

/**
 * Transactions as rows: what it did, the shortened hash (copyable), block, gas, and a link to the block explorer.
 * Every transaction the run recorded is listed; none is hidden behind "more".
 */
export function TxList({ txs, className }: { txs: Tx[]; className?: string }) {
  if (!txs.length) return null;
  return (
    <ul className={cn("divide-y divide-border overflow-hidden rounded-lg border border-border", className)}>
      {txs.map((t) => (
        <li
          key={t.hash}
          className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1 bg-card px-3 py-2 text-13 sm:grid-cols-[minmax(0,1fr)_auto_auto_auto]"
        >
          <span className="min-w-0 truncate" title={t.label}>
            {t.label}
          </span>
          <span className="flex items-center gap-0.5 justify-self-end sm:order-3">
            {t.url ? (
              <a
                href={t.url}
                target="_blank"
                rel="noreferrer"
                data-tx={t.hash}
                aria-label={`${t.label}: transaction ${shortHash(t.hash)} on ${explorer(t.url)} (opens in a new tab)`}
                className="inline-flex items-center gap-1.5 rounded-md px-1.5 py-1 font-mono text-xs text-foreground underline-offset-4 hover:bg-accent hover:underline"
              >
                {shortHash(t.hash)}
                <ExternalLink className="size-3 text-subtle-foreground" aria-hidden />
              </a>
            ) : (
              <span className="px-1.5 font-mono text-xs" title={t.hash}>
                {shortHash(t.hash)}
              </span>
            )}
            <CopyButton value={t.hash} label={`Copy the hash of "${t.label}"`} />
          </span>
          <span className="tabular col-span-2 text-xs text-subtle-foreground sm:order-2 sm:col-span-1 sm:text-right">
            {t.block != null && <>block {int(t.block)} · </>}
            {int(t.gas)} gas
          </span>
        </li>
      ))}
    </ul>
  );
}
