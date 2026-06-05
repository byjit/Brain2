import { Link } from "@tanstack/react-router";
import { Menu, X } from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";
import { Logo } from "./Logo";
import { Button, buttonVariants } from "./ui/button";

export default function Header() {
	const [isOpen, setIsOpen] = useState(false);
	const navLinks: { title: string; url: string }[] = [];

	return (
		<header className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-6 py-4 max-w-5xl mx-auto bg-background/80 backdrop-blur-md ">
			<div className="flex items-center gap-2">
				<Logo showText />
			</div>

			<nav className="hidden md:flex items-center gap-1 p-1 rounded-full border">
				{navLinks.map((item) => (
					<Link
						className={cn(
							buttonVariants({ variant: "ghost", className: "rounded-full" })
						)}
						key={item.title}
						to={item.url}
					>
						{item.title}
					</Link>
				))}
			</nav>

			<div className="hidden md:flex items-center gap-4">
				<Button>Get Mirage</Button>
			</div>

			<Button className="md:hidden p-2" onClick={() => setIsOpen(!isOpen)}>
				{isOpen ? <X /> : <Menu />}
			</Button>

			{/* Mobile Menu */}
			{isOpen && (
				<div className="absolute top-full left-0 right-0 bg-background border-b p-4 flex flex-col gap-4 md:hidden shadow-lg">
					{navLinks.map((item) => (
						<Link
							className={cn(
								buttonVariants({ variant: "ghost", className: "rounded-full" })
							)}
							key={item.title}
							onClick={() => setIsOpen(false)}
							to={item.url}
						>
							{item.title}
						</Link>
					))}
					<Button size={"sm"}>Get Started</Button>
				</div>
			)}
		</header>
	);
}
