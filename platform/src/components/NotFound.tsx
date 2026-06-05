import { Link } from "@tanstack/react-router";
import { FileQuestion } from "lucide-react";
import { Button } from "@/components/ui/button";

export function NotFound() {
	return (
		<div className="flex flex-col items-center justify-center min-h-screen bg-background text-foreground p-4">
			<FileQuestion className="w-16 h-16 text-muted-foreground mb-4" />
			<h1 className="text-4xl font-bold mb-2">404 - Page Not Found</h1>
			<p className="text-muted-foreground mb-6 text-center max-w-md">
				Sorry, we couldn't find the page you're looking for. It might have been
				removed, renamed, or doesn't exist.
			</p>
			<Button asChild>
				<Link to="/">Go Home</Link>
			</Button>
		</div>
	);
}
