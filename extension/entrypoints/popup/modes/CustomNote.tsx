import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { NotebookPen, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Spinner } from "@/components/ui/spinner";
import { saveNoteMsg } from "@/services/capture/messages";
import { isSignedOutError } from "../lib/is-signed-out";

interface CustomNoteProps {
  /** Routes the popup back to the sign-in view when a save reveals no token. */
  onSignedOut: () => void;
}

/**
 * Free-form note capture. Save is disabled for empty/whitespace input.
 * Fire-and-forget: toast on success, then close.
 */
export function CustomNote({ onSignedOut }: CustomNoteProps) {
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
    <div className="space-y-2">
      <div className="space-y-1.5">
        <Label htmlFor="custom-note" className="flex items-center gap-1 text-[11px] font-semibold text-foreground/80">
          <NotebookPen className="size-3 text-primary" />
          Quick Note
        </Label>
        <Textarea
          id="custom-note"
          placeholder="Jot down notes, code snippets, or thoughts to save to your memory..."
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={3}
          className="rounded-lg border-border/80 focus-visible:ring-1 focus-visible:ring-primary/30 focus-visible:border-primary text-[11px] resize-none leading-relaxed transition-all duration-200"
        />
      </div>
      <Button
        className="w-full h-8 bg-primary text-primary-foreground hover:bg-primary/95 cursor-pointer rounded-lg font-medium text-[11px] gap-1 transition-all duration-200 hover:scale-[1.01] active:scale-[0.99] disabled:opacity-50"
        onClick={handleSave}
        disabled={!canSave || saving}
      >
        {saving ? <Spinner className="size-3 animate-spin" /> : <Send className="size-3" />}
        Save Note
      </Button>
    </div>
  );
}
