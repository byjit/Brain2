import { Brain } from "lucide-react";
import { APP_NAME } from "@/lib/constant";
import { cn } from "@/lib/utils";

export const LogoIcon = Brain;
export const Logo = ({
	className,
	showText,
}: {
	className?: string;
	showText?: boolean;
}) => (
	<div className={cn("flex gap-2 items-center", className)}>
		<div className="bg-primary p-1.5 rounded-lg">
			<Brain className="h-6 w-6 text-primary-foreground" />
		</div>
		{showText && <span className="font-semibold">{APP_NAME}</span>}
	</div>
);
