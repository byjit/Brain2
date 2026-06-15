import { useCallback, useEffect, useState } from "react";
import { Brain, ExternalLink, AlertCircle, CheckCircle2, Wrench, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { Toaster } from "@/components/ui/sonner";
import { Textarea } from "@/components/ui/textarea";
import { authStore, needsAttentionStore } from "@/services/capture/stores";
import { getFailedMsg, repairMsg, deleteEntryMsg } from "@/services/capture/messages";
import type { FailedEntry } from "@/services/capture/types";
import { SignIn } from "../popup/SignIn";
import { toast } from "sonner";

type AuthState = "loading" | "signed-in" | "signed-out";

function App() {
  const [auth, setAuth] = useState<AuthState>("loading");
  const [entries, setEntries] = useState<FailedEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [noteMap, setNoteMap] = useState<{ [id: string]: string }>({});
  const [processing, setProcessing] = useState<{ [id: string]: boolean }>({});

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

  // Initial fetch of failed entries
  useEffect(() => {
    if (auth === "signed-in") {
      setLoading(true);
      getFailedMsg
        .send({}, { to: "background" })
        .then((res) => {
          setEntries(res.entries);
          const initialNotes: { [id: string]: string } = {};
          res.entries.forEach((entry) => {
            initialNotes[entry.id] = entry.note ?? "";
          });
          setNoteMap(initialNotes);
        })
        .catch(() => {
          toast.error("Couldn't load entries needing attention.");
        })
        .finally(() => {
          setLoading(false);
        });
    }
  }, [auth]);

  // Keep entries list synchronized if the needs-attention store count changes in background
  useEffect(() => {
    if (auth !== "signed-in") return;
    const unwatch = needsAttentionStore.watch(async () => {
      try {
        const res = await getFailedMsg.send({}, { to: "background" });
        setEntries(res.entries);
        setNoteMap((prev) => {
          const next = { ...prev };
          res.entries.forEach((entry) => {
            if (next[entry.id] === undefined) {
              next[entry.id] = entry.note ?? "";
            }
          });
          return next;
        });
      } catch {
        // Suppress background sync errors
      }
    });
    return unwatch;
  }, [auth]);

  function openDashboard() {
    const dashboardUrl = "http://localhost:3000/dashboard";
    browser.tabs.create({ url: dashboardUrl });
  }

  async function handleRepair(id: string) {
    const note = noteMap[id]?.trim();
    if (!note) return;
    setProcessing((prev) => ({ ...prev, [id]: true }));
    try {
      const { ok } = await repairMsg.send(
        { id, note },
        { to: "background" }
      );
      if (ok) {
        toast.success("Entry repaired successfully");
        setEntries((prev) => prev.filter((e) => e.id !== id));
      } else {
        toast.error("Repair failed. Please try again.");
      }
    } catch {
      toast.error("Repair failed. Please try again.");
    } finally {
      setProcessing((prev) => ({ ...prev, [id]: false }));
    }
  }

  async function handleForget(id: string) {
    setProcessing((prev) => ({ ...prev, [id]: true }));
    try {
      const { deleted } = await deleteEntryMsg.send(
        { id },
        { to: "background" }
      );
      if (deleted) {
        toast.success("Entry forgotten and skipped");
        setEntries((prev) => prev.filter((e) => e.id !== id));
      } else {
        toast.error("Failed to forget entry.");
      }
    } catch {
      toast.error("Failed to forget entry.");
    } finally {
      setProcessing((prev) => ({ ...prev, [id]: false }));
    }
  }

  return (
    <div className="min-h-screen bg-background text-foreground antialiased selection:bg-primary/10">
      <header className="border-b border-border/40 bg-card/20 backdrop-blur-md sticky top-0 z-50">
        <div className="max-w-4xl mx-auto px-4 h-14 flex items-center justify-between">
          <div className="flex items-center gap-2 select-none">
            <div className="flex size-7 items-center justify-center rounded-lg bg-primary/10 text-primary shadow-xs">
              <Brain className="size-4 text-primary/95" />
            </div>
            <span className="text-sm font-bold tracking-tight text-foreground">
              Brain2
            </span>
          </div>
          
          <Button
            variant="ghost"
            size="sm"
            className="h-8 text-xs text-muted-foreground hover:text-foreground hover:bg-muted gap-1.5 px-3 rounded-lg cursor-pointer transition-all duration-200 hover:scale-[1.01] active:scale-[0.99]"
            onClick={openDashboard}
          >
            <ExternalLink className="size-3.5" />
            Dashboard
          </Button>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-4 py-8">
        {auth === "loading" && (
          <div className="flex flex-col items-center justify-center py-20 gap-3">
            <Spinner className="size-6 text-primary animate-spin" />
            <p className="text-xs text-muted-foreground">Checking authentication...</p>
          </div>
        )}

        {auth === "signed-out" && (
          <div className="max-w-md mx-auto py-12">
            <SignIn onSignedIn={() => void refreshAuth()} />
          </div>
        )}

        {auth === "signed-in" && (
          <div className="space-y-6">
            <div className="flex flex-col gap-1 pb-4 border-b border-border/40">
              <h1 className="text-2xl font-extrabold tracking-tight text-foreground flex items-center gap-2">
                <AlertCircle className="size-6 text-destructive" />
                Needs Attention
                {entries.length > 0 && (
                  <span className="text-xs font-semibold bg-destructive/10 text-destructive border border-destructive/20 px-2 py-0.5 rounded-full ml-1">
                    {entries.length} {entries.length === 1 ? "issue" : "issues"}
                  </span>
                )}
              </h1>
              <p className="text-xs text-muted-foreground">
                Review and repair captured items that couldn't be automatically summarized or enriched.
              </p>
            </div>

            {loading && entries.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 gap-3">
                <Spinner className="size-5 text-muted-foreground animate-spin" />
                <p className="text-xs text-muted-foreground">Loading failed entries...</p>
              </div>
            ) : entries.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 px-4 text-center space-y-4 rounded-2xl border border-dashed border-border bg-card/30">
                <div className="flex size-14 items-center justify-center rounded-full bg-emerald-500/10 text-emerald-500 shadow-xs">
                  <CheckCircle2 className="size-7 animate-pulse" />
                </div>
                <div className="space-y-1.5">
                  <h3 className="text-base font-bold text-foreground">No attention needed</h3>
                  <p className="text-xs text-muted-foreground max-w-[280px] leading-relaxed mx-auto">
                    All captured items have been successfully enriched and indexed.
                  </p>
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                {entries.map((entry) => {
                  const heading = entry.title || entry.url || "Untitled capture";
                  const isEntryProcessing = processing[entry.id];
                  const entryNote = noteMap[entry.id] ?? "";
                  const canRepair = entryNote.trim().length > 0;

                  return (
                    <div
                      key={entry.id}
                      className="rounded-2xl border border-destructive/10 bg-card/40 p-5 space-y-4 shadow-xs hover:border-destructive/20 hover:shadow-sm transition-all duration-200"
                    >
                      <div className="space-y-1">
                        <h3 className="text-sm font-bold text-foreground leading-tight" title={heading}>
                          {heading}
                        </h3>
                        {entry.url && (
                          <a
                            href={entry.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-xs text-muted-foreground hover:text-primary hover:underline hover:underline-offset-2 break-all inline-flex items-center gap-1.5 transition-all mt-0.5"
                            title={entry.url}
                          >
                            {entry.url}
                            <ExternalLink className="size-3" />
                          </a>
                        )}
                      </div>

                      {entry.error_message && (
                        <div className="text-xs text-destructive bg-destructive/5 border border-destructive/10 rounded-xl p-3 leading-relaxed font-medium">
                          <span className="font-semibold uppercase tracking-wider text-[10px] mr-1.5">Error:</span>
                          {entry.error_message}
                        </div>
                      )}

                      <div className="space-y-1.5">
                        <label className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">
                          Summary Note
                        </label>
                        <Textarea
                          placeholder="Add summary note to manually index this entry…"
                          value={entryNote}
                          onChange={(e) =>
                            setNoteMap((prev) => ({ ...prev, [entry.id]: e.target.value }))
                          }
                          rows={3}
                          className="rounded-xl bg-background text-xs resize-none border-border/80 focus-visible:ring-1 focus-visible:ring-destructive/30 focus-visible:border-destructive transition-all duration-200"
                          disabled={isEntryProcessing}
                        />
                      </div>

                      <div className="flex items-center justify-end gap-2.5 pt-1">
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-8 px-3.5 text-xs font-medium text-muted-foreground border-border hover:text-destructive hover:bg-destructive/5 hover:border-destructive/20 rounded-lg cursor-pointer transition-all duration-200"
                          onClick={() => handleForget(entry.id)}
                          disabled={isEntryProcessing}
                        >
                          {isEntryProcessing ? (
                            <Spinner className="size-3" />
                          ) : (
                            <Trash2 className="size-3.5 mr-1" />
                          )}
                          Forget
                        </Button>
                        
                        <Button
                          size="sm"
                          className="h-8 bg-destructive text-destructive-foreground hover:bg-destructive/90 cursor-pointer rounded-lg text-xs font-semibold gap-1.5 transition-all duration-200 disabled:opacity-50"
                          onClick={() => handleRepair(entry.id)}
                          disabled={!canRepair || isEntryProcessing}
                        >
                          {isEntryProcessing ? (
                            <Spinner className="size-3.5 animate-spin" />
                          ) : (
                            <Wrench className="size-3.5" />
                          )}
                          Repair Entry
                        </Button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </main>

      <Toaster position="bottom-center" />
    </div>
  );
}

export default App;
