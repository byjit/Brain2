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
		{ name: "GitHub", href: "https://github.com/manaflow-ai/cmux" },
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
							href="/download"
						>
							<svg className="h-3.5 w-3.5 fill-current" viewBox="0 0 814 1000">
								<path d="M788.1 340.9c-5.8 4.5-108.2 62.2-108.2 190.5 0 148.4 130.3 200.9 134.2 202.2-.6 3.2-20.7 71.9-68.7 141.9-42.8 61.6-87.5 123.1-155.5 123.1s-85.5-39.5-164-39.5c-76.5 0-103.7 40.8-165.9 40.8s-105.6-57.8-155.5-127.4c-58.3-81.6-105.6-208.4-105.6-328.6 0-193 125.6-295.5 249.2-295.5 65.7 0 120.5 43.1 161.7 43.1 39.2 0 100.4-45.8 175.1-45.8 28.3 0 130.3 2.6 197.2 99.2zM554.1 159.4c31.1-36.9 53.1-88.1 53.1-139.3 0-7.1-.6-14.3-1.9-20.1-50.6 1.9-110.8 33.7-147.1 75.8-28.9 32.4-57.2 83.6-57.2 135.4 0 7.8 1.3 15.6 1.9 18.1 3.2.6 8.4 1.3 13.6 1.3 45.4 0 102.5-30.4 137.6-71.2z" />
							</svg>
							Download for Mac
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
								href="/download"
								onClick={() => setIsOpen(false)}
							>
								<svg
									className="h-3.5 w-3.5 fill-current"
									viewBox="0 0 814 1000"
								>
									<path d="M788.1 340.9c-5.8 4.5-108.2 62.2-108.2 190.5 0 148.4 130.3 200.9 134.2 202.2-.6 3.2-20.7 71.9-68.7 141.9-42.8 61.6-87.5 123.1-155.5 123.1s-85.5-39.5-164-39.5c-76.5 0-103.7 40.8-165.9 40.8s-105.6-57.8-155.5-127.4c-58.3-81.6-105.6-208.4-105.6-328.6 0-193 125.6-295.5 249.2-295.5 65.7 0 120.5 43.1 161.7 43.1 39.2 0 100.4-45.8 175.1-45.8 28.3 0 130.3 2.6 197.2 99.2zM554.1 159.4c31.1-36.9 53.1-88.1 53.1-139.3 0-7.1-.6-14.3-1.9-20.1-50.6 1.9-110.8 33.7-147.1 75.8-28.9 32.4-57.2 83.6-57.2 135.4 0 7.8 1.3 15.6 1.9 18.1 3.2.6 8.4 1.3 13.6 1.3 45.4 0 102.5-30.4 137.6-71.2z" />
								</svg>
								Download for Mac
							</a>
						</div>
					</div>
				</nav>
			)}
		</header>
	);
};
