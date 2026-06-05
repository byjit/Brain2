const faqs = [
	{
		question: "How does Brain2 work?",
		answer:
			"Brain2 acts as an open-source personal memory store. You save web pages, selections, or custom notes using our Chrome extension or directly through connected AI agents. In the background, Brain2 automatically parses, summarizes, tags, and indexes the items into a vector and full-text search database, which any of your AI tools can query.",
	},
	{
		question: "What AI tools and agents can I connect?",
		answer:
			"Brain2 exposes a Model Context Protocol (MCP) server with tools like save, retrieve, delete, and get_tags. You can connect any MCP-capable client, including Claude Code, Cursor, ChatGPT Custom GPTs / Actions, and Claude Desktop, to read from and write to your memory store.",
	},
	{
		question: "How does the automatic tagging work?",
		answer:
			"Brain2 uses RAG-grounded proposals and a canonicalization layer to keep your tags organized. It extracts structured metadata (e.g. GitHub topics or OpenGraph keywords) and fetches existing tags by vector similarity. Gemini Flash then proposes tags, biasing towards reuse over invention. Each candidate tag is normalized and snapped to existing tags if they match by a cosine similarity of 0.90 or higher, preventing vocabulary fragmentation.",
	},
	{
		question: "Where is my data stored?",
		answer:
			"Your data is kept in isolated, per-user SQLite databases ({user_id}.db) featuring both standard full-text indexing (FTS5) and high-performance vector search (sqlite-vec). The backend enforces strict tenant isolation, giving you complete data privacy and ownership.",
	},
	{
		question: "What auth mechanisms does Brain2 support?",
		answer:
			"We support Personal Access Tokens (API Keys) for CLI/Desktop environments (like Claude Code or Cursor) that don't natively support browser redirect loops, and OAuth 2.1 with PKCE for web clients and the Chrome extension.",
	},
	{
		question: "Is Brain2 open source?",
		answer:
			"Yes, Brain2 is completely open source and available on GitHub. The schema, extension, and FastAPI backend are public, so you can audit the code or self-host your own memory store.",
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
