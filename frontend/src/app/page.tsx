import { ApiStatus } from "@/components/api-status";

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center gap-4 p-8">
      <h1 className="text-2xl font-semibold">LifeSci Intelligence</h1>
      <p className="text-zinc-600 dark:text-zinc-400">
        Evidence-grounded Q&amp;A for pharmaceutical quality documentation. Document upload and
        chat arrive in Phase 1.
      </p>
      <ApiStatus />
    </main>
  );
}
