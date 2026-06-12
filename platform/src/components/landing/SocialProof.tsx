import { Link } from "@tanstack/react-router";
import { ArrowRight, Github } from "lucide-react";

const testimonials: {
	quote: string;
	author: string;
	role: string;
	gradient: string;
}[] = [];

export const SocialProof = () => {
	return (
		<div className="w-full max-w-2xl mx-auto px-6 py-6" id="community">
			{/* Community Section */}
			<section className="mb-14">
				<h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-4">
					Community
				</h2>
				<ul className="space-y-4 text-[15px] leading-relaxed">
					{testimonials.map((t, idx) => (
						// biome-ignore lint/suspicious/noArrayIndexKey: Static list
						<li className="group" key={idx}>
							<span className="text-muted-foreground group-hover:text-foreground transition-colors">
								&quot;{t.quote}&quot;
							</span>{" "}
							<span className="inline-flex items-center gap-1.5 text-muted-foreground whitespace-nowrap">
								—
								<span
									className={`w-4 h-4 rounded-full bg-linear-to-br ${t.gradient} flex items-center justify-center text-[8px] font-bold text-white uppercase select-none`}
								>
									{t.author.charAt(0)}
								</span>
								<span className="hover:text-foreground transition-colors">
									{t.author}
								</span>
								<span className="text-muted-foreground/60 text-xs">
									, {t.role}
								</span>
							</span>
						</li>
					))}
				</ul>
			</section>

			{/* Bottom CTA Block */}
			<section className="flex flex-col items-center justify-center border-t border-border/40 pt-12 pb-6">
				<div className="flex flex-wrap items-center justify-center gap-3 mb-4">
					<Link
						className="inline-flex items-center whitespace-nowrap rounded-full font-medium bg-foreground text-background hover:opacity-85 transition-opacity gap-2.5 px-5 py-2.5 text-[15px]"
						to="/login"
					>
						<ArrowRight className="h-4 w-4" />
						Get Started
					</Link>

					<a
						className="inline-flex items-center whitespace-nowrap gap-2 rounded-full border border-border px-5 py-2.5 text-[15px] font-medium text-foreground hover:bg-muted/30 transition-colors"
						href="https://github.com/byjit/Brain2"
						rel="noopener noreferrer"
						target="_blank"
					>
						<Github className="h-4 w-4" />
						View on GitHub
					</a>
				</div>
				<div className="flex items-center gap-4 text-xs text-muted-foreground mt-2">
					<a className="hover:text-foreground transition-colors" href="/docs">
						Read the Docs
					</a>
					<span className="text-muted-foreground/30">•</span>
					<a
						className="hover:text-foreground transition-colors"
						href="/changelog"
					>
						View Changelog
					</a>
				</div>
			</section>
		</div>
	);
};
