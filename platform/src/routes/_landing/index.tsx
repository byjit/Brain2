import { createFileRoute } from "@tanstack/react-router";
import { FAQ } from "@/components/landing/FAQ";
import { Hero } from "@/components/landing/Hero";
import { SocialProof } from "@/components/landing/SocialProof";

export const Route = createFileRoute("/_landing/")({
	component: Index,
});

function Index() {
	return (
		<div className="min-h-screen font-sans">
			<Hero />
			<SocialProof />
			<FAQ />
		</div>
	);
}
