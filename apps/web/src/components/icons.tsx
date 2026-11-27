// Icônes en SVG intégré (aucune ressource externe, CSP stricte).
type P = { title?: string };
const svg = (d: string) =>
  function Icon({ title }: P) {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden={title ? undefined : true} role={title ? "img" : undefined}>
        {title && <title>{title}</title>}
        <path d={d} />
      </svg>
    );
  };

export const IconChat = svg("M4 5h16v11H9l-5 4z");
export const IconDashboard = svg("M4 13h6V4H4zM14 20h6v-9h-6zM4 20h6v-3H4zM14 7h6V4h-6z");
export const IconSources = svg("M4 7c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3zm0 0v10c0 1.7 3.6 3 8 3s8-1.3 8-3V7M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3");
export const IconDocuments = svg("M7 3h7l5 5v13H7zM14 3v5h5M10 13h6M10 17h6");
export const IconAdmin = svg("M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19 12l2-1-2-4-2 .5-1.5-1L15 4h-4l-.5 2.5-1.5 1L7 7 5 11l2 1v0l-2 1 2 4 2-.5 1.5 1L11 20h4l.5-2.5 1.5-1 2 .5 2-4z");
export const IconLogout = svg("M15 4h4v16h-4M10 8l-4 4 4 4M6 12h10");
export const IconTheme = svg("M12 3a9 9 0 1 0 9 9 7 7 0 0 1-9-9z");
export const IconSend = svg("M4 12l16-8-6 16-2-7z");
export const IconStop = svg("M7 7h10v10H7z");
export const IconCopy = svg("M9 9h11v11H9zM5 15H4V4h11v1");
export const IconOpen = svg("M14 4h6v6M20 4l-9 9M18 14v6H4V6h6");
export const IconPlus = svg("M12 5v14M5 12h14");
export const IconEdit = svg("M4 20h4L19 9l-4-4L4 16zM14 6l4 4");
export const IconTrash = svg("M5 7h14M10 7V4h4v3M7 7l1 13h8l1-13M10 11v6M14 11v6");
export const IconDownload = svg("M12 4v11M7 10l5 5 5-5M5 20h14");
export const IconSearch = svg("M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM20 20l-4-4");
