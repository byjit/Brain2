import { useState } from "react";
import { toast } from "sonner";
import { Brain, LogIn } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { signInMsg } from "@/services/capture/messages";

interface SignInProps {
  /** Called after a successful sign-in so App re-reads the auth store. */
  onSignedIn: () => void;
}

/**
 * Signed-out view: a single intent — start the Google sign-in flow. The
 * background owns the OAuth dance; the popup only fires the request and
 * reacts to the boolean result.
 */
export function SignIn({ onSignedIn }: SignInProps) {
  const [loading, setLoading] = useState(false);

  async function handleSignIn() {
    setLoading(true);
    try {
      const { ok } = await signInMsg.send({}, { to: "background" });
      if (ok) {
        onSignedIn();
      } else {
        toast.error("Sign-in failed. Please try again.");
      }
    } catch {
      toast.error("Sign-in failed. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col items-center text-center py-4 px-2 space-y-6">
      <div className="space-y-3 flex flex-col items-center">
        <div className="flex size-14 items-center justify-center rounded-2xl bg-primary/10 text-primary shadow-xs">
          <Brain className="size-7 animate-pulse" />
        </div>
        <div className="space-y-1">
          <h1 className="text-xl font-bold tracking-tight">Welcome to Brain2</h1>
          <p className="text-xs text-muted-foreground max-w-[260px] mx-auto leading-relaxed">
            Save anything you read or write, and instantly bring it as context to all of your AI agents.
          </p>
        </div>
      </div>
      
      <Button
        className="w-full h-11 bg-primary text-primary-foreground hover:bg-primary/95 cursor-pointer rounded-xl font-semibold text-sm gap-2.5 shadow-sm transition-colors"
        onClick={handleSignIn}
        disabled={loading}
      >
        {loading ? (
          <Spinner className="size-4" />
        ) : (
          <LogIn className="size-4" />
        )}
        Sign in with Google
      </Button>
    </div>
  );
}
