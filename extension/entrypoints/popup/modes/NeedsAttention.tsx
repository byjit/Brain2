import { useEffect, useState } from "react";
import { toast } from "sonner";
import { AlertCircle, CheckCircle2, Wrench, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Spinner } from "@/components/ui/spinner";
import { getFailedMsg, repairMsg, deleteEntryMsg } from "@/services/capture/messages";
import type { FailedEntry } from "@/services/capture/types";

interface NeedsAttentionProps {
  /** Current failed-entry count from the store; drives whether we fetch. */
  count: number;
}

/**
 * "Needs attention" repair list. When the count is positive we load the failed
 * entries and let the user attach the missing note and re-submit each one.
 * Repaired or deleted rows are removed from local state on success.
 */
export function NeedsAttention({ count }: NeedsAttentionProps) {
  const [entries, setEntries] = useState<FailedEntry[]>([]);
  // Full failed count from the response; the loaded list may be a bounded page of it.
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [isFirstLoad, setIsFirstLoad] = useState(true);

  useEffect(() => {
    if (count <= 0) {
      setEntries([]);
      return;
    }
    let cancelled = false;
    if (isFirstLoad) {
      setLoading(true);
    }
    getFailedMsg
      .send({}, { to: "background" })
      .then((res) => {
        if (!cancelled) {
          setEntries(res.entries);
          setTotal(res.total);
          setIsFirstLoad(false);
        }
      })
      .catch(() => {
        if (!cancelled) toast.error("Couldn't load entries needing attention.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [count]);

  if (count <= 0 || entries.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-10 px-4 text-center space-y-3">
        <div className="flex size-12 items-center justify-center rounded-full bg-emerald-500/10 text-emerald-500">
          <CheckCircle2 className="size-6 animate-pulse" />
        </div>
        <div className="space-y-1">
          <h3 className="text-xs font-bold text-foreground">No attention needed</h3>
          <p className="text-[11px] text-muted-foreground max-w-[200px] leading-relaxed">
            All captured items have been successfully enriched and indexed.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <h2 className="flex items-center gap-1.5 text-xs font-semibold text-destructive uppercase tracking-wider">
        <AlertCircle className="size-3.5 text-destructive" />
        Needs Attention ({total})
      </h2>
      {loading ? (
        <div className="flex items-center gap-2 text-xs text-muted-foreground py-2">
          <Spinner className="size-3.5 animate-spin" />
          Loading issues…
        </div>
      ) : (

        <div className="space-y-3 max-h-[300px] overflow-y-auto pr-1">
          {entries.map((entry) => (
            <RepairRow
              key={entry.id}
              entry={entry}
              onRemoved={() => {
                setEntries((prev) => prev.filter((e) => e.id !== entry.id));
                setTotal((prev) => Math.max(0, prev - 1));
              }}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function RepairRow({
  entry,
  onRemoved,
}: {
  entry: FailedEntry;
  onRemoved: () => void;
}) {
  const [note, setNote] = useState(entry.note ?? "");
  const [repairing, setRepairing] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const canRepair = note.trim().length > 0;
  const heading = entry.title || entry.url || "Untitled capture";

  async function handleRepair() {
    const value = note.trim();
    if (!value) return;
    setRepairing(true);
    try {
      const { ok } = await repairMsg.send(
        { id: entry.id, note: value },
        { to: "background" },
      );
      if (ok) {
        toast.success("Repaired");
        onRemoved();
      } else {
        toast.error("Repair failed. Please try again.");
      }
    } catch {
      toast.error("Repair failed. Please try again.");
    } finally {
      setRepairing(false);
    }
  }

  async function handleDelete() {
    setDeleting(true);
    try {
      const { deleted } = await deleteEntryMsg.send(
        { id: entry.id },
        { to: "background" }
      );
      if (deleted) {
        toast.success("Entry deleted");
        onRemoved();
      } else {
        toast.error("Failed to delete entry.");
      }
    } catch {
      toast.error("Failed to delete entry.");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="rounded-xl border border-destructive/15 bg-destructive/5/80 p-3 space-y-2.5 shadow-sm transition-all duration-200 hover:border-destructive/35 hover:shadow-md">
      <div className="flex items-start justify-between gap-2">
        <div className="space-y-0.5 min-w-0 flex-1">
          <p className="truncate text-xs font-semibold text-foreground" title={heading}>
            {heading}
          </p>
          {entry.url && (
            <p className="truncate text-[10px] text-muted-foreground" title={entry.url}>
              {entry.url}
            </p>
          )}
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="size-6 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded-md cursor-pointer shrink-0 transition-all duration-200"
          onClick={handleDelete}
          disabled={deleting || repairing}
          aria-label={`Delete ${heading}`}
        >
          {deleting ? (
            <Spinner className="size-3" />
          ) : (
            <Trash2 className="size-3.5" />
          )}
        </Button>
      </div>

      {entry.error_message && (
        <p className="text-[10px] text-destructive leading-tight font-medium bg-destructive/10 p-1.5 rounded-md border border-destructive/10">
          {entry.error_message}
        </p>
      )}

      <Textarea
        aria-label={`Note for ${heading}`}
        placeholder="Add summary note to manually index this entry…"
        value={note}
        onChange={(e) => setNote(e.target.value)}
        rows={2}
        className="rounded-lg bg-background text-xs resize-none border-border/80 focus-visible:ring-1 focus-visible:ring-destructive/30 focus-visible:border-destructive transition-all duration-200"
      />
      <Button
        size="sm"
        className="w-full h-8 bg-destructive text-destructive-foreground hover:bg-destructive/90 cursor-pointer rounded-lg text-xs font-medium gap-1.5 transition-all duration-200 hover:scale-[1.01] active:scale-[0.99] disabled:opacity-50"
        onClick={handleRepair}
        disabled={!canRepair || repairing || deleting}
      >
        {repairing ? <Spinner className="size-3.5 animate-spin" /> : <Wrench className="size-3.5" />}
        Repair Entry
      </Button>
    </div>
  );
}

