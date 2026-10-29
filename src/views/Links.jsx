import { Link2 } from "lucide-react";

export default function Links() {
  return (
    <section className="mx-auto flex h-full max-w-3xl flex-col items-center justify-center text-center">
      <Link2 className="mb-4 size-10 text-muted-foreground" />
      <h2 className="text-2xl font-bold">Links</h2>
      <p className="mt-2 max-w-md text-sm text-muted-foreground">
        Proposed and reviewed links between findings and theory claims will be managed
        here.
      </p>
    </section>
  );
}
