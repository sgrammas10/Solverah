import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

type Props = {
  onRequestEarlyAccess: () => void;
};

export default function LandingNav({ onRequestEarlyAccess }: Props) {
  const [scrolled, setScrolled] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    const handleScroll = () => setScrolled(window.scrollY > 60);
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  const navLinks = [
    { label: "How it works", href: "#features" },
    { label: "About", href: "#about" },
    { label: "FAQ", href: "#faq" },
  ];

  return (
    <header
      className="sticky top-0 z-50 transition-all duration-300"
      style={{
        backgroundColor: scrolled ? "rgba(250,247,242,0.92)" : "transparent",
        backdropFilter: scrolled ? "blur(12px)" : "none",
        borderBottom: scrolled ? "1px solid #D4CFC8" : "1px solid transparent",
      }}
    >
      <div className="mx-auto max-w-7xl px-6 h-16 flex items-center justify-between">
        <a href="/" className="font-display text-2xl font-bold text-forest-dark tracking-tight">
          Solverah
        </a>

        <nav className="hidden md:flex items-center gap-8" aria-label="Primary navigation">
          {navLinks.map(({ label, href }) => (
            <a
              key={label}
              href={href}
              className="text-[15px] font-medium text-ink-primary tracking-[0.02em] relative after:absolute after:bottom-0 after:left-0 after:h-[2px] after:w-0 after:bg-forest-light after:transition-all after:duration-300 hover:after:w-full hover:text-forest-mid transition-colors"
            >
              {label}
            </a>
          ))}
        </nav>

        <div className="hidden md:flex items-center gap-3">
          <a
            href="/login"
            className="text-[15px] font-medium text-ink-primary px-4 py-2 rounded hover:text-forest-mid transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-forest-light focus-visible:ring-offset-2"
          >
            Sign In
          </a>
          <a
            href="/register"
            className="bg-forest-dark text-white font-semibold text-[15px] px-6 py-2.5 rounded hover:bg-forest-mid transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-forest-light focus-visible:ring-offset-2"
          >
            Get Started
          </a>
        </div>

        <button
          type="button"
          aria-label={mobileMenuOpen ? "Close menu" : "Open menu"}
          onClick={() => setMobileMenuOpen((v) => !v)}
          className="md:hidden flex flex-col gap-1.5 p-2"
        >
          <span className={`block h-0.5 w-6 bg-ink-primary transition-transform duration-200 ${mobileMenuOpen ? "translate-y-2 rotate-45" : ""}`} />
          <span className={`block h-0.5 w-6 bg-ink-primary transition-opacity duration-200 ${mobileMenuOpen ? "opacity-0" : ""}`} />
          <span className={`block h-0.5 w-6 bg-ink-primary transition-transform duration-200 ${mobileMenuOpen ? "-translate-y-2 -rotate-45" : ""}`} />
        </button>
      </div>

      {mobileMenuOpen && (
        <div className="md:hidden bg-cream-base border-t border-cream-muted px-6 py-6 space-y-4 animate-fade-in">
          {navLinks.map(({ label, href }) => (
            <a
              key={label}
              href={href}
              onClick={() => setMobileMenuOpen(false)}
              className="block text-base font-medium text-ink-primary hover:text-forest-mid transition-colors"
            >
              {label}
            </a>
          ))}
          <a
            href="/login"
            className="block text-base font-medium text-ink-primary hover:text-forest-mid transition-colors"
          >
            Sign In
          </a>
          <a
            href="/register"
            onClick={() => setMobileMenuOpen(false)}
            className="block w-full bg-forest-dark text-white font-semibold text-sm px-6 py-3 rounded hover:bg-forest-mid transition-colors text-center"
          >
            Get Started
          </a>
        </div>
      )}
    </header>
  );
}
