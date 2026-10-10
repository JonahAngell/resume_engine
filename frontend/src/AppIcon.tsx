import type { ReactNode, SVGProps } from "react";
export type AppIconName =
  | "profile"
  | "home"
  | "library"
  | "bin"
  | "document"
  | "all-items"
  | "experience"
  | "projects"
  | "education"
  | "leadership"
  | "skills"
  | "interests"
  | "custom-sections"
  | "search"
  | "list-view"
  | "card-view"
  | "tip"
  | "details";
const paths: Record<AppIconName, ReactNode> = {
  profile: (
    <>
      <circle cx="12" cy="8" r="4" />
      <path d="M4 21a8 8 0 0 1 16 0" />
    </>
  ),
  home: (
    <>
      <path d="M3 11.5 12 4l9 7.5" />
      <path d="M5.5 10.5V20h13v-9.5" />
      <path d="M9.5 20v-6h5v6" />
    </>
  ),
  library: (
    <>
      <path d="M4 4h5v16H4zM10.5 4h4v16h-4z" />
      <path d="m16 5 3-1 3.5 14-3 1z" />
    </>
  ),
  bin: <path d="M4 7h16M9 3h6l1 4M6.5 7l1 14h9l1-14M10 11v6M14 11v6" />,
  document: (
    <>
      <path d="M6 2h8l4 4v16H6z" />
      <path d="M14 2v5h5M9 12h6M9 16h6" />
    </>
  ),
  "all-items": (
    <>
      <rect x="4" y="4" width="6" height="6" rx="1" />
      <rect x="14" y="4" width="6" height="6" rx="1" />
      <rect x="4" y="14" width="6" height="6" rx="1" />
      <rect x="14" y="14" width="6" height="6" rx="1" />
    </>
  ),
  experience: (
    <>
      <path d="M4 8h16v11H4z" />
      <path d="M9 8V5h6v3M4 12h16M10 12v2h4v-2" />
    </>
  ),
  projects: (
    <>
      <path d="M3 7h7l2 2h9v10H3z" />
      <path d="M3 7V5h7l2 2" />
    </>
  ),
  education: (
    <>
      <path d="m3 9 9-5 9 5-9 5z" />
      <path d="M7 12v4.5c3 2 7 2 10 0V12M21 9v6" />
    </>
  ),
  leadership: (
    <>
      <circle cx="9" cy="8" r="3" />
      <circle cx="17" cy="9" r="2.5" />
      <path d="M3.5 20v-2c0-3 2.5-5 5.5-5s5.5 2 5.5 5v2M14 14c3.5 0 6 1.8 6 5v1" />
    </>
  ),
  skills: (
    <path d="M14.5 6.5a4 4 0 0 0-5 5L4 17l3 3 5.5-5.5a4 4 0 0 0 5-5l-2.5 2.5-3-3z" />
  ),
  interests: (
    <path d="M12 20S4 15.5 4 9.5A4.5 4.5 0 0 1 12 6.7a4.5 4.5 0 0 1 8 2.8C20 15.5 12 20 12 20z" />
  ),
  "custom-sections": (
    <>
      <path d="M4 4h6v6H4zM14 14h6v6h-6z" />
      <path d="M17 4v6M14 7h6M7 14v6M4 17h6" />
    </>
  ),
  search: <path d="m21 21-4.4-4.4M19 11a8 8 0 1 1-16 0 8 8 0 0 1 16 0z" />,
  "list-view": (
    <>
      <path d="M9 6h11M9 12h11M9 18h11" />
      <path d="M4 6h1M4 12h1M4 18h1" />
    </>
  ),
  "card-view": (
    <>
      <rect x="4" y="4" width="6" height="6" rx="1" />
      <rect x="14" y="4" width="6" height="6" rx="1" />
      <rect x="4" y="14" width="6" height="6" rx="1" />
      <rect x="14" y="14" width="6" height="6" rx="1" />
    </>
  ),
  tip: (
    <>
      <path d="M9 18h6M10 22h4" />
      <path d="M8.3 14.5A7 7 0 1 1 15.7 14.5c-.9.7-1.4 1.6-1.5 2.5h-4.4c-.1-.9-.6-1.8-1.5-2.5z" />
    </>
  ),
  details: (
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1A1.7 1.7 0 0 0 9 4.6 1.7 1.7 0 0 0 10 3v-.2h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1z" />
    </>
  ),
};

export function AppIcon({
  name,
  ...props
}: { name: AppIconName } & SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="1em"
      height="1em"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...props}
    >
      {paths[name]}
    </svg>
  );
}
