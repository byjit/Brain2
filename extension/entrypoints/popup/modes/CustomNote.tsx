import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Spinner } from "@/components/ui/spinner";
import { saveNoteMsg } from "@/services/capture/messages";
import { isSignedOutError } from "../lib/is-signed-out";

interface CustomNoteProps {
  /** Routes the popup back to the sign-in view when a save reveals no token. */
  onSignedOut: () => void;
  /** Callback to close the note editor dialog. */
  onClose: () => void;
}

/**
 * Free-form note capture content component designed to be displayed inside a modal Dialog.
 */
export function CustomNote({ onSignedOut, onClose }: CustomNoteProps) {
  const [text, setText] = useState("");
  const [saving, setSaving] = useState(false);

  const canSave = text.trim().length > 0;

  // Guards the post-await flag clear: a signed-out error unmounts this
  // component (App swaps in <SignIn>), so we must not setState afterwards.
  const mountedRef = useRef(true);
  useEffect(() => () => { mountedRef.current = false; }, []);

  async function handleSave() {
    const note = text.trim();
    if (!note) return;
    setSaving(true);
    try {
      await saveNoteMsg.send({ text: note }, { to: "background" });
      toast.success("Note saved to Brain2");
      setTimeout(() => window.close(), 600);
    } catch (err) {
      if (isSignedOutError(err)) {
        onSignedOut();
        return;
      }
      toast.error("Couldn't save your note. Please try again.");
    } finally {
      if (mountedRef.current) setSaving(false);
    }
  }

  return (
    <div className="space-y-3">
      <Textarea
        id="custom-note"
        placeholder="Jot down notes, code snippets, or thoughts..."
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={4}
        autoFocus
        className="w-full rounded-xl border border-border bg-card p-3 text-xs leading-relaxed focus-visible:ring-1 focus-visible:ring-primary/30 focus-visible:border-primary resize-none transition-all duration-200"
      />
      <div className="flex gap-2">
        <Button
          variant="outline"
          onClick={onClose}
          disabled={saving}
          className="flex-1 h-9 rounded-xl text-xs font-semibold border-border/80 hover:bg-accent cursor-pointer transition-all duration-200 active:scale-98"
        >
          Cancel
        </Button>
        <Button
          onClick={handleSave}
          disabled={!canSave || saving}
          className="flex-1 h-9 bg-primary text-primary-foreground hover:bg-primary/95 cursor-pointer rounded-xl font-semibold text-xs gap-1.5 transition-all duration-200 hover:scale-[1.01] active:scale-[0.99] disabled:opacity-50"
        >
          {saving ? <Spinner className="size-3.5 animate-spin" /> : <Send className="size-3.5" />}
          Save Note
        </Button>
      </div>
    </div>
  );
}


