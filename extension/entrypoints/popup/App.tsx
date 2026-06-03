import { useState } from "react";
import { Button } from "@/components/ui/button";
import { RefreshCcw } from "lucide-react";

function App() {
  const [count, setCount] = useState(0);

  return (
    <div className="min-w-[320px] p-6 flex flex-col items-center gap-4 bg-background text-foreground">
      <h1 className="text-xl font-semibold tracking-tight">
        WXT + React + shadcn
      </h1>
      <Button onClick={() => setCount((c) => c + 1)}>count is {count}</Button>
      <Button variant="outline" onClick={() => setCount(0)}>
        <RefreshCcw className="mr-2 h-4 w-4" />
        Reset
      </Button>
      <p className="text-sm text-muted-foreground">
        Edit{" "}
        <code className="rounded bg-muted px-1">entrypoints/popup/App.tsx</code>{" "}
        to test HMR
      </p>
    </div>
  );
}

export default App;
