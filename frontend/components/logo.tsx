import { useId } from "react";

export function LogoMark({ size = 32, className }: { size?: number; className?: string }) {
  // Unique gradient id per instance: a shared id breaks when the first copy sits inside a display:none tree.
  const gradientId = `kirai-logo-${useId().replace(/:/g, "")}`;
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" fill="none" className={className} aria-hidden>
      <defs>
        <linearGradient id={gradientId} x1="2" y1="2" x2="38" y2="38" gradientUnits="userSpaceOnUse">
          <stop stopColor="#4338CA" />
          <stop offset="0.6" stopColor="#6D5AE6" />
          <stop offset="1" stopColor="#8B5CF6" />
        </linearGradient>
      </defs>
      <rect width="40" height="40" rx="11" fill={`url(#${gradientId})`} />
      {/* shopping bag */}
      <path
        d="M12.5 17h15l-1.2 11.4a2 2 0 0 1-2 1.8H15.7a2 2 0 0 1-2-1.8L12.5 17Z"
        stroke="white"
        strokeWidth="1.9"
        strokeLinejoin="round"
      />
      <path d="M16.6 17v-1.6a3.4 3.4 0 0 1 6.8 0V17" stroke="white" strokeWidth="1.9" strokeLinecap="round" />
      {/* AI spark */}
      <path d="M30 6.2l1.05 2.65 2.65 1.05-2.65 1.05L30 13.6l-1.05-2.65-2.65-1.05 2.65-1.05L30 6.2Z" fill="white" />
    </svg>
  );
}

export function Logo({ showTagline = true }: { showTagline?: boolean }) {
  return (
    <div className="flex items-center gap-3">
      <LogoMark size={36} />
      <div className="leading-tight">
        <div className="text-[17px] font-semibold tracking-tight text-foreground">KirAI</div>
        {showTagline && <div className="text-xs text-muted-foreground">AI-powered store operator</div>}
      </div>
    </div>
  );
}
