import { MDXContent } from "@content-collections/mdx/react";
import { createFileRoute, notFound } from "@tanstack/react-router";
import { allTerms } from "content-collections";

export const Route = createFileRoute("/_landing/terms")({
	loader: () => {
		const doc = allTerms.find((t) => t._meta.path === "index") || allTerms[0];
		if (!doc) {
			throw notFound();
		}
		return { doc };
	},
	component: TermsPage,
});

function TermsPage() {
	const { doc } = Route.useLoaderData();

	return (
		<div className="max-w-3xl mx-auto py-16 px-6 space-y-8">
			<header className="space-y-3">
				<h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-foreground">
					{doc.title}
				</h1>
				{doc.date && (
					<div className="text-sm text-muted-foreground">
						Last updated:{" "}
						{new Date(doc.date).toLocaleDateString("en-US", {
							month: "long",
							day: "numeric",
							year: "numeric",
						})}
					</div>
				)}
			</header>

			<hr className="border-border" />

			<article className="prose dark:prose-invert max-w-none">
				<MDXContent code={doc.mdx} />
			</article>
		</div>
	);
}
