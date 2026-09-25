"""Small, consistent SVG symbols with no remote assets or icon fonts."""

from html import escape


_PATHS = {
    "home": '<path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1Z"/>',
    "play": '<path d="m7 3 14 9L7 21Z"/>',
    "chart": '<path d="M4 20V13h3v7M10.5 20V8h3v12M17 20V3h3v17"/>',
    "network": '<circle cx="12" cy="4" r="2.5"/><circle cx="4" cy="19" r="2.5"/><circle cx="20" cy="19" r="2.5"/><path d="m10.8 6.2-5.6 10.6m8-10.6 5.6 10.6M6.5 19h11"/>',
    "users": '<circle cx="9" cy="7" r="3"/><path d="M3 21v-3a6 6 0 0 1 12 0v3M16 4a3 3 0 0 1 0 6m3 11v-3a6 6 0 0 0-2-4.5"/>',
    "database": '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
    "eye": '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>',
    "search": '<circle cx="10.5" cy="10.5" r="7"/><path d="m16 16 5 5"/>',
    "settings": '<path d="m10 2-.7 3a8 8 0 0 0-1.7 1l-3-.8-2 3.5 2.3 2.2a9 9 0 0 0 0 2.2l-2.3 2.2 2 3.5 3-.8a8 8 0 0 0 1.7 1L10 22h4l.7-3a8 8 0 0 0 1.7-1l3 .8 2-3.5-2.3-2.2a9 9 0 0 0 0-2.2l2.3-2.2-2-3.5-3 .8a8 8 0 0 0-1.7-1L14 2Z"/><circle cx="12" cy="12" r="3"/>',
    "check": '<path d="m5 12 4 4L19 6"/>',
    "check-circle": '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
    "shield": '<path d="m12 2 8 4v6c0 5-8 10-8 10S4 17 4 12V6Z"/><path d="m8 12 3 3 5-6"/>',
    "user": '<circle cx="12" cy="7" r="4"/><path d="M4 22v-3a8 8 0 0 1 16 0v3"/>',
    "arrow": '<path d="M3 12h17m-6-6 6 6-6 6"/>',
    "file": '<path d="M14 2H5v20h14V7Zm0 0v5h5M8 12h8m-8 4h8"/>',
    "layers": '<path d="m12 2 10 5-10 5L2 7Zm-10 10 10 5 10-5M2 17l10 5 10-5"/>',
    "code": '<path d="m8 6-6 6 6 6m8-12 6 6-6 6M14 3l-4 18"/>',
    "link": '<path d="m10 13 4-4m-7 5-2 2a4 4 0 0 0 6 6l4-4a4 4 0 0 0-1-6M17 10l2-2a4 4 0 0 0-6-6L9 6a4 4 0 0 0 1 6" transform="translate(0 -1)"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v6l4 2"/>',
    "close": '<path d="m6 6 12 12M6 18 18 6"/>',
    "warning": '<path d="m12 3 10 18H2Zm0 5v6m0 3v.1"/>',
    "target": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
    "activity": '<path d="M2 12h4l3-8 6 16 3-8h4"/>',
    "sparkles": '<path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5ZM20 2v4m-2-2h4"/>',
    "filter": '<path d="M3 4h18l-7 8v8l-4-2v-6Z"/>',
    "chevron": '<path d="m9 5 7 7-7 7"/>',
    "bolt": '<path d="m13 2-9 12h7l-1 8 10-13h-8Z"/>',
    "refresh": '<path d="M20 7a9 9 0 0 0-15-2L2 8m0-5v5h5m-3 9a9 9 0 0 0 15 2l3-3m0 5v-5h-5"/>',
    "server": '<rect x="3" y="3" width="18" height="7" rx="2"/><rect x="3" y="14" width="18" height="7" rx="2"/><path d="M7 6.5h.01M7 17.5h.01M16 6.5h2m-2 11h2"/>',
    "cube": '<path d="m12 2 9 5v10l-9 5-9-5V7Zm-9 5 9 5 9-5M12 12v10M7.5 4.5l9 5v5"/>',
    "pause": '<path d="M8 4v16M16 4v16" stroke-width="4"/>',
    "linkedin": '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M7 10v7m0-10v.1M11 17v-7m0 3a3 3 0 0 1 6 0v4"/>',
}


def icon(name: str, size: int = 20) -> str:
    """Return an aria-hidden inline icon; surrounding text supplies its label."""
    size = max(8, min(128, int(size)))
    path = _PATHS.get(name, _PATHS["activity"])
    return (
        f'<svg class="ui-icon icon-{escape(name, quote=True)}" width="{size}" height="{size}" '
        'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" '
        'stroke-linecap="round" stroke-linejoin="round" xmlns="http://www.w3.org/2000/svg" '
        f'aria-hidden="true" focusable="false">{path}</svg>'
    )


def logo_svg(size: int = 44) -> str:
    """Return the cyan triangular RAGOps brand mark."""
    size = max(16, min(128, int(size)))
    return f'''<svg class="brand-mark" width="{size}" height="{size}" viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg" fill="none" aria-hidden="true">
      <path d="M20.5 6.3a4 4 0 0 1 7 0L43 34.5a4.5 4.5 0 0 1-4 6.7H9a4.5 4.5 0 0 1-4-6.7Z" stroke="#00cdef" stroke-width="3" stroke-linejoin="round"/>
      <path d="m24 13.5 11 20H18m11 1H13l8-14" stroke="#23b6ff" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
      <path d="M11 43h15M29 43h5" stroke="#208cdc" stroke-opacity=".5" stroke-width="1.5" stroke-linecap="round"/>
    </svg>'''
