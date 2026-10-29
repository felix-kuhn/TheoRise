import { LibraryBig } from "lucide-react";

export default function Library() {
  return (
    <section className="mx-auto flex h-full max-w-3xl flex-col items-center justify-center text-center">
      <LibraryBig className="mb-4 size-10 text-muted-foreground" />
      <h2 className="text-2xl font-bold">Library</h2>
      <p className="mt-2 max-w-md text-sm text-muted-foreground">
        Local research documents and theory sources will be organized here.
      </p>
    </section>
  );
}
