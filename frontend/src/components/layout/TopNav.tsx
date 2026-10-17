import { NavLink } from "react-router";
import { Button } from "@/components/ui/button";
import { PAGES, REPO_URL } from "@/routes";
import { cn } from "@/lib/utils";
import { GitHubMark, Logo } from "./Logo";
import { MobileMenu } from "./MobileMenu";
import { RunStatusPill } from "./RunStatusPill";
import { ThemeToggle } from "./ThemeToggle";

export function TopNav() {
  return (
    <header className="sticky top-0 z-40 h-[var(--header-height)] border-b border-border bg-background/85 backdrop-blur supports-[backdrop-filter]:bg-background/70">
      <div className="mx-auto flex h-full max-w-6xl items-center gap-6 px-4 sm:px-6">
        <Logo />
        <nav aria-label="Main" className="hidden lg:block">
          <ul className="flex items-center gap-0.5">
            {PAGES.map((p) => (
              <li key={p.path}>
                <NavLink
                  to={p.path}
                  end={p.path === "/"}
                  className={({ isActive }) =>
                    cn(
                      "rounded-md px-2.5 py-1.5 text-sm transition-colors",
                      isActive
                        ? "bg-accent font-medium text-foreground"
                        : "text-muted-foreground hover:text-foreground",
                    )
                  }
                >
                  {p.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
        <div className="ml-auto flex items-center gap-1.5">
          <div className="mr-1 hidden md:block">
            <RunStatusPill />
          </div>
          <ThemeToggle />
          <Button variant="ghost" size="icon" asChild className="hidden sm:inline-flex">
            <a href={REPO_URL} target="_blank" rel="noreferrer" aria-label="Source code on GitHub (opens in a new tab)">
              <GitHubMark />
            </a>
          </Button>
          <MobileMenu />
        </div>
      </div>
    </header>
  );
}
