import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { ChevronDown, Link2, Save } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { savePageMsg } from "@/services/capture/messages";
import { isSignedOutError } from "../lib/is-signed-out";

interface SavePageProps {
  /** Routes the popup back to the sign-in view when a save reveals no token. */
  onSignedOut: () => void;
}

/**
 * The prominent default capture mode. Fire-and-forget: on success we toast and
 * close the popup shortly after; we never block on a spinner beyond the
 * in-flight button state. A secondary collapsible lets the user save a
 * different URL than the active tab.
 */
export function SavePage({ onSignedOut }: SavePageProps) {
  const [savingPage, setSavingPage] = useState(false);
  const [savingUrl, setSavingUrl] = useState(false);
  const [overrideUrl, setOverrideUrl] = useState("");
  const [isOpen, setIsOpen] = useState(false);

  // Guards post-await state updates: a signed-out error unmounts this
  // component (App swaps in <SignIn>), so the in-flight flags must not be
  // cleared on an unmounted instance.
  const mountedRef = useRef(true);
  useEffect(() => () => { mountedRef.current = false; }, []);

  async function save(overrideUrlArg?: string) {
    try {
      await savePageMsg.send(
        overrideUrlArg ? { overrideUrl: overrideUrlArg } : {},
        { to: "background" },
      );
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

  async function handleSaveUrl() {
    const url = overrideUrl.trim();
    if (!url) return;
    setSavingUrl(true);
    try {
      await save(url);
    } finally {
      if (mountedRef.current) setSavingUrl(false);
    }
  }

  return (
    <div className="space-y-2.5">
      <Button
        size="lg"
        className="w-full h-10 bg-primary text-primary-foreground hover:bg-primary/95 cursor-pointer rounded-lg font-medium text-xs gap-1.5 shadow-xs transition-all duration-200 hover:scale-[1.01] active:scale-[0.99] disabled:opacity-50"
        onClick={handleSavePage}
        disabled={savingPage}
      >
        {savingPage ? <Spinner className="size-3.5 animate-spin" /> : <Save className="size-3.5" />}
        Save Current Page
      </Button>

      <Collapsible open={isOpen} onOpenChange={setIsOpen}>
        <CollapsibleTrigger asChild>
          <Button
            variant="ghost"
            size="sm"
            className="w-full justify-between text-muted-foreground hover:text-foreground hover:bg-accent/40 rounded-md h-7 px-1.5 cursor-pointer transition-all duration-200"
          >
            <span className="flex items-center gap-1.5 text-[11px] font-medium">
              <Link2 className="size-3" />
              Save a different URL
            </span>
            <ChevronDown className={`size-3 transition-transform duration-200 ${isOpen ? "rotate-180" : ""}`} />
          </Button>
        </CollapsibleTrigger>
        <CollapsibleContent className="pt-1.5 space-y-2">
          <div className="space-y-1">
            <Label htmlFor="override-url" className="text-[10px] font-medium text-muted-foreground">URL Path</Label>
            <Input
              id="override-url"
              type="url"
              placeholder="https://example.com/article"
              value={overrideUrl}
              onChange={(e) => setOverrideUrl(e.target.value)}
              className="h-8 rounded-md text-[11px] border-border/80 focus-visible:ring-1 focus-visible:ring-primary/30 focus-visible:border-primary transition-all duration-200"
            />
          </div>
          <Button
            variant="secondary"
            className="w-full h-8 rounded-md text-[11px] font-medium gap-1 cursor-pointer transition-all duration-200 hover:scale-[1.01] active:scale-[0.99] disabled:opacity-50"
            onClick={handleSaveUrl}
            disabled={savingUrl || !overrideUrl.trim()}
          >
            {savingUrl ? <Spinner className="size-3 animate-spin" /> : <Save className="size-3" />}
            Save URL
          </Button>
        </CollapsibleContent>
      </Collapsible>
    </div>
  );
}
