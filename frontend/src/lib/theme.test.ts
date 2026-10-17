import { resolveTheme, setTheme, THEME_KEY } from "./theme";

function osPrefers(scheme: "light" | "dark" | null) {
  vi.stubGlobal("matchMedia", (q: string) => ({
    matches: scheme !== null && q.includes(scheme),
    media: q,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
}

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("theme", () => {
  it("defaults to dark when the OS states no preference", () => {
    osPrefers(null);
    expect(resolveTheme()).toBe("dark");
  });

  it("follows the OS preference when nothing is saved", () => {
    osPrefers("light");
    expect(resolveTheme()).toBe("light");
    osPrefers("dark");
    expect(resolveTheme()).toBe("dark");
  });

  it("a saved choice wins over the OS preference", () => {
    osPrefers("light");
    setTheme("dark");
    expect(localStorage.getItem(THEME_KEY)).toBe("dark");
    expect(resolveTheme()).toBe("dark");
    expect(document.documentElement).toHaveClass("dark");
  });
});
