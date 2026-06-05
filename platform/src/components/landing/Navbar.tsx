import { Link } from "@tanstack/react-router";
import { Menu, Moon, Sun, X } from "lucide-react";
import { useTheme } from "next-themes";
import { useState } from "react";

export const Navbar = () => {
	const [isOpen, setIsOpen] = useState(false);
	const { theme, setTheme } = useTheme();

  const navItems = [
    { name: "Home", to: "/"},
		{ name: "Blog", to: "/blogs" },
		{ name: "Changelog", to: "/changelog" },
		{ name: "GitHub", href: "https://github.com/byjit/Brain2" },
	];

	const toggleTheme = () => {
		setTheme(theme === "dark" ? "light" : "dark");
	};

	return (
		<header className="sticky top-0 z-30 w-full bg-background/80 backdrop-blur-md border-b border-border/40">
			<div className="w-full max-w-3xl mx-auto flex h-14 items-center px-6 justify-between">
				{/* Desktop Nav */}
				<nav className="hidden min-w-0 items-center justify-center gap-6 text-sm text-muted-foreground min-[940px]:flex">
					{navItems.map((item) =>
						item.href ? (
							<a
								className="hover:text-foreground transition-colors"
								href={item.href}
								key={item.name}
								rel="noopener noreferrer"
								target="_blank"
							>
								{item.name}
							</a>
						) : (
							<Link
								className="hover:text-foreground transition-colors [&.active]:text-foreground"
								key={item.name}
								to={item.to}
							>
								{item.name}
							</Link>
						)
					)}
				</nav>

				{/* Actions (Right) */}
				<div className="ml-auto flex min-w-0 items-center justify-end gap-3 min-[940px]:ml-0">
					<div className="hidden min-[940px]:block">
						<a
							className="inline-flex items-center whitespace-nowrap rounded-full font-medium bg-foreground text-background hover:opacity-85 transition-opacity gap-2 px-4 py-1.5 text-xs"
							href="/login"
						>
							Get Started
						</a>
					</div>

					{/* Theme Switcher Button */}
					<button
						aria-label="Toggle theme"
						className="inline-flex h-9 w-9 items-center justify-center text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
						onClick={toggleTheme}
						type="button"
					>
						<Sun className="hidden dark:block h-4 w-4" />
						<Moon className="block dark:hidden h-4 w-4" />
					</button>

					{/* Mobile Menu Button */}
					<button
						aria-expanded={isOpen}
						className="min-[940px]:hidden w-8 h-8 flex items-center justify-center text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
						onClick={() => setIsOpen(!isOpen)}
						type="button"
					>
						{isOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
					</button>
				</div>
			</div>

			{/* Mobile Menu */}
			{isOpen && (
				<nav className="min-[940px]:hidden border-b border-border/40 bg-background/95 backdrop-blur-md">
					<div className="flex flex-col gap-3 text-sm text-muted-foreground px-6 py-4">
						{navItems.map((item) =>
							item.href ? (
								<a
									className="hover:text-foreground transition-colors py-1"
									href={item.href}
									key={item.name}
									onClick={() => setIsOpen(false)}
									rel="noopener noreferrer"
									target="_blank"
								>
									{item.name}
								</a>
							) : (
								<Link
									className="hover:text-foreground transition-colors py-1 [&.active]:text-foreground"
									key={item.name}
									onClick={() => setIsOpen(false)}
									to={item.to}
								>
									{item.name}
								</Link>
							)
						)}
						<div className="pt-2">
							<a
								className="inline-flex w-full items-center justify-center whitespace-nowrap rounded-full font-medium bg-foreground text-background hover:opacity-85 transition-opacity gap-2 px-4 py-2 text-xs"
								href="/login"
								onClick={() => setIsOpen(false)}
							>
								Get Started
							</a>
						</div>
					</div>
				</nav>
			)}
		</header>
	);
};
