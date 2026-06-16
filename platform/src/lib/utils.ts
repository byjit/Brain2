import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Merge Tailwind class names, resolving conflicts (shadcn/ui convention).
 * Used across the UI component library via the `cn` helper.
 */
export function cn(...inputs: ClassValue[]) {
	return twMerge(clsx(inputs));
}
