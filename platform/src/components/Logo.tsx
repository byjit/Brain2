import { Cherry } from "lucide-react";
import { APP_NAME } from "@/lib/constant";
import { cn } from "@/lib/utils";

export const LogoIcon = Cherry;
export const Logo = ({
	className,
	showText,
}: {
	className?: string;
	showText?: boolean;
}) => (
	<div className={cn("flex gap-2 items-center", className)}>
		<Cherry className="h-6 w-6" />
		{showText && <span className="font-semibold">{APP_NAME}</span>}
	</div>
);
