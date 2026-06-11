// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Logo } from "../components/Logo";

describe("Logo Component", () => {
	it("renders successfully", () => {
		const { container } = render(<Logo />);
		expect(container.querySelector("svg")).not.toBeNull();
	});

	it("renders app name when showText is true", () => {
		render(<Logo showText />);
		expect(screen.getByText("Brain2")).toBeDefined();
	});
});
