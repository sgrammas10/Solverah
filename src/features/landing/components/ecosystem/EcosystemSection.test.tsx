import { render, screen, fireEvent, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import EcosystemSection, { HUB_NODES } from "./EcosystemSection";

function renderAt(search = "") {
  return render(
    <MemoryRouter initialEntries={[`/${search}`]}>
      <EcosystemSection />
    </MemoryRouter>
  );
}

describe("ecosystem section", () => {
  it("defaults to the card, with the hub described for screen readers", () => {
    renderAt();

    expect(screen.getByRole("heading", { name: "One profile, read six ways." })).toBeInTheDocument();
    const hub = screen.getByRole("img", { name: /Solverah at the centre/ });
    for (const n of HUB_NODES) expect(hub).toHaveAccessibleName(expect.stringContaining(n.name));
    expect(screen.getByRole("link", { name: "See how a reading is made" })).toHaveAttribute(
      "href",
      "#how-it-reads"
    );
  });

  it("falls back to the card on an unknown variant", () => {
    renderAt("?eco=nonsense");

    expect(screen.getByRole("heading", { name: "One profile, read six ways." })).toBeInTheDocument();
  });

  it("split lists every instrument, and hovering one lights its node", () => {
    const { container } = renderAt("?eco=split");

    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(HUB_NODES.length);

    const node = container.querySelector('[data-node="situation-report"]');
    expect(node).toHaveAttribute("data-active", "false");

    fireEvent.mouseEnter(screen.getByText("Situation Report").closest("li")!);
    expect(node).toHaveAttribute("data-active", "true");

    fireEvent.mouseLeave(screen.getByText("Situation Report").closest("li")!);
    expect(node).toHaveAttribute("data-active", "false");
  });

  it("flow shows what goes in and what comes back", () => {
    renderAt("?eco=flow");

    expect(screen.getByRole("heading", { name: "What goes in, what comes back." })).toBeInTheDocument();
    expect(screen.getByText("Your resume")).toBeInTheDocument();
    expect(screen.getByText("Manager playbook")).toBeInTheDocument();
  });

  it("off renders no section", () => {
    const { container } = renderAt("?eco=off");

    expect(container.querySelector("#ecosystem")).toBeNull();
  });

  it("the development switcher changes the layout", () => {
    renderAt();

    const switcher = screen.getByRole("group", { name: /Ecosystem layout/ });
    fireEvent.click(within(switcher).getByRole("button", { name: "flow" }));

    expect(screen.getByRole("heading", { name: "What goes in, what comes back." })).toBeInTheDocument();
    expect(within(switcher).getByRole("button", { name: "flow" })).toHaveAttribute("aria-pressed", "true");
  });
});
