import { MDXContent } from "@content-collections/mdx/react";
import { createFileRoute, Link, notFound } from "@tanstack/react-router";
import { allBlogs } from "content-collections";

export const Route = createFileRoute("/_landing/blogs/$slug")({
	loader: ({ params }) => {
		const post = allBlogs.find((p) => p._meta.path === params.slug);
		if (!post) {
			throw notFound();
		}
		return { post };
	},
	component: BlogPostPage,
});

function BlogPostPage() {
	const { post } = Route.useLoaderData();

	return (
		<div className="max-w-3xl mx-auto py-16 px-6 space-y-8">
			<div>
				<Link
					className="text-sm font-medium text-primary hover:underline"
					to="/blogs"
				>
					← Back to Blog
				</Link>
			</div>

			<header className="space-y-3">
				<h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-foreground">
					{post.title}
				</h1>
				<div className="text-sm text-muted-foreground">
					{new Date(post.date).toLocaleDateString("en-US", {
						month: "long",
						day: "numeric",
						year: "numeric",
					})}
					{post.author && ` by ${post.author}`}
				</div>
			</header>

			<hr className="border-border" />

			<article className="prose dark:prose-invert max-w-none">
				<MDXContent code={post.mdx} />
			</article>
		</div>
	);
}
