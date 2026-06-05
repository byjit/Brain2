import { Github } from "lucide-react";

const testimonials = [
	{
		quote:
			"Another day another sandboxed agent project, this time with vertical tabs, visual diffs, and real-time token tracking specifically targeted towards people who use a ton of terminal-based agentic workflows.",
		author: "Mitchell Hashimoto",
		role: "Creator of Ghostty & Founder of HashiCorp",
		gradient: "from-pink-500 to-rose-500",
	},
	{
		quote:
			"This is exactly the developer tool I've been looking for. Safe execution loops and side-by-side terminal logs make agent coding incredibly satisfying.",
		author: "Nick Schrock",
		role: "Creator of Dagster, GraphQL co-creator",
		gradient: "from-blue-500 to-cyan-500",
	},
	{
		quote:
			"I've been running my local agents in Mirage all weekend and it's amazing. Zero worry about shell commands running wild.",
		author: "Edward Grefenstette",
		role: "Director of Research at Google DeepMind",
		gradient: "from-purple-500 to-indigo-500",
	},
	{
		quote:
			"Finally a tool that makes agent execution feel like a native, controlled IDE rather than just watching stdout scroll by in a basic shell.",
		author: "Peter Steinberger",
		role: "OpenClaw Creator, Founder of PSPDFKit",
		gradient: "from-amber-500 to-orange-500",
	},
	{
		quote:
			"The visual filesystem diffs are game-changing. I can see exactly what files my agents are modifying in real-time, side-by-side.",
		author: "Joe Riddle",
		role: "Frontend Architect",
		gradient: "from-emerald-500 to-teal-500",
	},
];

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
									className={`w-4 h-4 rounded-full bg-gradient-to-br ${t.gradient} flex items-center justify-center text-[8px] font-bold text-white uppercase select-none`}
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
					<a
						className="inline-flex items-center whitespace-nowrap rounded-full font-medium bg-foreground text-background hover:opacity-85 transition-opacity gap-2.5 px-5 py-2.5 text-[15px]"
						href="/download"
					>
						<svg className="h-4 w-4 fill-current" viewBox="0 0 814 1000">
							<path d="M788.1 340.9c-5.8 4.5-108.2 62.2-108.2 190.5 0 148.4 130.3 200.9 134.2 202.2-.6 3.2-20.7 71.9-68.7 141.9-42.8 61.6-87.5 123.1-155.5 123.1s-85.5-39.5-164-39.5c-76.5 0-103.7 40.8-165.9 40.8s-105.6-57.8-155.5-127.4c-58.3-81.6-105.6-208.4-105.6-328.6 0-193 125.6-295.5 249.2-295.5 65.7 0 120.5 43.1 161.7 43.1 39.2 0 100.4-45.8 175.1-45.8 28.3 0 130.3 2.6 197.2 99.2zM554.1 159.4c31.1-36.9 53.1-88.1 53.1-139.3 0-7.1-.6-14.3-1.9-20.1-50.6 1.9-110.8 33.7-147.1 75.8-28.9 32.4-57.2 83.6-57.2 135.4 0 7.8 1.3 15.6 1.9 18.1 3.2.6 8.4 1.3 13.6 1.3 45.4 0 102.5-30.4 137.6-71.2z" />
						</svg>
						Download for Mac
					</a>
					<a
						className="inline-flex items-center whitespace-nowrap gap-2 rounded-full border border-border px-5 py-2.5 text-[15px] font-medium text-foreground hover:bg-muted/30 transition-colors"
						href="https://github.com/manaflow-ai/cmux"
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
