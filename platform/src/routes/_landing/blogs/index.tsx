import { createFileRoute, Link } from "@tanstack/react-router";
import { allBlogs } from "content-collections";

export const Route = createFileRoute("/_landing/blogs/")({
	component: BlogsPage,
});

function BlogsPage() {
	const sortedBlogs = allBlogs
		.filter((blog) => blog.published !== false)
		.sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());

	return (
		<div className="max-w-3xl mx-auto py-16 px-6">
			<header className="mb-12 border-b border-border pb-6">
				<h1 className="text-3xl font-bold">Blog</h1>
				<p className="text-muted-foreground mt-2">
					Latest stories, updates, and tutorials.
				</p>
			</header>

			<div className="space-y-12">
				{sortedBlogs.map((blog) => (
					<article className="group space-y-2" key={blog._meta.path}>
						<div className="text-xs text-muted-foreground">
							{new Date(blog.date).toLocaleDateString("en-US", {
								month: "long",
								day: "numeric",
								year: "numeric",
							})}
						</div>
						<h2 className="text-2xl font-semibold">
							<Link
								className="text-foreground hover:text-primary hover:underline transition-colors"
								params={{ slug: blog._meta.path }}
								to="/blogs/$slug"
							>
								{blog.title}
							</Link>
						</h2>
						{blog.description && (
							<p className="text-muted-foreground text-sm leading-relaxed line-clamp-3">
								{blog.description}
							</p>
						)}
					</article>
				))}
			</div>
		</div>
	);
}
