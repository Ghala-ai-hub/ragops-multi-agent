"""Keep local navigation inside the current Streamlit session.

The visible links retain their normal URL and keyboard semantics. Ordinary
in-app clicks use native widget callbacks so the live graph/checkpointer and
the accepted answer remain in session_state. New tabs and full page reloads
intentionally start a separate Streamlit session.
"""
from __future__ import annotations

import streamlit as st

from frontend.config import NAV_ITEMS


def retain_action_widgets() -> None:
    # Streamlit cleans up widgets that are absent on the next page. Detach
    # these draft values from that cleanup while preserving their widget keys.
    for key in ("query_text", "case_picker", "mode_choice"):
        if key in st.session_state:
            st.session_state[key] = st.session_state[key]


def navigate(page: str, case_id: str | None = None) -> None:
    st.query_params["page"] = page
    if page == "action":
        explicit_case = case_id is not None
        case_id = case_id if explicit_case else st.session_state.get("selected_case_id") or ""
        mode = "saved" if explicit_case else "live" if st.session_state.get("runtime_mode") == "LIVE MODE" else "saved"
        if case_id:
            st.query_params["case"], st.query_params["mode"] = case_id, mode
        else:
            st.query_params.pop("case", None)
            st.query_params.pop("mode", None)
        if not explicit_case:
            st.session_state.loaded_link_case = (case_id, mode if case_id else "")
    else:
        st.query_params.pop("case", None)
        st.query_params.pop("mode", None)


NAVIGATION_SCRIPT = r"""
<style>
.st-key-session_navigation {display:none!important}
[data-testid="stLayoutWrapper"]:has(>.st-key-session_navigation) {display:none!important}
</style>
<script>
(() => {
  if (window.__ragopsSessionNavigation) return;
  const navigate = event => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const link = event.target.closest('a[href]');
    if (!link || link.target === '_blank' || link.hasAttribute('download')) return;
    const url = new URL(link.href, window.location.href);
    if (url.origin !== location.origin || url.pathname !== location.pathname || url.hash) return;
    const page = url.searchParams.get('page');
    if (!['overview','action','dashboard','architecture','team'].includes(page)) return;
    const caseId = page === 'action' ? url.searchParams.get('case') : null;
    const key = caseId ? 'session_nav_case_' + caseId : 'session_nav_' + page;
    const button = document.querySelector('.st-key-' + CSS.escape(key) + ' button');
    if (!button || button.disabled) return;
    event.preventDefault();
    button.click();
    const main = document.querySelector('[data-testid="stMain"]');
    if (main) main.scrollTo({top:0, behavior:'instant'});
  };
  document.addEventListener('click', navigate);
  window.__ragopsSessionNavigation = navigate;
})();
</script>
"""


def navigation_bridge(cases: list[dict]) -> None:
    """Native callbacks for existing navbar, hero, and verified-case links."""
    retain_action_widgets()
    with st.container(key="session_navigation"):
        st.html(NAVIGATION_SCRIPT, unsafe_allow_javascript=True)
        for page, label in NAV_ITEMS:
            st.button(label, key=f"session_nav_{page}", on_click=navigate, args=(page,))
        for case in cases:
            st.button(f"Inspect {case['id']}", key=f"session_nav_case_{case['id']}",
                      on_click=navigate, args=("action", case["id"]))
