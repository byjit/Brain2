import { Spinner } from "@/components/ui/spinner";

export function Pending() {
	return (
		<div className="flex flex-col items-center justify-center min-h-screen bg-background text-foreground p-4">
			<Spinner className="w-12 h-12 text-primary" />
			<p className="mt-4 text-muted-foreground animate-pulse font-medium">
				Loading...
			</p>
		</div>
	);
}
