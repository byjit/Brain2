import { useState } from "react";
import { toast } from "sonner";
import { ChevronsUpDown, Link2, Save } from "lucide-react";
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
      setSavingPage(false);
    }
  }

  async function handleSaveUrl() {
    const url = overrideUrl.trim();
    if (!url) return;
    setSavingUrl(true);
    try {
      await save(url);
    } finally {
      setSavingUrl(false);
    }
  }

  return (
    <div className="space-y-3">
      <Button
        size="lg"
        className="w-full"
        onClick={handleSavePage}
        disabled={savingPage}
      >
        {savingPage ? <Spinner className="size-4" /> : <Save className="size-4" />}
        Save this page
      </Button>

      <Collapsible>
        <CollapsibleTrigger asChild>
          <Button
            variant="ghost"
            size="sm"
            className="w-full justify-between text-muted-foreground"
          >
            <span className="flex items-center gap-2">
              <Link2 className="size-4" />
              Save a different URL
            </span>
            <ChevronsUpDown className="size-4" />
          </Button>
        </CollapsibleTrigger>
        <CollapsibleContent className="pt-2 space-y-2">
          <div className="space-y-1.5">
            <Label htmlFor="override-url">URL</Label>
            <Input
              id="override-url"
              type="url"
              placeholder="https://example.com/article"
              value={overrideUrl}
              onChange={(e) => setOverrideUrl(e.target.value)}
            />
          </div>
          <Button
            variant="secondary"
            className="w-full"
            onClick={handleSaveUrl}
            disabled={savingUrl || !overrideUrl.trim()}
          >
            {savingUrl ? <Spinner className="size-4" /> : <Save className="size-4" />}
            Save URL
          </Button>
        </CollapsibleContent>
      </Collapsible>
    </div>
  );
}
