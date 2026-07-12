// bayleaf brand mark — a single bay leaf: a veined blade (lanceolate outline + central
// midrib + three pairs of lateral veins), tilted for life. Pure inline SVG so it scales
// crisply and can be tinted. Defaults to a white blade with deep-green venation, sized to
// sit inside the app's green brand tile (sidebar + login); override `leaf`/`vein` for other
// surfaces. This is the single source of truth for the logo mark rendered in the UI.
export function Logo({
  size = 20,
  leaf = '#ffffff',
  vein = '#2e7850',
  className,
}: {
  size?: number
  leaf?: string
  vein?: string
  className?: string
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      className={className}
      aria-hidden="true"
    >
      <g transform="rotate(-14 16 16)">
        <path d="M16 5.5C10 10 10 20 16 26C22 20 22 10 16 5.5Z" fill={leaf} />
        <path d="M16 8V23.5" stroke={vein} strokeWidth="1.3" strokeLinecap="round" />
        <path
          d="M16 12.5L12.4 10.9M16 12.5L19.6 10.9M16 16L11.9 14.6M16 16L20.1 14.6M16 19.5L12.7 18.3M16 19.5L19.3 18.3"
          stroke={vein}
          strokeWidth="1.05"
          strokeLinecap="round"
        />
      </g>
    </svg>
  )
}
