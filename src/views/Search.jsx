import { Search as SearchIcon } from "lucide-react";

export default function Search() {
  return (
    <section className="mx-auto flex h-full max-w-3xl flex-col items-center justify-center text-center">
      <SearchIcon className="mb-4 size-10 text-muted-foreground" />
      <h2 className="text-2xl font-bold">Search</h2>
      <p className="mt-2 max-w-md text-sm text-muted-foreground">
        Hybrid search across theories, findings, and notes will be available here.
      </p>
    </section>
  );
}
