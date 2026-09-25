"""Compact architecture: local SVG connectors, four agents, conditional review."""
from .icons import icon


def _node(key, title, role, glyph, description, theme="cyan", step=0):
    return (f'<div class="architecture-node arch-tone-{theme}" data-node="{key}" data-role="{role}" '
            f'aria-description="{description}" style="--node-step:{step}"><span class="architecture-icon">{icon(glyph,23)}</span>'
            f'<h3>{title}</h3><span class="architecture-role">{role}</span></div>')


def _path(start, end, route, shape, arrow=True):
    marker = ' marker-end="url(#architecture-arrow)"' if arrow else ''
    return (f'<path class="arch-link" data-from="{start}" data-to="{end}" data-route="{route}" '
            f'd="{shape}"{marker}/>')


def _fixed_arrowhead(route, right=False):
    # Keep the head outside the stretched SVG so its shape stays proportional.
    shape = "M4 2L9 6L4 10" if right else "M8 2L3 6L8 10"
    return (f'<svg class="architecture-arrowhead" data-route="{route}" '
            f'viewBox="0 0 12 12" aria-hidden="true"><path d="{shape}"/></svg>')


def _arrow(start, end, column, row=1, route="shared", reverse=False):
    shape = "M30 12H3" if reverse else "M2 12H29"
    placement = " architecture-return" if row == 3 else ""
    return (f'<div class="architecture-arrow{placement}" style="grid-column:{column};grid-row:{row}" '
            'aria-hidden="true"><svg viewBox="0 0 32 24">'
            + _path(start, end, route, shape) + '</svg>'
            + ('<span class="architecture-arrow-label">NO</span>' if route == "unhealthy" else '') + '</div>')


def architecture_html():
    stages = [
        ("user-query", "User Query", "INPUT", "user", "A question for the knowledge corpus."),
        ("baseline-rag", "Baseline RAG", "SYSTEM", "database", "Retrieve the baseline evidence."),
        ("monitoring", "Monitoring", "AGENT 01", "eye", "Observe retrieval quality."),
        ("retrieval-health", "Retrieval healthy?", "CONTROL", "check-circle", "Healthy retrieval accepts the baseline; only a detected failure continues to Diagnosis."),
        ("diagnosis", "Diagnosis", "AGENT 02", "search", "Identify the retrieval failure."),
        ("optimization", "Optimization", "AGENT 03", "settings", "Propose a targeted change."),
    ]
    chain = []
    for index, stage in enumerate(stages):
        if index:
            route = "unhealthy" if stage[0] == "diagnosis" else "shared"
            chain.append(_arrow(stages[index-1][0], stage[0], index*2, route=route))
        chain.append(f'<div class="architecture-stage" style="grid-column:{index*2+1}">'
                     + _node(*stage, theme="amber" if stage[0] == "retrieval-health" else "cyan", step=index) + '</div>')
    outcomes = [
        ("improved", "IMPROVED", "optimized-accepted", "Accept optimized evidence"),
        ("same", "NO MEANINGFUL CHANGE", "baseline-unchanged", "Retain baseline"),
        ("worse", "WORSE", "baseline-worse", "Retain baseline"),
    ]
    verdict_rows = ''.join(
        f'<div class="architecture-verdict-row" data-route="{route}"><b>{label}</b>'
        f'<svg viewBox="0 0 24 16" aria-hidden="true">{_path("validation-decision", key, route, "M1 8H22")}</svg>'
        f'<span data-node="{key}" data-role="OUTCOME">{result}</span></div>'
        for route, label, key, result in outcomes
    )
    return f'''<div class="architecture-flow" tabindex="0" role="region" aria-label="Architecture workflow. Monitoring checks retrieval health. Healthy retrieval accepts baseline evidence; detected failures enter optimization. Accepted evidence leads to a final grounded answer for this run. Scroll horizontally on smaller screens.">
      <svg class="architecture-defs" aria-hidden="true"><defs><marker id="architecture-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto"><path d="M1 1 9 5 1 9" fill="none" stroke="context-stroke" stroke-width="1.8"/></marker></defs></svg>
      <div class="architecture-layout">
        <div class="architecture-stages">{''.join(chain)}</div>
        <div class="architecture-healthy-lane" aria-label="Yes: accept baseline evidence and generate the final grounded answer without optimization.">
          <div class="architecture-baseline-accepted" data-node="baseline-accepted" data-role="OUTCOME">{icon('check-circle',16)}<b>Baseline accepted</b></div>
          <span class="architecture-healthy-label">YES</span>
          <div class="architecture-healthy-connector" aria-hidden="true">
            <svg class="architecture-route-line" viewBox="0 0 100 52" preserveAspectRatio="none">
              {_path('retrieval-health','baseline-accepted','healthy','M100 1V24Q100 30 96 30H0',False)}
            </svg>
            {_fixed_arrowhead('healthy')}
          </div>
        </div>
        <div class="architecture-healthy-return" aria-hidden="true">
          <svg class="architecture-route-line" viewBox="0 0 24 100" preserveAspectRatio="none">
            {_path('baseline-accepted','final-answer','healthy','M21 0H6V100H21',False)}
          </svg>
          {_fixed_arrowhead('healthy',right=True)}
        </div>
        <svg class="architecture-drop" viewBox="0 0 24 95" aria-hidden="true">
          {_path('optimization','risk-gate','shared','M12 1V92')}
        </svg>
        <div class="architecture-risk">{_node('risk-gate','Risk Gate','CONTROL','shield','Route by action impact.','amber')}</div>
        <svg class="architecture-split" viewBox="0 0 32 182" preserveAspectRatio="none" aria-hidden="true">
          {_path('risk-gate','auto-approved','low','M31 75H23Q17 75 17 69V45Q17 39 11 39H3')}
          {_path('risk-gate','human-approval','high','M31 107H23Q17 107 17 113V129Q17 135 11 135H3')}
          <circle cx="31" cy="75" r="2" fill="#48ddbb"/>
          <circle cx="31" cy="107" r="2" fill="#eaba62"/>
        </svg>
        <div class="architecture-branches">
          <div class="arch-route-control arch-route-low" data-route="low" tabindex="0" role="group" aria-label="Low-impact path: Risk Gate, auto-approved by policy, Action Executor. Human Approval is bypassed.">
            <div class="architecture-lane-label">LOW IMPACT</div>
            <div class="architecture-policy-node" data-node="auto-approved" data-role="CONTROL">{icon('check-circle',18)}<b>Auto-approved by policy</b></div>
            <code>rewrite_query · change_top_k</code>
          </div>
          <div class="architecture-high-group">
            <div class="arch-route-control arch-route-high" data-route="high" tabindex="0" role="group" aria-label="High-impact path: Risk Gate, Human Approval. Only approval continues to Action Executor.">
              <div class="architecture-lane-label">HIGH IMPACT <span>CONTROL</span></div>
              <div class="architecture-policy-node" data-node="human-approval" data-role="CONTROL">{icon('user',18)}<b>Human Approval</b></div>
              <code>rechunk_and_reindex</code>
              <div class="architecture-decisions"><span class="architecture-approve">← Approve</span><span class="architecture-reject">Reject ↓</span></div>
            </div>
            <div class="arch-route-control architecture-terminal" data-route="rejected" tabindex="0" role="group" aria-label="Rejected high-impact path: no action execution; retain baseline evidence for the final grounded answer.">
              <svg viewBox="0 0 24 12" aria-hidden="true">{_path('human-approval','baseline-retained','rejected','M12 1V9')}</svg>
              <div data-node="baseline-retained" data-role="OUTCOME"><b>{icon('close',13)} Retain Baseline</b><small>No execution</small></div>
            </div>
          </div>
        </div>
        <svg class="architecture-merge" viewBox="0 0 32 182" preserveAspectRatio="none" aria-label="Both approved paths merge into Action Executor.">
          {_path('auto-approved','action-executor','low','M31 39H22Q16 39 16 45V91',False)}
          {_path('human-approval','action-executor','approved','M31 164H22Q16 164 16 158V91',False)}
          <path class="architecture-merge-trunk" d="M16 91H3" marker-end="url(#architecture-arrow)"/>
          <circle class="architecture-merge-junction" cx="16" cy="91" r="3.5" fill="#48ddbb"/>
        </svg>
        <div class="architecture-executor">{_node('action-executor','Action Executor','SYSTEM','play','Apply only an allowed action.')}</div>
        {_arrow('action-executor','validation',6,3,reverse=True)}
        <div class="architecture-validation">{_node('validation','Validation Agent','AGENT 04','check-circle','Compare baseline and candidate retrieval.','green',6)}</div>
        <svg class="architecture-decision-input" viewBox="0 0 32 182" preserveAspectRatio="none" aria-hidden="true">
          {_path('validation','validation-decision','shared','M31 91H22Q16 91 16 85V30Q16 24 10 24H2')}
        </svg>
        <div class="architecture-validation-decision" data-node="validation-decision" data-role="CONTROL">
          <div class="architecture-decision-heading"><b>Validation Decision</b><span class="architecture-role">CONTROL</span></div>
          {verdict_rows}
          <svg class="architecture-verdict-merge" viewBox="0 0 18 212" aria-label="All validation outcomes select evidence for the final grounded answer.">
            {_path('optimized-accepted','final-answer','shared','M1 22H10V210',False)}
            {_path('baseline-unchanged','final-answer','shared','M1 66H10V210',False)}
            {_path('baseline-worse','final-answer','shared','M1 110H10V210',False)}
            <path class="architecture-result-trunk" d="M10 110V210" marker-end="url(#architecture-arrow)"/>
          </svg>
        </div>
        <div class="architecture-rejected-return" aria-hidden="true">
          <svg class="architecture-route-line" viewBox="0 0 100 64" preserveAspectRatio="none">
            {_path('baseline-retained','final-answer','rejected','M100 0V9Q100 14 98 14H8Q6 14 6 20V54Q6 60 4 60H0',False)}
          </svg>
          {_fixed_arrowhead('rejected')}
        </div>
        <div class="architecture-final-answer">{_node('final-answer','Final Grounded Answer','SYSTEM','file','Answer from the accepted evidence and preserve sources.','green')}</div>
      </div>
    </div>'''


ARCHITECTURE_CSS = r"""<style>
/* Reserve the navbar's real height, including its two-row mobile layout. */
[data-testid="stMain"]:has(.st-key-architecture_content){height:100dvh;overflow:hidden}
[data-testid="stMainBlockContainer"]:has(.st-key-architecture_content){height:100%;min-height:0;padding-bottom:0!important}
[data-testid="stMainBlockContainer"]:has(.st-key-architecture_content)>[data-testid="stVerticalBlock"]{height:100%;min-height:0;gap:0!important}
[data-testid="stMain"]:has(.st-key-architecture_content) [data-testid="stElementContainer"]:has(.ragops-nav-shell){flex:0 0 auto!important}
[data-testid="stMain"]:has(.st-key-architecture_content) [data-testid="stMarkdownContainer"]:has(>.ragops-nav-shell){margin-bottom:0!important}
[data-testid="stMainBlockContainer"]:has(.st-key-architecture_content)>[data-testid="stVerticalBlock"]>[data-testid="stLayoutWrapper"]:has(>.st-key-architecture_content){display:flex;flex-direction:column;flex:1 1 0!important;min-height:0!important;height:auto!important;overflow:hidden}
.st-key-architecture_content{flex:1 1 0!important;min-height:0!important;height:auto!important;overflow-y:auto!important;overflow-x:hidden!important;padding-top:.85rem;padding-bottom:2rem;scrollbar-gutter:stable;overscroll-behavior-y:contain}
.architecture-flow{padding:1rem 1.3rem .85rem;margin-bottom:.6rem;border:1px solid rgba(25,158,197,.36);border-radius:17px;background:linear-gradient(130deg,rgba(4,29,47,.76),rgba(2,17,31,.82));position:relative;isolation:isolate;animation:architecture-reveal .5s ease both;max-width:100%;min-width:0;overflow-x:auto;overscroll-behavior-x:contain;scroll-padding-inline:1.3rem;scrollbar-width:thin;scrollbar-color:#245569 #061c2b}
.architecture-flow,.architecture-flow *{box-sizing:border-box}.architecture-flow:focus-visible{outline:2px solid #76cbdb;outline-offset:3px}
.architecture-defs{position:absolute;width:0;height:0;overflow:hidden}
/* Keep labels at their normal size. The policy lane needs more room than the
   agent cards; the board scrolls within its frame only below laptop widths. */
.architecture-layout{display:grid;grid-template-columns:repeat(4,minmax(0,1fr) 24px) 225px 24px minmax(0,1fr);grid-template-rows:96px 52px 234px 20px 72px;align-items:start;min-width:1100px;max-width:1400px;margin-inline:auto;padding-left:20px;position:relative}.architecture-stages{display:contents}
.architecture-stage{grid-row:1;min-width:0}.architecture-risk,.architecture-executor,.architecture-validation{grid-row:3;min-width:0;margin-top:43px}
.architecture-risk{grid-column:11}.architecture-executor{grid-column:7}.architecture-validation{grid-column:5}
.architecture-node{width:100%}
.architecture-node{--arch-accent:#27d9f3;position:relative;border:1px solid rgba(39,217,243,.38);border-radius:11px;padding:.6rem .4rem;height:96px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:.32rem;text-align:center;background:linear-gradient(145deg,#06283b,#041626);transition:border-color .22s,box-shadow .22s}
.architecture-node[data-role="SYSTEM"],.architecture-node[data-role="INPUT"]{--arch-accent:#8faebf;border-color:rgba(119,156,178,.34);background:linear-gradient(145deg,#102333,#091927)}
.architecture-node[data-role^="AGENT"]:after{content:"";position:absolute;inset:-1px;border:1px solid var(--arch-accent);border-radius:inherit;opacity:0;pointer-events:none;animation:architecture-node-pulse 10s ease-in-out infinite;animation-delay:calc(var(--node-step)*1.4s)}
.architecture-node.arch-tone-amber{--arch-accent:#ffc34a;background:linear-gradient(145deg,#302515,#161b20);border-color:rgba(255,195,74,.55)}.architecture-node.arch-tone-green{--arch-accent:#25e6ae;background:linear-gradient(145deg,#073a35,#05222b);border-color:rgba(37,230,174,.45)}
.architecture-icon{color:var(--arch-accent);line-height:1}.architecture-node h3{font-size:.94rem!important;line-height:1.35!important;margin:0!important;padding:0!important;color:#ebf7ff}.architecture-role{color:var(--arch-accent,#e6bc6b);font-size:.54rem;font-weight:650;letter-spacing:.07em;line-height:1.5;white-space:nowrap;padding:.08rem .28rem;border-radius:4px;background:rgba(0,0,0,.18)}
.architecture-arrow{width:24px;height:96px;display:flex;align-items:center;justify-content:center;position:relative}.architecture-arrow.architecture-return{height:182px}.architecture-arrow svg{width:24px;height:24px;overflow:visible}.architecture-arrow-label{position:absolute;top:21px;left:0;right:0;text-align:center;font-size:.56rem;font-weight:700;color:#edc578}
.architecture-drop{grid-column:11;grid-row:2;justify-self:center;width:24px;height:95px;overflow:visible}
.arch-link,.architecture-merge-trunk,.architecture-result-trunk{fill:none;stroke:#2cd9eb;stroke-width:1.6;stroke-dasharray:3 5;stroke-linecap:round;opacity:.65;animation:architecture-direction 1.6s linear infinite;transition:opacity .2s,stroke-width .2s;vector-effect:non-scaling-stroke}
.arch-link:is([data-route="low"],[data-route="approved"],[data-route="healthy"],[data-route="improved"]),.architecture-merge-trunk,.architecture-result-trunk{stroke:#48ddbb}.arch-link:is([data-route="high"],[data-route="unhealthy"],[data-route="same"]){stroke:#eaba62}.arch-link[data-route="worse"]{stroke:#d58e82}.arch-link[data-route="rejected"]{stroke:#d58e82;animation:none;stroke-dasharray:none}
.architecture-split,.architecture-merge{grid-row:3;width:24px;height:182px;overflow:visible}.architecture-split{grid-column:10}.architecture-merge{grid-column:8}.architecture-split .arch-link,.architecture-merge .arch-link{opacity:.85;stroke-width:1.8}
.architecture-merge-trunk{opacity:.9;stroke-width:2}.architecture-merge-junction{stroke:#092d30;stroke-width:1.2;transition:opacity .2s,filter .2s}
.architecture-branches{grid-column:9;grid-row:3;min-width:0}.architecture-high-group{margin-top:10px}
.arch-route-control{outline:none;scroll-margin-inline:1rem}.arch-route-low,.arch-route-high{padding:.5rem .75rem;border:1px solid rgba(62,211,184,.38);background:linear-gradient(120deg,rgba(10,64,59,.4),rgba(4,34,43,.62));border-radius:10px;transition:border-color .2s,box-shadow .2s;display:flex;flex-direction:column;justify-content:center;gap:.16rem;height:78px}
.arch-route-high{height:94px;border-color:rgba(231,180,78,.45);background:linear-gradient(120deg,rgba(59,42,15,.46),rgba(24,26,27,.62))}
.architecture-lane-label{font-size:.56rem;letter-spacing:.09em;font-weight:750;color:#55e4bf;line-height:1.5;display:flex;align-items:center;justify-content:space-between;gap:.3rem}.arch-route-high .architecture-lane-label{color:#f4c46d}.architecture-lane-label>span{font-size:.46rem;letter-spacing:.04em;opacity:.8;font-weight:500}
.arch-route-control code{color:#9eccc7;background:none;font-size:.63rem;padding:0;overflow-wrap:anywhere;white-space:normal;line-height:1.5}.arch-route-high code{color:#cabc9e}
.architecture-policy-node{display:flex;align-items:center;gap:.35rem;color:#67e6c9;min-width:0}.architecture-policy-node>svg{flex:none}.architecture-policy-node>b{font-size:.82rem;line-height:1.35}.arch-route-high .architecture-policy-node{color:#f5c870}.architecture-decisions{display:flex;justify-content:space-between;gap:.35rem;margin-top:.18rem;font-size:.64rem;font-weight:600;line-height:1.5}.architecture-approve{color:#72d9b3}.architecture-reject{color:#e6a091}
.architecture-terminal{width:145px;max-width:100%;text-align:center;margin-inline:auto}.architecture-terminal>svg{height:12px;width:24px;display:block;margin:0 auto}.architecture-terminal>[data-node]{border:1px solid rgba(197,111,103,.32);background:rgba(45,25,31,.45);border-radius:8px;padding:.2rem .35rem;transition:border-color .2s,box-shadow .2s}.architecture-terminal b{display:block;font-size:.65rem;line-height:1.5;color:#dca999;white-space:nowrap}.architecture-terminal small{display:block;font-size:.57rem;color:#b9a6a6;line-height:1.5}
.architecture-healthy-lane{grid-column:1 / 8;grid-row:2;position:relative;height:52px;min-width:0}.architecture-baseline-accepted{position:absolute;top:15px;left:0;width:185px;height:30px;display:flex;align-items:center;justify-content:center;gap:.4rem;border:1px solid rgba(72,221,187,.35);border-radius:8px;color:#78dfc2;background:#08272e;font-size:.73rem}.architecture-healthy-connector{position:absolute;top:0;left:193px;width:calc(100% - 193px - (100% - 72px)/8);height:52px;overflow:visible}.architecture-healthy-label{position:absolute;top:4px;right:calc((100% - 72px)/8 + 8px);font-size:.56rem;font-weight:700;color:#78dfc2}.architecture-healthy-return{grid-column:1;grid-row:2 / 6;position:relative;top:30px;height:calc(100% - 66px);width:24px;margin-left:-22px;overflow:visible}.architecture-healthy-return .arch-link{opacity:.55;animation-duration:2.4s}
.architecture-route-line{display:block;width:100%;height:100%;overflow:visible}.architecture-arrowhead{position:absolute;left:-3px;top:24px;width:12px;height:12px;overflow:visible;fill:none;stroke:#48ddbb;stroke-width:1.6;stroke-linecap:round;stroke-linejoin:round;opacity:.8;pointer-events:none;transition:opacity .2s,stroke-width .2s}.architecture-healthy-return .architecture-arrowhead{left:12px;top:calc(100% - 6px)}.architecture-rejected-return .architecture-arrowhead{top:54px;stroke:#d58e82;stroke-width:1.5;opacity:.6}
.architecture-decision-input{grid-column:4;grid-row:3;width:24px;height:182px;overflow:visible}.architecture-validation-decision{grid-column:1 / 4;grid-row:3;position:relative;height:182px;border:1px solid rgba(72,221,187,.3);border-radius:11px;padding:10px 28px 8px 10px;background:linear-gradient(145deg,#092c33,#071c2b);min-width:0}.architecture-decision-heading{height:30px;display:flex;align-items:center;justify-content:space-between;gap:.3rem;color:#dff6ec}.architecture-decision-heading>b{font-size:.84rem}.architecture-verdict-row{height:44px;display:grid;grid-template-columns:minmax(0,1fr) 22px minmax(0,1fr);align-items:center;gap:3px;border-top:1px solid rgba(98,158,169,.13);font-size:.73rem;line-height:1.3;color:#bfd9df}.architecture-verdict-row>b{font-size:.6rem;letter-spacing:.02em;color:#88b8c3}.architecture-verdict-row[data-route="improved"]>b{color:#68dab5}.architecture-verdict-row[data-route="same"]>b{color:#dfc18b}.architecture-verdict-row[data-route="worse"]>b{color:#dca194}.architecture-verdict-row>svg{width:22px;height:16px;overflow:visible}.architecture-verdict-merge{position:absolute;right:8px;top:42px;width:18px;height:212px;overflow:visible;pointer-events:none}.architecture-verdict-merge .arch-link{stroke:#48ddbb;opacity:.5}.architecture-result-trunk{opacity:.8}
.architecture-rejected-return{grid-column:6 / 10;grid-row:4;position:relative;top:-4px;margin-left:8px;width:calc(100% - 120.5px);height:64px;overflow:visible;pointer-events:none}.architecture-rejected-return .arch-link{opacity:.6;stroke-width:1.5}
.architecture-final-answer{grid-column:1 / 6;grid-row:5;min-width:0}.architecture-final-answer .architecture-node{height:72px;flex-direction:row;gap:.8rem;border-color:rgba(72,221,187,.45);background:linear-gradient(120deg,#08352f,#06242e)}.architecture-final-answer .architecture-node h3{font-size:1rem!important}
.architecture-flow:has(.arch-route-control:is(:hover,:focus-visible)) :is(.arch-link,.architecture-arrowhead):is([data-route="low"],[data-route="high"],[data-route="approved"],[data-route="rejected"]){opacity:.14}
.architecture-flow:has(.arch-route-low:is(:hover,:focus-visible)) .arch-link[data-route="low"],.architecture-flow:has(.arch-route-high:is(:hover,:focus-visible)) .arch-link:is([data-route="high"],[data-route="approved"]),.architecture-flow:has(.architecture-terminal:is(:hover,:focus-visible)) :is(.arch-link,.architecture-arrowhead):is([data-route="high"],[data-route="rejected"]){opacity:1;stroke-width:2.3}
.architecture-flow:has(.arch-route-control:is(:hover,:focus-visible)) [data-node="risk-gate"]{border-color:#ffd06a;box-shadow:0 0 13px rgba(255,195,74,.1)}
.architecture-flow:has(.arch-route-low:is(:hover,:focus-visible),.arch-route-high:is(:hover,:focus-visible)) [data-node="action-executor"]{border-color:#57e7c1;box-shadow:0 0 13px rgba(37,230,174,.1)}
.architecture-flow:has(.arch-route-low:is(:hover,:focus-visible),.arch-route-high:is(:hover,:focus-visible)) :is(.architecture-merge-trunk,.architecture-merge-junction){opacity:1;filter:drop-shadow(0 0 3px #48ddbb)}
.architecture-flow:has(.architecture-terminal:is(:hover,:focus-visible)) :is(.architecture-merge-trunk,.architecture-merge-junction){opacity:.14}
.arch-route-low:is(:hover,:focus-visible){border-color:#57e7c1;box-shadow:0 0 14px rgba(37,230,174,.09)}.arch-route-high:is(:hover,:focus-visible){border-color:#ffd071;box-shadow:0 0 14px rgba(255,195,74,.1)}.architecture-terminal:is(:hover,:focus-visible)>[data-node]{border-color:#e6a091;box-shadow:0 0 12px rgba(215,130,111,.09)}
.arch-route-control:focus-visible{outline:2px solid #76cbdb;outline-offset:3px;border-radius:10px}
.st-key-architecture_state,.st-key-architecture_langgraph,.st-key-architecture_langsmith{animation:architecture-reveal .5s ease both;animation-delay:.08s}.st-key-architecture_langsmith{animation-delay:.14s}.st-key-architecture_state{animation-delay:.2s}
.st-key-architecture_state .state-code{padding:.6rem;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.2rem 1rem}.st-key-architecture_state .state-code>div{flex-direction:column;gap:0;align-items:flex-start}.st-key-architecture_state .state-code code{font-size:.69rem}.st-key-architecture_state .state-code span{font-size:.65rem}.st-key-architecture_langgraph,.st-key-architecture_langsmith{padding:.65rem .9rem!important;min-height:90px}.st-key-architecture_langgraph .panel-heading,.st-key-architecture_langsmith .panel-heading{font-size:.8rem}.st-key-architecture_langgraph [data-testid="stVerticalBlock"],.st-key-architecture_langsmith [data-testid="stVerticalBlock"]{gap:.25rem}.st-key-architecture_langsmith .source-note{font-size:.68rem}
/* Equalize the supporting cards to their tallest content only while side by side. */
@media(min-width:801px){
  .st-key-architecture_content [data-testid="stHorizontalBlock"]:has(>[data-testid="stColumn"] .st-key-architecture_langgraph){align-items:stretch!important}
  .st-key-architecture_content [data-testid="stHorizontalBlock"]:has(>[data-testid="stColumn"] .st-key-architecture_langgraph)>[data-testid="stColumn"]{display:flex;flex-direction:column;align-self:stretch!important}
  .st-key-architecture_content [data-testid="stColumn"]:has(.st-key-architecture_langgraph,.st-key-architecture_langsmith)>[data-testid="stVerticalBlock"],
  .st-key-architecture_content [data-testid="stColumn"] [data-testid="stLayoutWrapper"]:has(>.st-key-architecture_langgraph,>.st-key-architecture_langsmith){display:flex;flex-direction:column;flex:1 1 auto!important;align-self:stretch}
  .st-key-architecture_langgraph,.st-key-architecture_langsmith{flex:1 1 auto!important;height:auto!important}
}
@keyframes architecture-direction{to{stroke-dashoffset:-16}}@keyframes architecture-reveal{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}@keyframes architecture-node-pulse{0%,25%,100%{opacity:0}8%,15%{opacity:.5}}
@media(max-width:1100px){.st-key-architecture_state .state-code{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:700px){.architecture-flow{padding:.9rem;scroll-padding-inline:.9rem}.st-key-architecture_state .state-code{grid-template-columns:1fr}.st-key-architecture_state .state-code code{overflow-wrap:anywhere}}
@media(prefers-reduced-motion:reduce){.architecture-flow,.architecture-flow *,.architecture-flow *:after,.st-key-architecture_state,.st-key-architecture_langgraph,.st-key-architecture_langsmith{animation:none!important;transition:none!important}.architecture-flow,.st-key-architecture_state,.st-key-architecture_langgraph,.st-key-architecture_langsmith{opacity:1!important;transform:none!important}.architecture-node:after{display:none}}
</style>"""
