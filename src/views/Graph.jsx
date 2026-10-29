import { Network } from "lucide-react";

export default function Graph() {
  return (
    <section className="mx-auto flex h-full max-w-3xl flex-col items-center justify-center text-center">
      <Network className="mb-4 size-10 text-muted-foreground" />
      <h2 className="text-2xl font-bold">Graph</h2>
      <p className="mt-2 max-w-md text-sm text-muted-foreground">
        The knowledge graph explorer will show theory claims, findings, and constructs
        here.
      </p>
    </section>
  );
}
