import { createFileRoute } from "@tanstack/react-router";
import { Brain, LogIn } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import { env } from "@/env";

export const Route = createFileRoute("/_public/login")({
	component: LoginPage,
});

function LoginPage() {
	const handleLogin = () => {
		const backendUrl = env.VITE_BRAIN2_API_URL;
		const nextUrl = `${window.location.origin}/dashboard`;
		window.location.href = `${backendUrl}/auth/login?next=${encodeURIComponent(nextUrl)}`;
	};

	return (
		<div className="min-h-screen flex items-center justify-center bg-background px-4">
			<Card className="w-full max-w-md">
				<CardHeader className="flex flex-col items-center text-center pb-2">
					<div className="flex size-12 items-center justify-center rounded-lg bg-primary text-primary-foreground mb-4">
						<Brain className="size-6" />
					</div>
					<CardTitle className="text-2xl font-bold tracking-tight">
						Welcome to Brain2
					</CardTitle>
					<CardDescription className="text-sm max-w-xs">
						Save anything from your browser, and bring it as context to every AI
						agent you use.
					</CardDescription>
				</CardHeader>

				<CardContent className="flex flex-col items-center pt-4">
					<Button className="w-full" onClick={handleLogin}>
						<LogIn className="size-4 mr-2" />
						Sign in with Google
					</Button>

					<div className="mt-6 text-xs text-muted-foreground text-center">
						By signing in, you agree to our Terms of Service and Privacy Policy.
					</div>
				</CardContent>
			</Card>
		</div>
	);
}
