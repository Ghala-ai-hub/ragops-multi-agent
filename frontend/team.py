"""Team presentation using supplied content and symbolic SVG illustrations."""
from __future__ import annotations

from html import escape
from urllib.parse import urlsplit

from .animations import avatar_svg
from .config import TEAM, TEAM_LINKEDIN
from .icons import icon


TEAM_CSS = """
<style>
.team-showcase{isolation:isolate;min-width:0}
.team-showcase .team-grid{gap:1.15rem;padding-top:.35rem}
.team-showcase .team-card{--team-accent:#24d6ff;--team-rgb:36,214,255;position:relative;isolation:isolate;border-color:rgba(var(--team-rgb),.57);box-shadow:inset 0 1px rgba(218,248,255,.035),0 10px 30px rgba(0,0,0,.12);animation:team-card-reveal .6s ease-out backwards;animation-delay:calc(var(--team-order,0)*85ms);transition:transform .24s ease,border-color .24s ease,box-shadow .24s ease}
.team-showcase .team-card.theme-teal{--team-accent:#32e2cc;--team-rgb:50,226,204}
.team-showcase .team-card.theme-violet{--team-accent:#a18aff;--team-rgb:161,138,255}
.team-showcase .team-card.theme-amber{--team-accent:#efbf67;--team-rgb:239,191,103}
.team-showcase .team-card::before{content:"";position:absolute;z-index:-1;inset:0;pointer-events:none;background:radial-gradient(ellipse at 78% 14%,rgba(var(--team-rgb),.13),transparent 58%);opacity:.5;animation:team-ambient 7s ease-in-out infinite;animation-delay:calc(var(--team-order,0)*-1.6s)}
.team-showcase .team-card:is(:hover,:focus-within){transform:translateY(-5px);border-color:var(--team-accent);box-shadow:0 15px 34px rgba(0,0,0,.22),0 0 20px rgba(var(--team-rgb),.13),inset 0 1px rgba(var(--team-rgb),.13)}
.team-showcase .team-avatar-link{display:block;color:inherit;text-decoration:none;outline-offset:-4px}
.team-showcase .team-avatar-link:focus-visible{outline:2px solid var(--team-accent);border-radius:13px 13px 0 0}
.team-showcase .team-avatar-link::after{content:"↗";position:absolute;top:.9rem;right:.9rem;display:grid;place-items:center;width:1.7rem;height:1.7rem;border:1px solid rgba(var(--team-rgb),.4);border-radius:50%;background:rgba(3,20,32,.68);color:var(--team-accent);font-size:.8rem;opacity:.8;transition:transform .22s ease,background .22s ease}
.team-showcase .team-avatar-link:is(:hover,:focus-visible)::after{transform:translate(1px,-1px);background:rgba(var(--team-rgb),.15)}
.team-showcase .team-avatar-link .team-stage{top:auto;bottom:1rem;left:1.1rem;max-width:12rem;font-size:.59rem;letter-spacing:.12em;text-shadow:0 2px 10px #03121f}
.team-showcase .team-copy{position:relative;z-index:1;padding-top:.65rem}
.team-showcase .team-grid{grid-template-columns:repeat(4,minmax(0,1fr));gap:1.15rem}
.team-showcase .team-copy{padding-inline:1rem;padding-bottom:1.1rem}
.team-showcase .avatar-wrap{min-height:0;max-height:280px;aspect-ratio:4/3}
.team-showcase .team-description{font-size:.9rem!important}
.team-showcase .team-description{min-height:4.8em;margin:.65rem 0 1rem!important}
.team-showcase .team-link{gap:.5rem;border-color:rgba(var(--team-rgb),.55);background:linear-gradient(110deg,rgba(var(--team-rgb),.075),rgba(3,24,39,.85));transition:background .22s ease,border-color .22s ease,box-shadow .22s ease}
.team-showcase .team-link svg{color:var(--team-accent)}
.team-showcase .team-link:is(:hover,:focus-visible){border-color:var(--team-accent);background:rgba(var(--team-rgb),.12);box-shadow:0 0 15px rgba(var(--team-rgb),.10)}
.team-showcase .team-link:focus-visible{outline:2px solid var(--team-accent);outline-offset:3px}
.team-showcase .team-link-arrow{display:inline-block;margin-left:.15rem;color:var(--team-accent);transition:transform .2s ease}
.team-showcase .team-link:is(:hover,:focus-visible) .team-link-arrow{transform:translate(2px,-2px)}
.team-showcase .avatar-rings{transform-origin:262px 119px;animation:team-ring-orbit 42s linear infinite}
.team-showcase .avatar-tech-lines{stroke-dasharray:120 9;animation:team-tech-flow 28s linear infinite}
.team-showcase .avatar-particles{animation:team-particle-breathe 5.5s ease-in-out infinite;animation-delay:calc(var(--team-order,0)*-.8s)}
.team-showcase .avatar-caption{color:#94b3c4!important;font-size:.72rem!important;line-height:1.5;margin:.8rem .1rem .45rem!important}
.st-key-team_stack .stack-items>div{transition:transform .22s ease,border-color .22s ease,box-shadow .22s ease}
.st-key-team_stack .stack-items>div:hover{transform:translateY(-3px);border-color:rgba(36,214,255,.55);box-shadow:0 5px 16px rgba(0,0,0,.12),0 0 14px rgba(36,214,255,.09)}
@keyframes team-card-reveal{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}
@keyframes team-ambient{0%,100%{opacity:.4}50%{opacity:.75}}
@keyframes team-ring-orbit{to{transform:rotate(360deg)}}
@keyframes team-tech-flow{to{stroke-dashoffset:-129}}
@keyframes team-particle-breathe{0%,100%{opacity:.45}50%{opacity:.75}}
@media(max-width:1150px){.team-showcase .team-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:1.15rem}.team-showcase .team-description{min-height:3.3em}}
@media(max-width:800px){.team-showcase .team-grid{gap:1.1rem}.team-showcase .team-description{min-height:0}.team-showcase .team-avatar-link .team-stage{font-size:.63rem}}
@media(max-width:640px){.team-showcase .team-grid{grid-template-columns:minmax(0,1fr)}}
@media(prefers-reduced-motion:reduce){
  .team-showcase,.team-showcase *, .team-showcase *::before,.team-showcase *::after,
  .st-key-team_stack .stack-items>div,.st-key-team_stack .stack-items>div *{animation:none!important;transition:none!important}
  .team-showcase .team-card,.team-showcase .team-card:is(:hover,:focus-within),
  .team-showcase .team-avatar-link::after,.team-showcase .team-avatar-link:is(:hover,:focus-visible)::after,
  .team-showcase .team-link-arrow,.team-showcase .team-link:is(:hover,:focus-visible) .team-link-arrow,
  .team-showcase .avatar-rings,.st-key-team_stack .stack-items>div,.st-key-team_stack .stack-items>div:hover{transform:none!important}
}
</style>
"""


def team_html() -> str:
    """Four supplied team identities with explicit, accessible profile links."""
    cards = []
    for index, member in enumerate(TEAM):
        name = str(member["name"])
        url = str(TEAM_LINKEDIN.get(name) or "").strip()
        parsed = urlsplit(url)
        valid = parsed.scheme in {"http", "https"} and bool(parsed.netloc)
        accent = member.get("accent") if member.get("accent") in {"cyan", "teal", "violet", "amber"} else "cyan"
        illustration = avatar_svg(member["avatar"])
        stage = f'<span class="team-stage">{escape(str(member["verb"]))}</span>'
        if valid:
            attributes = f'href="{escape(url, quote=True)}" target="_blank" rel="noopener noreferrer" aria-label="Open {escape(name, quote=True)}’s LinkedIn profile in a new tab"'
            avatar = f'<a class="avatar-wrap team-avatar-link" {attributes}>{illustration}{stage}</a>'
            link = f'<a class="team-link" {attributes}>{icon("link",18)}<span>LinkedIn</span> <span class="team-link-arrow" aria-hidden="true">↗</span></a>'
        else:
            avatar = f'<div class="avatar-wrap">{illustration}{stage}</div>'
            link = '<span class="team-link unavailable">Profile link unavailable</span>'
        cards.append(
            f'<article class="team-card theme-{accent}" style="--team-order:{index}">{avatar}'
            f'<div class="team-copy"><h3 class="team-name">{escape(name)}</h3>'
            f'<div class="team-role">{escape(str(member["role"]))}</div>'
            f'<p class="team-description">{escape(str(member.get("description") or ""))}</p>{link}</div></article>'
        )
    return '<div class="team-showcase"><div class="team-grid">' + ''.join(cards) + '</div><p class="avatar-caption">Concept illustrations are symbolic and do not depict actual team members.</p></div>'
