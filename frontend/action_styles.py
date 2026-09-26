"""Action-page conversation and evidence styling; no global page overrides."""

ACTION_CSS = r"""<style>
.st-key-action_query,.st-key-action_results,.st-key-action_validation{min-width:0}
/* Streamlit reserves fixed-height containers through their outer flex wrapper. */
.st-key-action_query div:has(>.st-key-action_conversation){flex-basis:clamp(340px,48svh,520px)!important;min-height:0}
.st-key-action_conversation{min-width:0;min-height:0;height:clamp(340px,48svh,520px)!important;scrollbar-width:thin;scrollbar-color:#255268 transparent;overscroll-behavior-y:contain}
.st-key-action_query .panel-heading,.st-key-action_results .panel-heading,.st-key-action_validation .panel-heading{flex-wrap:wrap;row-gap:.25rem}
.st-key-action_results .evidence-grid{grid-template-columns:repeat(auto-fit,minmax(min(100%,210px),1fr));gap:.75rem}
.st-key-action_results .approval-grid{grid-template-columns:repeat(auto-fit,minmax(min(100%,185px),1fr));gap:.85rem}
.st-key-action_conversation:focus-visible{outline:2px solid rgba(0,210,235,.65);outline-offset:3px}
.st-key-action_query [class*="st-key-action_chat_user"],
.st-key-action_query [class*="st-key-action_chat_assistant"]{background:transparent;border:0;padding:0;min-width:0;gap:0}

/* Keep physical conversation alignment independent of message language. */
.st-key-action_query [class*="st-key-action_chat_user"] [data-testid="stChatMessage"]{
  display:flex;flex-direction:row-reverse;direction:ltr;align-items:flex-start;
  width:fit-content;max-width:85%;margin:.35rem 0 .25rem auto;padding:.8rem .85rem;
  gap:.65rem;border:1px solid rgba(74,152,193,.35);border-radius:15px 15px 4px 15px;
  background:linear-gradient(130deg,#0b2b40,#092235);color:#d8eaf6;
}
.st-key-action_query [class*="st-key-action_chat_assistant"] [data-testid="stChatMessage"]{
  display:flex;flex-direction:row;direction:ltr;align-items:flex-start;
  width:100%;max-width:100%;margin:.15rem auto .3rem 0;padding:1rem;
  gap:.75rem;border:1px solid rgba(0,209,236,.47);border-radius:5px 16px 16px 16px;
  background:linear-gradient(135deg,rgba(4,37,53,.98),rgba(4,22,37,.98));
  box-shadow:inset 3px 0 rgba(0,216,244,.22),0 5px 20px rgba(0,0,0,.1);
  color:#e2f1fa;animation:action-answer-in .23s ease-out both;
}
.st-key-action_query :is([class*="st-key-action_chat_user"],[class*="st-key-action_chat_assistant"]) [data-testid="stChatMessageContent"]{
  flex:1 1 auto;min-width:0;max-width:100%;overflow-wrap:anywhere;
}
.st-key-action_query [class*="st-key-action_chat_user"] [data-testid="stChatMessageContent"]{width:auto;margin:0;align-self:flex-start}
.st-key-action_query [class*="st-key-action_chat_user"] [data-testid="stChatMessageContent"]>[data-testid="stVerticalBlock"]{height:auto!important;flex:0 0 auto;gap:.3rem}
.st-key-action_query [class*="st-key-action_chat_assistant"] [data-testid="stChatMessageContent"]{width:100%}
.st-key-action_query [class*="st-key-action_chat_user"] [data-testid="stMarkdownContainer"]{
  color:#d7e9f5;font-size:.91rem;line-height:1.7;margin-bottom:0;
}
.st-key-action_query [class*="st-key-action_chat_assistant"] [class*="st-key-live_answer_text"] [data-testid="stMarkdownContainer"]{
  color:#e3f1fa;font-size:.97rem;line-height:1.8;
}
.st-key-action_query [class*="st-key-action_chat_assistant"] [class*="st-key-live_answer_text"] :is(p,li){
  font-size:inherit;line-height:1.8;overflow-wrap:anywhere;
}
.st-key-action_query [class*="st-key-action_chat_assistant"] [class*="st-key-live_answer_text"] p{margin:0 0 .65rem}
.st-key-action_query [class*="st-key-action_chat_assistant"] [class*="st-key-live_answer_text"] p:last-child{margin-bottom:0}
.st-key-action_query [class*="st-key-action_chat_assistant"] [class*="st-key-live_answer_text"] :is(ul,ol){
  margin:.4rem 0 .65rem;padding-inline-start:1.35rem;
}
.st-key-action_query [class*="st-key-action_chat_assistant"] [class*="st-key-live_answer_text"] li+li{margin-top:.35rem}
.st-key-action_query :is([class*="st-key-action_chat_user"],[class*="st-key-action_chat_assistant"]) [dir="auto"]{
  unicode-bidi:plaintext;text-align:start;
}

/* Override both native avatar colors and custom material-icon avatars. */
.st-key-action_query [class*="st-key-action_chat_user"] [data-testid^="stChatMessageAvatar"]{
  width:27px!important;height:27px!important;min-width:27px;flex:0 0 27px;
  display:flex;align-items:center;justify-content:center;border-radius:8px;
  color:#a7bdcf!important;background:#16364a!important;border:1px solid rgba(129,171,196,.24);
}
.st-key-action_query [class*="st-key-action_chat_assistant"] [data-testid^="stChatMessageAvatar"]{
  width:29px!important;height:29px!important;min-width:29px;flex:0 0 29px;
  display:flex;align-items:center;justify-content:center;border-radius:9px;
  color:#27dcee!important;background:#073348!important;border:1px solid rgba(0,216,244,.37);
}
.st-key-action_query :is([class*="st-key-action_chat_user"],[class*="st-key-action_chat_assistant"]) [data-testid^="stChatMessageAvatar"] :is(span,svg){
  color:inherit!important;font-size:18px!important;width:18px!important;height:18px!important;line-height:18px!important;
}
.st-key-action_query [class*="st-key-action_chat_assistant"] [data-testid="stCaptionContainer"] p{
  color:#88b2c6;font-size:.68rem;line-height:1.55;margin:.15rem 0;
}
.action-answer-label{display:flex;align-items:center;gap:.4rem;font-size:.64rem;font-weight:700;letter-spacing:.1em;color:#65cee0;text-transform:uppercase;margin-bottom:.45rem}

/* References stay subordinate to the answer and remain accessible on mobile. */
.action-source-chips{display:flex;flex-wrap:wrap;align-items:center;gap:.35rem;margin:.6rem 0 .1rem;min-width:0}
.action-source-chip{display:inline-flex;align-items:center;gap:.3rem;max-width:100%;padding:.22rem .5rem;
  border:1px solid rgba(42,160,195,.3);border-radius:999px;background:rgba(0,132,168,.075);
  color:#9bd6e4!important;font-size:.65rem;font-weight:500;line-height:1.5;text-decoration:none!important;overflow-wrap:anywhere;
  transition:border-color .15s,background .15s;
}
.action-source-chip svg{width:12px;height:12px;flex:none;color:#64c9df}
a.action-source-chip:hover,button.action-source-chip:hover{border-color:rgba(0,214,239,.6);background:rgba(0,155,187,.13)}
.action-source-chip:focus-visible{outline:2px solid #36d7ec;outline-offset:3px}
.action-source-summary{display:flex;flex-direction:column;gap:.35rem;min-width:0;padding:.1rem 0;color:#a7c5d8;font-size:.75rem;line-height:1.6;overflow-wrap:anywhere}
.action-source-summary+.action-source-summary{margin-top:.6rem;padding-top:.7rem;border-top:1px solid rgba(41,139,177,.21)}
.action-source-summary :is(b,strong){color:#d6eaf7;font-size:.8rem;font-weight:650;line-height:1.5}
.action-source-summary small,.action-source-platform{color:#79bfd3;font-size:.65rem;line-height:1.5}
.action-source-service{color:#d3e9f6;font-size:.81rem;font-weight:650;line-height:1.55}
.action-source-excerpt,.action-source-summary p{color:#a2c3d7;font-size:.75rem;line-height:1.75;margin:0!important;white-space:pre-wrap;overflow-wrap:anywhere}
.st-key-action_query .action-source-summary [dir="auto"]{unicode-bidi:plaintext;text-align:start}
.st-key-action_query .evidence-grid:has(.action-source-summary){grid-template-columns:repeat(2,minmax(0,1fr));gap:.55rem}
.st-key-action_query .evidence-card:has(.action-source-summary){padding:.7rem .75rem;background:rgba(3,29,45,.57)}
.st-key-action_query [class*="st-key-action_chat_assistant"] [data-testid="stExpander"]{
  border-color:rgba(41,145,175,.23)!important;background:rgba(3,26,42,.45)!important;border-radius:9px!important;
}
.st-key-action_query [class*="st-key-action_chat_assistant"] [data-testid="stExpander"] summary{min-height:36px}
.st-key-action_query [class*="st-key-action_chat_assistant"] [data-testid="stExpander"] summary p{font-size:.73rem}

/* Suggestions wrap at a readable width instead of becoming a scrolling strip. */
.st-key-action_suggestions{min-width:0;gap:.2rem}
.st-key-action_suggestions [data-testid="stCaptionContainer"] p{font-size:.68rem;color:#8eb2c5;margin:0}
.st-key-action_suggestions [data-testid="stHorizontalBlock"]{
  display:flex;flex-wrap:wrap!important;align-items:stretch;gap:.5rem;
  width:100%;max-width:100%;padding:.1rem .05rem .35rem;
}
.st-key-action_suggestions [data-testid="stColumn"]{flex:1 1 150px!important;width:auto!important;min-width:min(150px,100%)!important;max-width:none}
.st-key-action_suggestions [data-testid="stButton"]>button{
  width:100%;min-height:38px;height:100%;padding:.4rem .6rem;border-radius:10px;
  color:#b9dce8!important;border:1px solid rgba(43,158,185,.31)!important;
  background:rgba(7,43,60,.66)!important;box-shadow:none;
  transition:border-color .15s,background .15s,transform .15s;
}
.st-key-action_suggestions [data-testid="stButton"]>button p{
  font-size:.76rem;line-height:1.6;unicode-bidi:plaintext;text-align:start;overflow-wrap:anywhere;
}
.st-key-action_suggestions [data-testid="stButton"]>button:hover:not(:disabled){border-color:rgba(0,215,235,.6)!important;background:rgba(8,62,78,.7)!important;transform:translateY(-1px)}
.st-key-action_suggestions [data-testid="stButton"]>button:focus-visible{outline:2px solid #36d7ec;outline-offset:2px}
.st-key-action_composer{border-top:1px solid rgba(48,146,176,.22);padding-top:.65rem;gap:.5rem;min-width:0}
.st-key-action_composer textarea{min-height:72px!important;unicode-bidi:plaintext;text-align:start;line-height:1.65}
.st-key-action_composer [data-testid="stChatInput"]{border:1px solid rgba(49,169,196,.45);background:#08273a;border-radius:13px}
.st-key-action_composer [data-testid="stChatInput"] textarea{min-height:24px!important}
.st-key-action_composer [data-testid="stChatInputSubmitButton"]{color:#48d9eb}

/* Latest-turn validation uses the page width, separate from the trace. */
.st-key-action_validation{
  border:1px solid rgba(0,162,209,.36)!important;border-radius:15px!important;
  background:linear-gradient(125deg,rgba(3,28,44,.79),rgba(3,18,31,.86));padding:1rem!important;
}
.st-key-action_validation .metric-grid{grid-template-columns:repeat(5,minmax(0,1fr));gap:.65rem;margin:.65rem 0}
.st-key-action_validation .metric-card{padding:.8rem;min-width:0}
.st-key-action_validation .metric-name{font-size:.73rem}
.st-key-action_validation .metric-values{gap:.45rem;margin:.55rem 0 .4rem}
.st-key-action_validation .metric-before{font-size:1.03rem}
.st-key-action_validation .metric-after{font-size:1.2rem}
.st-key-action_validation .action-feedback{margin-top:.3rem}

/* Status words are supplied by runtime state; CSS adds no status claims. */
.action-runtime{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:.35rem .75rem;
  padding:.5rem .7rem;border:1px solid rgba(64,144,174,.22);border-radius:9px;
  background:rgba(4,25,39,.58);color:#91afc2;font-size:.69rem;line-height:1.5;
}
.action-runtime-badge{display:inline-flex;align-items:center;gap:.4rem;flex:none;
  padding:.16rem .4rem;border:1px solid rgba(91,159,184,.25);border-radius:6px;
  color:#adcbdc;background:rgba(25,65,84,.26);font-size:.64rem;font-weight:650;line-height:1.5;
}
.action-runtime-badge>svg{width:13px;height:13px;color:#89b9cb;flex:none}
.action-runtime.available .action-runtime-badge{color:#91dce7;border-color:rgba(27,182,199,.28);background:rgba(0,114,142,.1)}
.action-runtime.neutral .action-runtime-badge,.action-runtime.unavailable .action-runtime-badge{color:#a6bfce;border-color:rgba(106,149,172,.25);background:rgba(32,61,80,.26)}
.action-runtime-note{color:#89a8bd;font-size:.67rem;line-height:1.5}
.action-feedback{display:flex;align-items:flex-start;gap:.5rem;padding:.6rem .75rem;
  border:1px solid rgba(56,147,178,.27);border-radius:9px;background:rgba(3,35,48,.47);
  color:#a0c5d7;font-size:.74rem;line-height:1.6;
}
.action-feedback>svg{flex:none;width:17px;height:17px;margin-top:.08rem;color:#6fc5d9}
.action-feedback :is(b,strong){color:#c2e4ef;font-weight:650}
.action-feedback.positive{color:#a0d8c8;border-color:rgba(38,193,151,.32);background:rgba(0,70,53,.19)}
.action-feedback.positive>svg,.action-feedback.positive :is(b,strong){color:#68dfba}
.action-feedback.neutral{color:#9dbdce;border-color:rgba(57,139,171,.24);background:rgba(8,31,46,.55)}

/* One compact stage ribbon; detailed execution evidence remains in its inspector. */
.st-key-action_results .trace-ribbon{gap:0;padding:.35rem .05rem .6rem;max-width:100%;overflow-x:auto;overscroll-behavior-x:contain;scrollbar-width:thin}
.st-key-action_results .trace-stage{min-width:66px;flex:1 0 66px}
.st-key-action_results .trace-dot{width:38px;height:38px;margin-bottom:.35rem}
.st-key-action_results .trace-dot svg{width:19px;height:19px}
.st-key-action_results .trace-connector{height:38px;flex:0 0 12px}
.st-key-action_results .trace-number{font-size:.53rem;margin-bottom:.12rem}
.st-key-action_results .trace-name{font-size:.73rem;line-height:1.4;overflow-wrap:normal;word-break:normal;hyphens:none}
.st-key-action_results .trace-role{font-size:.6rem;letter-spacing:.025em;margin-top:.16rem}
.st-key-action_results .trace-status{font-size:.65rem;line-height:1.45;margin-top:.17rem;overflow-wrap:anywhere}
.st-key-action_results .trace-detail{display:none}
.st-key-action_results .trace-stage:is(.active,.pending,.rejected) .trace-detail{display:block;color:#8cacbe;font-size:.65rem;line-height:1.5;overflow-wrap:anywhere;margin-top:.25rem}
.st-key-action_results .trace-source{font-size:.68rem;padding:.1rem .1rem .4rem}
.st-key-action_results .policy-banner{padding:.65rem .75rem}
.st-key-action_results .policy-banner b{font-size:.79rem}
.st-key-action_results .policy-banner span{font-size:.7rem}

@keyframes action-answer-in{from{opacity:.4;transform:translateY(3px)}to{opacity:1;transform:none}}
@media(max-width:1150px){
  [data-testid="stHorizontalBlock"]:has(>[data-testid="stColumn"] .st-key-action_query){flex-wrap:wrap!important;gap:1rem!important}
  [data-testid="stHorizontalBlock"]:has(>[data-testid="stColumn"] .st-key-action_query)>[data-testid="stColumn"]{width:100%!important;flex:1 1 100%!important;min-width:0!important}
}
@media(max-width:1100px){
  .st-key-action_query [class*="st-key-action_chat_assistant"] [data-testid="stChatMessage"]{padding:.85rem .75rem;gap:.6rem}
  .st-key-action_validation .metric-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
}
@media(max-width:800px){
  .action-runtime{gap:.3rem .65rem;padding:.45rem .6rem}
  .st-key-action_conversation{max-height:62svh!important}
}
@media(max-width:520px){
  .st-key-action_query [class*="st-key-action_chat_user"] [data-testid="stChatMessage"]{max-width:85%;padding:.65rem;gap:.45rem;border-radius:12px 12px 3px 12px}
  .st-key-action_query [class*="st-key-action_chat_assistant"] [data-testid="stChatMessage"]{padding:.8rem .6rem;gap:.5rem;border-radius:4px 12px 12px 12px}
  .st-key-action_query :is([class*="st-key-action_chat_user"],[class*="st-key-action_chat_assistant"]) [data-testid^="stChatMessageAvatar"]{width:24px!important;height:24px!important;min-width:24px;flex-basis:24px;border-radius:7px}
  .st-key-action_query :is([class*="st-key-action_chat_user"],[class*="st-key-action_chat_assistant"]) [data-testid^="stChatMessageAvatar"] :is(span,svg){width:16px!important;height:16px!important;font-size:16px!important;line-height:16px!important}
  .st-key-action_query .evidence-grid:has(.action-source-summary){grid-template-columns:1fr}
  .action-source-chip{font-size:.61rem;padding:.18rem .4rem}
  .action-source-excerpt,.action-source-summary p{font-size:.72rem}
  .action-runtime{align-items:flex-start;flex-direction:column;gap:.25rem}
  .action-runtime-note{font-size:.63rem}
  .action-feedback{padding:.55rem .6rem;font-size:.7rem}
  .st-key-action_suggestions [data-testid="stColumn"]{flex:1 1 100%!important;min-width:0!important}
  .st-key-action_validation{padding:.8rem!important}
  .st-key-action_validation .metric-grid{grid-template-columns:1fr;gap:.5rem}
  .st-key-action_validation .metric-card{padding:.75rem}
}
@media(prefers-reduced-motion:reduce){
  .st-key-action_query [class*="st-key-action_chat_assistant"] [data-testid="stChatMessage"],
  .st-key-action_results :is(.trace-stage,.trace-dot,.trace-connector svg),
  .st-key-action_suggestions [data-testid="stButton"]>button,
  .st-key-action_validation :is(.metric-card,.metric-after),
  .action-source-chip{animation:none!important;transition:none!important;opacity:1;transform:none}
}
</style>"""
