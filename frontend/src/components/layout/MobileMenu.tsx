import { ArrowUpRight, Menu } from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, useLocation } from "react-router";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { PAGES, REPO_URL } from "@/routes";
import { cn } from "@/lib/utils";
import { GitHubMark, Logo } from "./Logo";
import { RunStatusPill } from "./RunStatusPill";

export function MobileMenu() {
  const [open, setOpen] = useState(false);
  const { pathname } = useLocation();
  useEffect(() => setOpen(false), [pathname]); // close after navigating

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button variant="ghost" size="icon" className="lg:hidden" aria-label="Open menu">
          <Menu className="!size-5" aria-hidden />
        </Button>
      </SheetTrigger>
      <SheetContent aria-describedby="mobile-menu-desc">
        <div className="flex h-[var(--header-height)] items-center border-b border-border px-4">
          <Logo onClick={() => setOpen(false)} />
        </div>
        <SheetTitle className="sr-only">Menu</SheetTitle>
        <SheetDescription id="mobile-menu-desc" className="sr-only">
          Pages, run status and links
        </SheetDescription>
        <div className="flex flex-1 flex-col gap-6 overflow-y-auto p-4">
          <RunStatusPill variant="menu" />
          <nav aria-label="Main">
            <ul className="flex flex-col gap-1">
              {PAGES.map((p) => (
                <li key={p.path}>
                  <NavLink
                    to={p.path}
                    end={p.path === "/"}
                    className={({ isActive }) =>
                      cn(
                        "flex flex-col gap-0.5 rounded-md px-3 py-2.5 transition-colors",
                        isActive
                          ? "bg-accent font-medium text-foreground"
                          : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
                      )
                    }
                  >
                    <span className="text-base">{p.path === "/" ? p.label : p.title}</span>
                    <span className="text-13 leading-snug font-normal text-subtle-foreground">{p.plain}</span>
                  </NavLink>
                </li>
              ))}
            </ul>
          </nav>
        </div>
        <div className="border-t border-border p-4">
          <a
            href={REPO_URL}
            target="_blank"
            rel="noreferrer"
            className="flex h-11 items-center gap-2.5 rounded-md px-3 text-sm text-muted-foreground hover:bg-accent/60 hover:text-foreground"
          >
            <GitHubMark />
            Source on GitHub
            <ArrowUpRight className="ml-auto size-4" aria-hidden />
            <span className="sr-only">(opens in a new tab)</span>
          </a>
        </div>
      </SheetContent>
    </Sheet>
  );
}
