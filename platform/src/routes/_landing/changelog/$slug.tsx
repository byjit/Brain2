import { MDXContent } from "@content-collections/mdx/react";
import { createFileRoute, Link, notFound } from "@tanstack/react-router";
import { allChangelogs } from "content-collections";
import { Badge } from "@/components/ui/badge";

export const Route = createFileRoute("/_landing/changelog/$slug")({
	loader: ({ params }) => {
		const post = allChangelogs.find((p) => p._meta.path === params.slug);
		if (!post) {
			throw notFound();
		}
		return { post };
	},
	component: ChangelogPostPage,
});

function ChangelogPostPage() {
	const { post } = Route.useLoaderData();

	return (
		<div className="max-w-3xl mx-auto py-16 px-6 space-y-8">
			<div>
				<Link
					className="text-sm font-medium text-primary hover:underline"
					to="/changelog"
				>
					Back to Changelog
				</Link>
			</div>

			<header className="space-y-3">
				<div className="flex flex-wrap items-center gap-3">
					<time className="text-xs text-muted-foreground">
						{new Date(post.date).toLocaleDateString("en-US", {
							month: "long",
							day: "numeric",
							year: "numeric",
						})}
					</time>
					{post.version && <Badge variant={"secondary"}>{post.version}</Badge>}
				</div>
				<h1 className="text-2xl  font-semibold text-foreground">
					{post.title}
				</h1>
			</header>

			<hr className="border-border" />

			<article className="prose dark:prose-invert max-w-none">
				<MDXContent code={post.mdx} />
			</article>
		</div>
	);
}
