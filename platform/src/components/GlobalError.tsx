import {
	type ErrorComponentProps,
	Link,
	useRouter,
} from "@tanstack/react-router";
import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";

export function GlobalError({ error, reset }: ErrorComponentProps) {
	const router = useRouter();

	return (
		<div className="flex flex-col items-center justify-center min-h-screen bg-background text-foreground p-4">
			<AlertTriangle className="w-16 h-16 text-destructive mb-4" />
			<h1 className="text-4xl font-bold mb-2">Something went wrong!</h1>
			<p className="text-muted-foreground mb-6 text-center max-w-md">
				An unexpected error occurred.
			</p>

			<div className="bg-muted p-4 rounded-md mb-6 max-w-lg w-full overflow-auto text-left">
				<p className="font-semibold text-sm mb-1">Error Details:</p>
				<code className="text-sm text-destructive font-mono whitespace-pre-wrap block">
					{(error as Error).message || JSON.stringify(error)}
				</code>
			</div>

			<div className="flex gap-4">
				<Button
					onClick={() => {
						reset();
						router.invalidate();
					}}
				>
					Try Again
				</Button>
				<Button asChild variant="outline">
					<Link to="/">Go Home</Link>
				</Button>
			</div>
		</div>
	);
}
