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
      <Label htmlFor="custom-note" className="flex items-center gap-2">
        <NotebookPen className="size-4" />
        Quick note
      </Label>
      <Textarea
        id="custom-note"
        placeholder="Jot something down to save to Brain2…"
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={3}
      />
      <Button
        variant="secondary"
        className="w-full"
        onClick={handleSave}
        disabled={!canSave || saving}
      >
        {saving ? <Spinner className="size-4" /> : <Send className="size-4" />}
        Save note
      </Button>
    </div>
  );
}
