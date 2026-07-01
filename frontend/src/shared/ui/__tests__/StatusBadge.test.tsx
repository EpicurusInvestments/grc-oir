import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusBadge } from "@/shared/ui/StatusBadge";

describe("StatusBadge", () => {
  it("muestra 'Activo' con clase b-green cuando activo=true", () => {
    render(<StatusBadge activo />);
    const badge = screen.getByText("Activo");
    expect(badge).toHaveClass("badge", "b-green");
  });

  it("muestra 'Inactivo' con clase b-gray cuando activo=false", () => {
    render(<StatusBadge activo={false} />);
    const badge = screen.getByText("Inactivo");
    expect(badge).toHaveClass("badge", "b-gray");
  });
});
