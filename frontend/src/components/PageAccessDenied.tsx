import { Lock } from 'lucide-react'
import { Link } from 'react-router-dom'
import { type PageId, pageLabel } from '../access'

// Friendly route-guard fallback shown when a user deep-links a page that isn't in their access
// profile. Modeled on Admin's admin-required card. It is explicitly labelled a VIEW-GATE, not a
// security control — reads remain open in the dev shim (the API has no per-page authz), so this
// hides the page's nav/entry but does not stop a determined fetch. The production seam is
// server-side page/read authz.
export function PageAccessDenied({ page }: { page: PageId }) {
  return (
    <div className="mx-auto max-w-md rounded-xl border border-line bg-card p-8 text-center shadow-card">
      <Lock size={26} className="mx-auto text-text-3" />
      <div className="mt-2 text-[15px] font-semibold text-text">
        {pageLabel(page)} isn&apos;t in your access profile
      </div>
      <p className="mt-1 text-[12.5px] leading-relaxed text-text-2">
        Ask an admin to grant it under Admin → Page access. Your Runs and Decision cards stay
        available.
      </p>
      <p className="mt-3 text-[11px] leading-relaxed text-text-3">
        This is a client-side view-gate, not a security control — it hides the page from your nav.
        The API still authorizes every write by your role (a labelled seam).
      </p>
      <Link
        to="/"
        className="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-accent px-3.5 py-1.5 text-[12.5px] font-semibold text-white hover:bg-accent-strong"
      >
        Go to Runs
      </Link>
    </div>
  )
}
