import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CommandBar } from "@/components/lab-controls";
import { FALLBACK_TRACE } from "@/lib/trace";

describe("CommandBar Dropdown Click-Outside Behavior", () => {
  it("closes the case dropdown when clicking outside on the document", () => {
    const onCase = vi.fn();
    const onLive = vi.fn();

    const { container } = render(
      <div>
        <div data-testid="outside-area">Outside Content</div>
        <CommandBar
          trace={FALLBACK_TRACE}
          busy={false}
          onLive={onLive}
          caseId="hero"
          caseBusy={false}
          onCase={onCase}
        />
      </div>
    );

    // Initial state: case dropdown is closed
    expect(screen.queryByRole("group", { name: "Benchmark cases" })).not.toBeInTheDocument();

    // Click case selector button to open
    const caseBtn = screen.getByRole("button", { name: /Case Selector/i });
    fireEvent.click(caseBtn);
    expect(screen.getByRole("group", { name: "Benchmark cases" })).toBeInTheDocument();

    // Click outside on the outside area
    const outsideArea = screen.getByTestId("outside-area");
    fireEvent.mouseDown(outsideArea);

    // Dropdown should now be closed
    expect(screen.queryByRole("group", { name: "Benchmark cases" })).not.toBeInTheDocument();
  });

  it("closes the theme dropdown when clicking outside on the document", () => {
    const onCase = vi.fn();
    const onLive = vi.fn();

    render(
      <div>
        <div data-testid="outside-area">Outside Content</div>
        <CommandBar
          trace={FALLBACK_TRACE}
          busy={false}
          onLive={onLive}
          caseId="hero"
          caseBusy={false}
          onCase={onCase}
        />
      </div>
    );

    // Initial state: theme dropdown is closed
    expect(screen.queryByRole("group", { name: "Design Studio" })).not.toBeInTheDocument();

    // Click theme selector button to open
    const themeBtn = screen.getByRole("button", { name: /Porcelain & Signal Blue/i });
    fireEvent.click(themeBtn);
    expect(screen.getByRole("group", { name: "Design Studio" })).toBeInTheDocument();

    // Click outside on the outside area
    const outsideArea = screen.getByTestId("outside-area");
    fireEvent.mouseDown(outsideArea);

    // Dropdown should now be closed
    expect(screen.queryByRole("group", { name: "Design Studio" })).not.toBeInTheDocument();
  });

  it("closes open dropdowns when pressing the Escape key", () => {
    const onCase = vi.fn();
    const onLive = vi.fn();

    render(
      <CommandBar
        trace={FALLBACK_TRACE}
        busy={false}
        onLive={onLive}
        caseId="hero"
        caseBusy={false}
        onCase={onCase}
      />
    );

    // Open case menu
    const caseBtn = screen.getByRole("button", { name: /Case Selector/i });
    fireEvent.click(caseBtn);
    expect(screen.getByRole("group", { name: "Benchmark cases" })).toBeInTheDocument();

    // Press Escape
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("group", { name: "Benchmark cases" })).not.toBeInTheDocument();
  });

  it("switches cleanly between case menu and theme menu", () => {
    const onCase = vi.fn();
    const onLive = vi.fn();

    render(
      <CommandBar
        trace={FALLBACK_TRACE}
        busy={false}
        onLive={onLive}
        caseId="hero"
        caseBusy={false}
        onCase={onCase}
      />
    );

    // Open case menu
    const caseBtn = screen.getByRole("button", { name: /Case Selector/i });
    fireEvent.click(caseBtn);
    expect(screen.getByRole("group", { name: "Benchmark cases" })).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Design Studio" })).not.toBeInTheDocument();

    // Click theme button directly
    const themeBtn = screen.getByRole("button", { name: /Porcelain & Signal Blue/i });
    fireEvent.mouseDown(themeBtn);
    fireEvent.click(themeBtn);

    // Case menu should be closed, theme menu should be open
    expect(screen.queryByRole("group", { name: "Benchmark cases" })).not.toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Design Studio" })).toBeInTheDocument();
  });
});
