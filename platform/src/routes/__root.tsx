import { TanStackDevtools } from "@tanstack/react-devtools";
import { createRootRoute, Outlet } from "@tanstack/react-router";
import { TanStackRouterDevtoolsPanel } from "@tanstack/react-router-devtools";
import { GlobalError } from "@/components/GlobalError";
import { NotFound } from "@/components/NotFound";
import { Pending } from "@/components/Pending";
import { ThemeProvider } from "@/components/theme-provider";

export const Route = createRootRoute({
	component: () => (
		<ThemeProvider
			attribute="class"
			defaultTheme="dark"
			storageKey="vite-ui-theme"
		>
			<Outlet />
			<TanStackDevtools
				config={{
					position: "bottom-right",
				}}
				plugins={[
					{
						name: "Tanstack Router",
						render: <TanStackRouterDevtoolsPanel />,
					},
				]}
			/>
		</ThemeProvider>
	),
	notFoundComponent: NotFound,
	errorComponent: GlobalError,
	pendingComponent: Pending,
});
