/**
 * Build-time prerendering (prerender.mjs): render a page to HTML with the same routes, loaders and data the browser
 * uses. Data comes from the committed snapshot through the same /api paths (prerender.mjs answers fetch from it).
 */
import { StrictMode } from "react";
import { renderToString } from "react-dom/server";
import { createStaticHandler, createStaticRouter, StaticRouterProvider } from "react-router";
import { PAGES } from "./routes";
import { routes } from "./router";

export { PAGES };

export async function render(path: string): Promise<{ html: string; status: number }> {
  const handler = createStaticHandler(routes);
  const context = await handler.query(new Request(`http://prerender.local${path}`));
  if (context instanceof Response) throw new Error(`${path}: loader returned a redirect or response`);
  const router = createStaticRouter(handler.dataRoutes, context);
  const html = renderToString(
    <StrictMode>
      <StaticRouterProvider router={router} context={context} />
    </StrictMode>,
  );
  return { html, status: context.statusCode };
}
