import { Construction } from "lucide-react";

/** Stand-in page body until the phase that builds the real screen. */
export function Placeholder({
  title,
  phase,
  children,
}: {
  title: string;
  phase: string;
  children?: React.ReactNode;
}) {
  return (
    <section>
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      <div className="border-border bg-surface mt-6 flex items-start gap-3 rounded-[var(--radius-card)] border border-dashed p-6">
        <Construction className="text-muted-foreground mt-0.5 size-5 shrink-0" aria-hidden />
        <div>
          <p className="font-medium">This screen arrives in {phase}.</p>
          <div className="text-muted-foreground mt-1 text-sm">
            {children ?? "Your sign-in and role are working; you're on the right page for your role."}
          </div>
        </div>
      </div>
    </section>
  );
}
