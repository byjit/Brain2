import { createFileRoute, Outlet, redirect } from "@tanstack/react-router";
import { env } from "@/env";

/**
 * Authenticated section layout route.
 *
 * Place all authenticated-only pages under `src/routes/_authed/`.
 * This route acts as a shared layout + guard for those pages.
 */
export const Route = createFileRoute("/_authed")({
	beforeLoad: async ({ location }) => {
		let isAuthenticated = false;
		try {
			const res = await fetch(`${env.VITE_BRAIN2_API_URL}/auth/me`, {
				credentials: "include",
			});
			if (res.ok) {
				isAuthenticated = true;
			}
		} catch {
			isAuthenticated = false;
		}

		if (!isAuthenticated) {
			throw redirect({
				to: "/login",
				search: {
					redirect: location.href,
				},
			});
		}
	},
	component: AuthedLayout,
});

function AuthedLayout() {
	return (
		<div className="min-h-screen">
			{/* Shared authenticated app shell can be added here (sidebar/header/etc.) */}
			<Outlet />
		</div>
	);
}
