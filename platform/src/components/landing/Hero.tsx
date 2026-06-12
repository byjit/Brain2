import { Link } from "@tanstack/react-router";
import { ArrowRight, Github } from "lucide-react";
import { LogoIcon } from "@/components/Logo";
import { APP_NAME } from "@/lib/constant";

export const Hero = () => {
	return (
		<section className="w-full max-w-2xl mx-auto px-6 pt-16 pb-6">
			{/* Product Title Banner */}
			<div className="flex items-center gap-1 mb-8">
				<div className="inline-flex rounded-xl bg-muted/50 p-2">
					<LogoIcon className="h-8 w-8 text-foreground" />
				</div>
				<h1 className="text-lg font-semibold tracking-tight">{APP_NAME}</h1>
			</div>

			{/* Static Slogan */}
			<p className="text-3xl leading-relaxed mb-3 text-foreground font-semibold">
				Save your context in one place, and bring it to all AI agents you use
			</p>

			{/* Subtitle */}
			<p className="text-[15px] leading-relaxed text-muted-foreground mb-6">
				An open-source personal memory store. Save context once via Chrome
				extension or let your AI tools export and store their context in it. And
				bring it instantly in all the AI tools you use like Openclaw, Hermes,
				Codex, Claude, etc. Zero filing effort, perfect semantic recall.
			</p>

			{/* Action Buttons */}
			<div className="flex flex-wrap items-center gap-3 mb-8">
				<Link
					className="inline-flex items-center whitespace-nowrap rounded-full font-medium bg-foreground text-background hover:opacity-85 transition-opacity gap-2.5 px-5 py-2.5 text-[15px]"
					to="/login"
				>
					<ArrowRight className="h-4 w-4" />
					Get Chrome Extension
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

			{/* Features List */}
			<section className="pt-3 pb-6 border-t border-border/40">
				<h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-4">
					Features
				</h2>
				<ul className="space-y-3 text-[15px] text-muted-foreground leading-relaxed">
					{[
						{
							title: "Chrome extension save",
							desc: "capture articles, tutorials, notes, or bookmark with zero friction. And make them portable",
						},
						{
							title: "MCP integration",
							desc: "Connect through MCP and bring your saved memories and contexts in all the AI tools you use.",
						},
						{
							title: "Never loose information again",
							desc: "Your AI can always access your saved context from any device right when it is needed.",
						},
						{
							title: "Open source",
							desc: "Built with transparency and community in mind. Use our hosted solution or self-host your own instance.",
						},
					].map((feature) => (
						<li className="flex gap-3" key={feature.title}>
							<span className="text-muted-foreground/60 shrink-0">-</span>
							<span>
								<strong className="font-medium text-foreground">
									{feature.title}
								</strong>
								: {feature.desc}
							</span>
						</li>
					))}
				</ul>
			</section>

			<div className="mt-8 mb-12 md:-mx-20 mx-0 relative rounded-2xl overflow-hidden bg-transparent">
				<img
					alt="Brain2 Flow Diagram"
					className="w-full h-auto block dark:hidden"
					height={660}
					src="/brain2-flow.svg"
					width={1240}
				/>
				<img
					alt="Brain2 Flow Diagram"
					className="w-full h-auto hidden dark:block"
					height={660}
					src="/brain2-flow-dark.svg"
					width={1240}
				/>
			</div>
		</section>
	);
};
