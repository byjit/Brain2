import { useCallback, useEffect, useState } from "react";
import { Brain, MousePointerClick, ExternalLink, NotebookPen, ArrowLeft, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Spinner } from "@/components/ui/spinner";
import { Toaster } from "@/components/ui/sonner";
import { authStore, needsAttentionStore } from "@/services/capture/stores";
import { startPickerMsg, startNoteMsg } from "@/services/capture/messages";
import { SignIn } from "./SignIn";
import { SavePage } from "./modes/SavePage";
import { CustomNote } from "./modes/CustomNote";
import { NeedsAttention } from "./modes/NeedsAttention";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

type AuthState = "loading" | "signed-in" | "signed-out";
type ViewState = "main" | "attention";

function App() {
  const [auth, setAuth] = useState<AuthState>("loading");
  const [needsAttention, setNeedsAttention] = useState(0);
  const [noteOpen, setNoteOpen] = useState(false);
  const [view, setView] = useState<ViewState>("main");

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

  async function handleQuickNote() {
    try {
      const response = await startNoteMsg.send({}, { to: "background" });
      if (response.ok) {
        window.close();
      } else {
        // Fallback to inline dialog if injection failed (e.g. on restricted pages)
        setNoteOpen(true);
      }
    } catch {
      // Fallback on any error
      setNoteOpen(true);
    }
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
          <header className="flex items-center justify-between pb-1.5 border-b border-border/40">
            <div className="flex items-center gap-1.5">
              {view === "attention" ? (
                <Button
                  variant="ghost"
                  size="icon"
                  className="size-6 text-muted-foreground hover:text-foreground hover:bg-muted rounded-md cursor-pointer transition-all duration-200 shrink-0"
                  onClick={() => setView("main")}
                  aria-label="Back to main view"
                >
                  <ArrowLeft className="size-3.5 text-foreground" />
                </Button>
              ) : (
                <div className="flex size-6 items-center justify-center rounded-lg bg-primary/10 text-primary shadow-xs">
                  <Brain className="size-3.5 text-primary/95" />
                </div>
              )}
              <span
                className="text-xs font-bold tracking-tight text-foreground cursor-pointer select-none"
                onClick={() => setView("main")}
              >
                Brain2
              </span>
            </div>
            
            <div className="flex items-center gap-1">
              <Button
                variant={view === "attention" ? "secondary" : "ghost"}
                size="sm"
                className={`h-7 text-[11px] hover:text-foreground hover:bg-muted gap-1 px-2 rounded-md cursor-pointer transition-all duration-200 hover:scale-[1.02] active:scale-[0.98] ${
                  view === "attention"
                    ? "text-foreground bg-muted font-semibold"
                    : "text-muted-foreground"
                }`}
                onClick={() => setView(view === "attention" ? "main" : "attention")}
              >
                <AlertCircle className={`size-3 ${needsAttention > 0 ? "text-destructive animate-pulse" : ""}`} />
                Attention
                {needsAttention > 0 && (
                  <Badge variant="destructive" className="h-3.5 min-w-[14px] px-1 justify-center rounded-full text-[8px] font-bold border-none shadow-sm ml-0.5">
                    {needsAttention}
                  </Badge>
                )}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="h-7 text-[11px] text-muted-foreground hover:text-foreground hover:bg-muted gap-1 px-2 rounded-md cursor-pointer transition-all duration-200 hover:scale-[1.02] active:scale-[0.98]"
                onClick={openDashboard}
              >
                <ExternalLink className="size-3" />
                Dashboard
              </Button>
            </div>
          </header>

          {view === "main" ? (
            <>
              <div className="grid grid-cols-3 gap-2 py-1">
                <SavePage onSignedOut={() => setAuth("signed-out")} />

                <button
                  onClick={handlePicker}
                  className="flex flex-col items-center justify-center h-[90px] rounded-xl border border-border/80 bg-card hover:bg-muted/50 cursor-pointer hover:border-primary/30 transition-all duration-200 hover:scale-[1.03] active:scale-[0.97] group text-center"
                >
                  <div className="flex items-center justify-center size-9 rounded-lg bg-primary/5 text-primary/80 group-hover:bg-primary/10 group-hover:text-primary transition-all duration-200 mb-1.5">
                    <MousePointerClick className="size-4.5" />
                  </div>
                  <span className="text-[10px] font-semibold text-muted-foreground group-hover:text-foreground transition-all duration-200 leading-tight">
                    Select Area
                  </span>
                </button>

                <button
                  onClick={handleQuickNote}
                  className="flex flex-col items-center justify-center h-[90px] rounded-xl border border-border/80 bg-card hover:bg-muted/50 cursor-pointer hover:border-primary/30 transition-all duration-200 hover:scale-[1.03] active:scale-[0.97] group text-center"
                >
                  <div className="flex items-center justify-center size-9 rounded-lg bg-primary/5 text-primary/80 group-hover:bg-primary/10 group-hover:text-primary transition-all duration-200 mb-1.5">
                    <NotebookPen className="size-4.5" />
                  </div>
                  <span className="text-[10px] font-semibold text-muted-foreground group-hover:text-foreground transition-all duration-200 leading-tight">
                    Quick Note
                  </span>
                </button>
              </div>

              <Dialog open={noteOpen} onOpenChange={setNoteOpen}>
                <DialogContent className="max-w-[280px] p-4 gap-3" aria-describedby={undefined}>
                  <DialogHeader className="text-left pb-0.5">
                    <DialogTitle className="flex items-center gap-1.5 text-xs font-semibold text-foreground/80">
                      <NotebookPen className="size-3.5 text-primary" />
                      Quick Note
                    </DialogTitle>
                  </DialogHeader>
                  <CustomNote 
                    onSignedOut={() => setAuth("signed-out")} 
                    onClose={() => setNoteOpen(false)} 
                  />
                </DialogContent>
              </Dialog>
            </>
          ) : (
            <div className="py-1">
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



