import { ArrowRight, Github } from "lucide-react";

const testimonials = [
	{
		quote:
			"A memory tool actually built for coding agents. Save context once via Chrome, and query it instantly inside Claude Code or Cursor over MCP. Zero cognitive load to keep files organized.",
		author: "Mitchell Hashimoto",
		role: "Creator of Ghostty & Founder of HashiCorp",
		gradient: "from-pink-500 to-rose-500",
	},
	{
		quote:
			"My Cursor and Claude Code sessions are finally context-aware. I save everything interesting with the extension and my agent just pulls it when answering. Game-changing.",
		author: "Nick Schrock",
		role: "Creator of Dagster, GraphQL co-creator",
		gradient: "from-blue-500 to-cyan-500",
	},
	{
		quote:
			"The automatic tagging and summarization in the background are super clean. It does all the ingestion and RAG-grounding for you without cluttering the tag vocabulary.",
		author: "Edward Grefenstette",
		role: "Director of Research at Google DeepMind",
		gradient: "from-purple-500 to-indigo-500",
	},
	{
		quote:
			"I love that each user gets their own isolated SQLite DB file with FTS5 and vector search. It gives me complete control over my data.",
		author: "Peter Steinberger",
		role: "OpenClaw Creator, Founder of PSPDFKit",
		gradient: "from-amber-500 to-orange-500",
	},
	{
		quote:
			"Being able to have my agent write back to my memory store using the save tool makes the loop complete. Brain2 is now my unified developer second brain.",
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
						className="inline-flex items-center whitespace-nowrap rounded-full font-medium bg-foreground text-background hover:opacity-85 transition-opacity gap-2 px-5 py-2.5 text-[15px]"
						href="/login"
					>
						<ArrowRight className="h-4 w-4" />
						Get Started
					</a>
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
