import { useState } from "react";
import { toast } from "sonner";
import { Brain, LogIn } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
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
    <Card className="border-none shadow-none">
      <CardHeader className="items-center text-center gap-2">
        <div className="flex size-12 items-center justify-center rounded-xl bg-primary/10 text-primary">
          <Brain className="size-6" />
        </div>
        <div className="space-y-1">
          <h1 className="text-lg font-semibold tracking-tight">Brain2</h1>
          <p className="text-sm text-muted-foreground">
            Save anything. Bring it as context to every AI agent.
          </p>
        </div>
      </CardHeader>
      <CardContent>
        <Button
          className="w-full"
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
      </CardContent>
    </Card>
  );
}
