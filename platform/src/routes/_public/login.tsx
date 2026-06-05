import { createFileRoute } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";

export const Route = createFileRoute("/_public/login")({
	component: LoginPage,
});

function LoginPage() {
	return (
		<div className="min-h-screen flex items-center justify-center">
			<div>
				<p>Sign in by clicking here</p>
				<Button>Login</Button>
			</div>
		</div>
	);
}
