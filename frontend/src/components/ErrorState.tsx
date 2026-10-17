import { AlertTriangle, RotateCw } from "lucide-react";
import { isRouteErrorResponse, useRouteError } from "react-router";
import { Button } from "@/components/ui/button";

export function ErrorState({ title, detail }: { title: string; detail?: string }) {
  return (
    <div role="alert" className="rounded-xl border border-danger/40 bg-danger-subtle px-6 py-10 text-center">
      <AlertTriangle className="mx-auto mb-3 size-6 text-danger" aria-hidden />
      <h2 className="text-base font-medium">{title}</h2>
      {detail && <p className="mx-auto mt-2 max-w-md font-mono text-xs break-words text-muted-foreground">{detail}</p>}
      <Button variant="outline" size="sm" className="mt-5" onClick={() => window.location.reload()}>
        <RotateCw aria-hidden /> Reload
      </Button>
    </div>
  );
}

/** Route errorElement: a failed loader or render shows here, inside the shell, never as a blank page. */
export function RouteError() {
  const error = useRouteError();
  const detail = isRouteErrorResponse(error)
    ? `${error.status} ${error.statusText}`
    : error instanceof Error
      ? error.message
      : String(error);
  return (
    <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
      <ErrorState title="This page could not load its data" detail={detail} />
    </div>
  );
}
