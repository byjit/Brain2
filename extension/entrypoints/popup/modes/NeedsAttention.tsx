import { useEffect, useState } from "react";
import { toast } from "sonner";
import { AlertTriangle, CheckCircle2, Wrench } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Spinner } from "@/components/ui/spinner";
import { getFailedMsg, repairMsg } from "@/services/capture/messages";
import type { FailedEntry } from "@/services/capture/types";

interface NeedsAttentionProps {
  /** Current failed-entry count from the store; drives whether we fetch. */
  count: number;
}

/**
 * "Needs attention" repair list. When the count is positive we load the failed
 * entries and let the user attach the missing note and re-submit each one.
 * Repaired rows are removed from local state on success.
 */
export function NeedsAttention({ count }: NeedsAttentionProps) {
  const [entries, setEntries] = useState<FailedEntry[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (count <= 0) {
      setEntries([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    getFailedMsg
      .send({}, { to: "background" })
      .then((res) => {
        if (!cancelled) setEntries(res.entries);
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

  if (count <= 0) {
    return (
      <p className="flex items-center gap-2 text-xs text-muted-foreground">
        <CheckCircle2 className="size-3.5" />
        All caught up
      </p>
    );
  }

  return (
    <div className="space-y-2">
      <h2 className="flex items-center gap-2 text-sm font-medium">
        <AlertTriangle className="size-4 text-amber-500" />
        Needs attention
      </h2>
      {loading ? (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Spinner className="size-3.5" />
          Loading…
        </div>
      ) : (
        <div className="space-y-2">
          {entries.map((entry) => (
            <RepairRow
              key={entry.id}
              entry={entry}
              onRepaired={() =>
                setEntries((prev) => prev.filter((e) => e.id !== entry.id))
              }
            />
          ))}
        </div>
      )}
    </div>
  );
}

function RepairRow({
  entry,
  onRepaired,
}: {
  entry: FailedEntry;
  onRepaired: () => void;
}) {
  const [note, setNote] = useState(entry.note ?? "");
  const [repairing, setRepairing] = useState(false);

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
        onRepaired();
      } else {
        toast.error("Repair failed. Please try again.");
      }
    } catch {
      toast.error("Repair failed. Please try again.");
    } finally {
      setRepairing(false);
    }
  }

  return (
    <div className="rounded-md border border-border p-3 space-y-2">
      <div className="space-y-0.5">
        <p className="truncate text-sm font-medium" title={heading}>
          {heading}
        </p>
        {entry.url && (
          <p className="truncate text-xs text-muted-foreground" title={entry.url}>
            {entry.url}
          </p>
        )}
        {entry.error_message && (
          <p className="text-xs text-destructive">{entry.error_message}</p>
        )}
      </div>
      <Textarea
        aria-label={`Note for ${heading}`}
        placeholder="Add a note to repair this entry…"
        value={note}
        onChange={(e) => setNote(e.target.value)}
        rows={2}
      />
      <Button
        size="sm"
        variant="secondary"
        className="w-full"
        onClick={handleRepair}
        disabled={!canRepair || repairing}
      >
        {repairing ? <Spinner className="size-4" /> : <Wrench className="size-4" />}
        Repair
      </Button>
    </div>
  );
}
