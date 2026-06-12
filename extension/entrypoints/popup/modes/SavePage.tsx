import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Globe } from "lucide-react";
import { Spinner } from "@/components/ui/spinner";
import { savePageMsg } from "@/services/capture/messages";
import { isSignedOutError } from "../lib/is-signed-out";

interface SavePageProps {
  /** Routes the popup back to the sign-in view when a save reveals no token. */
  onSignedOut: () => void;
}

/**
 * The prominent default capture mode, refactored to fit as a horizontal card button.
 * Fire-and-forget: on success we toast and close the popup shortly after.
 */
export function SavePage({ onSignedOut }: SavePageProps) {
  const [savingPage, setSavingPage] = useState(false);

  // Guards post-await state updates: a signed-out error unmounts this
  // component (App swaps in <SignIn>), so the in-flight flags must not be
  // cleared on an unmounted instance.
  const mountedRef = useRef(true);
  useEffect(() => () => { mountedRef.current = false; }, []);

  async function save() {
    try {
      await savePageMsg.send({}, { to: "background" });
      toast.success("Saved to Brain2");
      setTimeout(() => window.close(), 600);
    } catch (err) {
      if (isSignedOutError(err)) {
        onSignedOut();
        return;
      }
      toast.error("Couldn't save this page. Please try again.");
    }
  }

  async function handleSavePage() {
    setSavingPage(true);
    try {
      await save();
    } finally {
      if (mountedRef.current) setSavingPage(false);
    }
  }

  return (
    <button
      onClick={handleSavePage}
      disabled={savingPage}
      className="flex flex-col items-center justify-center h-[90px] rounded-xl border border-border/80 bg-card hover:bg-muted/50 cursor-pointer hover:border-primary/30 transition-all duration-200 hover:scale-[1.03] active:scale-[0.97] group text-center disabled:opacity-50"
    >
      <div className="flex items-center justify-center size-9 rounded-lg bg-primary/5 text-primary/80 group-hover:bg-primary/10 group-hover:text-primary transition-all duration-200 mb-1.5">
        {savingPage ? <Spinner className="size-4.5 animate-spin" /> : <Globe className="size-4.5" />}
      </div>
      <span className="text-[10px] font-semibold text-muted-foreground group-hover:text-foreground transition-all duration-200 leading-tight">
        {savingPage ? "Saving..." : "Save Page"}
      </span>
    </button>
  );
}


