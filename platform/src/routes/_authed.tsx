import { createFileRoute, Outlet, redirect } from "@tanstack/react-router";

/**
 * Authenticated section layout route.
 *
 * Place all authenticated-only pages under `src/routes/_authed/`.
 * This route acts as a shared layout + guard for those pages.
 */
export const Route = createFileRoute("/_authed")({
	beforeLoad: async ({ location }) => {
		/**
		 * TODO: Replace this placeholder with your real auth check
		 * (e.g. token validation, session lookup, Zustand auth store, API call).
		 */
		const isAuthenticated = false;

		if (!isAuthenticated) {
			throw redirect({
				to: "/",
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
