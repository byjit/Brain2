import { createFileRoute, useNavigate } from "@tanstack/react-router";
import {
	AlertTriangle,
	Check,
	Copy,
	Key,
	Loader2,
	LogOut,
	Plus,
	ShieldCheck,
	Trash2,
} from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Logo } from "@/components/Logo";
import { Button } from "@/components/ui/button";
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Toaster } from "@/components/ui/sonner";
import {
	Table,
	TableBody,
	TableCell,
	TableHead,
	TableHeader,
	TableRow,
} from "@/components/ui/table";
import { env } from "@/env";
import { ThemeSwitcher } from "@/components/theme-switcher";

export const Route = createFileRoute("/_authed/dashboard")({
	component: DashboardPage,
});

interface TokenInfo {
	id: string;
	prefix: string;
	name: string | null;
	created_at: string;
	last_used_at: string | null;
	revoked: boolean;
}

interface UserProfile {
	user_id: string;
	email: string | null;
	created_at: string;
}

function DashboardPage() {
	const navigate = useNavigate();
	const [user, setUser] = useState<UserProfile | null>(null);
	const [tokens, setTokens] = useState<TokenInfo[]>([]);
	const [loading, setLoading] = useState(true);
	const [newTokenName, setNewTokenName] = useState("");
	const [creating, setCreating] = useState(false);
	const [isCreateOpen, setIsCreateOpen] = useState(false);

	// Holds the raw API key when successfully created (returned exactly once)
	const [createdKey, setCreatedKey] = useState<{
		id: string;
		api_key: string;
		prefix: string;
	} | null>(null);
	const [isKeyRevealOpen, setIsKeyRevealOpen] = useState(false);
	const [copied, setCopied] = useState(false);

	// Fetch user profile and tokens
	const fetchData = async () => {
		try {
			// Fetch User Profile
			const userRes = await fetch(`${env.VITE_BRAIN2_API_URL}/auth/me`, {
				credentials: "include",
			});
			if (!userRes.ok) throw new Error("Unauthorized");
			const userData = await userRes.json();
			setUser(userData);

			// Fetch Tokens
			const tokensRes = await fetch(
				`${env.VITE_BRAIN2_API_URL}/settings/tokens`,
				{
					credentials: "include",
				}
			);
			if (tokensRes.ok) {
				const tokensData = await tokensRes.json();
				setTokens(tokensData.filter((t: TokenInfo) => !t.revoked));
			}
		} catch (err) {
			console.error("Failed to load dashboard data", err);
			toast.error("Failed to authenticate session. Please sign in again.");
			navigate({ to: "/login" });
		} finally {
			setLoading(false);
		}
	};

	// biome-ignore lint/correctness/useExhaustiveDependencies: Only fetch on mount
	useEffect(() => {
		fetchData();
	}, []);

	// Handle token creation
	const handleCreateToken = async (e: React.FormEvent) => {
		e.preventDefault();
		if (creating) return;
		setCreating(true);

		try {
			const res = await fetch(`${env.VITE_BRAIN2_API_URL}/settings/tokens`, {
				method: "POST",
				headers: {
					"Content-Type": "application/json",
				},
				body: JSON.stringify({ name: newTokenName.trim() || null }),
				credentials: "include",
			});

			if (!res.ok) {
				throw new Error("Failed to create token");
			}

			const data = await res.json();
			setCreatedKey(data);
			setIsCreateOpen(false);
			setNewTokenName("");
			setIsKeyRevealOpen(true);
			toast.success("Personal Access Token created successfully!");

			// Refresh list
			fetchData();
		} catch (err) {
			console.error("Token creation error", err);
			toast.error("Failed to generate token. Please try again.");
		} finally {
			setCreating(false);
		}
	};

	// Handle token revocation
	const handleRevokeToken = async (tokenId: string) => {
		if (
			!confirm(
				"Are you sure you want to revoke this Personal Access Token? Any agents or CLI tools using this key will immediately lose access to your memory store."
			)
		) {
			return;
		}

		try {
			const res = await fetch(
				`${env.VITE_BRAIN2_API_URL}/settings/tokens/${tokenId}`,
				{
					method: "DELETE",
					credentials: "include",
				}
			);

			if (!res.ok) {
				throw new Error("Failed to revoke token");
			}

			toast.success("Token revoked successfully");
			fetchData();
		} catch (err) {
			console.error("Token revocation error", err);
			toast.error("Failed to revoke token. Please try again.");
		}
	};

	// Handle sign out
	const handleSignOut = async () => {
		try {
			await fetch(`${env.VITE_BRAIN2_API_URL}/auth/logout`, {
				method: "POST",
				credentials: "include",
			});
			toast.success("Signed out successfully");
			navigate({ to: "/login" });
		} catch (err) {
			console.error("Sign out error", err);
			toast.error("Failed to sign out");
		}
	};

	const copyToClipboard = () => {
		if (!createdKey) return;
		navigator.clipboard.writeText(createdKey.api_key);
		setCopied(true);
		toast.success("API key copied to clipboard");
		setTimeout(() => setCopied(false), 2000);
	};

	if (loading) {
		return (
			<div className="min-h-screen bg-background text-foreground flex items-center justify-center">
				<div className="flex flex-col items-center gap-4">
					<Loader2 className="h-8 w-8 animate-spin text-primary" />
					<p className="text-muted-foreground text-sm">Loading dashboard...</p>
				</div>
			</div>
		);
	}

	return (
		<div className="min-h-screen bg-background text-foreground font-sans">
			<Toaster />

			{/* Dashboard Navigation */}
			<header className="border-b bg-background/95 backdrop-blur-md sticky top-0 z-40">
				<div className="max-w-5xl mx-auto px-6 h-16 flex items-center justify-between">
					<div className="flex items-center gap-2">
						<Logo showText />
					</div>

					{user && (
						<div className="flex items-center gap-4">
							<span className="text-sm text-muted-foreground hidden sm:inline-block">
								{user.email}
							</span>
							<ThemeSwitcher />
							<Button onClick={handleSignOut} size="sm" variant="ghost">
								<LogOut className="h-4 w-4 mr-2" />
								Sign out
							</Button>
						</div>
					)}
				</div>
			</header>

			<main className="max-w-5xl mx-auto px-6 py-10 space-y-8">
				{/* Welcome Header */}
				<div className="space-y-2">
					<h1 className="text-3xl font-bold tracking-tight">
						Developer Settings
					</h1>
					<p className="text-muted-foreground text-sm">
						Manage your Personal Access Tokens (API Keys) to authenticate CLI
						tools and desktop agents (e.g. Claude Code, Cursor) with Brain2.
					</p>
				</div>

				{/* Access Token Card */}
				<Card>
					<CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4">
						<div>
							<CardTitle className="text-lg font-semibold flex items-center gap-2">
								<Key className="h-5 w-5 text-primary" />
								Personal Access Tokens
							</CardTitle>
							<CardDescription className="text-xs mt-1">
								Tokens you generate to authorize external agents to read/write
								your memory.
							</CardDescription>
						</div>
						<Button onClick={() => setIsCreateOpen(true)} size="sm">
							<Plus className="h-4 w-4 mr-1.5" />
							Generate token
						</Button>
					</CardHeader>

					<CardContent>
						{tokens.length === 0 ? (
							<div className="text-center py-12 border border-dashed border-border rounded-xl">
								<Key className="h-10 w-10 text-muted-foreground mx-auto mb-3" />
								<h3 className="text-sm font-medium">No active tokens</h3>
								<p className="text-xs text-muted-foreground mt-1 max-w-sm mx-auto">
									Create a Personal Access Token to get started with Claude
									Code, Cursor, or ChatGPT Custom Actions.
								</p>
							</div>
						) : (
							<div className="border border-border rounded-xl overflow-hidden">
								<Table>
									<TableHeader>
										<TableRow>
											<TableHead className="text-xs">Name</TableHead>
											<TableHead className="text-xs">Token Prefix</TableHead>
											<TableHead className="text-xs">Created</TableHead>
											<TableHead className="text-xs">Last Used</TableHead>
											<TableHead className="text-xs text-right pr-6">
												Action
											</TableHead>
										</TableRow>
									</TableHeader>
									<TableBody>
										{tokens.map((token) => (
											<TableRow key={token.id}>
												<TableCell className="font-medium py-3.5">
													{token.name || "Unnamed Token"}
												</TableCell>
												<TableCell className="font-mono text-xs text-muted-foreground">
													<code>{token.prefix}…</code>
												</TableCell>
												<TableCell className="text-muted-foreground text-xs">
													{new Date(token.created_at).toLocaleDateString(
														undefined,
														{
															year: "numeric",
															month: "short",
															day: "numeric",
														}
													)}
												</TableCell>
												<TableCell className="text-muted-foreground text-xs">
													{token.last_used_at ? (
														new Date(token.last_used_at).toLocaleDateString(
															undefined,
															{
																year: "numeric",
																month: "short",
																day: "numeric",
																hour: "2-digit",
																minute: "2-digit",
															}
														)
													) : (
														<span className="text-muted-foreground/50 italic">
															Never
														</span>
													)}
												</TableCell>
												<TableCell className="text-right pr-6">
													<Button
														onClick={() => handleRevokeToken(token.id)}
														size="icon-xs"
														title="Revoke Token"
														variant="destructive"
													>
														<Trash2 className="h-4 w-4" />
													</Button>
												</TableCell>
											</TableRow>
										))}
									</TableBody>
								</Table>
							</div>
						)}
					</CardContent>
				</Card>

				{/* Configuration / Copy paste Guide block */}
				<Card>
					<CardHeader>
						<CardTitle className="text-sm font-semibold">
							How to use with Claude Code / Cursor
						</CardTitle>
					</CardHeader>
					<CardContent className="space-y-4 text-xs text-muted-foreground leading-relaxed">
						<p>
							Once you generate a Personal Access Token, copy and add it to your
							local MCP client configuration. For example:
						</p>
						<div className="bg-muted border border-border rounded-lg p-4 font-mono text-foreground overflow-x-auto">
							<pre>{`{
  "mcpServers": {
    "brain2": {
      "url": "${env.VITE_BRAIN2_API_URL}/connect/mcp",
      "headers": {
        "Authorization": "Bearer br2_live_..."
      }
    }
  }
}`}</pre>
						</div>
					</CardContent>
				</Card>
			</main>

			{/* Dialog to create token */}
			<Dialog onOpenChange={setIsCreateOpen} open={isCreateOpen}>
				<DialogContent>
					<form className="space-y-4" onSubmit={handleCreateToken}>
						<DialogHeader>
							<DialogTitle className="text-lg font-semibold">
								Generate Personal Access Token
							</DialogTitle>
							<DialogDescription className="text-xs">
								Give your token a descriptive name to keep track of where it is
								used (e.g. "Claude Code Home", "Cursor Workspace").
							</DialogDescription>
						</DialogHeader>

						<div className="space-y-2">
							<Input
								autoFocus
								maxLength={100}
								onChange={(e) => setNewTokenName(e.target.value)}
								placeholder="e.g. Cursor MacBook"
								required
								value={newTokenName}
							/>
						</div>

						<DialogFooter className="pt-2">
							<Button
								onClick={() => setIsCreateOpen(false)}
								type="button"
								variant="ghost"
							>
								Cancel
							</Button>
							<Button disabled={creating} type="submit">
								{creating && <Loader2 className="h-4 w-4 animate-spin mr-2" />}
								Generate Token
							</Button>
						</DialogFooter>
					</form>
				</DialogContent>
			</Dialog>

			{/* Key Reveal Dialog (Returned exactly once) */}
			<Dialog
				onOpenChange={(open) => {
					// Prevent closing via backdrop click or ESC unless copy was confirmed
					if (!open) {
						setIsKeyRevealOpen(false);
						setCreatedKey(null);
					}
				}}
				open={isKeyRevealOpen}
			>
				<DialogContent className="max-w-md" showCloseButton={false}>
					<DialogHeader className="items-center text-center">
						<div className="p-3 bg-yellow-500/10 border border-yellow-500/20 text-yellow-500 rounded-full mb-3">
							<AlertTriangle className="h-6 w-6" />
						</div>
						<DialogTitle className="text-lg font-semibold">
							Save your Personal Access Token
						</DialogTitle>
						<DialogDescription className="text-xs max-w-sm">
							Make sure to copy your Personal Access Token now. For your
							security, <strong>you will not be able to see it again</strong>.
						</DialogDescription>
					</DialogHeader>

					{createdKey && (
						<div className="space-y-4 py-4">
							<div className="bg-muted border border-border rounded-xl p-3.5 flex items-center justify-between gap-3 font-mono text-sm overflow-hidden select-all">
								<span className="truncate font-semibold text-primary">
									{createdKey.api_key}
								</span>
								<Button
									onClick={copyToClipboard}
									size="icon-sm"
									variant="ghost"
								>
									{copied ? (
										<Check className="h-4 w-4 text-green-500" />
									) : (
										<Copy className="h-4 w-4" />
									)}
								</Button>
							</div>

							<div className="flex items-start gap-2 bg-amber-500/10 border border-amber-500/20 rounded-lg p-3 text-xs text-amber-500">
								<ShieldCheck className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
								<span>
									Never share this token or commit it to GitHub. This token
									grants full read and write access to your Brain2 memory store.
								</span>
							</div>
						</div>
					)}

					<DialogFooter className="sm:justify-center">
						<Button
							onClick={() => {
								setIsKeyRevealOpen(false);
								setCreatedKey(null);
							}}
						>
							I have saved this token
						</Button>
					</DialogFooter>
				</DialogContent>
			</Dialog>
		</div>
	);
}
