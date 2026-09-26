"""Dashboard-only presentation; official evaluation values remain static."""

DASHBOARD_CSS = """
<style>
.st-key-dashboard_content {--dashboard-muted:#91b2c7;min-width:0;gap:1rem!important}
.st-key-dashboard_content .page-heading {margin-bottom:.1rem}
.st-key-dashboard_content .page-subtitle {max-width:920px}
.st-key-dashboard_content .kpi-grid {grid-template-columns:repeat(5,minmax(0,1fr));gap:1rem;margin:.6rem 0 .5rem}
.st-key-dashboard_content .kpi {min-height:112px;padding:1rem;align-items:center;min-width:0}
.st-key-dashboard_content .kpi>div {min-width:0}
.st-key-dashboard_content .kpi .label {font-size:.74rem;line-height:1.5;letter-spacing:.025em;overflow-wrap:break-word}
.st-key-dashboard_content .kpi .value {font-size:2rem;line-height:1.25;font-variant-numeric:tabular-nums}
.st-key-dashboard_content .kpi .sub {font-size:.72rem;line-height:1.5}
.st-key-dashboard_content .dashboard-snapshot-label,
.st-key-dashboard_content .dashboard-section-label {display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:.3rem .8rem;color:var(--dashboard-muted);font-size:.72rem;line-height:1.5}
.st-key-dashboard_content .dashboard-snapshot-label b {color:#cce6f3;font-size:.82rem;font-weight:650}
.st-key-dashboard_content .dashboard-section-label b {color:#dbedf6;font-size:.85rem;letter-spacing:.035em}
.st-key-dashboard_content .dashboard-section-label {padding-bottom:.65rem}
.st-key-dashboard_content .dashboard-scope-note {color:var(--dashboard-muted);font-size:.72rem;line-height:1.6;margin:.45rem 0 .15rem!important}
.st-key-dashboard_content [class*="st-key-chart_"] {padding:1rem!important;min-width:0;gap:.35rem!important}
.st-key-dashboard_content [class*="st-key-chart_"]>[data-testid="stElementContainer"] {flex-shrink:0}
.st-key-dashboard_content [class*="st-key-chart_"] :is([data-testid="stMarkdownContainer"],[data-testid="stCaptionContainer"]) {margin-bottom:0!important}
.st-key-dashboard_content [class*="st-key-chart_"] [data-testid="stCaptionContainer"] p:last-child {margin-bottom:0}
.st-key-dashboard_content [class*="st-key-chart_"]>[data-testid="stElementContainer"]:has([data-testid="stCaptionContainer"]) {margin-top:auto;padding-top:.4rem}
.st-key-dashboard_content .chart-title {font-size:.96rem;line-height:1.45;margin:0 0 .2rem}
.st-key-dashboard_content :is(.st-key-chart_compare,.st-key-chart_latency,.st-key-chart_chunking) .chart-title {min-height:2.8rem}
.st-key-dashboard_content .chart-subtitle {font-size:.76rem;line-height:1.55;color:var(--dashboard-muted);min-height:2.4rem}
.st-key-dashboard_content .dashboard-chart-legend {display:flex;flex-wrap:wrap;gap:.4rem .8rem;padding:.15rem .1rem;min-height:2rem;color:#bfd7e5;font-size:.75rem;line-height:1.65}
.st-key-dashboard_content .dashboard-chart-legend span {display:flex;flex-wrap:wrap;gap:.4rem;align-items:center;max-width:100%}
.st-key-dashboard_content .dashboard-chart-legend i {width:8px;height:8px;border-radius:50%;flex:none}
.st-key-dashboard_content .dashboard-chart-legend b {color:#e7f6ff;font-variant-numeric:tabular-nums}
.st-key-dashboard_content .st-key-dashboard_compare_metrics {gap:.6rem!important;padding:.3rem 0 .8rem}
.st-key-dashboard_content .metric-grid {grid-template-columns:repeat(4,minmax(0,1fr));gap:.85rem;margin:0}
.st-key-dashboard_content .metric-card {padding:.75rem .85rem;min-height:0}
.st-key-dashboard_content .metric-values {font-size:1.15rem;margin:.5rem 0 .35rem;white-space:nowrap}
.st-key-dashboard_content .metric-after {animation:none!important}
.st-key-dashboard_content .metric-delta {font-size:.69rem}
.st-key-dashboard_content .metric-name {font-size:.71rem}
.st-key-dashboard_content .st-key-history,
.st-key-dashboard_content .st-key-inspector {padding:1rem!important;gap:.7rem!important}
.st-key-dashboard_content .st-key-dashboard_history_mobile {display:none!important}
.st-key-dashboard_content .dashboard-inspector-query {margin:0 0 .8rem}
.st-key-dashboard_content .dashboard-inspector-query small,
.st-key-dashboard_content .dashboard-inspector-fields small,
.st-key-dashboard_content .dashboard-accepted small,
.st-key-dashboard_content .dashboard-live-fields small {display:block;color:var(--dashboard-muted);font-size:.67rem;line-height:1.6}
.st-key-dashboard_content .dashboard-inspector-query p {font-size:.97rem;line-height:1.85;margin:.2rem 0!important;overflow-wrap:anywhere}
.st-key-dashboard_content .dashboard-inspector-fields {display:grid;grid-template-columns:1fr 1fr;gap:.7rem 1rem}
.st-key-dashboard_content .dashboard-inspector-fields b {display:block;color:#cfe5f2;font-size:.79rem;line-height:1.6;font-weight:550;overflow-wrap:anywhere}
.st-key-dashboard_content .dashboard-accepted {margin-top:.8rem;padding:.6rem .75rem;border-left:2px solid #759aab;background:rgba(16,58,71,.24);border-radius:0 6px 6px 0}
.st-key-dashboard_content .dashboard-accepted b {font-size:.8rem;line-height:1.6;color:#d0e6f2}
.st-key-dashboard_content .st-key-inspector .metric-grid {grid-template-columns:repeat(2,minmax(0,1fr))}
.st-key-dashboard_content .st-key-inspector .verdict {padding:.65rem .85rem;min-height:0;margin:.5rem 0}
.st-key-dashboard_content .st-key-inspector .verdict .title {font-size:.86rem}
.st-key-dashboard_content .st-key-dashboard_live_run {padding:.8rem 1rem!important;border-color:rgba(117,154,171,.25)!important;background:rgba(8,26,40,.5)!important;gap:.6rem!important}
.st-key-dashboard_content .dashboard-live-fields {display:grid;grid-template-columns:2fr 1fr 1fr 1fr;gap:.75rem;font-size:.77rem;line-height:1.7;color:#bfd7e5}
.st-key-dashboard_content .dashboard-live-fields span {display:block;overflow-wrap:anywhere}
.st-key-dashboard_content [data-testid="stCaptionContainer"] p {color:var(--dashboard-muted);font-size:.75rem;line-height:1.6}
/* Keep three chart panels on laptops; allow the primary chart a full row on tablets. */
.st-key-dashboard_content [data-testid="stHorizontalBlock"]:has(>[data-testid="stColumn"] [class*="st-key-chart_"]){gap:1rem!important;align-items:stretch}
.st-key-dashboard_content [data-testid="stColumn"]:has([class*="st-key-chart_"]){display:flex;flex-direction:column;align-self:stretch}
.st-key-dashboard_content [data-testid="stColumn"]:has([class*="st-key-chart_"])>[data-testid="stVerticalBlock"]{flex:1;min-height:0}
.st-key-dashboard_content [data-testid="stLayoutWrapper"]:has(>[class*="st-key-chart_"]){display:flex;flex:1;min-height:0}
.st-key-dashboard_content [data-testid="stVerticalBlock"][class*="st-key-chart_"]{flex:1;height:auto!important}
@media(max-width:1200px){
  .st-key-dashboard_content [data-testid="stHorizontalBlock"]:has(>[data-testid="stColumn"] [class*="st-key-chart_"]){display:grid;grid-template-columns:repeat(2,minmax(0,1fr))}
  .st-key-dashboard_content [data-testid="stHorizontalBlock"]:has(>[data-testid="stColumn"] [class*="st-key-chart_"])>[data-testid="stColumn"]{width:100%!important;min-width:0!important}
  .st-key-dashboard_content [data-testid="stHorizontalBlock"]:has(>[data-testid="stColumn"] [class*="st-key-chart_"])>[data-testid="stColumn"]:first-child{grid-column:1/-1}
  .st-key-dashboard_content .st-key-chart_compare .chart-title{min-height:0}
}
@media(max-width:1100px){
  .st-key-dashboard_content .kpi-grid {grid-template-columns:repeat(3,minmax(0,1fr))}
  .st-key-dashboard_content .st-key-inspector [data-testid="stHorizontalBlock"]{flex-wrap:wrap!important;gap:1rem!important}
  .st-key-dashboard_content .st-key-inspector [data-testid="stHorizontalBlock"]>[data-testid="stColumn"]{width:100%!important;flex:1 1 100%!important}
}
@media(max-width:800px){
  .st-key-dashboard_content .kpi-grid {grid-template-columns:repeat(2,minmax(0,1fr))}
  .st-key-dashboard_content .kpi-grid .kpi:last-child {grid-column:1/-1}
  .st-key-dashboard_content .metric-grid {grid-template-columns:repeat(2,minmax(0,1fr))}
  .st-key-dashboard_content .dashboard-live-fields {grid-template-columns:1fr 1fr}
  .st-key-dashboard_content .dashboard-live-fields>div:first-child {grid-column:1/-1}
  .st-key-dashboard_content .st-key-history,.st-key-dashboard_content .st-key-inspector {padding:.75rem!important}
  .st-key-dashboard_content .st-key-dashboard_history_desktop {display:none!important}
  .st-key-dashboard_content .st-key-dashboard_history_mobile {display:flex!important;gap:.5rem!important}
  .st-key-dashboard_content .st-key-dashboard_history_mobile summary p {overflow-wrap:anywhere;white-space:normal;font-size:.75rem!important;line-height:1.6}
  .st-key-dashboard_content .st-key-dashboard_history_mobile button {margin-top:.6rem}
}
@media(max-width:680px){
  .st-key-dashboard_content [data-testid="stHorizontalBlock"]:has(>[data-testid="stColumn"] [class*="st-key-chart_"]){grid-template-columns:minmax(0,1fr)}
  .st-key-dashboard_content :is(.st-key-chart_latency,.st-key-chart_chunking) .chart-title{min-height:0}
}
@media(max-width:520px){
  .st-key-dashboard_content {gap:1rem!important}
  .st-key-dashboard_content .kpi-grid {gap:.75rem}
  .st-key-dashboard_content .kpi {padding:.85rem .75rem;min-height:112px;gap:.5rem}
  .st-key-dashboard_content .kpi-icon {display:none}
  .st-key-dashboard_content [class*="st-key-chart_"] {padding:.85rem!important}
  .st-key-dashboard_content .chart-subtitle {min-height:0}
  .st-key-dashboard_content .metric-card {padding:.65rem .6rem}
  .st-key-dashboard_content .dashboard-inspector-fields {gap:.6rem}
  .st-key-dashboard_content .dashboard-chart-legend {gap:.4rem .7rem}
}
@media(prefers-reduced-motion:reduce){
  .st-key-dashboard_content * {animation:none!important;transition:none!important}
}
</style>
"""
