const faqs = [
	{
		question: "How does Mirage secure my workspace?",
		answer:
			"Mirage runs agents in a containerized environment. Any commands, file creations, or web requests are isolated inside the container, preventing unauthorized access to your host machine.",
	},
	{
		question: "What AI agents does Mirage support?",
		answer:
			"All agent frameworks. Mirage provides a standardized execution sandbox. Whether you use Claude Code, Aider, Cline, Goose, or custom scripts, they can run inside Mirage.",
	},
	{
		question: "How do I control my token budget?",
		answer:
			"You can set hard caps on token usage or cost per session. When an agent exceeds the limit, the sandbox pauses execution and requests manual approval.",
	},
	{
		question: "Can I customize shortcuts and settings?",
		answer:
			"Yes. Hotkeys for switching agents, resetting sandboxes, and opening diff viewers can be customized in Settings. Sandbox configurations are stored in standard JSON files.",
	},
	{
		question: "Is Mirage open source?",
		answer:
			"Yes, the core execution sandbox is open source and licensed under MIT, available on GitHub.",
	},
];

export const FAQ = () => {
	return (
		<section className="w-full max-w-2xl mx-auto px-6 py-6" id="faq">
			<h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-4">
				FAQ
			</h2>
			<div className="space-y-6 text-[15px] leading-relaxed">
				{faqs.map((faq, index) => (
					// biome-ignore lint/suspicious/noArrayIndexKey: Static list
					<div key={index}>
						<p className="font-medium text-foreground mb-1">{faq.question}</p>
						<p className="text-muted-foreground">{faq.answer}</p>
					</div>
				))}
			</div>
		</section>
	);
};
