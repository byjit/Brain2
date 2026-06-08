import { createFileRoute, Link } from "@tanstack/react-router";
import { allChangelogs } from "content-collections";
import { Badge } from "@/components/ui/badge";

export const Route = createFileRoute("/_landing/changelog/")({
	component: ChangelogPage,
});

function ChangelogPage() {
	const sortedChangelogs = allChangelogs
		.filter((item) => item.published !== false)
		.sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());

	return (
		<div className="max-w-3xl mx-auto py-16 px-6">
			<header className="mb-16  pb-8">
				<h1 className="text-3xl font-semibold tracking-tight">Changelog</h1>
				<p className="text-muted-foreground mt-3">
					Stay up to date with the latest features, improvements, and releases.
				</p>
			</header>

			{sortedChangelogs.length === 0 ? (
				<div className="text-center py-12 text-muted-foreground">
					No release updates available.
				</div>
			) : (
				<div className="relative border-l border-border/80 ml-4 pl-8 space-y-12">
					{sortedChangelogs.map((item) => (
						<article className="relative group space-y-3" key={item._meta.path}>
							{/* Timeline node */}
							<div className="absolute -left-[41px] top-1.5 w-5 h-5 rounded-full border-4 border-background bg-muted-foreground/30 group-hover:bg-primary transition-colors duration-300" />

							<div className="flex flex-wrap items-center gap-3">
								<time className="text-xs text-muted-foreground">
									{new Date(item.date).toLocaleDateString("en-US", {
										month: "long",
										day: "numeric",
										year: "numeric",
									})}
								</time>
								{item.version && (
									<Badge variant={"secondary"}>{item.version}</Badge>
								)}
							</div>

							<h2 className="text-lg font-semibold tracking-tight">
								<Link params={{ slug: item._meta.path }} to="/changelog/$slug">
									{item.title}
								</Link>
							</h2>

							{item.description && (
								<p className="text-muted-foreground text-base text-sm leading-relaxed max-w-2xl">
									{item.description}
								</p>
							)}

							<div>
								<Link
									className="inline-flex items-center text-sm font-medium text-primary hover:underline gap-1 group/link"
									params={{ slug: item._meta.path }}
									to="/changelog/$slug"
								>
									Read release notes
								</Link>
							</div>
						</article>
					))}
				</div>
			)}
		</div>
	);
}
