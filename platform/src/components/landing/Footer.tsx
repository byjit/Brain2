import { Link } from "@tanstack/react-router";
import { APP_NAME } from "@/lib/constant";

export const Footer = () => {
	const columns: Array<{
		title: string;
		links: Array<{ label: string; to?: string; href?: string }>;
	}> = [
		{
			title: "Resources",
			links: [
				{ label: "Blog", to: "/blogs" },
				{ label: "Changelog", to: "/changelog" },
			],
		},
		{
			title: "Legal",
			links: [
				{ label: "Privacy", to: "/privacy" },
				{ label: "Terms", to: "/terms" },
			],
		},
		{
			title: "Social",
			links: [
				{ label: "GitHub", href: "https://github.com/byjit/Brain2" },
				{ label: "X / Twitter", href: "https://x.com" },
				{ label: "Discord", href: "https://discord.com" },
			],
      },
      {
			title: "Contact Us",
			links: [
				{ label: "Contact", href: "mailto:support@brain2.app" },
			],
		},

	];

	return (
		<footer className="border-t border-border/40 bg-background pt-16 pb-12">
			<div className="w-full max-w-2xl mx-auto px-6">
				{/* Link Grid */}
				<div className="grid grid-cols-2 sm:grid-cols-4 gap-8 mb-12">
					{columns.map((col) => (
						<div className="flex flex-col gap-3" key={col.title}>
							<h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
								{col.title}
							</h3>
							<ul className="flex flex-col gap-2 text-sm">
								{col.links.map((link) => (
									<li key={link.label}>
										{link.href ? (
											<a
												className="text-muted-foreground hover:text-foreground transition-colors"
												href={link.href}
												rel="noopener noreferrer"
												target="_blank"
											>
												{link.label}
											</a>
										) : (
											<Link
												className="text-muted-foreground hover:text-foreground transition-colors [&.active]:text-foreground"
												to={link.to}
											>
												{link.label}
											</Link>
										)}
									</li>
								))}
							</ul>
						</div>
					))}
				</div>

				{/* Bottom Bar */}
				<div className="flex flex-col sm:flex-row items-center justify-between border-t border-border/10 pt-6 gap-4 text-xs text-muted-foreground">
					<p>
						© {new Date().getFullYear()} {APP_NAME}. All rights reserved.
					</p>
				</div>
			</div>
		</footer>
	);
};
