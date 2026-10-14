/**
 * The guidance registers of one dimension, one at a time. Three registers
 * rendered together were most of a card's length, and a reader deciding what
 * to do wants one route at a time -- so they sit behind tabs, with the first
 * the server sent selected.
 *
 * Every panel stays in the DOM (`hidden`, not unmounted): `print:block` puts
 * all of them on paper with a print-only heading each, and the experiment
 * control inside the first keeps its hook state across tab switches. With a
 * single register there is nothing to choose between, so it renders under a
 * plain heading instead of a one-tab strip.
 *
 * WAI-ARIA tabs pattern: roving tabindex, arrow keys and Home/End move the
 * selection, and each panel is labelled by its tab.
 */
import { useRef, useState } from "react";

export interface RegisterTab {
  key: string;
  label: string;
  content: React.ReactNode;
}

interface RegisterTabsProps {
  idBase: string;
  tabs: RegisterTab[];
}

const PANEL_HEADING = "font-headline text-[1.02rem] font-bold text-ink-primary";

export default function RegisterTabs({ idBase, tabs }: RegisterTabsProps) {
  const [selected, setSelected] = useState(0);
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);

  if (tabs.length === 0) return null;

  if (tabs.length === 1) {
    return (
      <section className="space-y-3 border-t border-cream-muted pt-4">
        <h4 className={PANEL_HEADING}>{tabs[0].label}</h4>
        {tabs[0].content}
      </section>
    );
  }

  const select = (index: number) => {
    const next = (index + tabs.length) % tabs.length;
    setSelected(next);
    tabRefs.current[next]?.focus();
  };

  const onKeyDown = (event: React.KeyboardEvent) => {
    const moves: Record<string, number> = {
      ArrowRight: selected + 1,
      ArrowLeft: selected - 1,
      Home: 0,
      End: tabs.length - 1,
    };
    if (!(event.key in moves)) return;
    event.preventDefault();
    select(moves[event.key]);
  };

  return (
    <div className="border-t border-cream-muted pt-1">
      <div
        role="tablist"
        aria-label="Ways to act on this"
        className="flex border-b border-cream-muted print:hidden"
      >
        {tabs.map((tab, index) => {
          const isSelected = index === selected;
          return (
            <button
              key={tab.key}
              ref={(node) => {
                tabRefs.current[index] = node;
              }}
              type="button"
              role="tab"
              id={`${idBase}-tab-${tab.key}`}
              aria-selected={isSelected}
              aria-controls={`${idBase}-panel-${tab.key}`}
              tabIndex={isSelected ? 0 : -1}
              onClick={() => setSelected(index)}
              onKeyDown={onKeyDown}
              className={[
                "-mb-px flex-1 border-b-2 px-2 py-2.5 text-center text-[0.9rem] font-semibold leading-tight transition-colors sm:flex-none sm:px-3.5",
                "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-forest-light",
                isSelected
                  ? "border-forest-dark text-forest-dark"
                  : "border-transparent text-ink-secondary hover:text-ink-primary",
              ].join(" ")}
            >
              {tab.label}
            </button>
          );
        })}
      </div>
      {tabs.map((tab, index) => (
        <section
          key={tab.key}
          role="tabpanel"
          id={`${idBase}-panel-${tab.key}`}
          aria-labelledby={`${idBase}-tab-${tab.key}`}
          hidden={index !== selected}
          className="space-y-3 pt-4 print:block print:break-inside-avoid"
        >
          <h4 className={`${PANEL_HEADING} hidden print:block`}>{tab.label}</h4>
          {tab.content}
        </section>
      ))}
    </div>
  );
}
