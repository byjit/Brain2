# Quick overview on the basic routes structure

- `src/routes/__root.tsx`
- `src/routes/_landing.tsx` (shared landing layout)
- `src/routes/_landing/index.tsx` (current home/landing page at `/`)
- `src/routes/_public.tsx` (shared public layout)
- `src/routes/_public/login.tsx` (public page at `/login`)
- `src/routes/_authed.tsx` (shared authenticated layout + `beforeLoad` guard placeholder)
- `src/routes/_authed/dashboard.tsx` (authed page at `/dashboard`)
