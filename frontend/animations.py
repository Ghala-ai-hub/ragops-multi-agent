"""Code-native conceptual diagram and synthetic team illustrations.

The overview diagram explains the system; it never implies live execution.
Team illustrations are abstract robots, not likenesses of real contributors.
"""

from frontend.icons import icon


def _diagram_icon(name: str, x: float, y: float, color: str, size: int = 28) -> str:
    return (
        f'<g transform="translate({x - size / 2} {y - size / 2})" color="{color}">'
        f'{icon(name, size)}</g>'
    )


def _agent_node(x: int, y: int, width: int, number: str, title: str,
                subtitle: tuple[str, str], symbol: str, color: str) -> str:
    center = x + width / 2
    agent_delay = (int(number) - 1) * 2
    path = (
        f'M{x + 24} {y + 34} H{center - 48} '
        f'C{center - 37} {y - 11} {center + 37} {y - 11} {center + 48} {y + 34} '
        f'H{x + width - 24} Q{x + width} {y + 34} {x + width} {y + 58} '
        f'V{y + 111} Q{x + width} {y + 135} {x + width - 24} {y + 135} '
        f'H{x + 24} Q{x} {y + 135} {x} {y + 111} V{y + 58} '
        f'Q{x} {y + 34} {x + 24} {y + 34} Z'
    )
    return f'''
      <g class="orbit-agent orbit-agent-{title.lower()}" style="--agent-delay:{agent_delay}s">
        <path class="orbit-agent-glow" d="{path}" fill="#041623" stroke="{color}" stroke-opacity=".22" stroke-width="9" filter="url(#orbit-soft-glow)"/>
        <path class="orbit-agent-stroke" d="{path}" fill="url(#orbit-node-fill)" stroke="{color}" stroke-width="1.4"/>
        {_diagram_icon(symbol, center, y + 36, color, 29)}
        <text x="{center}" y="{y + 76}" fill="{color}" font-size="11.3" font-weight="700" letter-spacing=".35">{number} · {title.upper()}</text>
        <text x="{center}" y="{y + 97}" fill="#b5d1e0" font-size="11.4">{subtitle[0]}</text>
        <text x="{center}" y="{y + 113}" fill="#b5d1e0" font-size="11.4">{subtitle[1]}</text>
      </g>'''


def control_loop_html(high_impact: bool = False) -> str:
    """Illustrate agent order; highlight the gate only for structural relevance.

    CSS animates the conceptual sequence, not a live run. ``high_impact`` only
    highlights where structural proposals are reviewed; it does not claim an
    approval decision or a pending backend interrupt.
    """
    nodes = "".join((
        _agent_node(267, 20, 166, "01", "Monitoring", ("Observe retrieval", "evidence"), "eye", "#2ddaff"),
        _agent_node(483, 203, 166, "02", "Diagnosis", ("Identify the", "root cause"), "search", "#61e8f2"),
        _agent_node(261, 385, 178, "03", "Optimization", ("Propose targeted", "improvements"), "settings", "#ab94ff"),
        _agent_node(51, 203, 166, "04", "Validation", ("Compare before", "and after"), "check-circle", "#48e6bf"),
    ))
    gate_class = "orbit-gate is-relevant" if high_impact else "orbit-gate"
    gate_glow = (
        '<path class="orbit-gate-glow" d="M197 554H503Q519 554 519 570V595'
        'Q519 611 503 611H197Q181 611 181 595V570Q181 554 197 554Z" '
        'fill="none" stroke="#f4bd59" stroke-opacity=".35" stroke-width="7" '
        'filter="url(#orbit-soft-glow)"/>'
        if high_impact else ""
    )
    return f'''
    <div class="control-wrap conceptual-flow">
      <svg class="control-loop-svg" style="display:block;width:100%;height:auto;overflow:visible" viewBox="0 0 700 624" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="orbit-title orbit-description">
        <title id="orbit-title">Four functional agents around Baseline RAG</title>
        <desc id="orbit-description">Conceptual workflow: Monitoring, Diagnosis, Optimization, and Validation. A human approval control gate applies only to structural changes. Low-impact actions are auto-approved by policy. This diagram does not indicate current execution.</desc>
        <defs>
          <radialGradient id="orbit-field"><stop offset="0" stop-color="#0074a9" stop-opacity=".2"/><stop offset=".66" stop-color="#004066" stop-opacity=".12"/><stop offset="1" stop-color="#00243c" stop-opacity="0"/></radialGradient>
          <radialGradient id="orbit-core" cx="44%" cy="30%" r="76%"><stop offset="0" stop-color="#0b405c"/><stop offset=".58" stop-color="#06263e"/><stop offset=".85" stop-color="#003e61"/><stop offset="1" stop-color="#08bce1"/></radialGradient>
          <linearGradient id="orbit-node-fill" x1="0" y1="0" x2=".6" y2="1"><stop offset="0" stop-color="#0a2439"/><stop offset="1" stop-color="#061221"/></linearGradient>
          <linearGradient id="orbit-gate-fill"><stop stop-color="#352711"/><stop offset=".5" stop-color="#1e1c18"/><stop offset="1" stop-color="#282010"/></linearGradient>
          <filter id="orbit-soft-glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="5"/></filter>
          <filter id="orbit-core-glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="10"/></filter>
          <marker id="orbit-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M1 1 9 5 1 9" fill="none" stroke="#4fddee" stroke-width="1.7"/></marker>
        </defs>
        <g font-family="Inter,Segoe UI,Arial,sans-serif" text-anchor="middle">
          <circle cx="350" cy="273" r="280" fill="url(#orbit-field)"/>
          <g fill="none" stroke="#126181">
            <circle cx="350" cy="273" r="236" stroke-opacity=".24"/>
            <circle cx="350" cy="273" r="222" stroke-opacity=".48"/>
            <circle cx="350" cy="273" r="204" stroke-opacity=".34"/>
            <circle cx="350" cy="273" r="173" stroke-opacity=".25"/>
            <circle cx="350" cy="273" r="144" stroke-opacity=".26"/>
            <circle cx="350" cy="273" r="120" stroke-opacity=".3"/>
            <path d="M183 106 517 440M183 440 517 106M114 273H586M350 37V509" stroke-opacity=".2"/>
          </g>
          <g class="orbit-directional-connectors" fill="none" stroke="#4fddee" stroke-width="1.8" stroke-dasharray="4 6" stroke-linecap="round" marker-end="url(#orbit-arrow)">
            <path class="orbit-flow orbit-flow-monitoring-diagnosis" style="--flow-delay:1.2s" d="M455 112 A195 195 0 0 1 518 180"/>
            <path class="orbit-flow orbit-flow-diagnosis-optimization" style="--flow-delay:3.2s" d="M515 361 A195 195 0 0 1 460 427"/>
            <path class="orbit-flow orbit-flow-optimization-validation" style="--flow-delay:5.2s" d="M245 435 A195 195 0 0 1 184 365"/>
            <path class="orbit-flow orbit-flow-validation-monitoring" style="--flow-delay:7.2s" d="M184 181 A195 195 0 0 1 240 117"/>
          </g>
          <g fill="none" stroke="#3ce7ef" stroke-width="1.4" stroke-dasharray="2 6">
            <path d="M350 155V176M350 369V385M217 273H253M447 273H483"/>
          </g>
          <g fill="#4fe6f4"><circle cx="350" cy="164" r="2.6"/><circle cx="239" cy="273" r="2.6"/><circle cx="463" cy="273" r="2.6"/><circle cx="350" cy="377" r="2.6"/></g>
          <circle cx="350" cy="273" r="94" fill="none" stroke="#00bdf1" stroke-opacity=".45" stroke-width="12" filter="url(#orbit-core-glow)"/>
          <circle cx="350" cy="273" r="94" fill="url(#orbit-core)" stroke="#2bdaff" stroke-width="1.8"/>
          <circle cx="350" cy="273" r="80" fill="none" stroke="#1985b8" stroke-opacity=".35"/>
          {_diagram_icon("database", 350, 241, "#24d8f4", 34)}
          <text x="350" y="284" fill="#f2fbff" font-size="30" font-weight="800" letter-spacing="1.2">RAG</text>
          <text x="350" y="307" fill="#58dfff" font-size="11.3" font-weight="600" letter-spacing="1.5">BASELINE SYSTEM</text>
          {nodes}
          <g class="{gate_class}">
            <path class="orbit-gate-connector" d="M350 521V545" stroke="#f4bd59" stroke-width="1.5" stroke-dasharray="3 4"/>
            <circle class="orbit-gate-junction" cx="350" cy="546" r="3" fill="#f4bd59"/>
            {gate_glow}
            <rect class="orbit-gate-surface" x="181" y="554" width="338" height="57" rx="16" fill="url(#orbit-gate-fill)" stroke="#b48535" stroke-width="1.2"/>
            {_diagram_icon("shield", 209, 582, "#f4c266", 25)}
            <text x="365" y="578" fill="#f4c266" font-size="10.8" font-weight="700" letter-spacing=".45">RISK / HUMAN APPROVAL GATE</text>
            <text x="365" y="596" fill="#d4c3a6" font-size="11.3">Structural changes only · control gate</text>
          </g>
        </g>
      </svg>
    </div>
    '''


def avatar_svg(kind: str) -> str:
    """Return an abstract robot illustration; never a real-person likeness."""
    palettes = {
        "observer": ("#24d6ff", "#087aa3", "eye", "01"),
        "diagnostician": ("#32e2cc", "#087e78", "search", "02"),
        "optimizer": ("#a18aff", "#5744a1", "settings", "03"),
        "integrator": ("#efbf67", "#92733d", "layers", "04"),
    }
    accent, shade, symbol, number = palettes.get(kind, palettes["observer"])
    safe_kind = kind if kind in palettes else "observer"
    key = f"avatar-{safe_kind}"
    crown = {
        "observer": '<path d="M222 58 235 36H286L304 58"/>',
        "diagnostician": '<path d="M217 74 224 46 252 31 281 36 305 56 311 85"/>',
        "optimizer": '<path d="M223 60 230 36 251 23 277 31 301 54"/>',
        "integrator": '<path d="M215 100 213 57 249 27 288 34 313 66 317 115"/>',
    }[safe_kind]
    circuit = {
        "observer": '<path d="M246 78v24h-11M287 78v24h10M240 149h17v15h20v-15h16"/>',
        "diagnostician": '<path d="M248 73v21h-15M286 76v26h15M240 139h13v18h22v-9h18"/>',
        "optimizer": '<path d="M265 57v28M247 73h36M237 140l16 16h23l18-16"/>',
        "integrator": '<path d="M240 78h16v21M291 80h-14v19M240 147l12 13h25l14-13"/>',
    }[safe_kind]
    return f'''
    <svg class="svg-avatar" style="display:block;width:100%;height:100%;object-fit:cover" viewBox="0 0 400 300" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Abstract futuristic robot illustration; visual placeholder, not a real portrait" preserveAspectRatio="xMidYMid slice">
      <defs>
        <radialGradient id="{key}-ambient" cx="66%" cy="42%" r="72%"><stop stop-color="{shade}" stop-opacity=".7"/><stop offset=".52" stop-color="#092031"/><stop offset="1" stop-color="#05111d"/></radialGradient>
        <linearGradient id="{key}-armor" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#456578"/><stop offset=".3" stop-color="#152c3c"/><stop offset=".65" stop-color="#091b29"/><stop offset="1" stop-color="#254453"/></linearGradient>
        <linearGradient id="{key}-head" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#527889"/><stop offset=".38" stop-color="#1d3c4d"/><stop offset=".7" stop-color="#0d2332"/><stop offset="1" stop-color="#365567"/></linearGradient>
        <linearGradient id="{key}-glass" x1="0" y1="0" x2="0" y2="1"><stop stop-color="{shade}" stop-opacity=".7"/><stop offset=".7" stop-color="#03131f"/><stop offset="1" stop-color="#163443"/></linearGradient>
        <linearGradient id="{key}-fade" x1="0" y1="0" x2="0" y2="1"><stop offset=".65" stop-color="#05111d" stop-opacity="0"/><stop offset="1" stop-color="#05111d" stop-opacity=".78"/></linearGradient>
        <filter id="{key}-glow"><feGaussianBlur stdDeviation="4"/></filter>
      </defs>
      <rect width="400" height="300" fill="url(#{key}-ambient)"/>
      <g fill="none" stroke="{accent}" stroke-width=".8">
        <path d="M23 81V29h71M378 101V26h-57M23 236v35h62M326 274h52v-46" stroke-opacity=".34"/>
        <path class="avatar-tech-lines" d="M22 107H93l25 25h56M27 198h83l30-30h41M304 118h41l30-30M312 178h35l29 28" stroke-opacity=".17"/>
        <g class="avatar-rings">
          <circle cx="262" cy="119" r="94" stroke-opacity=".28"/>
          <circle cx="262" cy="119" r="103" stroke-opacity=".1" stroke-dasharray="3 6"/>
          <path d="M169 115a94 94 0 0 1 47-78M307 34a94 94 0 0 1 49 63" stroke-opacity=".75" stroke-width="2"/>
        </g>
      </g>
      <g class="avatar-particles" fill="{accent}" opacity=".7"><circle cx="24" cy="107" r="2"/><circle cx="111" cy="198" r="2"/><circle cx="347" cy="178" r="2"/><circle cx="356" cy="96" r="2.5"/></g>
      <g font-family="Inter,Segoe UI,Arial,sans-serif" fill="{accent}">
        <text x="36" y="51" font-size="9" letter-spacing="2.2" opacity=".85">RAGOPS / {number}</text>
        <text x="36" y="66" font-size="6.8" letter-spacing="1.6" opacity=".5">SYNTHETIC AVATAR</text>
      </g>
      <g transform="translate(36 99)" color="{accent}" opacity=".9">{icon(symbol, 41)}</g>
      <g stroke="{accent}" stroke-width="1" stroke-opacity=".25"><path d="M38 159h48M38 169h64M38 179h36"/><path d="M38 209h6m5 0h6m5 0h6m5 0h6m5 0h6m5 0h6" stroke-width="3"/></g>
      <ellipse cx="264" cy="264" rx="108" ry="22" fill="{accent}" fill-opacity=".15" filter="url(#{key}-glow)"/>
      <path d="M145 300 160 234Q166 216 193 208L233 192H285L329 209Q350 218 359 238L382 300Z" fill="url(#{key}-armor)" stroke="#426073" stroke-width="1.5"/>
      <path d="M234 168 232 208 263 226 289 207 287 169" fill="#091c2a" stroke="#415d6c" stroke-width="1.5"/>
      <path d="M241 174v24l21 13 18-12v-24M246 184h29M246 192h29" fill="none" stroke="{accent}" stroke-opacity=".5" stroke-width="1.5"/>
      <path d="M192 210 219 200 240 223 224 241 197 239 181 277 164 274 173 234Z" fill="#142f40" stroke="#385b6d"/>
      <path d="M293 202 319 209 343 235 354 275 337 280 320 239 290 238 278 225Z" fill="#183342" stroke="#416273"/>
      <path d="M201 218 217 215 229 228M299 214l19 9 14 22M193 242l-12 28M323 249l10 29" fill="none" stroke="{accent}" stroke-opacity=".75" stroke-width="2"/>
      <path d="M231 238 261 246 291 235 308 282 269 297 219 278Z" fill="#0a1e2d" stroke="#2d4e60"/>
      <path d="M241 252h40M247 258h28" stroke="{accent}" stroke-opacity=".4"/>
      <circle cx="263" cy="272" r="10" fill="#0c3041" stroke="{accent}" stroke-opacity=".55"/><circle cx="263" cy="272" r="4" fill="{accent}" fill-opacity=".8"/>
      <path d="M219 74Q224 44 253 39L280 42Q304 50 309 77L306 137Q302 161 283 175L267 182 248 177Q226 165 220 141Z" fill="url(#{key}-head)" stroke="#7594a1" stroke-opacity=".7" stroke-width="1.4"/>
      <g fill="none" stroke="{accent}" stroke-width="2" stroke-opacity=".8">{crown}</g>
      <path d="M225 88 241 79 292 83 305 95 302 127 291 142 240 140 224 126Z" fill="url(#{key}-glass)" stroke="{accent}" stroke-opacity=".45"/>
      <path d="M230 91 243 85h26" fill="none" stroke="#a4e5e8" stroke-opacity=".25" stroke-width="2"/>
      <path d="M237 111h18M277 111h17" stroke="{accent}" stroke-width="5" stroke-linecap="round" filter="url(#{key}-glow)"/>
      <path d="M237 111h18M277 111h17" stroke="{accent}" stroke-width="2.5" stroke-linecap="round"/>
      <path d="M260 116v13h8" fill="none" stroke="#87a8b7" stroke-opacity=".45"/>
      <path d="M252 148h25M257 153h16" stroke="#9ab8c1" stroke-opacity=".6" stroke-linecap="round"/>
      <g fill="none" stroke="{accent}" stroke-opacity=".35" stroke-width=".8">{circuit}</g>
      <path d="M217 89 208 96 208 124 219 137M309 88l10 9v27l-12 13" fill="#162f3f" stroke="#53798a"/>
      <path d="M212 100v19M315 101v18" stroke="{accent}" stroke-width="2.5"/>
      <circle cx="223" cy="148" r="2.5" fill="{accent}" fill-opacity=".65"/><circle cx="301" cy="148" r="2.5" fill="{accent}" fill-opacity=".65"/>
      <rect width="400" height="300" fill="url(#{key}-fade)"/>
    </svg>
    '''
