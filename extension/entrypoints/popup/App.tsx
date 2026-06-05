import { useCallback, useEffect, useState } from "react";
import { Brain, MousePointerClick } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
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

  return (
    <div className="min-w-[340px] max-w-[380px] bg-background text-foreground p-4">
      {auth === "loading" && (
        <div className="flex items-center justify-center py-10">
          <Spinner className="size-5 text-muted-foreground" />
        </div>
      )}

      {auth === "signed-out" && (
        <SignIn onSignedIn={() => setAuth("signed-in")} />
      )}

      {auth === "signed-in" && (
        <div className="space-y-4">
          <header className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="flex size-7 items-center justify-center rounded-md bg-primary/10 text-primary">
                <Brain className="size-4" />
              </div>
              <span className="text-sm font-semibold tracking-tight">Brain2</span>
            </div>
            {needsAttention > 0 && (
              <Badge variant="secondary" className="gap-1">
                {needsAttention} needs attention
              </Badge>
            )}
          </header>

          <SavePage onSignedOut={() => setAuth("signed-out")} />

          <Button
            variant="outline"
            className="w-full"
            onClick={handlePicker}
          >
            <MousePointerClick className="size-4" />
            Select content
          </Button>

          <Separator />

          <CustomNote onSignedOut={() => setAuth("signed-out")} />

          <Separator />

          <NeedsAttention count={needsAttention} />
        </div>
      )}

      <Toaster position="bottom-center" />
    </div>
  );
}

export default App;
