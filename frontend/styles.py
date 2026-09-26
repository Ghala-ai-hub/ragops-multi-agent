"""Local, responsive visual system for the five RAGOps pages."""

CSS = r"""
<style>
:root {
  color-scheme:dark;
  --bg:#020b15;--bg2:#041221;--panel:#041725;--panel2:#061b2d;
  --line:rgba(24,175,223,.29);--line2:rgba(0,216,244,.58);
  --text:#f0f8ff;--muted:#9dbcd0;--muted2:#7496ac;
  --cyan:#00d8f4;--cyan2:#4cbfff;--green:#25e6ae;--purple:#a78bfa;
  --amber:#ffc34a;--red:#ff667e;--shadow:0 12px 35px rgba(0,0,0,.18);--radius:15px;
  --content-max:1640px;--page-gutter:2rem;--panel-gap:1rem;
}
html,body,[data-testid="stApp"]{font-family:"Inter","Segoe UI",Arial,sans-serif;background:var(--bg);color:var(--text)}
[data-testid="stAppViewContainer"]{background:radial-gradient(ellipse at 90% 12%,rgba(0,125,191,.12),transparent 38%),radial-gradient(ellipse at 2% 58%,rgba(0,136,165,.07),transparent 30%),linear-gradient(150deg,#020b15 0%,#020e1a 48%,#010810 100%)!important}
[data-testid="stHeader"],[data-testid="stToolbar"],.stDeployButton,#MainMenu,footer{display:none!important}
[data-testid="stAppViewBlockContainer"],.block-container{width:100%;max-width:var(--content-max)!important;margin-inline:auto;padding:0 var(--page-gutter) 2.4rem!important}
[data-testid="stMainBlockContainer"]{padding-top:0!important}
[data-testid="stVerticalBlock"],[data-testid="stHorizontalBlock"]{gap:.85rem}
[data-testid="stMarkdownContainer"] p{line-height:1.6}
*{box-sizing:border-box;scrollbar-width:thin;scrollbar-color:#16475e #03101c}
a{text-underline-offset:3px}a:focus-visible,button:focus-visible{outline:2px solid var(--cyan)!important;outline-offset:4px}svg{vertical-align:middle}

/* One navigation bar, with a factual runtime indicator. */
[data-testid="stMain"]{scrollbar-gutter:stable}
[data-testid="stElementContainer"]:has(.ragops-nav-shell){position:sticky;top:0;z-index:990}
[data-testid="stMarkdownContainer"]:has(>.ragops-nav-shell){margin-bottom:0!important}
.ragops-nav-shell{margin:0 -2rem .1rem;padding:.8rem 1.45rem;background:rgba(2,12,23,.95);backdrop-filter:blur(18px);border-bottom:1px solid rgba(19,158,206,.23);border-radius:0 0 26px 26px}
.ragops-nav{display:grid;grid-template-columns:minmax(215px,1fr) auto minmax(180px,1fr);align-items:center;gap:1.15rem}
.brand-wrap{display:flex;align-items:center;gap:.7rem;text-decoration:none!important;color:var(--text)!important}
.brand-mark{display:flex;align-items:center;justify-content:center;width:43px;height:43px;color:var(--cyan);flex:none;filter:drop-shadow(0 0 7px rgba(0,190,255,.24))}.brand-mark svg{width:100%;height:100%}
.brand-name{font-size:1.43rem;font-weight:790;letter-spacing:-.055em;white-space:nowrap}.brand-name span{color:var(--cyan)}
.nav-links{display:flex;align-items:center;gap:3px;padding:4px;border:1px solid rgba(23,148,190,.4);border-radius:18px;background:linear-gradient(180deg,rgba(1,15,29,.8),rgba(3,19,32,.55))}
.nav-links a{display:flex;align-items:center;justify-content:center;gap:.6rem;padding:.63rem 1.15rem;border:1px solid transparent;border-radius:13px;color:#c0d9e8!important;font-size:.81rem;font-weight:550;text-decoration:none!important;white-space:nowrap;transition:background .18s,border-color .18s,color .18s}
.nav-links a svg{width:17px;height:17px;flex:none}.nav-links a:hover{color:#fff!important;background:rgba(0,174,218,.065)}
.nav-links a.active{color:var(--cyan)!important;border-color:#00bde9;background:linear-gradient(145deg,rgba(0,119,186,.3),rgba(1,51,78,.65));box-shadow:inset 0 0 17px rgba(0,161,252,.09),0 0 13px rgba(0,170,255,.12)}
.nav-status{display:flex;align-items:center;justify-self:end;gap:.7rem;width:12.5rem;height:2.5rem;flex-shrink:0;padding-left:1.2rem;border-left:1px solid rgba(45,137,172,.24)}
.status-dot{width:8px;height:8px;border-radius:50%;background:#799aac;flex:none}.status-dot.available{background:var(--green);box-shadow:0 0 10px rgba(37,230,174,.35)}.status-dot.neutral{background:#8aaec4}
.status-copy{color:#c6dfec;font-size:.64rem;font-weight:700;line-height:1.45;letter-spacing:.025em}.status-note{display:block;color:#89aabf;font-weight:400;font-size:.61rem;margin-top:.08rem;letter-spacing:0}

/* Shared hierarchy. */
.eyebrow,.section-kicker{color:var(--cyan);font-size:.63rem;font-weight:750;letter-spacing:.26em;text-transform:uppercase;line-height:1.6}.section-kicker{margin-bottom:.4rem}
.page-heading{position:relative;padding:1rem .65rem .3rem;isolation:isolate}
.page-heading:after{content:"";z-index:-1;position:absolute;right:0;top:-15px;width:40%;height:160px;opacity:.36;pointer-events:none;background:radial-gradient(ellipse at 60% 60%,rgba(0,180,244,.24),transparent 64%);border-bottom:1px solid rgba(0,191,242,.15);border-radius:50%;transform:rotate(-8deg)}
.page-title,.section-title{font-size:clamp(2rem,3.35vw,3.25rem);font-weight:780;letter-spacing:-.045em;line-height:1.14;margin:0 0 .35rem;color:#f4f9ff}.section-title{font-size:clamp(1.55rem,2.1vw,2rem)}
.page-subtitle,.section-copy{color:#a7c9dd;font-size:.88rem;line-height:1.65;max-width:1090px;margin:0 0 .5rem}.section-copy{font-size:.84rem}
.section{padding:1.65rem 0}.accent{color:var(--cyan)}.good{color:var(--green)}.warn{color:var(--amber)}.bad{color:var(--red)}.small-note{color:#89aabe;font-size:.68rem;line-height:1.6}
.rule{height:1px;background:linear-gradient(90deg,rgba(0,189,235,.35),rgba(0,189,235,0));margin:1rem 0}
.panel-heading{display:flex;gap:.5rem;align-items:center;color:#deeff9;font-size:.78rem;font-weight:740;line-height:1.55;letter-spacing:.045em;margin:0 0 .3rem}.panel-heading svg{color:var(--cyan);width:22px;height:22px}
.panel-subtitle{color:#8aacbf;font-size:.71rem;line-height:1.55;margin:0 0 .45rem}
.empty-state{display:flex;align-items:center;justify-content:center;flex-direction:column;gap:.45rem;min-height:125px;border:1px dashed rgba(71,156,190,.23);border-radius:11px;padding:1.2rem;text-align:center;color:#92b1c5;background:rgba(4,20,34,.3);font-size:.78rem;line-height:1.6}.empty-state strong{color:#d7edf9;font-size:.85rem}
.page-footer{display:flex;justify-content:space-between;align-items:center;gap:1rem;padding:1rem .6rem .25rem;color:#8cafc2;border-top:1px solid rgba(14,154,203,.22);font-size:.68rem;letter-spacing:.055em}.page-footer span{color:var(--cyan)}

/* Overview. */
.hero-grid{display:grid;grid-template-columns:minmax(0,.9fr) minmax(0,1.1fr);align-items:center;gap:.8rem;padding:.7rem .65rem .1rem;min-height:535px}
.hero-left{padding:.4rem 0 .8rem 1rem}
.hero-badge{display:inline-flex;align-items:center;gap:.4rem;color:#9cc5d9;border:1px solid rgba(21,141,172,.25);border-radius:20px;padding:.3rem .6rem;margin:.65rem 0;font-size:.59rem;letter-spacing:.07em}.hero-badge i{width:5px;height:5px;background:var(--cyan);border-radius:50%}
.hero-title{margin:1rem 0 .6rem!important;color:#f6fbff;font-size:clamp(3.3rem,5.25vw,5.1rem)!important;font-weight:850!important;line-height:1.02!important;letter-spacing:-.065em!important;white-space:nowrap}
.hero-title .accent{color:var(--cyan);background:linear-gradient(120deg,#49e5f6,#00bde5);background-clip:text;-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.hero-subtitle{font-size:clamp(1.15rem,1.8vw,1.65rem);font-weight:640;line-height:1.4;color:#bdd8e9;margin-bottom:.8rem;letter-spacing:-.025em}
.hero-tagline{font-size:1.05rem;color:#a9d3e6;letter-spacing:.15em;line-height:1.65;margin-bottom:.8rem}
.hero-copy{max-width:640px;font-size:.9rem;color:#accbde;line-height:1.72;letter-spacing:.012em}
.hero-actions{display:flex;flex-wrap:wrap;gap:.9rem;margin-top:1.15rem}
.hero-btn{display:inline-flex;align-items:center;justify-content:center;gap:.65rem;padding:.86rem 1.35rem;min-height:49px;border-radius:11px;font-size:.86rem;font-weight:740;text-decoration:none!important;transition:background .18s,box-shadow .18s,transform .18s}.hero-btn svg{width:18px;height:18px}
.hero-btn.primary{color:#00121e!important;border:1px solid #74f4ff;background:linear-gradient(110deg,#11e0ea,#10aff2);box-shadow:0 0 24px rgba(0,197,246,.17),inset 0 1px 1px rgba(255,255,255,.28)}
.hero-btn.secondary{color:#e6f4ff!important;border:1px solid #356078;background:linear-gradient(130deg,rgba(4,33,56,.9),rgba(5,25,44,.75))}.hero-btn:hover{transform:translateY(-2px);box-shadow:0 8px 24px rgba(0,159,229,.18)}
.control-wrap{width:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;min-width:0}.control-loop-svg{width:100%;max-width:600px;height:auto;display:block}
.hero-statbar{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));border:1px solid rgba(25,142,183,.39);background:linear-gradient(110deg,rgba(3,24,39,.94),rgba(4,20,35,.84));border-radius:16px;margin:.7rem 0 1.1rem;padding:1rem .75rem}
.hero-stat{display:flex;flex-direction:column;justify-content:center;min-height:44px;padding:.1rem 1.25rem;border-right:1px solid rgba(72,158,187,.25)}.hero-stat:last-child{border-right:0}.hero-stat b{color:#f2f8ff;font-size:1.2rem;font-weight:760;line-height:1.25}.hero-stat span{color:#9ebed2;font-size:.7rem;line-height:1.5;margin-top:.17rem}.hero-stat svg{color:var(--cyan)}

/* Failure and response cards. */
.failure-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1rem}
.failure-card{--card-accent:var(--cyan);border:1px solid rgba(0,181,230,.4);border-radius:15px;padding:1rem 1.1rem;background:linear-gradient(135deg,rgba(2,34,54,.93),rgba(3,23,40,.86));transition:border-color .18s,transform .18s}
.failure-card:nth-child(2){--card-accent:var(--purple);border-color:rgba(151,112,239,.43);background:linear-gradient(130deg,rgba(28,20,65,.55),rgba(8,18,44,.92))}
.failure-card:nth-child(3){--card-accent:var(--green);border-color:rgba(15,191,158,.4);background:linear-gradient(130deg,rgba(0,45,44,.58),rgba(2,26,30,.9))}.failure-card.interactive:hover,.failure-card.interactive:focus-visible{transform:translateY(-2px);border-color:var(--card-accent)}
.failure-top{display:flex;align-items:center;gap:.9rem}.failure-icon{width:47px;height:47px;flex:none;display:flex;align-items:center;justify-content:center;border-radius:12px;color:var(--card-accent);background:rgba(51,157,222,.1)}.failure-icon svg{width:27px;height:27px}
.failure-card h3{margin:0 0 .2rem!important;color:#edf5ff;font-size:.98rem!important;font-weight:750;line-height:1.4}.failure-card p{color:#a4c3d7;font-size:.75rem;line-height:1.55;margin:0}
.failure-arrow{margin-left:auto;flex:none;display:flex;align-items:center;justify-content:center;width:31px;height:31px;border:1px solid rgba(72,165,202,.3);border-radius:50%;color:var(--card-accent)}.failure-arrow svg{width:15px;height:15px}
.failure-response{display:flex;gap:.7rem;align-items:center;margin-top:.8rem;padding-top:.7rem;border-top:1px solid rgba(73,152,186,.22);font-size:.72rem;line-height:1.55;color:#9dbed2}.failure-response>svg{width:22px;height:22px;flex:none;color:var(--card-accent)}.failure-response strong,.failure-response b{display:block;color:var(--card-accent);font-size:.7rem;margin-bottom:.14rem}
.failure-card .num{color:var(--card-accent);font-size:.64rem;letter-spacing:.12em}.failure-card .action{color:var(--card-accent);font-size:.71rem;margin-top:.5rem}

/* Action controls and native panels. */
.command-header,.dashboard-hero{display:flex;align-items:flex-end;justify-content:space-between;gap:1rem;margin:1.1rem 0 .7rem}.command-title{font-size:2.7rem;font-weight:800;letter-spacing:-.045em;line-height:1.12}.command-sub{color:#a8c7da;font-size:.88rem;margin-top:.4rem}
.mode-banner{display:flex;align-items:center;justify-content:space-between;gap:1rem;padding:.6rem .85rem;border:1px solid rgba(32,141,182,.24);border-radius:10px;background:rgba(2,24,40,.65);margin:.2rem 0 .35rem}.mode-left{display:flex;align-items:center;gap:.7rem}
.mode-pill{display:inline-flex;align-items:center;font-size:.64rem;font-weight:740;letter-spacing:.05em;white-space:nowrap;padding:.35rem .6rem;border-radius:7px;border:1px solid rgba(0,190,234,.35);color:#aeeef8;background:rgba(0,154,202,.08)}.mode-pill.live{color:#a5f8dc;border-color:rgba(37,230,174,.3);background:rgba(16,124,100,.12)}
.mode-note{color:#a2c0d3;font-size:.72rem;line-height:1.5}.backend-status{color:#85a7be;font-size:.67rem;text-align:right}.quick-label{color:var(--cyan);font-size:.62rem;font-weight:700;letter-spacing:.14em;text-transform:uppercase;margin:.2rem 0 .35rem}.query-strip{margin-top:.25rem}
[data-testid="stVerticalBlockBorderWrapper"]>div,[data-testid="stVerticalBlock"][data-test-scroll-behavior="normal"][style*="border"]{border-color:var(--line)!important;border-radius:var(--radius)!important;background:linear-gradient(135deg,rgba(4,27,43,.82),rgba(3,18,32,.85))}
[class*="st-key-action_"]>[data-testid="stVerticalBlock"],[class*="st-key-chart_"]>[data-testid="stVerticalBlock"],[class*="st-key-history"]>[data-testid="stVerticalBlock"],[class*="st-key-inspector"]>[data-testid="stVerticalBlock"]{gap:.7rem}
.action-grid{display:grid;grid-template-columns:minmax(0,.95fr) minmax(0,1.05fr);gap:1rem}.chat-shell,.trace-shell{border:1px solid var(--line);border-radius:15px;background:rgba(3,21,36,.8);overflow:hidden}.shell-head{display:flex;align-items:center;justify-content:space-between;gap:.6rem;padding:.85rem 1rem;border-bottom:1px solid rgba(42,140,175,.2)}.shell-title{color:#d9effb;font-size:.72rem;font-weight:720;letter-spacing:.05em}.shell-meta{color:#91b0c6;font-size:.66rem}.chat-body{padding:1rem}
.user-bubble{max-width:92%;margin-left:auto;padding:.8rem 1rem;background:rgba(0,171,218,.07);border:1px solid rgba(0,180,232,.26);border-radius:12px 12px 3px 12px;color:#e4f4fc;font-size:.87rem;line-height:1.7}.system-bubble{margin-top:.7rem;padding:.75rem .9rem;border:1px solid rgba(94,159,189,.15);border-radius:12px 12px 12px 3px;color:#a9c6d8;font-size:.78rem;line-height:1.6;background:rgba(12,39,60,.33)}
.rtl{direction:rtl;text-align:right}[dir="auto"],[dir="rtl"]{unicode-bidi:plaintext}
.evidence-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.6rem}.evidence-card{min-width:0;padding:.7rem .75rem;border:1px solid rgba(14,135,179,.32);border-radius:10px;background:linear-gradient(130deg,rgba(4,39,61,.45),rgba(3,24,40,.75));color:#b5cfe0;font-size:.74rem;line-height:1.65;overflow-wrap:anywhere}.evidence-card p{margin:.4rem 0!important;font-size:.77rem;line-height:1.7}.evidence-rank{color:#d4edfb;font-size:.73rem;font-weight:760;margin-bottom:.5rem}.evidence-source{color:#83acc4;font-size:.63rem;line-height:1.6;margin-top:.5rem;overflow-wrap:anywhere}.evidence-source a{color:#80d7eb}.evidence-chip{display:inline-flex;padding:.2rem .4rem;border:1px solid rgba(0,177,216,.2);border-radius:5px;color:#98d4e2;font-size:.63rem;margin:.15rem .15rem 0 0}
.context-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.55rem}.context-item{min-width:0;border:1px solid rgba(15,132,174,.29);border-radius:10px;padding:.7rem;font-size:.69rem;color:#96b8cd;line-height:1.55;background:rgba(3,27,44,.65)}.context-item strong,.context-item b{display:block;color:#daedf9;font-size:.8rem;margin-bottom:.16rem}
.query-context{padding:.7rem .85rem;border:1px solid rgba(21,132,168,.32);border-radius:10px;color:#acccdf;font-size:.78rem;line-height:1.75;background:rgba(4,33,51,.38);overflow-wrap:anywhere}.query-context strong{color:#e2f3ff}

/* Motion is reserved for recorded transitions and active workflow stages. */
.trace-ribbon{display:flex;align-items:flex-start;justify-content:space-between;gap:0;padding:.45rem .1rem .7rem;overflow-x:auto}
.trace-stage{flex:1 1 0;min-width:66px;text-align:center;animation:trace-reveal .38s both;animation-delay:calc(var(--step,0) * 70ms)}
.trace-dot{width:43px;height:43px;margin:0 auto .5rem;display:flex;align-items:center;justify-content:center;border:1px dashed #36718d;border-radius:50%;color:#74a1bb;background:#041725}.trace-dot svg{width:21px;height:21px}
.trace-stage.done .trace-dot,.trace-dot.done{border:1px solid #00c7ee;color:var(--green);background:radial-gradient(circle,rgba(0,196,199,.12),#052037);box-shadow:0 0 12px rgba(0,201,240,.09)}
.trace-stage.active .trace-dot,.trace-dot.active{color:var(--cyan);border:1px solid var(--cyan);animation:stage-pulse 1.8s ease-in-out infinite}
.trace-stage.waiting .trace-dot{color:#6b91aa}.trace-stage.pending .trace-dot{color:var(--amber);border:1px solid var(--amber);background:rgba(74,47,6,.22);box-shadow:0 0 20px rgba(255,184,25,.14)}.trace-stage.pending .trace-status{color:var(--amber)}
.trace-stage.human .trace-dot,.trace-stage.pending_human_approval .trace-dot,.trace-dot.human{color:var(--amber);border:1px solid var(--amber);background:rgba(74,47,6,.22);box-shadow:0 0 20px rgba(255,184,25,.14)}
.trace-stage.rejected .trace-dot{color:var(--red);border:1px solid rgba(255,102,126,.65)}
.trace-number{display:block;color:#6bdddf;font-size:.55rem;margin-bottom:.15rem}.trace-name{color:#d2e9f7;font-size:.66rem;font-weight:710;line-height:1.35}.trace-role{color:#83a5bb;font-size:.53rem;letter-spacing:.065em;text-transform:uppercase;margin-top:.2rem}.trace-status{color:#8fafc2;font-size:.56rem;line-height:1.4;margin-top:.18rem}.trace-stage.done .trace-status{color:#67d6b8}.trace-stage.active .trace-status{color:var(--cyan)}.trace-detail{color:#7498ad;font-size:.57rem;line-height:1.4;margin-top:.25rem}
.trace-connector{color:#00bde5;flex:0 0 18px;height:43px;display:flex;align-items:center;justify-content:center;opacity:.36}.trace-connector svg{width:100%;height:14px}.trace-connector.done{opacity:.82}.trace-connector.active{opacity:1}.trace-connector.active svg{stroke-dasharray:5 3;animation:connector-flow 1.2s linear infinite}
.trace-list{padding:.8rem}.trace-row{display:grid;grid-template-columns:30px 1fr auto;gap:.6rem;padding:.5rem 0}.trace-row .trace-dot{width:26px;height:26px;margin:0;font-size:.6rem}
.approval-card{border:1px solid rgba(255,194,63,.85);border-radius:12px;padding:1rem;margin:.25rem 0;background:linear-gradient(120deg,rgba(81,58,11,.4),rgba(39,31,10,.45));box-shadow:0 0 20px rgba(255,183,41,.05),inset 0 1px rgba(255,205,92,.08);animation:gate-reveal .3s ease both}
.approval-tag{display:flex;align-items:center;gap:.5rem;color:var(--amber);font-size:.73rem;letter-spacing:.06em;text-transform:uppercase;font-weight:780}.approval-tag svg{width:21px;height:21px}.approval-title{color:#fff0ca;font-size:1rem;font-weight:700;line-height:1.5;margin:.35rem 0 .7rem}
.approval-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.8rem;padding-top:.7rem;border-top:1px solid rgba(231,180,74,.23)}.approval-field{padding:.1rem .55rem .1rem 0;min-width:0}.approval-field span{display:block;color:#edca7a;font-size:.65rem;font-weight:700;margin-bottom:.28rem}.approval-field b{display:block;font-size:.74rem;font-weight:450;line-height:1.62;color:#bdd0d9;overflow-wrap:anywhere}
.policy-success{border-color:rgba(37,230,174,.43);background:linear-gradient(110deg,rgba(0,81,70,.25),rgba(3,36,38,.48));box-shadow:none}.policy-success .approval-tag,.policy-success .approval-title,.policy-success .approval-field span{color:#6ef3cd}.policy-success .approval-grid{border-top-color:rgba(37,230,174,.2)}
.metric-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.55rem;margin:.4rem 0}.metric-card{border:1px solid rgba(15,143,181,.36);border-radius:10px;background:linear-gradient(135deg,rgba(5,35,53,.74),rgba(3,23,36,.65));padding:.68rem .65rem;min-width:0}.metric-name{color:#d4e8f5;font-size:.66rem;font-weight:650;line-height:1.45}.metric-values{display:flex;align-items:center;flex-wrap:wrap;gap:.35rem;margin:.5rem 0 .35rem}.metric-before{color:#a6c6dc;font-size:.9rem}.metric-arrow{color:#6a9eb6;font-size:.8rem}.metric-after{color:#f2f9ff;font-size:1rem;font-weight:730;animation:metric-reveal .4s ease both}.metric-delta{color:#90aabc;font-size:.67rem;border-radius:5px;padding:.15rem .25rem;display:inline-block}.metric-delta.good{color:var(--green);background:rgba(0,141,108,.15)}.metric-delta.bad{color:#ff8496;background:rgba(168,51,77,.1)}.metric-delta.neutral{color:#87a6b9}
.verdict{display:flex;justify-content:space-between;align-items:center;gap:1rem;border:1px solid rgba(65,135,163,.35);border-radius:12px;background:rgba(9,34,50,.6);padding:.85rem 1rem;margin:.35rem 0}.verdict h3{font-size:1.12rem!important;font-weight:780;margin:0!important;line-height:1.25}.verdict p{color:#a0becf;font-size:.69rem;margin:0;line-height:1.55;text-align:right}.verdict-icon{display:flex;align-items:center;justify-content:center;width:40px;height:40px;flex:none}.verdict-icon svg{width:32px;height:32px}.verdict.improved{color:#65f7d0;border-color:rgba(37,230,174,.72);background:linear-gradient(105deg,rgba(0,90,69,.25),rgba(1,30,32,.75))}.verdict.worse{color:var(--red);border-color:rgba(255,102,126,.5);background:rgba(84,19,38,.23)}.verdict.same{color:#d2e8f5}.verdict.pending{color:var(--amber);border-color:rgba(255,195,74,.4)}
.inspection-summary{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.55rem;color:#a3c0d1;font-size:.73rem;line-height:1.7}.inspection-summary>div{padding:.55rem .7rem;border:1px solid rgba(43,133,167,.22);border-radius:8px;background:rgba(6,29,45,.6);overflow-wrap:anywhere}.inspection-summary b{color:#d6eaf7}

/* Dashboard: no decorative charts or invented trends. */
.kpi-grid{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:.6rem;margin:.15rem 0 .35rem}
.kpi{display:flex;align-items:center;gap:.75rem;position:relative;min-height:105px;padding:.95rem .95rem .8rem;border:1px solid rgba(0,164,220,.48);border-radius:12px;background:linear-gradient(125deg,rgba(2,38,60,.76),rgba(4,24,42,.92));overflow:hidden}
.kpi-copy{min-width:0}.kpi .label{color:#a9d9ed;font-size:.56rem;line-height:1.5;font-weight:650;letter-spacing:.08em;text-transform:uppercase}.kpi .value{color:#f5faff;font-size:1.8rem;font-weight:770;letter-spacing:-.04em;line-height:1.2;margin:.3rem 0 .13rem}.kpi .sub{color:#99bbd1;font-size:.62rem;line-height:1.4}
.kpi-icon{color:var(--cyan);display:flex;align-items:center;justify-content:center;width:40px;height:45px;flex:none;border:1px solid rgba(0,182,232,.35);border-radius:10px;background:rgba(0,102,153,.11)}.kpi-icon svg{width:24px;height:24px}.kpi:nth-child(3) .kpi-icon{color:var(--red);border-color:rgba(255,102,126,.35)}.kpi:nth-child(4) .kpi-icon,.kpi:nth-child(5) .kpi-icon{color:var(--green);border-color:rgba(37,230,174,.35)}.kpi:nth-child(6) .kpi-icon{color:var(--purple);border-color:rgba(167,139,250,.4)}
.dashboard-aside{max-width:390px;text-align:right;color:#8eafc4;font-size:.7rem;line-height:1.6}.chart-title,.chart-card-title{color:#eef6ff;font-size:.94rem;font-weight:740;line-height:1.4;margin:0 0 .08rem;letter-spacing:-.02em}.chart-subtitle,.chart-card-sub{color:#92b3c9;font-size:.67rem;line-height:1.5;margin:0;min-height:1.05rem}
[data-testid="stPlotlyChart"]{overflow:hidden;border-radius:8px;background:transparent}[data-testid="stDataFrame"]{border:1px solid rgba(34,135,170,.28);border-radius:9px;overflow:hidden}.run-history-head{display:flex;align-items:flex-end;justify-content:space-between;gap:1rem;margin-top:.5rem}.run-history-head .hint{color:#89aabd;font-size:.68rem}

/* Architecture: system components and functional agents are distinct. */
.arch-board{position:relative;padding:1.25rem 1.35rem;border:1px solid rgba(0,170,218,.4);border-radius:20px;background:radial-gradient(ellipse at 50% 25%,rgba(0,91,144,.08),transparent 70%),linear-gradient(140deg,rgba(2,26,41,.93),rgba(3,14,26,.95));overflow:hidden}
.arch-section-label{color:var(--cyan);font-size:.67rem;letter-spacing:.19em;text-transform:uppercase;text-align:center;font-weight:700;margin:0 0 .85rem}
.arch-main{display:flex;align-items:stretch;justify-content:center;gap:0}.arch-node2{position:relative;flex:1;min-width:0;max-width:220px;min-height:162px;padding:1.05rem .85rem .75rem;border:1px solid rgba(0,171,223,.6);border-radius:12px;background:linear-gradient(135deg,rgba(0,53,91,.55),rgba(5,25,43,.8));text-align:center;transition:border-color .18s,transform .18s}.arch-node2:hover{transform:translateY(-2px);border-color:var(--cyan)}
.arch-node2.system{border-color:rgba(59,150,197,.5);background:linear-gradient(135deg,rgba(4,49,78,.6),rgba(4,24,41,.8))}.arch-node2.gate,.arch-node2.human{border-color:rgba(255,195,74,.85);background:linear-gradient(140deg,rgba(80,53,13,.54),rgba(35,26,17,.82))}
.arch-kind{color:#73def0;font-size:.56rem;font-weight:730;letter-spacing:.1em;text-transform:uppercase;line-height:1.5}.arch-node2.gate .arch-kind,.arch-node2.human .arch-kind{color:var(--amber)}.arch-node2 h4{font-size:.88rem!important;line-height:1.35;margin:.5rem 0!important;color:#ecf7ff;font-weight:750}.arch-node2 p{font-size:.69rem;line-height:1.55;color:#a5c8db;margin:0}
.arch-node-icon{color:var(--cyan);margin:.5rem auto}.arch-node-icon svg{width:29px;height:29px}.arch-node2.gate .arch-node-icon,.arch-node2.human .arch-node-icon{color:var(--amber)}
.arch-arrow{position:relative;flex:0 0 35px;min-height:24px;display:flex;justify-content:center;align-items:center;color:var(--cyan)}.arch-arrow:before{content:"";width:26px;border-top:1px dashed var(--cyan);opacity:.7}.arch-arrow:after{content:"";width:6px;height:6px;border-top:2px solid var(--cyan);border-right:2px solid var(--cyan);transform:rotate(45deg);position:absolute;right:3px}.arch-arrow svg{display:none}
.arch-risk-flow{display:flex;align-items:stretch;justify-content:center;gap:0;margin-top:1rem}.arch-branches{flex:1.6;display:grid;grid-template-columns:1fr 1fr;gap:.7rem;min-width:0}.arch-branch{min-width:0;border:1px solid rgba(37,230,174,.35);border-radius:11px;padding:.75rem;background:rgba(2,63,53,.2)}.arch-branch.high{border-color:rgba(255,195,74,.56);background:rgba(76,49,12,.22)}
.arch-branches h4{font-size:.79rem!important;margin:.35rem 0!important}.arch-branches p{color:#a8c6d9;font-size:.69rem;line-height:1.5;margin:0}.arch-branches .arch-kind,.branch-label{color:var(--green);font-size:.6rem;font-weight:700;letter-spacing:.07em}.arch-branch.high .arch-kind,.arch-branch.high .branch-label{color:var(--amber)}
.arch-feedback{margin:1rem auto 0;padding:.55rem 1rem;max-width:850px;color:#a1bfce;text-align:center;font-size:.71rem;line-height:1.6;border:1px dashed rgba(0,194,226,.38);border-radius:25px}.arch-feedback span{color:var(--cyan)}
.arch-lower{display:flex;gap:.7rem;margin-top:1rem}.impact-card,.human-card,.executor-card,.validation-card{flex:1;border:1px solid var(--line);border-radius:11px;padding:.8rem;background:rgba(4,29,45,.6)}.human-card{border-color:rgba(255,195,74,.5);background:rgba(62,42,13,.24)}.lower-k{color:var(--cyan);font-size:.56rem;text-transform:uppercase;letter-spacing:.1em}.human-card .lower-k{color:var(--amber)}.lower-title{color:#e2f0fa;font-size:.82rem;font-weight:730;margin:.3rem 0}.lower-copy{color:#a2c0d2;font-size:.72rem;line-height:1.6}.branch-labels{display:flex;gap:2rem;justify-content:center;color:#80aec5;font-size:.6rem;margin-top:.5rem}

/* Team illustrations are explicitly visual placeholders. */
.team-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1.2rem;margin:.2rem 0 .5rem}.team-card{--team-accent:var(--cyan);display:flex;flex-direction:column;min-width:0;border:1px solid var(--team-accent);border-radius:16px;overflow:hidden;background:linear-gradient(155deg,rgba(4,39,59,.74),rgba(3,23,37,.96));transition:transform .2s,box-shadow .2s;color:inherit!important;text-decoration:none!important}.team-card.theme-teal{--team-accent:#14dbc7}.team-card.theme-violet{--team-accent:#9b7df7;background:linear-gradient(155deg,rgba(29,22,74,.6),rgba(8,20,45,.96))}.team-card.theme-amber{--team-accent:#efc267}.team-card:hover{transform:translateY(-3px);box-shadow:0 12px 30px rgba(0,0,0,.22)}
.avatar-wrap{position:relative;height:auto;aspect-ratio:4/3;min-height:210px;display:flex;align-items:center;justify-content:center;background:radial-gradient(ellipse at 50% 60%,rgba(0,195,234,.12),transparent 70%);overflow:hidden}.svg-avatar{display:block;width:100%;height:100%;object-fit:cover}.avatar-caption{color:#82aabd;font-size:.58rem;line-height:1.4;margin:.45rem 1.05rem 0;letter-spacing:.02em}.team-copy{display:flex;flex-direction:column;flex:1;padding:.85rem 1.15rem 1.1rem}
.team-stage{color:var(--team-accent);font-size:.58rem;letter-spacing:.14em;line-height:1.6;text-transform:uppercase}.avatar-wrap .team-stage{position:absolute;z-index:1;top:1rem;left:1rem;max-width:115px}
.team-name{color:#f4faff;font-size:1.55rem;font-weight:780;line-height:1.2;letter-spacing:-.04em;margin:.35rem 0 .45rem}.team-verb{color:var(--team-accent);font-size:.85rem;font-weight:650}.team-role{color:var(--team-accent);font-size:.89rem;line-height:1.45;font-weight:650}.team-description{color:#b1cddd;font-size:.79rem;line-height:1.65;margin:.65rem 0 1rem;flex:1}
.team-link{display:flex;align-items:center;justify-content:center;gap:.6rem;margin-top:auto;border:1px solid rgba(54,174,220,.6);border-radius:10px;padding:.58rem .7rem;color:#daf0fc!important;font-size:.8rem;font-weight:650;text-decoration:none!important;background:rgba(2,26,46,.7)}.team-link svg{width:18px;height:18px;color:var(--cyan)}.team-link:hover{background:rgba(0,144,203,.12)}
.stack-strip{display:flex;align-items:center;justify-content:space-between;gap:1.5rem;padding:1.1rem 1.5rem;border:1px solid rgba(14,150,190,.38);border-radius:15px;background:rgba(3,26,42,.75)}.stack-items{display:flex;flex-wrap:wrap;gap:.45rem}.stack-item{display:flex;flex-direction:column;align-items:center;gap:.55rem;border:1px solid rgba(35,133,175,.23);border-radius:11px;padding:.8rem .85rem;color:#b9d5e6;font-size:.7rem;background:rgba(4,35,55,.4)}.stack-item svg{color:var(--cyan);width:25px;height:25px}

/* Native Streamlit controls. */
[data-testid="stButton"]>button,[data-testid="stDownloadButton"]>button{min-height:39px;width:100%;padding:.45rem .7rem;border:1px solid rgba(41,147,188,.49);border-radius:10px;color:#cce6f6;background:linear-gradient(130deg,rgba(3,32,53,.8),rgba(4,24,39,.82));font-size:.77rem;font-weight:590;transition:border-color .18s,background .18s,transform .18s}
[data-testid="stButton"]>button p{font-size:.76rem;line-height:1.25}[data-testid="stButton"]>button:hover,[data-testid="stDownloadButton"]>button:hover{border-color:var(--cyan);color:#fff;background:rgba(0,115,156,.18);transform:translateY(-1px)}
[data-testid="stButton"]>button[kind="primary"]{color:#001723;border-color:#3ce4f9;font-weight:750;background:linear-gradient(110deg,#00dceb,#11afea);box-shadow:0 0 18px rgba(0,197,231,.09)}[data-testid="stButton"]>button[kind="primary"]:hover{color:#00131f;background:linear-gradient(110deg,#35e7ef,#1ac2f8)}[data-testid="stButton"]>button:disabled{color:#7093a8;border-color:rgba(68,123,147,.24);background:rgba(10,37,52,.38);opacity:.65;transform:none;box-shadow:none}
[data-testid="stTextInput"] input,[data-testid="stTextArea"] textarea{background:#041828!important;color:#e2f2fb!important;border:0!important;border-radius:9px!important;font-size:.8rem!important;line-height:1.65!important}
[data-testid="stTextInput"] [data-baseweb="input"],[data-testid="stTextArea"] [data-baseweb="textarea"]{background:#041828!important;border:1px solid rgba(39,136,174,.44)!important;border-radius:10px!important}
[data-testid="stTextArea"] textarea{unicode-bidi:plaintext;text-align:start;padding:.8rem!important}.st-key-query_input textarea{min-height:94px;font-size:.95rem!important}
[data-testid="stTextInput"] input::placeholder,[data-testid="stTextArea"] textarea::placeholder{color:#6e93aa!important;opacity:1}
[data-testid="stSelectbox"] [data-baseweb="select"]>div{border-color:rgba(36,137,174,.43)!important;border-radius:9px!important;background:#051c2d!important;color:#c8e3f5!important;min-height:38px;font-size:.77rem}
[data-testid="stWidgetLabel"] p{color:#a7c5d8;font-size:.72rem}
[data-testid="stRadio"] [role="radiogroup"]{gap:.6rem}[data-testid="stRadio"] label{border:1px solid rgba(37,147,187,.35);border-radius:10px;padding:.3rem .7rem;background:rgba(3,29,48,.64)}[data-testid="stRadio"] label:has(input:checked){color:var(--cyan);border-color:#00b9e4;background:rgba(0,121,177,.2)}[data-testid="stRadio"] label p{font-size:.77rem}
[data-testid="stExpander"]{border:1px solid rgba(26,128,167,.29)!important;border-radius:10px!important;background:rgba(3,27,44,.65)!important;overflow:hidden}[data-testid="stExpander"] summary{color:#c8e4f5;font-size:.77rem;min-height:43px}[data-testid="stExpander"] summary:hover{color:var(--cyan)}
[data-testid="stTabs"] [role="tablist"]{gap:.4rem;border-bottom-color:rgba(41,144,181,.25)}[data-testid="stTabs"] [role="tab"]{padding:.5rem .75rem;color:#9abed4;font-size:.76rem}[data-testid="stTabs"] [role="tab"][aria-selected="true"]{color:var(--cyan);background:rgba(0,150,201,.06)}
[data-testid="stAlert"]{background:rgba(5,40,60,.65);border:1px solid rgba(41,150,190,.3);color:#accdde;border-radius:10px}[data-testid="stAlert"] p{font-size:.77rem}
[data-testid="stCode"],[data-testid="stJson"]{background:rgba(1,14,25,.75)!important;border:1px solid rgba(24,128,165,.23);border-radius:10px}[data-testid="stCode"] code{font-size:.72rem!important;line-height:1.7!important}[data-testid="stCaptionContainer"]{color:#86a9bf;font-size:.67rem}
.setup-panel{padding:1rem;border:1px solid rgba(0,169,208,.31);border-radius:12px;background:rgba(4,30,47,.7)}.setup-title{color:#e0f1fb;font-size:1rem;font-weight:700;margin-bottom:.35rem}.setup-copy{color:#9cbdd0;font-size:.77rem;line-height:1.65}

/* Additional app composition, evidence and policy panels. */
.hero-stat{flex-direction:row;align-items:center;justify-content:flex-start;gap:1rem}.hero-stat>svg{flex:none;width:30px;height:30px}.hero-stat span{display:block}
.hero-evidence-note{display:flex;align-items:center;gap:.45rem;color:#779fb6;font-size:.63rem;line-height:1.6;margin-top:.85rem}.hero-evidence-note svg{color:#6cbbd1;flex:none}
.hero-visual{min-width:0}.panel-heading>small{font-weight:450;letter-spacing:0;margin-left:auto;color:#81a8c0;font-size:.62rem;text-align:right}
.source-note,.trace-source{display:flex;align-items:center;gap:.4rem;color:#87b0c6;font-size:.65rem;line-height:1.6}.source-note svg{color:#64c9dd}.trace-source{padding:.3rem .2rem .6rem;border-bottom:1px solid rgba(34,138,169,.18)}
.panel-divider{height:1px;background:linear-gradient(90deg,rgba(34,152,190,.28),rgba(34,152,190,.06));margin:.35rem -.5rem}
.policy-banner{display:flex;align-items:center;gap:.7rem;border:1px solid rgba(41,141,175,.35);border-radius:10px;background:rgba(4,34,50,.64);padding:.75rem .85rem;margin:.15rem 0;color:#9ec5d9;animation:gate-reveal .3s ease both}
.policy-banner>svg{width:24px;height:24px;flex:none;color:#70c5df}.policy-banner b{display:block;color:#cde6f4;font-size:.77rem;font-weight:700;line-height:1.5}.policy-banner span{display:block;color:#91b2c7;font-size:.69rem;line-height:1.55;margin-top:.15rem}
.policy-banner.auto,.policy-banner.approved{border-color:rgba(37,230,174,.4);background:linear-gradient(110deg,rgba(0,75,58,.22),rgba(3,35,39,.65))}.policy-banner.auto b,.policy-banner.auto>svg,.policy-banner.approved b,.policy-banner.approved>svg{color:#56e9c4}
.policy-banner.pending{border-color:rgba(255,195,74,.7);background:rgba(76,49,12,.25)}.policy-banner.pending b,.policy-banner.pending>svg{color:var(--amber)}
.policy-banner.rejected{border-color:rgba(255,102,126,.4);background:rgba(71,20,40,.2)}.policy-banner.rejected b,.policy-banner.rejected>svg{color:#ff91a2}
.evidence-title{color:#c9e0ef;font-size:.76rem;line-height:1.7;min-height:2.4rem}.evidence-relevance{display:flex;gap:.35rem;align-items:center;margin-top:.6rem;color:#8daec2;font-size:.64rem;line-height:1.45}.evidence-relevance i{width:6px;height:6px;flex:none;border-radius:50%;background:#7c9baf}.evidence-relevance.good{color:#96d7c6}.evidence-relevance.good i{background:var(--green)}.evidence-relevance.bad{color:#a9c0d1}.evidence-relevance.bad i{background:var(--red)}.evidence-content{white-space:pre-wrap;overflow-wrap:anywhere;font-size:.81rem;color:#b2cddd;line-height:1.8;padding:.5rem .2rem}
.context-platform{display:flex;align-items:center;gap:.8rem}.context-platform>svg{color:var(--cyan);flex:none}.context-platform small{display:block;color:#8dadc2;font-size:.68rem}.context-item small,.query-context>small{color:#8fb5cc;font-size:.63rem;line-height:1.5}.query-context p{margin:.3rem 0 0!important}.query-context>small{letter-spacing:.08em}
.st-key-query_text textarea{min-height:94px;font-size:.95rem!important;unicode-bidi:plaintext;text-align:start}
.approval-field small{display:block;color:#b5bdad;font-size:.64rem;line-height:1.55;margin-top:.4rem}.verdict{justify-content:flex-start}.verdict p{text-align:left;margin-top:.25rem}.verdict>div{flex:1}
.failure-response span{color:var(--card-accent);font-size:.7rem;font-weight:650}.failure-response p{font-size:.72rem}
.arch-node2{display:flex;flex-direction:column;align-items:center}.arch-node2 .arch-kind{margin-top:auto;padding-top:.7rem}.arch-node2 .arch-node-icon{display:block}
.arch-node2.theme-violet{border-color:rgba(161,122,249,.72);background:linear-gradient(145deg,rgba(57,33,111,.47),rgba(16,24,50,.7))}.arch-node2.theme-violet .arch-node-icon,.arch-node2.theme-violet .arch-kind{color:var(--purple)}
.arch-node2.theme-teal{border-color:rgba(37,230,174,.56);background:linear-gradient(145deg,rgba(0,87,66,.3),rgba(3,35,40,.7))}.arch-node2.theme-teal .arch-node-icon,.arch-node2.theme-teal .arch-kind{color:var(--green)}
.arch-node2.theme-amber{border-color:rgba(255,195,74,.8);background:linear-gradient(145deg,rgba(76,50,13,.57),rgba(37,28,17,.85))}.arch-node2.theme-amber .arch-node-icon,.arch-node2.theme-amber .arch-kind{color:var(--amber)}
.arch-bridge{display:flex;align-items:center;justify-content:center;gap:.65rem;margin:.75rem auto 0;color:#8ebdd2;font-size:.62rem;line-height:1.5}.arch-bridge-arrow{color:var(--cyan);transform:rotate(90deg)}
.arch-branch{display:flex;flex-direction:column;justify-content:center}.arch-branch b{color:#a9efdf;font-size:.75rem;line-height:1.5;margin:.55rem 0}.arch-branch.high b{color:#ffda86}.arch-branch b svg{margin-right:.2rem}.arch-branch small{display:block;color:#a8b7bb;font-size:.62rem;line-height:1.6;margin-top:.4rem}.arch-branch p{font-size:.64rem;overflow-wrap:anywhere}.arch-feedback>svg{color:var(--cyan);margin-right:.5rem}.arch-feedback small{display:block;color:#87a8bb;font-size:.62rem;margin-top:.2rem}
.state-code{padding:.8rem;border:1px solid rgba(17,135,176,.3);border-radius:10px;background:rgba(1,14,26,.6)}.state-code>div{display:flex;gap:.5rem;justify-content:space-between;align-items:baseline;padding:.18rem 0;line-height:1.5}.state-code code{color:#29d8d9;background:none;font-size:.64rem;padding:0}.state-code span{color:#9dc1d5;font-size:.62rem;text-align:right}
.control-policy-grid{display:grid;grid-template-columns:1fr 1fr;gap:.7rem}.control-policy-grid>div{border:1px solid rgba(20,156,191,.4);border-radius:10px;background:rgba(1,49,62,.22);padding:.8rem}.control-policy-grid .policy-high{border-color:rgba(255,195,74,.55);background:rgba(65,47,16,.28)}.policy-high .section-kicker{color:var(--amber)}.control-policy-grid b{display:block;font-size:.75rem;color:#d8e8f2;line-height:1.5;margin-top:.6rem}.control-policy-grid p{font-size:.66rem;color:#9ebed0;margin:.3rem 0!important;line-height:1.55}.policy-high>span{display:block;color:#ffd789;font-size:.65rem;border:1px solid rgba(236,180,65,.35);border-radius:6px;padding:.35rem .4rem;margin-top:.6rem;text-align:center}
.stack-panel{display:flex;align-items:center;justify-content:space-between;gap:1rem;padding:.1rem .3rem}.stack-panel .section-title{font-size:1.55rem}.stack-panel .section-copy{font-size:.76rem;margin:0}.stack-items>div{display:flex;flex-direction:column;align-items:center;gap:.65rem;padding:.85rem .8rem;border:1px solid rgba(28,121,158,.24);border-radius:10px;background:rgba(4,32,53,.5);color:#c2deee;font-size:.67rem}.stack-items>div svg{color:var(--cyan)}
.team-name{font-size:1.55rem!important;margin:.35rem 0 .45rem!important;padding:0!important}.team-description{font-size:.79rem!important;line-height:1.65!important}.team-link.unavailable{color:#799cad!important;border-color:rgba(75,134,163,.28)}
.empty-state.compact{min-height:80px;font-size:.73rem}

@keyframes stage-pulse{0%,100%{box-shadow:0 0 0 0 rgba(0,216,244,.16)}50%{box-shadow:0 0 0 5px rgba(0,216,244,.015),0 0 18px rgba(0,216,244,.12)}}
@keyframes connector-flow{to{stroke-dashoffset:-16}}
@keyframes trace-reveal{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:translateY(0)}}
@keyframes gate-reveal{from{opacity:.5;transform:translateY(4px)}to{opacity:1;transform:translateY(0)}}
@keyframes metric-reveal{from{opacity:.4}to{opacity:1}}

@media(min-width:1550px){.nav-links a{padding:.68rem 1.4rem}.hero-grid{min-height:535px}.hero-copy{max-width:600px}}
@media(max-width:1350px){
  .ragops-nav{grid-template-columns:minmax(180px,1fr) auto minmax(135px,1fr);gap:.7rem}.brand-name{font-size:1.22rem}.brand-mark{width:36px;height:36px}.nav-links a{gap:.4rem;padding:.58rem .75rem;font-size:.74rem}.nav-status{padding-left:.65rem;gap:.45rem}.status-copy{font-size:.6rem}.status-note{font-size:.57rem}
  .hero-grid{min-height:480px}.hero-left{padding-left:.2rem}.hero-title{font-size:clamp(3.3rem,5.3vw,4.5rem)!important}.hero-subtitle{font-size:1.35rem}.hero-tagline{font-size:.88rem;letter-spacing:.1em}.hero-copy{font-size:.81rem}.hero-btn{font-size:.77rem;padding:.7rem 1rem}.hero-stat{padding:.1rem .75rem}.hero-stat b{font-size:1.05rem}
  .kpi{padding:.8rem .7rem;gap:.5rem}.kpi .value{font-size:1.6rem}.kpi-icon{width:31px;height:37px}.kpi-icon svg{width:20px;height:20px}
  .trace-stage{min-width:62px}.trace-connector{flex-basis:10px}.trace-name{font-size:.6rem}.trace-detail{display:none}.evidence-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
  .team-grid{gap:.85rem}.team-copy{padding:.8rem .85rem 1rem}.team-name{font-size:1.4rem}.team-role{font-size:.8rem}.team-description{font-size:.73rem}.avatar-wrap{min-height:180px}
  .arch-node2{padding:.85rem .6rem}.arch-arrow{flex-basis:24px}.arch-arrow:before{width:18px}.arch-arrow:after{right:1px}
}
@media(max-width:1100px){
  [data-testid="stAppViewBlockContainer"],.block-container{padding-right:1.25rem!important;padding-left:1.25rem!important}.ragops-nav-shell{margin-right:-1.25rem;margin-left:-1.25rem;padding:.7rem 1rem}.ragops-nav{grid-template-columns:auto 1fr}.nav-links{justify-self:end}.nav-status{display:none}
  .hero-grid{grid-template-columns:1fr 1fr;min-height:425px;gap:0;padding:.4rem 0}.hero-title{font-size:3.45rem!important;white-space:normal}.hero-subtitle{font-size:1.18rem}.hero-tagline{font-size:.78rem}.hero-copy{font-size:.78rem}.hero-actions{gap:.55rem}.hero-btn{padding:.7rem .8rem;font-size:.72rem;min-height:42px}
  .kpi-grid{grid-template-columns:repeat(3,minmax(0,1fr))}.kpi{min-height:97px}.kpi .label{font-size:.61rem}.context-grid,.metric-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.trace-ribbon{justify-content:flex-start;padding-bottom:.85rem}.trace-stage{flex:0 0 66px}.trace-connector{flex:0 0 12px}.approval-grid{gap:.6rem}
  .arch-risk-flow{flex-wrap:wrap;gap:.6rem}.arch-risk-flow .arch-arrow{display:none}.arch-risk-flow .arch-node2{max-width:none;flex-basis:20%}.arch-branches{flex-basis:50%}.team-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.avatar-wrap{aspect-ratio:4/2.8;min-height:0}.team-description{font-size:.82rem}.team-copy{padding:1rem 1.2rem}.stack-strip,.stack-panel{align-items:flex-start;flex-direction:column}
}
@media(max-width:800px){
  .ragops-nav{display:flex;flex-wrap:wrap;gap:.5rem}.brand-wrap{flex:1}.brand-name{font-size:1.2rem}.nav-links{order:3;width:100%;justify-content:space-between;overflow-x:auto;border-radius:11px;gap:1px}.nav-links a{flex:1;padding:.5rem .55rem;font-size:.69rem;gap:.35rem;border-radius:8px}.nav-links a svg{width:14px;height:14px}.nav-status{display:flex;width:11rem;height:2.5rem;border:0}.ragops-nav-shell{border-radius:0 0 17px 17px}
  .hero-grid{grid-template-columns:1fr;gap:0;padding:1rem .4rem 0}.hero-left{padding:0}.hero-title{font-size:clamp(3.4rem,8.5vw,4.7rem)!important;white-space:nowrap}.hero-subtitle{font-size:1.5rem}.hero-tagline{font-size:.95rem;letter-spacing:.13em}.hero-copy{font-size:.89rem;max-width:none}.hero-actions{margin-top:1.1rem}.hero-btn{font-size:.81rem;padding:.8rem 1.2rem}.control-loop-svg{max-width:560px}
  .hero-statbar{margin-top:0}.hero-stat{padding:.1rem .7rem}.hero-stat span{font-size:.64rem}.hero-stat b{font-size:1.05rem}.failure-grid{grid-template-columns:1fr;gap:.7rem}.failure-card{padding:1rem}.failure-response{margin-top:.65rem}
  .page-heading{padding:.8rem .2rem .25rem}.page-title{font-size:2.2rem}.page-subtitle{font-size:.83rem}.action-grid{grid-template-columns:1fr}
  [data-testid="stHorizontalBlock"]{flex-wrap:wrap}[data-testid="stHorizontalBlock"]>[data-testid="stColumn"]{width:100%!important;flex:1 1 100%!important;min-width:0!important}
  .trace-stage{flex:1;min-width:68px}.trace-connector{flex:0 0 17px}.metric-grid{grid-template-columns:repeat(3,minmax(0,1fr))}.evidence-grid{grid-template-columns:repeat(4,minmax(0,1fr))}.mode-banner{align-items:flex-start}.mode-left{align-items:flex-start}.mode-note{font-size:.68rem}.backend-status{display:none}
  .arch-board{padding:1rem}.arch-main{flex-wrap:wrap;gap:.65rem}.arch-main .arch-node2{min-width:150px;max-width:none;min-height:148px}.arch-main .arch-arrow{display:none}.arch-branches{flex:1 1 100%}.arch-risk-flow .arch-node2{flex:1 1 25%}.arch-node2 p{font-size:.72rem}.arch-lower{flex-wrap:wrap}.arch-lower>div{flex:1 1 45%}.page-footer{flex-direction:column;text-align:center;gap:.5rem}
}
@media(max-width:520px){
  [data-testid="stAppViewBlockContainer"],.block-container{padding-right:.75rem!important;padding-left:.75rem!important}.ragops-nav-shell{margin-left:-.75rem;margin-right:-.75rem;padding:.65rem .75rem}.nav-links{justify-content:flex-start}.nav-links a{flex:0 0 auto;padding:.52rem .62rem;font-size:.64rem}.nav-links a svg{display:none}.brand-mark{width:31px;height:31px}.brand-name{font-size:1.14rem}.nav-status{width:9rem;height:2.25rem}.status-copy{font-size:.56rem}.status-note{font-size:.52rem}
  .hero-grid{padding:.8rem .1rem 0}.hero-title{font-size:clamp(2.7rem,10vw,3.5rem)!important}.eyebrow,.section-kicker{font-size:.55rem;letter-spacing:.2em}.hero-subtitle{font-size:1.18rem}.hero-tagline{font-size:.78rem;letter-spacing:.08em}.hero-copy{font-size:.81rem}.hero-actions{gap:.5rem}.hero-btn{padding:.68rem .75rem;font-size:.7rem}
  .hero-statbar{grid-template-columns:repeat(2,minmax(0,1fr));row-gap:.8rem;padding:.8rem .5rem}.hero-stat:nth-child(2){border-right:0}.hero-stat:nth-child(n+3){border-top:1px solid rgba(72,158,187,.17);padding-top:.65rem}.page-title{font-size:1.85rem}.section-title{font-size:1.6rem}.page-subtitle{font-size:.77rem}
  .kpi-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:.5rem}.kpi .value{font-size:1.5rem}.kpi .sub{font-size:.6rem}.evidence-grid,.metric-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.approval-grid{grid-template-columns:1fr}.approval-card{padding:.85rem}.approval-title{font-size:.9rem}.verdict{flex-direction:column;align-items:flex-start;gap:.35rem}.verdict p{text-align:left}.trace-stage{flex:0 0 65px;min-width:65px}.trace-connector{flex-basis:13px}.mode-left{flex-direction:column;gap:.4rem}
  .team-grid{grid-template-columns:1fr;gap:1rem}.team-copy{padding:.9rem 1.1rem 1.1rem}.avatar-wrap{aspect-ratio:4/2.75}.team-name{font-size:1.65rem}.team-role{font-size:.93rem}.inspection-summary{grid-template-columns:1fr}.arch-main .arch-node2{min-width:120px}.arch-risk-flow .arch-node2{flex-basis:100%}.arch-branches,.control-policy-grid{grid-template-columns:1fr}.arch-feedback{border-radius:12px;font-size:.65rem}.arch-lower{flex-direction:column}.branch-labels{gap:1rem;font-size:.52rem}.stack-strip{padding:1rem}.stack-items{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));width:100%}.stack-item{padding:.7rem .5rem}.hero-stat{gap:.65rem}.hero-stat>svg{width:25px;height:25px}.state-code>div{flex-direction:column;gap:0}.state-code span{text-align:left}
}
/* Browser-verified sizing: override native Markdown heading padding and faces. */
[data-testid="stVerticalBlock"]:is(.st-key-action_query,.st-key-action_results,.st-key-overview_failures,.st-key-history,.st-key-inspector,.st-key-team_stack,[class*="st-key-chart_"]),
[data-testid="stVerticalBlock"]:has(>[data-testid="stElementContainer"] .panel-heading){border-color:rgba(0,162,209,.36)!important;border-radius:15px!important;background:linear-gradient(125deg,rgba(3,28,44,.79),rgba(3,18,31,.86));box-shadow:inset 0 1px rgba(112,213,244,.025);padding:1rem!important}
[data-testid="stMarkdownContainer"]{font-family:"Segoe UI",Arial,sans-serif}
[data-testid="stMarkdownContainer"] h1.page-title{font-family:inherit;font-size:clamp(2rem,3.5vw,3.65rem)!important;font-weight:780!important;line-height:1.13!important;letter-spacing:-.045em!important;margin:.5rem 0 .5rem!important;padding:0!important}
[data-testid="stMarkdownContainer"] h2.section-title{font-family:inherit;font-size:clamp(1.55rem,2.05vw,2rem)!important;line-height:1.2!important;margin:0 0 .55rem!important;padding:0!important}
[data-testid="stMarkdownContainer"] h1.hero-title{padding:0!important;font-family:inherit}
[data-testid="stMarkdownContainer"] .page-subtitle{font-size:1.03rem!important;line-height:1.65!important;margin:.45rem 0 .45rem!important}
[data-testid="stMarkdownContainer"] .section-copy{font-size:.88rem!important}
[data-testid="stMarkdownContainer"] .hero-copy{font-size:1rem!important;line-height:1.72!important}
.brand-name{font-size:1.5rem;letter-spacing:-.055em}.nav-links a{font-size:.84rem;font-weight:550}.nav-status .status-copy{font-size:.69rem}.status-note{font-size:.63rem}
.page-heading{padding-top:1rem;padding-bottom:.2rem}.page-heading:after{top:0;right:-2rem;width:60%;height:185px;border:0;transform:none;border-radius:0;opacity:.36;background-image:url("data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%221000%22%20height%3D%22280%22%20viewBox%3D%220%200%201000%20280%22%3E%3Cdefs%3E%3Cpattern%20id%3D%22dots%22%20width%3D%229%22%20height%3D%229%22%20patternUnits%3D%22userSpaceOnUse%22%3E%3Ccircle%20cx%3D%221%22%20cy%3D%221%22%20r%3D%22.8%22%20fill%3D%22%2306bcef%22%2F%3E%3C%2Fpattern%3E%3Cmask%20id%3D%22wave%22%3E%3Cg%20fill%3D%22none%22%20stroke%3D%22white%22%3E%3Cpath%20d%3D%22M-20%20200%20C100%2080%20235%20250%20375%20135%20S590%2055%20740%20110%20S880%2020%201030%2035%22%20stroke-width%3D%2280%22%2F%3E%3Cpath%20d%3D%22M-20%20235%20C170%20115%20235%20265%20435%20160%20S650%20180%20800%2080%20S940%20110%201040%2040%22%20stroke-width%3D%2245%22%2F%3E%3C%2Fg%3E%3C%2Fmask%3E%3ClinearGradient%20id%3D%22fade%22%3E%3Cstop%20stop-color%3D%22%23042338%22%20stop-opacity%3D%220%22%2F%3E%3Cstop%20offset%3D%22.3%22%20stop-color%3D%22%230582b4%22%2F%3E%3Cstop%20offset%3D%221%22%20stop-color%3D%22%2306bcef%22%2F%3E%3C%2FlinearGradient%3E%3C%2Fdefs%3E%3Crect%20width%3D%221000%22%20height%3D%22280%22%20fill%3D%22url(%23dots)%22%20mask%3D%22url(%23wave)%22%20opacity%3D%22.65%22%2F%3E%3Cg%20fill%3D%22none%22%20stroke%3D%22url(%23fade)%22%20stroke-width%3D%22.7%22%20opacity%3D%22.6%22%3E%3Cpath%20d%3D%22M-20%20200%20C100%2080%20235%20250%20375%20135%20S590%2055%20740%20110%20S880%2020%201030%2035%22%2F%3E%3Cpath%20d%3D%22M-20%20210%20C110%20100%20235%20240%20385%20145%20S600%2075%20750%20120%20S890%2040%201030%2055%22%2F%3E%3Cpath%20d%3D%22M-20%20235%20C170%20115%20235%20265%20435%20160%20S650%20180%20800%2080%20S940%20110%201040%2040%22%2F%3E%3C%2Fg%3E%3C%2Fsvg%3E");background-repeat:no-repeat;background-position:right center;background-size:cover}
.hero-grid{position:relative;isolation:isolate}.hero-grid:before{content:"";position:absolute;z-index:-1;right:-2rem;bottom:0;width:90%;height:220px;background:url("data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%221000%22%20height%3D%22280%22%20viewBox%3D%220%200%201000%20280%22%3E%3Cdefs%3E%3Cpattern%20id%3D%22dots%22%20width%3D%229%22%20height%3D%229%22%20patternUnits%3D%22userSpaceOnUse%22%3E%3Ccircle%20cx%3D%221%22%20cy%3D%221%22%20r%3D%22.8%22%20fill%3D%22%2306bcef%22%2F%3E%3C%2Fpattern%3E%3Cmask%20id%3D%22wave%22%3E%3Cg%20fill%3D%22none%22%20stroke%3D%22white%22%3E%3Cpath%20d%3D%22M-20%20200%20C100%2080%20235%20250%20375%20135%20S590%2055%20740%20110%20S880%2020%201030%2035%22%20stroke-width%3D%2280%22%2F%3E%3Cpath%20d%3D%22M-20%20235%20C170%20115%20235%20265%20435%20160%20S650%20180%20800%2080%20S940%20110%201040%2040%22%20stroke-width%3D%2245%22%2F%3E%3C%2Fg%3E%3C%2Fmask%3E%3ClinearGradient%20id%3D%22fade%22%3E%3Cstop%20stop-color%3D%22%23042338%22%20stop-opacity%3D%220%22%2F%3E%3Cstop%20offset%3D%22.3%22%20stop-color%3D%22%230582b4%22%2F%3E%3Cstop%20offset%3D%221%22%20stop-color%3D%22%2306bcef%22%2F%3E%3C%2FlinearGradient%3E%3C%2Fdefs%3E%3Crect%20width%3D%221000%22%20height%3D%22280%22%20fill%3D%22url(%23dots)%22%20mask%3D%22url(%23wave)%22%20opacity%3D%22.65%22%2F%3E%3Cg%20fill%3D%22none%22%20stroke%3D%22url(%23fade)%22%20stroke-width%3D%22.7%22%20opacity%3D%22.6%22%3E%3Cpath%20d%3D%22M-20%20200%20C100%2080%20235%20250%20375%20135%20S590%2055%20740%20110%20S880%2020%201030%2035%22%2F%3E%3Cpath%20d%3D%22M-20%20210%20C110%20100%20235%20240%20385%20145%20S600%2075%20750%20120%20S890%2040%201030%2055%22%2F%3E%3Cpath%20d%3D%22M-20%20235%20C170%20115%20235%20265%20435%20160%20S650%20180%20800%2080%20S940%20110%201040%2040%22%2F%3E%3C%2Fg%3E%3C%2Fsvg%3E") right bottom/cover no-repeat;opacity:.16;pointer-events:none}
.panel-heading{font-size:.88rem}.panel-heading>small{font-size:.68rem}.panel-subtitle{font-size:.78rem}.source-note,.trace-source{font-size:.72rem}.eyebrow,.section-kicker{font-size:.67rem}
.evidence-title{font-size:.86rem}.evidence-rank{font-size:.8rem}.evidence-source,.evidence-relevance{font-size:.69rem}.context-item{font-size:.76rem}.context-item small,.query-context>small{font-size:.68rem}.context-item b{font-size:.87rem}.query-context{font-size:.84rem}
.trace-name{font-size:.72rem}.trace-role{font-size:.57rem}.trace-status{font-size:.62rem}.trace-detail{font-size:.61rem}.trace-number{font-size:.59rem}
.policy-banner b{font-size:.86rem}.policy-banner span{font-size:.76rem}.empty-state{font-size:.85rem}.empty-state.compact{font-size:.8rem}
.chart-title,.chart-card-title{font-size:1.04rem}.chart-subtitle,.chart-card-sub{font-size:.74rem}.kpi .label{font-size:.62rem}.kpi .sub{font-size:.69rem}.kpi .value{font-size:1.95rem}
.metric-name{font-size:.74rem}.metric-before{font-size:1rem}.metric-after{font-size:1.1rem}.metric-delta{font-size:.73rem}
.arch-node2{min-height:160px}.arch-node2 h4{padding:0!important;margin:.45rem 0!important;font-size:.96rem!important}.arch-node2 p{font-size:.77rem;line-height:1.55}.arch-node2 .arch-kind{font-size:.6rem;padding-top:.7rem}.arch-node-icon{margin:.2rem auto}.arch-branch b{font-size:.83rem}.arch-branch p{font-size:.7rem}.arch-branch small,.arch-bridge{font-size:.68rem}.branch-label{font-size:.63rem}
.control-policy-grid b{font-size:.84rem}.control-policy-grid p{font-size:.73rem}.state-code code{font-size:.73rem}.state-code span{font-size:.69rem}.arch-feedback{font-size:.8rem}.arch-feedback small{font-size:.68rem}
[data-testid="stMarkdownContainer"] h3.team-name{font-size:1.7rem!important}.team-role{font-size:1rem}.team-description{font-size:.9rem!important;line-height:1.65!important}.team-link{font-size:.84rem}.avatar-caption{font-size:.72rem!important;margin:.6rem 0 .35rem!important}
.stack-panel .section-title{font-size:1.8rem!important}.stack-panel .section-copy{font-size:.88rem!important}.stack-items>div{font-size:.74rem}
.page-footer>span{display:inline-flex;align-items:center;gap:.65rem;font-size:.7rem}.page-footer .brand-mark{width:24px!important;height:24px!important;display:inline-block;flex:none}.page-footer{padding-top:.9rem}
[data-testid="stButton"]>button p{font-size:.85rem}[data-testid="stButton"]>button{min-height:42px}
[data-testid="stRadio"] label p{font-size:.85rem}[data-testid="stTextInput"] input,[data-testid="stTextArea"] textarea{font-size:.88rem!important}
[data-testid="stCaptionContainer"] p{font-size:.73rem;line-height:1.55}
[data-testid="stExpander"] summary p{font-size:.83rem}
@media(max-width:1100px){.brand-name{font-size:1.2rem}.nav-links a{font-size:.73rem}.trace-name{font-size:.65rem}.trace-status{font-size:.58rem}.arch-node2 p{font-size:.72rem}.page-heading:after{opacity:.2}.state-code>div{flex-direction:column;gap:0}.state-code span{text-align:left}}
@media(max-width:800px){[data-testid="stMarkdownContainer"] h1.page-title{font-size:2.5rem!important}[data-testid="stMarkdownContainer"] .page-subtitle{font-size:.9rem!important}.page-heading:after{width:90%}.team-role{font-size:.96rem}.nav-links a{font-size:.7rem}}
@media(max-width:520px){[data-testid="stMarkdownContainer"] h1.page-title{font-size:2rem!important}[data-testid="stMarkdownContainer"] .page-subtitle{font-size:.82rem!important}[data-testid="stMarkdownContainer"] .hero-copy{font-size:.84rem!important}.brand-name{font-size:1.1rem}.nav-links a{font-size:.64rem}.status-note{font-size:.52rem}.nav-status .status-copy{font-size:.55rem}.panel-heading{font-size:.82rem}.panel-heading>small{font-size:.6rem}.hero-grid:before{opacity:.1}}
/* Keep decorative waves within their sections, without clipping navigation or trace. */
.page-heading:after,.hero-grid:before{right:0;max-width:100%}
[data-testid="stMarkdownContainer"] [dir="auto"]{text-align:start!important;unicode-bidi:plaintext}
[data-testid="stVerticalBlock"],[data-testid="stColumn"],.hero-visual,.ragops-nav,.nav-links{min-width:0}
@media(max-width:800px){.page-heading:after{width:100%}.hero-grid:before{width:100%}.nav-links{max-width:100%}}
.st-key-approve_optimization button{background:linear-gradient(110deg,#ffd46a,#ffbc35)!important;border-color:#ffd26b!important;color:#231a09!important;box-shadow:0 0 18px rgba(255,195,74,.12)}
.st-key-reject_optimization button{border-color:rgba(255,195,74,.6)!important;color:#ff8797!important;background:rgba(41,28,13,.5)!important}
/* Overview motion illustrates workflow order; it does not represent live execution. */
.conceptual-flow .orbit-agent-glow{opacity:.24;animation:overview-agent-glow 8s ease-in-out infinite;animation-delay:var(--agent-delay)}
.conceptual-flow .orbit-agent-stroke{stroke-opacity:.66;animation:overview-agent-stroke 8s ease-in-out infinite;animation-delay:var(--agent-delay)}
.conceptual-flow .orbit-flow{opacity:.38;animation:overview-connector-flow 1.5s linear infinite,overview-connector-emphasis 8s ease-in-out infinite;animation-delay:0s,var(--flow-delay)}
.orbit-gate-surface{transition:filter .3s ease,stroke .3s ease}
.orbit-gate.is-relevant .orbit-gate-surface,.orbit-gate.is-preview-relevant .orbit-gate-surface{stroke:#ffd27b;filter:drop-shadow(0 0 7px rgba(255,195,74,.38))}
.orbit-gate.is-relevant .orbit-gate-connector,.orbit-gate.is-preview-relevant .orbit-gate-connector{animation:overview-gate-flow 1.4s linear infinite}
.evaluation-snapshot{scroll-margin-top:110px;outline:none;margin-top:.5rem}
.evaluation-snapshot>.section-kicker{margin:0 .2rem .5rem}
.evaluation-snapshot .hero-statbar{margin:.35rem 0 .55rem}
.hero-stat b .kpi-count{display:inline;color:inherit;font:inherit;line-height:inherit;margin:0;font-variant-numeric:tabular-nums}
[data-testid="stMarkdownContainer"] .corpus-note{font-size:.74rem!important;color:#8daabd;margin:0 .2rem 1.5rem!important}
a.failure-card{display:block;color:inherit!important;text-decoration:none!important}
a.failure-card:focus-visible{outline:2px solid var(--card-accent);outline-offset:4px}
.overview-scroll-cue{position:fixed;bottom:15px;left:50%;transform:translateX(-50%);z-index:30;display:flex;align-items:center;gap:.55rem;padding:.5rem .9rem;border:1px solid rgba(37,165,193,.2);border-radius:30px;background:rgba(3,16,29,.94);box-shadow:0 3px 18px rgba(0,0,0,.15);color:#9bbccc!important;text-decoration:none!important;font-size:.7rem;white-space:nowrap;transition:color .2s ease,border-color .2s ease}
.overview-scroll-cue[hidden]{display:none!important}
.overview-scroll-cue:hover,.overview-scroll-cue:focus-visible{color:#d2f5ff!important;border-color:rgba(45,218,255,.55)}
.overview-scroll-cue:focus-visible{outline:2px solid var(--cyan);outline-offset:3px}
.overview-scroll-cue>span{display:inline-block;color:#60cee0;animation:overview-scroll-drift 3s ease-in-out infinite}
@keyframes overview-agent-glow{0%,24%,100%{opacity:.24}7%,15%{opacity:.95}}
@keyframes overview-agent-stroke{0%,24%,100%{stroke-opacity:.66}7%,15%{stroke-opacity:1;stroke-width:2}}
@keyframes overview-connector-flow{to{stroke-dashoffset:-20}}
@keyframes overview-connector-emphasis{0%,22%,100%{opacity:.38}5%,15%{opacity:.9}}
@keyframes overview-gate-flow{to{stroke-dashoffset:-14}}
@keyframes overview-scroll-drift{0%,100%{transform:translateY(-1px)}50%{transform:translateY(2px)}}
@media(max-width:800px){.evaluation-snapshot{scroll-margin-top:135px}.overview-scroll-cue{bottom:12px;font-size:.67rem}}
/* Desktop-first layout: fixed reading sizes; reflow before panels become cramped. */
[data-testid="stAppViewBlockContainer"],.block-container{padding-inline:var(--page-gutter)!important}
.ragops-nav-shell{margin-inline:calc(-1 * var(--page-gutter));padding:.8rem var(--page-gutter)}
.ragops-nav{display:grid;grid-template-columns:minmax(0,1fr) auto minmax(0,1fr);gap:1rem}
.brand-wrap{gap:.65rem}.brand-mark{width:40px;height:40px}.brand-name{font-size:1.5rem}
.nav-links{width:auto;justify-self:center;gap:3px}
.nav-links a{flex:none;font-size:.86rem;line-height:1.5;padding:.65rem 1rem;gap:.55rem}
.nav-links a svg{display:block;width:17px;height:17px}
.nav-status{display:flex;width:13rem;height:2.75rem;padding-left:1rem;gap:.65rem}
.nav-status .status-copy{font-size:.7rem}.status-note{font-size:.65rem}
[data-testid="stMarkdownContainer"] h1.page-title{font-size:3rem!important;line-height:1.15!important}
[data-testid="stMarkdownContainer"] h2.section-title{font-size:1.9rem!important}
[data-testid="stMarkdownContainer"] .page-subtitle{font-size:1rem!important;max-width:75ch}
.page-heading{padding:1.25rem 0 .5rem}
.hero-grid{grid-template-columns:minmax(0,.95fr) minmax(0,1.05fr);gap:1.5rem;min-height:520px;padding:1rem 0}
.hero-left{min-width:0;padding:.5rem 0}.hero-title{font-size:4.5rem!important;white-space:normal}
.hero-subtitle{font-size:1.5rem}.hero-tagline{font-size:1rem;letter-spacing:.08em}
[data-testid="stMarkdownContainer"] .hero-copy{font-size:1rem!important;max-width:60ch}
.hero-actions{gap:.75rem}.hero-btn{min-height:46px;font-size:.85rem;padding:.8rem 1.1rem}
.hero-evidence-note{font-size:.72rem;flex-wrap:wrap}
.control-loop-svg{max-width:620px}
.hero-statbar{gap:0;padding:1rem .5rem}.hero-stat{padding:.25rem 1rem;gap:.8rem;min-width:0}
.hero-stat>div{min-width:0}.hero-stat b{font-size:1.3rem}.hero-stat span{font-size:.8rem}
.failure-grid{gap:var(--panel-gap)}.failure-card{padding:1.1rem;min-width:0}
.failure-card h3{font-size:1.05rem!important}.failure-card p{font-size:.86rem}
.failure-response{font-size:.8rem;align-items:flex-start}.failure-response b,.failure-response strong{font-size:.78rem}
.panel-heading{flex-wrap:wrap;row-gap:.3rem}.panel-heading>span{min-width:0;overflow-wrap:anywhere}
.evidence-grid{grid-template-columns:repeat(auto-fit,minmax(min(100%,220px),1fr));gap:.85rem}
.stack-panel{flex-wrap:wrap;gap:1.5rem}.stack-panel>div{min-width:0}
.stack-items{gap:.6rem}.stack-items>div{min-width:80px;flex:1 1 80px}
.page-footer{flex-wrap:wrap;line-height:1.6}
@media(max-width:1240px){
  .ragops-nav{grid-template-columns:minmax(0,1fr) auto;gap:.7rem}
  .nav-links{grid-column:1/-1;grid-row:2;justify-self:stretch;justify-content:center;max-width:100%;overflow-x:auto}
  .nav-status{grid-column:2;grid-row:1}
}
@media(max-width:1150px){
  :root{--page-gutter:1.5rem}
  .hero-grid{grid-template-columns:minmax(0,1fr);min-height:0;gap:1rem;padding:1.5rem 0}
  .hero-left{max-width:760px}.hero-visual{width:100%;max-width:660px;justify-self:center}
  .failure-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
  .failure-card:last-child{grid-column:1/-1}
  .hero-statbar{grid-template-columns:repeat(2,minmax(0,1fr));row-gap:1rem}
  .hero-stat:nth-child(2){border-right:0}.hero-stat:nth-child(n+3){border-top:1px solid rgba(72,158,187,.17);padding-top:1rem}
  [data-testid="stMarkdownContainer"] h1.page-title{font-size:2.5rem!important}
}
@media(max-width:700px){
  :root{--page-gutter:1rem}
  .ragops-nav-shell{padding:.7rem var(--page-gutter)}
  .ragops-nav{gap:.6rem}.brand-wrap{gap:.5rem}.brand-mark{width:32px;height:32px}.brand-name{font-size:1.1rem}
  .nav-status{width:10rem;height:2.5rem;padding-left:0;gap:.4rem;border-left:0}
  .nav-status .status-copy{font-size:.62rem}.status-note{font-size:.58rem}
  .nav-links{justify-content:flex-start;gap:3px;border-radius:11px;scroll-padding-inline:.5rem}
  .nav-links a{flex:0 0 auto;font-size:.78rem;padding:.65rem .7rem;gap:.35rem}
  .nav-links a svg{display:none}
  [data-testid="stMarkdownContainer"] h1.page-title{font-size:2rem!important}
  [data-testid="stMarkdownContainer"] h2.section-title{font-size:1.65rem!important}
  [data-testid="stMarkdownContainer"] .page-subtitle{font-size:.95rem!important}
  .hero-title{font-size:3rem!important}.hero-subtitle{font-size:1.3rem}.hero-tagline{font-size:.9rem}
  .hero-grid{padding:1rem 0}.hero-actions{flex-direction:column;align-items:stretch;max-width:360px}
  .hero-btn{font-size:.88rem}.hero-stat{gap:.6rem;padding:.25rem .55rem;align-items:flex-start}
  .hero-stat>svg{width:24px;height:24px}.hero-stat b{font-size:1.2rem}.hero-stat span{font-size:.78rem}
  .failure-grid{grid-template-columns:minmax(0,1fr)}.failure-card:last-child{grid-column:auto}
  .stack-items{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));width:100%}
  .stack-items>div{min-width:0}.page-footer{gap:.75rem}
}
@media(max-width:370px){
  .ragops-nav{grid-template-columns:minmax(0,1fr)}
  .nav-status{grid-column:1;grid-row:2;justify-self:start}.nav-links{grid-row:3}
}
@media(prefers-reduced-motion:reduce){*,*::before,*::after{animation:none!important;transition:none!important;scroll-behavior:auto!important}.trace-stage,.trace-row,.metric-after{opacity:1!important;transform:none!important}}
</style>
"""
