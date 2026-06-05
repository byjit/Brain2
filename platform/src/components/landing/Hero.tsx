import { ArrowDownToLine, Github } from "lucide-react";
import { LogoIcon } from "@/components/Logo";
import { APP_NAME } from "@/lib/constant";

export const Hero = () => {
	return (
		<section className="w-full max-w-2xl mx-auto px-6 pt-16 pb-6">
			{/* Product Title Banner */}
			<div className="flex items-center gap-4 mb-8">
				<div className="inline-flex rounded-xl bg-muted/50 p-2">
					<LogoIcon className="h-8 w-8 text-foreground" />
				</div>
				<h1 className="text-2xl font-semibold tracking-tight">{APP_NAME}</h1>
			</div>

			{/* Static Slogan */}
			<p className="text-lg leading-relaxed mb-3 text-foreground font-semibold">
				The local sandbox for coding agents
			</p>

			{/* Subtitle */}
			<p className="text-[15px] leading-relaxed text-muted-foreground mb-6">
				Native macOS & Linux app built for running coding agents. Visual
				filesystem logs, resource isolation, real-time token tracking, and a
				socket API for agent coordination.
			</p>

			{/* Action Buttons */}
			<div className="flex flex-wrap items-center gap-3 mb-8">
				<a
					className="inline-flex items-center whitespace-nowrap rounded-full font-medium bg-foreground text-background hover:opacity-85 transition-opacity gap-2.5 px-5 py-2.5 text-[15px]"
					href="/download"
        >
          <ArrowDownToLine />
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

			{/* Features List */}
			<section className="pt-3 pb-6 border-t border-border/40">
				<h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-4">
					Features
				</h2>
				<ul className="space-y-3 text-[15px] text-muted-foreground leading-relaxed">
					{[
						{
							title: "Visual diffs",
							desc: "side-by-side display of modifications made by agents in real-time",
						},
						{
							title: "Sandbox isolation",
							desc: "secure containerized environments so agents don't harm your local machine",
						},
						{
							title: "Token budgeting",
							desc: "track and cap API costs automatically with custom alerts and limits",
						},
						{
							title: "Embedded terminal",
							desc: "fully interactive shell with breakpoint debugging for agent execution",
						},
						{
							title: "Scriptable CLI",
							desc: "socket API and command line interface to programmatically control execution",
						},
						{
							title: "GPU-accelerated",
							desc: "high-performance log rendering and filesystem diff animations",
						},
						{
							title: "Cross-platform",
							desc: "native Swift wrapper for macOS, lightweight GTK layer for Linux",
						},
						{
							title: "Keyboard shortcuts",
							desc: "comprehensive shortcuts for splits, container restarts, and token approvals",
						},
					].map((feature) => (
						<li key={feature.title} className="flex gap-3">
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

			<div className="mt-8 mb-12 -mx-16 sm:-mx-32 md:-mx-48 lg:-mx-64 xl:-mx-80 relative rounded-2xl overflow-hidden bg-card">
				<img
					alt="Dashboard Preview"
					className="w-full h-auto object-cover block"
					height={1080}
					src="https://res.cloudinary.com/dz8mikz3h/image/upload/v1755173210/thumbnail_noa_demo_kfkmyn.png"
					width={1920}
				/>
			</div>
		</section>
	);
};
