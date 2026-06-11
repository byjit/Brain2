import { useCallback, useEffect, useState } from "react";
import { Brain, MousePointerClick, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Spinner } from "@/components/ui/spinner";
import { Toaster } from "@/components/ui/sonner";
import { authStore, needsAttentionStore } from "@/services/capture/stores";
import { startPickerMsg } from "@/services/capture/messages";
import { SignIn } from "./SignIn";
import { SavePage } from "./modes/SavePage";
import { CustomNote } from "./modes/CustomNote";
import { NeedsAttention } from "./modes/NeedsAttention";

type AuthState = "loading" | "signed-in" | "signed-out";

function App() {
  const [auth, setAuth] = useState<AuthState>("loading");
  const [needsAttention, setNeedsAttention] = useState(0);

  // Read the auth store once on mount and decide which view to show. A valid
  // token must be present and not yet expired.
  const refreshAuth = useCallback(async () => {
    const tokens = await authStore.get();
    const valid =
      !!tokens.accessToken &&
      (tokens.expiresAt === null || tokens.expiresAt > Date.now());
    setAuth(valid ? "signed-in" : "signed-out");
  }, []);

  useEffect(() => {
    void refreshAuth();
    const unwatch = authStore.watch(() => {
      void refreshAuth();
    });
    return unwatch;
  }, [refreshAuth]);

  // Track the needs-attention badge count via the store (the background keeps
  // it current; reading the store keeps the popup decoupled from the backend).
  useEffect(() => {
    void needsAttentionStore.get().then(setNeedsAttention);
    const unwatch = needsAttentionStore.watch((next) => setNeedsAttention(next));
    return unwatch;
  }, []);

  function handlePicker() {
    startPickerMsg.emit({}, { to: "background" });
    window.close();
  }

  function openDashboard() {
    const dashboardUrl = "http://localhost:3000/dashboard";
    browser.tabs.create({ url: dashboardUrl });
  }

  return (
    <div className="min-w-[320px] max-w-[320px] bg-background text-foreground p-3.5 antialiased selection:bg-primary/10">
      {auth === "loading" && (
        <div className="flex items-center justify-center py-12">
          <Spinner className="size-5 text-primary" />
        </div>
      )}

      {auth === "signed-out" && (
        <SignIn onSignedIn={() => void refreshAuth()} />
      )}

      {auth === "signed-in" && (
        <div className="space-y-3.5">
          <header className="flex items-center justify-between pb-2 mb-2 border-b border-border/40">
            <div className="flex items-center gap-1.5">
              <Brain className="size-4.5 text-primary" />
              <span className="text-xs font-bold tracking-tight text-foreground">Brain2</span>
            </div>
            
            <div className="flex items-center gap-1.5">
              <Button
                variant="ghost"
                size="sm"
                className="h-7 text-[11px] text-muted-foreground hover:text-foreground hover:bg-muted gap-1 px-2 rounded-md cursor-pointer transition-all duration-200 hover:scale-[1.02] active:scale-[0.98]"
                onClick={openDashboard}
              >
                <ExternalLink className="size-3" />
                Dashboard
              </Button>
              {needsAttention > 0 && (
                <Badge variant="destructive" className="h-4 min-w-[16px] px-1 justify-center rounded-full text-[9px] font-medium border-none shadow-sm animate-pulse">
                  {needsAttention}
                </Badge>
              )}
            </div>
          </header>

          <SavePage onSignedOut={() => setAuth("signed-out")} />

          <Button
            variant="outline"
            className="w-full h-9 border-border/80 hover:bg-accent/50 hover:text-accent-foreground cursor-pointer rounded-lg font-medium text-xs gap-1.5 transition-all duration-200 hover:scale-[1.01] active:scale-[0.99]"
            onClick={handlePicker}
          >
            <MousePointerClick className="size-3.5 text-muted-foreground" />
            Select Area to Clip
          </Button>

          <div className="border-t border-border/60 my-1"></div>

          <CustomNote onSignedOut={() => setAuth("signed-out")} />

          {needsAttention > 0 && (
            <div className="pt-2 border-t border-border/60">
              <NeedsAttention count={needsAttention} />
            </div>
          )}
        </div>
      )}

      <Toaster position="bottom-center" />
    </div>
  );
}

export default App;
