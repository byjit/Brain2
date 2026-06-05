import { createFileRoute, Outlet } from "@tanstack/react-router";
import { Footer } from "@/components/landing/Footer";
import { Navbar } from "@/components/landing/Navbar";

export const Route = createFileRoute("/_landing")({
	component: LandingLayout,
});

function LandingLayout() {
	return (
		<div className="min-h-screen bg-background text-foreground flex flex-col justify-between">
			<div>
				<Navbar />
				<main>
					<Outlet />
				</main>
			</div>
			<Footer />
		</div>
	);
}
