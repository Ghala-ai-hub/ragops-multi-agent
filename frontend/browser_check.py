"""Capture local UI previews using installed Chrome and its debugging protocol.

No live-run controls are clicked. Output and the disposable browser profile stay
in the requested temporary directory. Requires the app to be running locally.
Overview and Action interaction checks follow only local saved-evidence links;
no approval, live run, index build, or credential controls are activated.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.request
from urllib.parse import urlencode

from websockets.sync.client import connect


class Browser:
    def __init__(self, address):
        self.ws = connect(address, max_size=20_000_000, proxy=None)
        self.sequence = 0

    def command(self, method, params=None):
        self.sequence += 1
        current = self.sequence
        self.ws.send(json.dumps({"id":current,"method":method,"params":params or {}}))
        while True:
            reply = json.loads(self.ws.recv(timeout=20))
            if reply.get("id") == current:
                if "error" in reply:
                    raise RuntimeError(reply["error"]["message"])
                return reply.get("result", {})

    def evaluate(self, expression):
        result = self.command("Runtime.evaluate", {"expression":expression,"returnByValue":True,"awaitPromise":True})
        if result.get("exceptionDetails"):
            raise RuntimeError("Browser evaluation failed")
        return result.get("result", {}).get("value")

    def wait_ready(self):
        for _ in range(80):
            ready = self.evaluate("!!document.querySelector('.page-footer')")
            if ready:
                return
            time.sleep(.25)
        raise RuntimeError("The local page did not finish rendering")

    def navigate(self, url):
        # A previous page can remain visible briefly after Page.navigate returns.
        # Wait for a new document before testing the next Streamlit render.
        self.evaluate("document.documentElement.dataset.previousPreview='yes'")
        self.command("Page.navigate", {"url":url})
        self.wait_for("!document.documentElement.dataset.previousPreview && !!document.querySelector('.page-footer')")

    def wait_for(self, expression):
        for _ in range(80):
            try:
                if self.evaluate(expression):
                    return
            except RuntimeError:
                # Navigation briefly destroys the prior document/JS context.
                pass
            time.sleep(.2)
        raise RuntimeError("Expected saved-evidence UI state did not appear")

    def click_saved(self, label):
        # Deliberately refuse clicks outside the explicitly labelled saved view.
        if label != "Inspect saved run →":
            raise RuntimeError("Only the read-only saved-run inspection control may be clicked")
        self.evaluate("if(!document.querySelector('.source-note')?.textContent.includes('Saved Evidence Mode')) throw Error('Saved evidence mode required');")
        result = self.evaluate("(()=>{const b=Array.from(document.querySelectorAll('button')).find(b=>b.innerText.trim()===" + json.dumps(label) + ");if(!b)return false;b.click();return true})()")
        if not result:
            raise RuntimeError("Saved-evidence control not found")

    def screenshot(self, path):
        payload = self.command("Page.captureScreenshot", {"format":"png","captureBeyondViewport":False})
        path.write_bytes(base64.b64decode(payload["data"]))


def check_overview_interactions(browser, port, output):
    """Exercise presentation behavior and saved-case links without a live run."""
    overview_url = f"http://127.0.0.1:{port}/?page=overview"
    expected_counts = ["24", "48", "5/5", "89.6%"]
    counts_expression = "Array.from(document.querySelectorAll('#evaluation-snapshot .kpi-count'), el => el.textContent.trim())"

    def require(condition, message):
        if not condition:
            raise RuntimeError("Overview interaction check failed: " + message)

    def mouse_target(selector):
        point = browser.evaluate("""((selector) => {
          const el = document.querySelector(selector);
          if (!el) return null;
          el.scrollIntoView({behavior:'instant', block:'center'});
          const box = el.getBoundingClientRect();
          return {x:box.x + box.width / 2, y:box.y + box.height / 2};
        })(""" + json.dumps(selector) + ")")
        require(point is not None, "expected control missing: " + selector)
        browser.command("Input.dispatchMouseEvent", {"type":"mouseMoved", **point})
        return point

    def click_target(selector):
        point = mouse_target(selector)
        browser.command("Input.dispatchMouseEvent", {"type":"mousePressed", "button":"left", "clickCount":1, **point})
        browser.command("Input.dispatchMouseEvent", {"type":"mouseReleased", "button":"left", "clickCount":1, **point})

    browser.command("Emulation.setEmulatedMedia", {"features":[{"name":"prefers-reduced-motion", "value":"no-preference"}]})
    browser.navigate(overview_url)
    browser.wait_for("typeof window.__ragopsOverviewCleanup === 'function' && document.querySelectorAll('.kpi-count').length === 4")
    browser.wait_for("JSON.stringify(" + counts_expression + ") === " + json.dumps(json.dumps(expected_counts, separators=(",", ":"))))
    require(browser.evaluate(counts_expression) == expected_counts, "evaluation counters did not reach stored values")
    require(browser.evaluate("document.querySelectorAll('[data-testid=stException]').length") == 0, "Overview raised a Streamlit exception")

    motion = browser.evaluate("""(() => ({
      agents: [...document.querySelectorAll('.orbit-agent')].map(el => ({
        name: el.getAttribute('class'), delay: el.style.getPropertyValue('--agent-delay').trim(),
        glow: getComputedStyle(el.querySelector('.orbit-agent-glow')).animationName,
        stroke: getComputedStyle(el.querySelector('.orbit-agent-stroke')).animationName
      })),
      flows: [...document.querySelectorAll('.orbit-flow')].map(el => ({
        animation: getComputedStyle(el).animationName,
        dash: getComputedStyle(el).strokeDashoffset,
        marker: getComputedStyle(el).markerEnd,
        delay: el.style.getPropertyValue('--flow-delay').trim()
      }))
    }))()""")
    require(len(motion["agents"]) == 4 and len(motion["flows"]) == 4, "expected four agents and four directional connectors")
    for index, name in enumerate(("monitoring", "diagnosis", "optimization", "validation")):
        stage = motion["agents"][index]
        require("orbit-agent-" + name in stage["name"], "agent order must follow Monitoring, Diagnosis, Optimization, Validation")
        require(float(stage["delay"].removesuffix("s")) == index * 2, "agent pulse delays are not sequential")
        require(stage["glow"] != "none" or stage["stroke"] != "none", "agent pulse animation is missing")
    require(all(flow["animation"] != "none" and flow["marker"] != "none" for flow in motion["flows"]), "directional flow animation or arrow marker is missing")
    browser.wait_for("JSON.stringify([...document.querySelectorAll('.orbit-flow')].map(el => getComputedStyle(el).strokeDashoffset)) !== " + json.dumps(json.dumps([flow["dash"] for flow in motion["flows"]], separators=(",", ":"))))
    next_dashes = browser.evaluate("[...document.querySelectorAll('.orbit-flow')].map(el => getComputedStyle(el).strokeDashoffset)")
    require(any(flow["dash"] != after for flow, after in zip(motion["flows"], next_dashes)), "connector dash positions did not advance")
    require(browser.evaluate("!document.querySelector('.orbit-gate.is-relevant,.orbit-gate.is-preview-relevant,.orbit-gate-glow')"), "risk gate is highlighted without a structural selection")

    cue = browser.evaluate("""(() => {
      const el = document.querySelector('.overview-scroll-cue');
      const box = el.getBoundingClientRect();
      return {hidden:el.hidden, top:box.top, bottom:box.bottom, height:innerHeight,
        display:getComputedStyle(el).display};
    })()""")
    require(not cue["hidden"] and cue["display"] != "none", "scroll cue is not visible at the top of Overview")
    require(cue["top"] >= cue["height"] * .7 and cue["bottom"] <= cue["height"] + 2, "scroll cue is not near the bottom of the first viewport")
    browser.screenshot(output / "overview-interactions-initial.png")
    # The cue is already visible. Do not scroll it into view before clicking;
    # that could hide the cue and defeat this interaction check.
    cue_point = browser.evaluate("(()=>{const b=document.querySelector('.overview-scroll-cue').getBoundingClientRect();return {x:b.x+b.width/2,y:b.y+b.height/2}})()")
    browser.command("Input.dispatchMouseEvent", {"type":"mouseMoved", **cue_point})
    browser.command("Input.dispatchMouseEvent", {"type":"mousePressed", "button":"left", "clickCount":1, **cue_point})
    browser.command("Input.dispatchMouseEvent", {"type":"mouseReleased", "button":"left", "clickCount":1, **cue_point})
    browser.wait_for("!!document.querySelector('.overview-scroll-cue')?.hidden && ((document.querySelector('[data-testid=stMain]')?.scrollTop || window.scrollY) > 60)")
    require(browser.evaluate("document.activeElement?.id === 'evaluation-snapshot'"), "scroll cue did not focus the evaluation snapshot")

    require(browser.evaluate("!!document.querySelector('article.failure-card[data-failure-kind=structural]') && !document.querySelector('[data-failure-kind=structural][href],[data-failure-kind=structural] .failure-arrow')"), "chunking summary must not link to a synthetic workflow")
    print(json.dumps({"overview_interactions":"passed", "counts":expected_counts, "agent_delays":[item["delay"] for item in motion["agents"]], "directional_motion":True, "structural_link":False, "scroll_cue":True}))

    for kind, action in (("top-k", "change_top_k"), ("query-mismatch", "rewrite_query")):
        browser.navigate(overview_url)
        browser.wait_for("typeof window.__ragopsOverviewCleanup === 'function'")
        selector = f'a.failure-card[data-failure-kind="{kind}"]'
        destination = browser.evaluate("""((selector) => {
          const link = document.querySelector(selector);
          if (!link) return null;
          const url = new URL(link.href);
          return {origin:url.origin, page:url.searchParams.get('page'), caseId:url.searchParams.get('case')};
        })(""" + json.dumps(selector) + ")")
        require(destination is not None, "evidence-backed failure card is not linked: " + kind)
        require(destination["origin"] == f"http://127.0.0.1:{port}" and destination["page"] == "action" and destination["caseId"], "failure card must lead only to a local saved case")
        click_target(selector)
        browser.wait_for("new URLSearchParams(location.search).get('page') === 'action' && new URLSearchParams(location.search).get('case') === " + json.dumps(destination["caseId"]) + " && document.querySelector('.source-note')?.textContent.includes('Saved Evidence Mode') && !!document.querySelector('.page-footer')")
        browser.wait_for("!!document.querySelector('textarea')?.value.trim() && document.querySelectorAll('.trace-stage').length === 7")
        require(browser.evaluate("document.querySelectorAll('[data-testid=stException]').length") == 0, "saved case raised a Streamlit exception: " + kind)
        expected_words = action.replace("_", " ")
        require(browser.evaluate("[...document.querySelectorAll('.trace-detail,.approval-field,.policy-banner')].some(el => el.textContent.toLowerCase().includes(" + json.dumps(expected_words) + ") || el.textContent.includes(" + json.dumps(action) + "))"), "card opened the wrong proposed action: " + kind)
        controls = browser.evaluate("({approve:[...document.querySelectorAll('button')].filter(b=>b.innerText.trim()==='Approve Optimization').length,reject:[...document.querySelectorAll('button')].filter(b=>b.innerText.trim().startsWith('Reject')).length,pending:!!document.querySelector('.approval-card')})")
        require(controls == {"approve":0, "reject":0, "pending":False}, "low-impact case incorrectly offers human approval controls")
        require(browser.evaluate("document.querySelector('.policy-banner')?.textContent.includes('Auto-approved by policy')"), "low-impact case is missing automatic policy status")
        browser.screenshot(output / f"overview-link-{kind}.png")
        print(json.dumps({"overview_saved_link":kind, "case_id":destination["caseId"], "action":action, "approval_controls":controls}))

    # Refresh in reduced motion so the script starts with the preference already
    # active. Counts must render their final data and all overview motion stops.
    browser.command("Emulation.setEmulatedMedia", {"features":[{"name":"prefers-reduced-motion", "value":"reduce"}]})
    try:
        browser.navigate(overview_url)
        browser.wait_for("typeof window.__ragopsOverviewCleanup === 'function' && document.querySelectorAll('.kpi-count').length === 4")
        browser.wait_for("JSON.stringify(" + counts_expression + ") === " + json.dumps(json.dumps(expected_counts, separators=(",", ":"))))
        reduced = browser.evaluate("""(() => {
          const selectors = '.hero-grid *,.overview-scroll-cue,.evaluation-snapshot *,.failure-grid *';
          const nodes = [...document.querySelectorAll(selectors)];
          return {matches:matchMedia('(prefers-reduced-motion: reduce)').matches,
            animations:nodes.filter(el => getComputedStyle(el).animationName !== 'none').length,
            running:nodes.flatMap(el => el.getAnimations()).filter(animation => animation.playState === 'running').length,
            counts:[...document.querySelectorAll('.kpi-count')].map(el => el.textContent.trim())};
        })()""")
        require(reduced["matches"] and reduced["animations"] == 0 and reduced["running"] == 0, "reduced-motion preference did not stop Overview animation")
        require(reduced["counts"] == expected_counts, "reduced motion changed the final evaluation values")
        browser.screenshot(output / "overview-reduced-motion.png")
        print(json.dumps({"overview_reduced_motion":"passed", **reduced}))
    finally:
        browser.command("Emulation.setEmulatedMedia", {"features":[{"name":"prefers-reduced-motion", "value":"no-preference"}]})


def check_architecture_team_interactions(browser, port, output, width, height, architecture_only=False):
    """Check architecture; optionally continue with Team and Overview checks."""
    def require(condition, message):
        if not condition:
            raise RuntimeError("Architecture / Team check failed: " + message)

    def load(page):
        browser.navigate(f"http://127.0.0.1:{port}/?page={page}")
        browser.wait_ready()
        time.sleep(1.1)

    def clean_focus():
        browser.evaluate("document.activeElement?.blur()")
        browser.command("Input.dispatchMouseEvent", {"type":"mouseMoved", "x":5, "y":5})

    def hover(selector):
        point = browser.evaluate("""((selector) => {
          const element = document.querySelector(selector);
          if (!element) return null;
          element.scrollIntoView({behavior:'instant',block:'center'});
          const box = element.getBoundingClientRect();
          return {x:box.x+box.width/2,y:box.y+box.height/2};
        })(""" + json.dumps(selector) + ")")
        require(point is not None, "missing hover target " + selector)
        browser.command("Input.dispatchMouseEvent", {"type":"mouseMoved", **point})

    def no_overflow(page, viewport):
        result = browser.evaluate("""({
          exceptions:document.querySelectorAll('[data-testid=stException]').length,
          overflow:[document.documentElement,document.body,document.querySelector('[data-testid=stMain]')]
            .filter(Boolean).some(el=>el.scrollWidth>el.clientWidth+2)
        })""")
        require(not result["exceptions"] and not result["overflow"], f"{page} layout at {viewport}px: " + json.dumps(result))
        browser.screenshot(output / f"{page}-interaction-{viewport}.png")
        return result

    def check_shared_state():
        state = browser.evaluate(r"""(() => {
          const container=document.querySelector('.st-key-architecture_state');
          const details=container?.querySelector('details');
          return {exists:!!details,open:details?.open,
            label:details?.querySelector('summary')?.innerText.replace(/\s+/g,' ').trim(),
            policy:!!document.querySelector('.st-key-architecture_policy')};
        })()""")
        require(state["exists"] and not state["open"], "Shared State must start as a collapsed native expander")
        require("View Shared State" in (state["label"] or "") and not state["policy"], "Shared State label or removed Control Policy panel is incorrect")
        selector = ".st-key-architecture_state details summary"
        hover(selector)
        point = browser.evaluate("(()=>{const b=document.querySelector('.st-key-architecture_state details summary').getBoundingClientRect();return {x:b.x+b.width/2,y:b.y+b.height/2}})()")
        for expected in (True, False):
            browser.command("Input.dispatchMouseEvent", {"type":"mousePressed", "button":"left", "clickCount":1, **point})
            browser.command("Input.dispatchMouseEvent", {"type":"mouseReleased", "button":"left", "clickCount":1, **point})
            browser.wait_for("document.querySelector('.st-key-architecture_state details').open === " + json.dumps(expected))
            if expected:
                visible = browser.evaluate("(()=>{const el=document.querySelector('.st-key-architecture_state .state-code');return !!el && el.getBoundingClientRect().height>0 && getComputedStyle(el).visibility!=='hidden'})()")
                require(visible, "Shared State content did not become visible when expanded")
        print(json.dumps({"architecture_shared_state":"collapsed by default; expands and collapses", "control_policy_panel":False}))

    def reduced_motion(page, selector):
        load(page)
        result = browser.evaluate("""((selector)=>{
          const nodes=[...document.querySelectorAll(selector)];
          return {matches:matchMedia('(prefers-reduced-motion: reduce)').matches,
            animations:nodes.filter(el=>getComputedStyle(el).animationName!=='none').length,
            running:nodes.flatMap(el=>el.getAnimations()).filter(animation=>animation.playState==='running').length};
        })(""" + json.dumps(selector) + ")")
        require(result["matches"] and result["animations"] == 0 and result["running"] == 0, page + " animations did not honor reduced motion")
        browser.screenshot(output / f"{page}-reduced-motion.png")
        print(json.dumps({"reduced_motion_page":page,**result}))

    def navbar_separation(viewport):
        samples = browser.evaluate("""(async () => {
          const content=document.querySelector('.st-key-architecture_content');
          const nav=document.querySelector('.ragops-nav-shell');
          if(!content||!nav) return null;
          const prior=content.scrollTop;
          const maximum=Math.max(0,content.scrollHeight-content.clientHeight);
          const values=[];
          for(const offset of [...new Set([0,Math.min(120,maximum),maximum])]) {
            content.scrollTop=offset;
            await new Promise(requestAnimationFrame);
            const n=nav.getBoundingClientRect(),c=content.getBoundingClientRect();
            const link=nav.querySelector('.nav-links a.active');
            const b=link.getBoundingClientRect();
            const hit=document.elementFromPoint(b.x+b.width/2,b.y+b.height/2);
            values.push({offset:content.scrollTop,nav_top:n.top,nav_bottom:n.bottom,
              content_top:c.top,content_height:content.clientHeight,overflow:getComputedStyle(content).overflowY,
              nav_statuses:nav.querySelectorAll('.nav-status').length,
              outer_scroll:document.querySelector('[data-testid=stMain]').scrollTop,
              nav_frame:nav.closest('[data-testid=stElementContainer]').getBoundingClientRect().toJSON(),
              nav_hit:!!hit&&nav.contains(hit),title_top:content.querySelector('.page-title')?.getBoundingClientRect().top});
          }
          content.scrollTop=prior;
          return values;
        })()""")
        require(samples is not None and len(samples) > 0, "Architecture needs a separate content scroller below navigation")
        for sample in samples:
            require(sample["nav_statuses"] == 0, "Architecture navbar must omit the mode/status area")
            require(sample["content_height"] > 0 and sample["overflow"] in {"auto", "scroll"}, "Architecture content must scroll independently")
            require(sample["content_top"] >= sample["nav_bottom"] - 1, "Architecture content viewport overlaps the navbar: " + json.dumps(sample))
            require(abs(sample["nav_top"] - samples[0]["nav_top"]) <= 1 and sample["nav_hit"], "scrolling or focus covers or moves the navbar: " + json.dumps(sample))
            if sample["offset"] == 0:
                require(sample["title_top"] >= sample["nav_bottom"] - 1, "Architecture title overlaps navigation at the top")
        print(json.dumps({"architecture_navbar_separation":"passed","width":viewport,"scroll_positions":len(samples)}))

    def architecture_geometry(viewport):
        result = browser.evaluate("""(() => {
          const rect=element=>{const b=element.getBoundingClientRect();return {left:b.left,right:b.right,top:b.top,bottom:b.bottom,width:b.width,height:b.height,cx:b.left+b.width/2,cy:b.top+b.height/2}};
          const board=document.querySelector('.architecture-flow');
          const layout=board.querySelector('.architecture-layout');
          const node=id=>rect(document.querySelector('.architecture-flow [data-node="'+id+'"]'));
          const top=['user-query','baseline-rag','monitoring','retrieval-health','diagnosis','optimization'].map(id=>({id,...node(id)}));
          const lower=['validation','action-executor','risk-gate'].map(id=>({id,...node(id)}));
          const low=rect(document.querySelector('.arch-route-control[data-route="low"]'));
          const high=rect(document.querySelector('.arch-route-control[data-route="high"]'));
          const rejected=node('baseline-retained');
          const drop=board.querySelector('.arch-link[data-from="optimization"][data-to="risk-gate"]');
          const execution_link=rect(board.querySelector('.arch-link[data-from="action-executor"][data-to="validation"]'));
          const trunk=board.querySelector('.architecture-merge-trunk');
          const policy_content=[...board.querySelectorAll('.arch-route-low,.arch-route-high')].map(card=>({box:rect(card),children:[...card.children].map(rect)}));
          const semantic=[...board.querySelectorAll('[data-node]')];
          const overlaps=[];
          semantic.forEach((left,index)=>semantic.slice(index+1).forEach(right=>{
            const a=rect(left),b=rect(right);
            if(Math.min(a.right,b.right)-Math.max(a.left,b.left)>1 && Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top)>1){
              const outcomeInsideDecision=(left.dataset.node==='validation-decision' && left.contains(right) && right.dataset.role==='OUTCOME') ||
                (right.dataset.node==='validation-decision' && right.contains(left) && left.dataset.role==='OUTCOME');
              if(!outcomeInsideDecision)overlaps.push([left.dataset.node,right.dataset.node]);
            }
          }));
          const label_fonts=[...board.querySelectorAll('.architecture-node h3')].map(label=>({text:label.textContent,size:parseFloat(getComputedStyle(label).fontSize)}));
          const nodes=semantic.map(element=>({id:element.dataset.node,...rect(element)}));
          return {top,lower,low,high,rejected,execution_link,policy_content,overlaps,label_fonts,nodes,
            merge_trunks:board.querySelectorAll('.architecture-merge-trunk').length,
            trunk:rect(trunk),merge_arrows:board.querySelectorAll('.architecture-merge path[marker-end]').length,drop:rect(drop),layout:rect(layout),
            layout_count:board.querySelectorAll('.architecture-layout').length,
            board:{client_width:board.clientWidth,scroll_width:board.scrollWidth,overflow_x:getComputedStyle(board).overflowX},
            mobile_duplicates:board.querySelectorAll('.architecture-merge-mobile,.architecture-mobile-flow').length};
        })()""")
        low, high, rejected = result["low"], result["high"], result["rejected"]
        top, lower = result["top"], result["lower"]
        require(result["layout_count"] == 1 and result["mobile_duplicates"] == 0, "architecture must use one unified board at every width")
        require(max(node["cy"] for node in top) - min(node["cy"] for node in top) <= 3, "top pipeline must remain horizontal at every width: " + json.dumps(result))
        require(len(top) == 6 and all(node["width"] > 100 and node["height"] > 60 for node in top), "six top nodes need usable card dimensions")
        require(all(left["right"] <= right["left"] + 1 for left, right in zip(top, top[1:])), "top pipeline must read left to right")
        require(max(node["cy"] for node in lower) - min(node["cy"] for node in lower) <= 3, "lower main nodes must share an aligned row")
        require(all(left["right"] <= right["left"] + 1 for left, right in zip(lower, lower[1:])), "lower row must flow Risk Gate to Executor and Validation from right to left")
        require(abs(result["execution_link"]["cy"] - lower[0]["cy"]) <= 3 and abs(result["execution_link"]["cy"] - lower[1]["cy"]) <= 3, "execution arrow must connect Executor and Validation centerlines")
        require(result["merge_trunks"] == 1 and result["merge_arrows"] == 1 and abs(result["trunk"]["cy"] - lower[1]["cy"]) <= 3, "approved branches must share one centered arrow into Action Executor")
        require(abs(low["left"] - high["left"]) <= 1.5 and abs(low["width"] - high["width"]) <= 1.5 and low["bottom"] <= high["top"] + 1, "low and high policy lanes must be parallel stacked branches")
        require(low["left"] >= lower[1]["right"] - 1 and low["right"] <= lower[2]["left"] + 1, "policy branches must sit between Risk Gate and Executor")
        require(lower[2]["top"] > top[5]["bottom"] and abs(lower[2]["cx"] - top[5]["cx"]) <= 3 and result["drop"]["width"] <= 3, "Optimization must drop directly into the Risk Gate below it")
        require(rejected["height"] < high["height"] and rejected["width"] * rejected["height"] < high["width"] * high["height"] * .8, "rejected outcome must remain smaller than the main branch: " + json.dumps(result))
        require(not result["overlaps"], "semantic nodes overlap: " + json.dumps(result["overlaps"]))
        require(all(label["size"] >= 14 for label in result["label_fonts"]), "node labels must retain readable type at every viewport: " + json.dumps(result["label_fonts"]))
        layout = result["layout"]
        require(all(node["left"] >= layout["left"] - 1 and node["right"] <= layout["right"] + 1 and node["bottom"] <= layout["bottom"] + 1 for node in result["nodes"]), "semantic nodes must remain inside the single board layout")
        for card in result["policy_content"]:
            require(all(child["top"] >= card["box"]["top"] and child["bottom"] <= card["box"]["bottom"] for child in card["children"]), "policy text must fit within its compact card at every width")
        if viewport >= 1280:
            require(result["board"]["scroll_width"] <= result["board"]["client_width"] + 2, "desktop board must fit its content width without horizontal scrolling")
        if viewport <= 900:
            require(result["board"]["scroll_width"] > result["board"]["client_width"] and result["board"]["overflow_x"] in {"auto", "scroll"}, "narrow viewports must keep board overflow inside a horizontal scroller")
            scrolled = browser.evaluate("(()=>{const board=document.querySelector('.architecture-flow');board.scrollLeft=board.scrollWidth;const offset=board.scrollLeft;board.scrollLeft=0;return offset})()")
            require(scrolled > 0, "unified board must support internal horizontal scrolling")
        print(json.dumps({"architecture_flow_geometry":"passed", "width":viewport,
                          "board_width":round(result["layout"]["width"], 2),
                          "board_height":round(result["layout"]["height"], 2),
                          "top_cards":len(top), "internal_scroll":result["board"]["scroll_width"] > result["board"]["client_width"]}))

    browser.command("Emulation.setEmulatedMedia", {"features":[{"name":"prefers-reduced-motion","value":"no-preference"}]})
    load("architecture")
    no_overflow("architecture", width)
    geometry = browser.evaluate("""(() => {
      const graph=document.querySelector('.architecture-flow').getBoundingClientRect();
      const answer=document.querySelector('[data-node="final-answer"]').getBoundingClientRect();
      return {graph_height:graph.height,answer_bottom:answer.bottom};
    })()""")
    print(json.dumps({"architecture_compactness":geometry,"width":width,"height":height}))
    architecture_geometry(width)
    navbar_separation(width)
    browser.evaluate("""(() => {
      const panel=document.querySelector('.st-key-architecture_state');
      panel?.scrollIntoView({behavior:'instant',block:'start'});
      const content=document.querySelector('.st-key-architecture_content');
      if(content) content.scrollTop=Math.max(0,content.scrollTop-12);
    })()""")
    browser.screenshot(output / "architecture-desktop-lower-panels.png")
    require(browser.evaluate("document.querySelectorAll('.architecture-flow [data-role^=AGENT]').length") == 4, "diagram must contain exactly four functional agents")
    routes = browser.evaluate("""[...document.querySelectorAll('.architecture-flow .arch-link')].map(path => ({
      from:path.dataset.from,to:path.dataset.to,route:path.dataset.route,
      animation:getComputedStyle(path).animationName
    }))""")
    require(any(path["animation"] != "none" for path in routes), "diagram connectors have no directional motion")
    semantics = browser.evaluate("""(() => {
      const board=document.querySelector('.architecture-flow');
      return {nodes:[...board.querySelectorAll('[data-node]')].map(node=>node.dataset.node),
        agents:[...board.querySelectorAll('[data-role^=AGENT]')].map(node=>node.dataset.node),
        outcomes:[...board.querySelectorAll('.architecture-verdict-row')].map(row=>({route:row.dataset.route,
          label:row.querySelector('b')?.textContent.trim(),node:row.querySelector('[data-node]')?.dataset.node})),
        feedback:!!board.querySelector('[data-node="validation-feedback"]') || board.textContent.includes('Validation Feedback'),
        rejected:board.querySelector('.architecture-terminal')?.textContent.trim(),
        healthy_label:board.querySelector('.architecture-healthy-label')?.textContent.trim(),
        unhealthy_label:board.querySelector('.architecture-arrow-label')?.textContent.trim(),
        future_loop:!!board.querySelector('[data-node="feedback-loop"],[data-route="next-cycle"]')};
    })()""")
    require(set(semantics["agents"]) == {"monitoring", "diagnosis", "optimization", "validation"}, "agent roles must remain exactly Monitoring, Diagnosis, Optimization, and Validation")
    require(len(semantics["nodes"]) == len(set(semantics["nodes"])) == 18, "the unified board must contain exactly 18 unique workflow nodes")
    require(semantics["healthy_label"] == "YES" and semantics["unhealthy_label"] == "NO", "retrieval health needs explicit healthy and failure branches")
    require(not semantics["feedback"] and not semantics["future_loop"], "removed feedback annotations or future-cycle paths must not appear")
    require("Retain Baseline" in semantics["rejected"] and "No execution" in semantics["rejected"], "rejection must explicitly retain baseline with no execution")
    require({(item["route"], item["node"]) for item in semantics["outcomes"]} == {
        ("improved", "optimized-accepted"), ("same", "baseline-unchanged"), ("worse", "baseline-worse")}, "Validation Decision must show all three evidence-selection outcomes")
    edges = {(path["from"], path["to"]) for path in routes}
    expected_edges = {
        ("user-query", "baseline-rag"), ("baseline-rag", "monitoring"), ("monitoring", "retrieval-health"),
        ("retrieval-health", "diagnosis"), ("diagnosis", "optimization"), ("optimization", "risk-gate"),
        ("retrieval-health", "baseline-accepted"), ("baseline-accepted", "final-answer"),
        ("risk-gate", "auto-approved"), ("auto-approved", "action-executor"),
        ("risk-gate", "human-approval"), ("human-approval", "action-executor"),
        ("human-approval", "baseline-retained"), ("baseline-retained", "final-answer"),
        ("action-executor", "validation"), ("validation", "validation-decision"),
        ("validation-decision", "optimized-accepted"), ("optimized-accepted", "final-answer"),
        ("validation-decision", "baseline-unchanged"), ("baseline-unchanged", "final-answer"),
        ("validation-decision", "baseline-worse"), ("baseline-worse", "final-answer"),
    }
    require(expected_edges <= edges, "required workflow paths are missing: " + json.dumps(sorted(expected_edges - edges)))
    require(all(source in semantics["nodes"] and target in semantics["nodes"] for source, target in edges), "connectors must reference visible semantic nodes")
    require(not any("validation-feedback" in edge for edge in edges), "removed feedback annotation must not appear in the workflow")
    graph = {node: {target for source, target in edges if source == node} for node in semantics["nodes"]}

    def reachable(start):
        found, pending = set(), list(graph[start])
        while pending:
            node = pending.pop()
            if node not in found:
                found.add(node)
                pending.extend(graph[node] - found)
        return found

    workflow_nodes = set(semantics["nodes"])
    require(all(node not in reachable(node) for node in workflow_nodes), "the diagram must not imply an automatic optimization or future-retrieval cycle")
    require(reachable("user-query") == workflow_nodes - {"user-query"}, "every workflow branch must connect to the original query")
    require(all("final-answer" in reachable(node) for node in workflow_nodes - {"final-answer"}), "each accepted or retained evidence path must reach the final grounded answer")
    require(graph["baseline-accepted"] == {"final-answer"}, "healthy baseline must bypass optimization and execution")
    require(graph["baseline-retained"] == {"final-answer"}, "rejection must answer from baseline without executing the proposed action")
    require(not graph["final-answer"], "the current run ends at its final grounded answer")
    print(json.dumps({"architecture_semantics":"passed", "agents":len(semantics["agents"]),
                      "validation_outcomes":len(semantics["outcomes"]), "workflow_edges":len(edges),
                      "healthy_bypass":True, "rejection_retains_baseline":True, "automatic_rerun":False}))
    path_state = """[...document.querySelectorAll('.architecture-flow .arch-link')]
      .filter(path=>['low','high','approved','rejected'].includes(path.dataset.route))
      .map(path=>({route:path.dataset.route,opacity:Number(getComputedStyle(path).opacity)}))"""
    for selected, highlighted in (("low", {"low"}), ("high", {"high", "approved"}), ("rejected", {"high", "rejected"})):
        selector = f'.architecture-flow .arch-route-control[data-route="{selected}"]'
        for interaction in ("hover", "focus"):
            clean_focus()
            if interaction == "hover":
                hover(selector)
            else:
                # Establish keyboard modality so :focus-visible is exercised,
                # rather than depending on Chrome's prior pointer interaction.
                browser.command("Input.dispatchKeyEvent", {"type":"keyDown", "key":"Tab", "code":"Tab", "windowsVirtualKeyCode":9})
                browser.command("Input.dispatchKeyEvent", {"type":"keyUp", "key":"Tab", "code":"Tab", "windowsVirtualKeyCode":9})
                browser.evaluate("document.querySelector(" + json.dumps(selector) + ").focus({preventScroll:true})")
            desired = json.dumps(sorted(highlighted))
            browser.wait_for("(" + path_state + ").every(path=>" + desired + ".includes(path.route)?path.opacity>=.8:path.opacity<=.3)")
            state = browser.evaluate(path_state)
            require({path["route"] for path in state} == {"low", "high", "approved", "rejected"}, "branch paths are missing")
            print(json.dumps({"architecture_route":selected,"interaction":interaction,"highlighted":sorted(highlighted),"passed":True}))
        browser.screenshot(output / f"architecture-route-{selected}.png")
    clean_focus()
    check_shared_state()
    navbar_separation(width)

    try:
        for compact_width, compact_height in ((390,844),(900,650)):
            browser.command("Emulation.setDeviceMetricsOverride", {"width":compact_width,"height":compact_height,"deviceScaleFactor":1,"mobile":False})
            load("architecture")
            status = no_overflow("architecture", compact_width)
            architecture_geometry(compact_width)
            navbar_separation(compact_width)
            require(browser.evaluate("document.querySelectorAll('.architecture-flow [data-role^=AGENT]').length") == 4, "narrow board duplicates semantic agent nodes")
            require(browser.evaluate("document.querySelector('.architecture-flow .architecture-approve')?.textContent.includes('Approve')"), "approved branch must remain explicitly labelled on the unified narrow board")
            browser.evaluate("""(() => {
              document.querySelector('.architecture-flow [data-node="risk-gate"]')?.scrollIntoView({behavior:'instant',block:'start'});
              const content=document.querySelector('.st-key-architecture_content');
              if(content) content.scrollTop=Math.max(0,content.scrollTop-12);
            })()""")
            browser.screenshot(output / f"architecture-branches-{compact_width}.png")
            check_shared_state()
            navbar_separation(compact_width)
            print(json.dumps({"responsive_interaction_page":"architecture","width":compact_width,**status}))
    finally:
        browser.command("Emulation.setDeviceMetricsOverride", {"width":width,"height":height,"deviceScaleFactor":1,"mobile":False})
    browser.command("Emulation.setEmulatedMedia", {"features":[{"name":"prefers-reduced-motion","value":"reduce"}]})
    try:
        reduced_motion("architecture", ".architecture-flow,.architecture-flow *,[class*=st-key-arch] *")
    finally:
        browser.command("Emulation.setEmulatedMedia", {"features":[{"name":"prefers-reduced-motion","value":"no-preference"}]})
    if architecture_only:
        print(json.dumps({"architecture_interactions":"passed"}))
        return

    if __package__:
        from .config import TEAM_LINKEDIN
    else:
        from config import TEAM_LINKEDIN

    load("team")
    no_overflow("team", width)
    cards = browser.evaluate(r"""[...document.querySelectorAll('.team-card')].map(card => ({
      name:card.querySelector('.team-name')?.textContent.trim(),
      links:[...card.querySelectorAll('a.team-avatar-link,a.team-link')].map(link=>({href:link.getAttribute('href'),resolved_href:link.href,
        target:link.target,raw_target:link.getAttribute('target'),raw_rel:link.getAttribute('rel'),
        rel:[...link.relList],class_name:link.className,
        label:link.classList.contains('team-link')?link.textContent.replace(/\s+/g,' ').trim():null}))
    }))""")
    require([card["name"] for card in cards] == ["Jawaher", "Ghala", "Hanan", "Hajer"], "team identity/order differs from supplied content")
    for index, card in enumerate(cards):
        require(len(card["links"]) == 2, "team member must have exactly two explicit profile links")
        for link in card["links"]:
            details = json.dumps({"member":card["name"], "expected_href":TEAM_LINKEDIN[card["name"]], "dom":link}, ensure_ascii=False)
            require(link["href"] == TEAM_LINKEDIN[card["name"]], "profile destination is incorrect: " + details)
            require(link["target"] == "_blank", "profile link must open a new tab: " + details)
            require({"noopener","noreferrer"}.issubset(link["rel"]), "profile link lacks required browser rel tokens: " + details)
        require(any(link["label"] == "LinkedIn ↗" for link in card["links"]), "LinkedIn call to action is missing")
        clean_focus()
        selector = f'.team-card:nth-child({index + 1})'
        hover(selector)
        time.sleep(.4)
        lift = browser.evaluate("(()=>{const transform=getComputedStyle(document.querySelector(" + json.dumps(selector) + ")).transform;return transform==='none'?0:new DOMMatrixReadOnly(transform).m42})()")
        require(-6.1 <= lift <= -3.9, f"{card['name']} hover lift should be 4–6px, observed {lift}")
        print(json.dumps({"team_profile":card["name"],"destination_checked":True,"safe_new_tab":True,"hover_lift_px":lift,"external_navigation":False}))
    clean_focus()

    # These dimensions exercise the same content and routing at phone width.
    browser.command("Emulation.setDeviceMetricsOverride", {"width":390,"height":844,"deviceScaleFactor":1,"mobile":False})
    try:
        for page in ("team",):
            load(page)
            status = no_overflow(page, 390)
            require(browser.evaluate("document.querySelectorAll('.team-card').length") == 4, "phone layout lost a team card")
            print(json.dumps({"responsive_interaction_page":page,"width":390,**status}))
    finally:
        browser.command("Emulation.setDeviceMetricsOverride", {"width":width,"height":height,"deviceScaleFactor":1,"mobile":False})

    browser.command("Emulation.setEmulatedMedia", {"features":[{"name":"prefers-reduced-motion","value":"reduce"}]})
    try:
        reduced_motion("team", ".team-showcase,.team-showcase *,.st-key-team_stack *")
        hover(".team-card")
        require(browser.evaluate("getComputedStyle(document.querySelector('.team-card')).transform === 'none'"), "reduced motion still moves the team card")
    finally:
        browser.command("Emulation.setEmulatedMedia", {"features":[{"name":"prefers-reduced-motion","value":"no-preference"}]})

    load("overview")
    require(browser.evaluate("document.querySelector('.overview-scroll-cue')?.textContent.trim()") == "Explore more ↓", "Overview scroll cue wording differs from requested text")
    print(json.dumps({"overview_scroll_cue":"Explore more ↓","architecture_team_interactions":"passed"}))


def check_action_dashboard_interactions(browser, port, output, width, height):
    """Inspect real saved records and mode controls; never execute a live run."""
    workflow_path = Path(__file__).resolve().parents[1] / "evaluation" / "real_failure_workflow_results.json"
    records = json.loads(workflow_path.read_text(encoding="utf-8"))["results"]
    expected_names = ["Baseline RAG", "Monitoring", "Diagnosis", "Optimization", "Risk Gate", "Action Executor", "Validation"]

    def require(condition, message):
        if not condition:
            raise RuntimeError("Action / Dashboard check failed: " + message)

    def mode(label):
        selected = browser.evaluate("""((label) => {
          const group = document.querySelector('.st-key-mode_choice') || document.querySelector('[data-testid=stRadio]');
          const target = [...group.querySelectorAll('label')].find(el => el.querySelector('input[type=radio]') && el.textContent.trim() === label);
          if (!target) return false;
          target.click(); return true;
        })(""" + json.dumps(label) + ")")
        require(selected, "execution source selector missing")
        browser.wait_for("[...document.querySelectorAll('[data-testid=stRadio] label')].some(el => el.textContent.trim() === " + json.dumps(label) + " && el.querySelector('input[type=radio]')?.checked)")
        if label == "Saved evidence":
            browser.wait_for("document.querySelector('.source-note')?.textContent.includes('Saved Evidence Mode')")
        else:
            browser.wait_for("!document.querySelector('.source-note') && [...document.querySelectorAll('button')].some(el => el.innerText.trim() === 'Run RAGOps →')")

    def clean_layout(page, viewport, filename):
        browser.wait_ready()
        browser.wait_for("document.fonts.status === 'loaded'")
        result = browser.evaluate("""({
          exceptions:document.querySelectorAll('[data-testid=stException]').length,
          overflow:[document.documentElement,document.body,document.querySelector('[data-testid=stMain]')]
            .filter(Boolean).some(el => el.scrollWidth > el.clientWidth + 2)
        })""")
        require(not result["exceptions"] and not result["overflow"], f"{page} layout at {viewport}px: " + json.dumps(result))
        browser.screenshot(output / filename)
        return result

    browser.navigate(f"http://127.0.0.1:{port}/?page=action")
    browser.wait_ready()
    initial = browser.evaluate("""(() => {
      const group=document.querySelector('.st-key-mode_choice') || document.querySelector('[data-testid=stRadio]');
      const options=[...group.querySelectorAll('label')].filter(el=>el.querySelector('input[type=radio]')).map(el => ({label:el.textContent.trim(),checked:!!el.querySelector('input[type=radio]')?.checked}));
      return {options,unavailable:[...document.querySelectorAll('[data-testid=stAlert]')].some(el=>el.textContent.includes('Live Runtime Unavailable'))};
    })()""")
    require([item["label"] for item in initial["options"]] == ["Live run", "Saved evidence"], "Live run must be the first mode option; observed " + json.dumps(initial))
    expected_initial = "Saved evidence" if initial["unavailable"] else "Live run"
    require(next((item["label"] for item in initial["options"] if item["checked"]), None) == expected_initial, "default mode disagrees with runtime readiness; observed " + json.dumps(initial))
    clean_layout("action", width, "action-default-desktop.png")
    mode("Live run")
    require(browser.evaluate("document.querySelectorAll('.metric-card,.approval-card').length === 0"), "switching to live mode retained a saved result")
    if initial["unavailable"]:
        require(browser.evaluate("[...document.querySelectorAll('button')].find(el=>el.innerText.trim()==='Run RAGOps →')?.disabled"), "unconfigured live runtime permits a run")
        require(browser.evaluate("document.querySelector('[data-testid=stAlert]')?.textContent.includes('missing')"), "missing runtime requirements are not explained")
    mode("Saved evidence")
    print(json.dumps({"action_mode_controls":"passed", "initial_mode":expected_initial, "live_run_clicked":False}))

    require(len(records) == 5, "expected five stored workflow records")
    for record in records:
        browser.navigate(f"http://127.0.0.1:{port}/?" + urlencode({"page":"action", "case":record["id"]}))
        browser.wait_for("document.querySelector('.source-note')?.textContent.includes('Saved Evidence Mode') && document.querySelectorAll('.trace-name').length === 7")
        browser.wait_for("document.querySelector('textarea')?.value === " + json.dumps(record["original_query"]) + " && !!document.querySelector('.page-footer')")
        state = browser.evaluate("""(() => ({
          names:[...document.querySelectorAll('.trace-ribbon .trace-name')].map(el=>el.textContent.trim()),
          roles:[...document.querySelectorAll('.trace-role')].map(el=>el.textContent.trim()),
          statuses:[...document.querySelectorAll('.trace-status')].map(el=>el.textContent.trim()),
          query:document.querySelector('textarea')?.value,
          policy:document.querySelector('.policy-banner')?.textContent,
          humanButtons:[...document.querySelectorAll('button')].filter(el=>/^(Approve|Reject)/.test(el.innerText.trim())).length,
          pending:document.querySelectorAll('.approval-card').length,
          metrics:[...document.querySelectorAll('.metric-name')].map(el=>el.textContent.trim()),
          evidence:document.body.innerText.includes('RETRIEVAL EVIDENCE') && document.body.innerText.includes('EVALUATION CORPUS'),
          arabicDirections:[...document.querySelectorAll('.evidence-title,.evidence-content')].map(el=>el.getAttribute('dir'))
        }))()""")
        require(state["names"] == expected_names and sum(role.startswith("Agent") for role in state["roles"]) == 4, "trace stage or agent semantics differ from the workflow")
        require(state.get("query") == record["original_query"], "saved case query does not match its stored record: " + record["id"])
        require(state["humanButtons"] == 0 and state["pending"] == 0, "saved low-impact record offers a human decision")
        require("Auto-approved by policy" in (state["policy"] or ""), "recorded automatic approval is missing")
        require("Not recorded" in state["statuses"], "missing saved trace stages are shown as executed")
        require(state["evidence"] and all(direction == "auto" for direction in state["arabicDirections"]), "evidence labels or Arabic direction were lost")
        validation = record.get("validation") or {}
        if not any("judge_score" in (validation.get(side) or {}) for side in ("before", "after")):
            require("LLM Judge" not in state["metrics"], "missing judge score was displayed")
        require(record.get("proposal", {}).get("action") in {"rewrite_query", "change_top_k"}, "unexpected action in genuine stored cases")
        clean_layout("action", width, f"action-recorded-{record['id']}.png")
        print(json.dumps({"recorded_case":record["id"], "trace_names":True, "human_controls":False, "actual_sources_only":True}))

    picker_point = browser.evaluate("""(() => {
      const input=document.querySelector('.st-key-case_picker [role=combobox]') || document.querySelector('[role=combobox]');
      const target=input.closest('[data-baseweb=select]') || input;
      target.scrollIntoView({behavior:'instant',block:'center'});
      const box=target.getBoundingClientRect();
      return {x:box.x+box.width/2,y:box.y+box.height/2};
    })()""")
    browser.command("Input.dispatchMouseEvent", {"type":"mouseMoved", **picker_point})
    browser.command("Input.dispatchMouseEvent", {"type":"mousePressed", "button":"left", "clickCount":1, **picker_point})
    browser.command("Input.dispatchMouseEvent", {"type":"mouseReleased", "button":"left", "clickCount":1, **picker_point})
    browser.wait_for("document.querySelectorAll('[role=option]').length > 0")
    options = browser.evaluate("[...document.querySelectorAll('[role=option]')].map(el=>el.innerText.trim())")
    require(len(options) == len(records) + 1 and not any("Chunking Quality" in option or "Structural" in option for option in options), "case picker includes a generated structural workflow; observed " + json.dumps(options))
    browser.command("Input.dispatchKeyEvent", {"type":"keyDown", "key":"Escape", "code":"Escape", "windowsVirtualKeyCode":27})
    browser.command("Input.dispatchKeyEvent", {"type":"keyUp", "key":"Escape", "code":"Escape", "windowsVirtualKeyCode":27})

    for viewport, viewport_height in ((width, height), (390, 844)):
        browser.command("Emulation.setDeviceMetricsOverride", {"width":viewport,"height":viewport_height,"deviceScaleFactor":1,"mobile":False})
        if viewport == 390:
            browser.navigate(f"http://127.0.0.1:{port}/?" + urlencode({"page":"action", "case":records[0]["id"]}))
            browser.wait_for("document.querySelectorAll('.trace-name').length === 7")
            clean_layout("action", viewport, "action-recorded-phone.png")
        browser.navigate(f"http://127.0.0.1:{port}/?page=dashboard")
        browser.wait_for("document.querySelectorAll('.js-plotly-plot').length === 6")
        labels = browser.evaluate("[...document.querySelectorAll('.js-plotly-plot')].flatMap(el => (el.data || []).filter(trace => trace.type === 'pie').map(trace => trace.labels))")
        require(["Improved", "No Meaningful Change", "Worse"] in labels, "Dashboard confuses validation verdicts with approval decisions")
        clean_layout("dashboard", viewport, f"dashboard-verified-{viewport}.png")
        print(json.dumps({"verified_dashboard_width":viewport,"validation_labels":True,"overflow":False}))
    browser.command("Emulation.setDeviceMetricsOverride", {"width":width,"height":height,"deviceScaleFactor":1,"mobile":False})
    print(json.dumps({"action_dashboard_interactions":"passed","saved_cases":len(records),"live_or_approval_buttons_clicked":False}))


def check_final_action_interactions(browser, port, output, width, height, fixture_dir):
    """Inspect captured live results; the only clicked controls are evidence summaries."""
    expected_stages = ["Baseline RAG", "Monitoring", "Diagnosis", "Optimization", "Risk Gate", "Action Executor", "Validation"]
    fixture_files = {"mismatch":"balady_building_permit_001.json", "topk":"absher_driving_license_renewal_002.json",
                     "custom":"custom_unlabelled.json", "reject":"structural_reject.json"}
    fixtures = {case:json.loads((Path(fixture_dir) / name).read_text(encoding="utf-8-sig")) for case,name in fixture_files.items()}

    def require(condition, message, details=None):
        if not condition:
            suffix = "; observed " + json.dumps(details, ensure_ascii=False) if details is not None else ""
            raise RuntimeError("Final Action check failed: " + message + suffix)

    def scroll_to(selector):
        found = browser.evaluate("""((selector) => {
          const target=document.querySelector(selector);
          if(!target) return false;
          target.scrollIntoView({behavior:'instant',block:'start'});
          const scroller=document.querySelector('[data-testid=stMain]');
          const nav=document.querySelector('.ragops-nav-shell')?.getBoundingClientRect().height || 0;
          if(scroller) scroller.scrollTop=Math.max(0,scroller.scrollTop-nav-14);
          return true;
        })(""" + json.dumps(selector) + ")")
        require(found, "missing screenshot target " + selector)
        time.sleep(.3)

    def evidence_summary(which):
        # This selector only identifies native disclosure summaries. It never
        # discovers or clicks Streamlit buttons, including Run/Approve/Reject.
        point = browser.evaluate("""((which) => {
          const root=document.querySelector('.st-key-action_chat_assistant');
          const outer=[...root.querySelectorAll('details')].find(el=>el.querySelector(':scope > summary')?.textContent.includes('View full evidence'));
          const details=which==='outer'?outer:outer?.querySelector('details');
          const summary=details?.querySelector(':scope > summary');
          if(!summary || summary.tagName!=='SUMMARY') return null;
          summary.scrollIntoView({behavior:'instant',block:'center'});
          const box=summary.getBoundingClientRect();
          return {x:box.x+box.width/2,y:box.y+box.height/2};
        })(""" + json.dumps(which) + ")")
        require(point is not None, "missing full-evidence disclosure " + which)
        browser.command("Input.dispatchMouseEvent", {"type":"mouseMoved", **point})
        browser.command("Input.dispatchMouseEvent", {"type":"mousePressed", "button":"left", "clickCount":1, **point})
        browser.command("Input.dispatchMouseEvent", {"type":"mouseReleased", "button":"left", "clickCount":1, **point})

    def cool_color(color):
        # RGB components of neutral/navy/cyan avatars must not be red-dominant.
        import re
        channels = [float(value) for value in re.findall(r"[\d.]+", color)]
        return len(channels) >= 3 and channels[2] >= channels[0] and channels[1] >= channels[0]

    try:
        for viewport, viewport_height in ((width, height), (390, 844)):
            browser.command("Emulation.setDeviceMetricsOverride", {"width":viewport,"height":viewport_height,"deviceScaleFactor":1,"mobile":False})
            for case in ("mismatch", "topk", "custom", "reject"):
                fixture = fixtures[case]
                browser.navigate(f"http://127.0.0.1:{port}/?" + urlencode({"page":"action", "inspect":case}))
                browser.wait_ready()
                browser.wait_for("document.querySelectorAll('.trace-name').length===7 && !!document.querySelector('.st-key-action_chat_assistant .st-key-live_answer_text p') && !!document.querySelector('textarea')?.value")
                browser.wait_for("document.querySelector('textarea')?.value === " + json.dumps(fixture["query"]))
                browser.wait_for("document.fonts.status==='loaded'")
                time.sleep(.35)
                layout = browser.evaluate("""(() => {
                  const userRoot=document.querySelector('.st-key-action_chat_user');
                  const assistantRoot=document.querySelector('.st-key-action_chat_assistant');
                  const user=userRoot.querySelector('[data-testid=stChatMessage]');
                  const assistant=assistantRoot.querySelector('[data-testid=stChatMessage]');
                  const ur=userRoot.getBoundingClientRect(), ar=assistantRoot.getBoundingClientRect();
                  const ub=user.getBoundingClientRect(), ab=assistant.getBoundingClientRect();
                  const avatar=root=>[...root.querySelectorAll('[data-testid^=stChatMessageAvatar]')].map(el=>({background:getComputedStyle(el).backgroundColor,color:getComputedStyle(el).color,icon:el.textContent.trim()}));
                  const answer=[...document.querySelectorAll('.st-key-live_answer_text [data-testid=stMarkdownContainer]')].find(el=>el.querySelector('p,ol,ul'));
                  return {
                    exceptions:document.querySelectorAll('[data-testid=stException]').length,
                    overflow:[document.documentElement,document.body,document.querySelector('[data-testid=stMain]')].filter(Boolean).some(el=>el.scrollWidth>el.clientWidth+2),
                    userRatio:ub.width/ur.width,userRightGap:ur.right-ub.right,assistantLeftGap:ab.left-ar.left,
                    userTextBottomGap:ub.bottom-userRoot.querySelector('[dir=auto]').getBoundingClientRect().bottom,
                    userBackground:getComputedStyle(user).backgroundImage,assistantBackground:getComputedStyle(assistant).backgroundImage,
                    userAvatars:avatar(userRoot),assistantAvatars:avatar(assistantRoot),
                    query:document.querySelector('textarea').value,
                    userDirection:getComputedStyle(userRoot.querySelector('[dir=auto]')).direction,
                    answerDirection:getComputedStyle(answer).direction,
                    sourceChips:[...assistantRoot.querySelectorAll('.action-source-chip')].map(el=>({text:el.textContent.trim(),dir:el.getAttribute('dir')})),
                    excerpts:[...assistantRoot.querySelectorAll('.action-source-excerpt')].map(el=>el.textContent.trim().length),
                    details:[...document.querySelectorAll('.st-key-action_query details,.st-key-action_results details')].map(el=>({open:el.open,label:el.querySelector(':scope > summary')?.textContent.trim()})),
                    stages:[...document.querySelectorAll('.trace-name')].map(el=>el.textContent.trim()),
                    traceDetails:[...document.querySelectorAll('.trace-detail')].map(el=>el.textContent.trim()),
                    traceLabels:[...document.querySelectorAll('.trace-status')].map(el=>el.textContent.trim()),
                    feedback:[...document.querySelectorAll('.action-feedback')].map(el=>el.textContent.trim()),
                    runtime:[...document.querySelectorAll('.action-runtime-badge')].map(el=>el.textContent.trim()),
                    metricCards:document.querySelectorAll('.metric-card').length,verdicts:document.querySelectorAll('.verdict').length,
                    humanButtons:[...document.querySelectorAll('button')].filter(el=>/^(Approve|Reject)/.test(el.innerText.trim())).length,
                    unlabelledNotice:document.body.innerText.includes('Unlabelled query — retrieval quality is not formally validated.'),
                    unsupportedNotice:document.body.innerText.includes('Retrieved evidence does not sufficiently support this query.'),
                    unsafeScript:!!document.querySelector('.st-key-live_answer_text script')
                  };
                })()""")
                label = f"{case} at {viewport}px"
                require(not layout["exceptions"] and not layout["overflow"], label + " has a page exception or horizontal overflow", {key:layout[key] for key in ("exceptions","overflow")})
                require(layout["userRatio"] <= .86 and abs(layout["userRightGap"]) <= 3 and abs(layout["assistantLeftGap"]) <= 3, label + " chat bubbles are not physically right/left aligned", {key:layout[key] for key in ("userRatio","userRightGap","assistantLeftGap")})
                require(layout["userBackground"] != layout["assistantBackground"], label + " user and assistant bubbles look identical")
                require(layout["userTextBottomGap"] >= 5, label + " user text reaches outside its bubble", {"bottomGap":layout["userTextBottomGap"]})
                for role in ("userAvatars", "assistantAvatars"):
                    require(bool(layout[role]), label + " is missing an avatar: " + role)
                    require(all(cool_color(item["background"]) and cool_color(item["color"]) for item in layout[role]), label + " uses a warm avatar color", layout[role])
                require(any("person" in item["icon"] for item in layout["userAvatars"]) and any("smart_toy" in item["icon"] for item in layout["assistantAvatars"]), label + " avatar identities are incorrect")
                if any("\u0600" <= character <= "\u06ff" for character in layout["query"]):
                    require(layout["userDirection"] == "rtl" and layout["answerDirection"] == "rtl", label + " Arabic direction is incorrect", {"user":layout["userDirection"],"answer":layout["answerDirection"]})
                require(not layout["unsafeScript"], label + " rendered model HTML as executable markup")
                require(layout["stages"] == expected_stages and all(not value for value in layout["traceDetails"]), label + " trace stage names or compact details are incorrect")
                require(all(len(value) < 45 for value in layout["traceLabels"]), label + " trace contains long stage text")
                require(all(not item["open"] for item in layout["details"]), label + " full evidence is expanded by default", layout["details"])
                require(all(value <= 210 for value in layout["excerpts"]) and all(item["dir"] == "auto" for item in layout["sourceChips"]), label + " source previews are too long or lose text direction")
                expected_chips = []
                for source in fixture["answer_result"].get("sources") or []:
                    row = source["document"]
                    name = " · ".join(str(value) for value in (str(row["platform"]).title() if row.get("platform") else None, row.get("service") or row.get("source")) if value)
                    expected_chips.append(f'[{source["citation"]}] {name or "Retrieved passage"}')
                require([item["text"] for item in layout["sourceChips"]] == expected_chips, label + " source chips do not match captured answer evidence")
                require(bool(fixture.get("before_run")), label + " fixture lacks completed baseline retrieval supporting the badges")
                require(layout["runtime"] == ["OpenAI ✓","FAISS ✓","Live runtime ✓"], label + " runtime indicators disagree with captured completed retrieval", layout["runtime"])
                require(layout["humanButtons"] == 0, label + " terminal captured run still offers human decisions")
                if case in {"mismatch", "topk"}:
                    require(bool(layout["sourceChips"]) and "Optimized retrieval accepted" in layout["feedback"], label + " is missing accepted answer sources or feedback")
                    require(layout["metricCards"] > 0, label + " is missing recorded evaluation metrics")
                else:
                    require("Baseline retained" in layout["feedback"], label + " did not report baseline retention")
                if case == "custom":
                    require(layout["metricCards"] == 0 and layout["verdicts"] == 0 and layout["unlabelledNotice"], label + " exposes formal unlabelled quality or omits its notice")
                    require(not any(value.lower() in {"improved","worse"} for value in layout["traceLabels"]), label + " exposes an unlabelled validation verdict")
                    rows = (fixture.get("final_run") or {}).get("retrieved_results") or []
                    platforms = {str(row["platform"]).casefold() for row in rows if row.get("platform")}
                    monitoring = fixture.get("monitoring_report") or {}
                    if not rows or all(row.get("relevant") is False for row in rows) or len(platforms) > 1 or monitoring.get("failure_detected") is True or monitoring.get("chunking_signal") is True:
                        require(layout["unsupportedNotice"], label + " omits the recorded insufficient-evidence warning")
                scroll_to(".st-key-action_chat_user")
                screenshot = output / f"action-final-{case}-{viewport}.png"
                browser.screenshot(screenshot)
                print(json.dumps({"final_action_case":case,"width":viewport,"chat_alignment":"passed","rtl":"passed","compact_trace":True,"collapsed_evidence":True,"horizontal_overflow":False,"screenshot":str(screenshot)}), flush=True)
                if case == "mismatch":
                    evidence_summary("outer")
                    browser.wait_for("[...document.querySelectorAll('.st-key-action_chat_assistant details')].some(el=>el.open && el.querySelector(':scope > summary')?.textContent.includes('View full evidence'))")
                    evidence_summary("source")
                    browser.wait_for("[...document.querySelectorAll('.st-key-action_chat_assistant details details')].some(el=>el.open && el.querySelector('.evidence-content')?.textContent.trim())")
                    opened = browser.evaluate("""(() => {
                      const details=[...document.querySelectorAll('.st-key-action_chat_assistant details details')].find(el=>el.open);
                      return {label:details.querySelector(':scope > summary')?.textContent.trim(),content:details.querySelector('.evidence-content')?.textContent.trim(),source:details.querySelector('.query-context')?.textContent.trim()};
                    })()""")
                    require(bool(opened["content"]) and bool(opened["source"]), label + " opened source lacks actual document evidence")
                    first_source = fixture["answer_result"]["sources"][0]["document"]
                    expected_content = first_source.get("content") or first_source.get("page_content") or first_source.get("text")
                    require(" ".join(opened["content"].split()) == " ".join(str(expected_content).split()), label + " opened full evidence does not match the captured source")
                    require(all(str(value) in opened["source"] for value in (first_source.get("service"),first_source.get("source")) if value), label + " opened source metadata differs from the captured document")
                    browser.screenshot(output / f"action-final-evidence-{viewport}.png")
                    print(json.dumps({"final_action_evidence":viewport,"expanded_actual_source":True,"live_or_approval_buttons_clicked":False}), flush=True)
    finally:
        browser.command("Emulation.setDeviceMetricsOverride", {"width":width,"height":height,"deviceScaleFactor":1,"mobile":False})
    print(json.dumps({"final_action_interactions":"passed","captured_cases":4,"viewports":[width,390],"live_or_approval_buttons_clicked":False}), flush=True)


def check_session_navigation(browser, port, output, width, *, clear=False):
    """Follow actual visible links using a preloaded, API-blocked Action run.

    Only local navigation links (and optionally Clear) are activated. A window
    nonce proves that the existing browser document/WebSocket was retained.
    """
    def require(condition, message):
        if not condition:
            raise RuntimeError("Session navigation check failed: " + message)

    headings = {"action":"RAGOps in Action", "dashboard":"Evaluation Evidence",
                "architecture":"Four functional agents", "team":"Meet the Team", "overview":"RAGOps Agent"}

    def wait_page(page):
        browser.wait_for("new URLSearchParams(location.search).get('page') === " + json.dumps(page) +
                         " && document.querySelector('.nav-links a.active')?.getAttribute('href') === " + json.dumps("?page=" + page) +
                         " && document.querySelector('h1')?.textContent.includes(" + json.dumps(headings[page]) +
                         ") && !!document.querySelector('.page-footer')")
        require(browser.evaluate("!document.querySelector('[data-testid=stException]')"), page + " raised an exception")
        require(browser.evaluate("window.__ragopsSessionCheckNonce === " + json.dumps(nonce)), page + " caused a full document reload")
        if page == "action":
            browser.wait_for("!!document.querySelector('.st-key-live_answer_text')?.innerText.trim() && document.querySelectorAll('[data-testid=stChatMessage]').length === 2 && !!document.querySelector('textarea')?.value && document.querySelectorAll('.trace-stage').length === 7")

    def click_link(selector, *, keyboard=False):
        point = browser.evaluate("""((selector) => {
          const link = document.querySelector(selector);
          if (!link || link.tagName !== 'A') return null;
          link.scrollIntoView({block:'nearest', inline:'nearest', behavior:'instant'});
          link.focus({preventScroll:true});
          const box = link.getBoundingClientRect();
          return {x:box.x+box.width/2, y:box.y+box.height/2};
        })(""" + json.dumps(selector) + ")")
        require(point is not None, "navigation link missing: " + selector)
        if keyboard:
            browser.command("Input.dispatchKeyEvent", {"type":"keyDown", "key":"Enter", "code":"Enter", "windowsVirtualKeyCode":13})
            browser.command("Input.dispatchKeyEvent", {"type":"keyUp", "key":"Enter", "code":"Enter", "windowsVirtualKeyCode":13})
        else:
            browser.command("Input.dispatchMouseEvent", {"type":"mouseMoved", **point})
            browser.command("Input.dispatchMouseEvent", {"type":"mousePressed", "button":"left", "clickCount":1, **point})
            browser.command("Input.dispatchMouseEvent", {"type":"mouseReleased", "button":"left", "clickCount":1, **point})

    snapshot_expression = """(() => ({
      query:document.querySelector('textarea')?.value,
      mode:document.querySelector('.st-key-mode_choice input:checked')?.closest('label')?.innerText.trim(),
      answer:document.querySelector('.st-key-live_answer_text')?.innerText.trim(),
      sources:[...document.querySelectorAll('.action-source-chip')].map(el=>el.textContent.trim()),
      trace:[...document.querySelectorAll('.trace-stage')].map(el=>el.textContent.trim()),
      metrics:[...document.querySelectorAll('.metric-card')].map(el=>el.textContent.trim()),
      feedback:document.querySelector('.action-feedback')?.textContent.trim() || '',
      chats:document.querySelectorAll('[data-testid=stChatMessage]').length
    }))()"""
    browser.navigate(f"http://127.0.0.1:{port}/?page=action")
    browser.wait_for("typeof window.__ragopsSessionNavigation === 'function' && !!document.querySelector('.st-key-live_answer_text')?.innerText.trim()")
    nonce = f"navigation-check-{time.monotonic_ns()}"
    browser.evaluate("window.__ragopsSessionCheckNonce = " + json.dumps(nonce))
    wait_page("action")
    expected = browser.evaluate(snapshot_expression)
    require(expected["answer"] and expected["query"] and expected["sources"] and expected["mode"], "an answered captured run with sources and mode must be preloaded")
    require(browser.evaluate("(() => {const bridge=document.querySelector('.st-key-session_navigation');return !!bridge && getComputedStyle(bridge).display === 'none' && bridge.getBoundingClientRect().height === 0})()"), "hidden navigation controls affect layout")
    require(browser.evaluate("[...document.querySelectorAll('.nav-links a')].map(el=>el.textContent.trim()).join('|')") == "Overview|RAGOps in Action|Dashboard|Architecture|Team", "five-page navigation labels changed")
    for page in ("dashboard", "architecture", "team", "overview"):
        click_link('.nav-links a[href="?page=' + page + '"]', keyboard=page == "team")
        wait_page(page)
        click_link('.nav-links a[href="?page=action"]')
        wait_page("action")
        require(browser.evaluate(snapshot_expression) == expected, page + " round trip changed the active run or draft")
        print(json.dumps({"session_round_trip":page, "document_retained":True, "run_unchanged":True, "keyboard":page == "team"}), flush=True)
    click_link('.nav-links a[href="?page=overview"]')
    wait_page("overview")
    click_link('.hero-btn.primary[href="?page=action"]')
    wait_page("action")
    require(browser.evaluate(snapshot_expression) == expected, "Overview Run RAGOps link changed the active run")
    require(browser.evaluate("![document.documentElement,document.body,document.querySelector('[data-testid=stMain]')].filter(Boolean).some(el=>el.scrollWidth>el.clientWidth+2)"), "Action has horizontal overflow")
    browser.screenshot(output / f"session-preserved-{width}.png")
    if clear:
        clicked = browser.evaluate("(()=>{const button=[...document.querySelectorAll('.st-key-action_query button')].find(el=>el.innerText.trim()==='Clear');if(!button)return false;button.click();return true})()")
        require(clicked, "Clear control is unavailable")
        browser.wait_for("!document.querySelector('[data-testid=stChatMessage]') && !document.querySelector('.action-source-chip') && document.querySelector('textarea')?.value === '' && !!document.querySelector('.page-footer')")
        require(browser.evaluate("window.__ragopsSessionCheckNonce === " + json.dumps(nonce)), "Clear caused a document reload")
        browser.screenshot(output / f"session-cleared-{width}.png")
    print(json.dumps({"session_navigation":"passed", "four_page_round_trips":True, "keyboard_enter":True,
                      "overview_hero":True, "clear_checked":clear, "live_or_approval_buttons_clicked":False}), flush=True)


def check_conversation(browser, port, output, width, height, fixture_path=None):
    """Inspect a preloaded three-turn conversation with live callbacks blocked.

    Only navigation, a suggestion chip, and New Chat are activated. No message
    submission, model call, workflow, or approval action is requested here.
    """
    fixture = json.loads(Path(fixture_path).read_text(encoding="utf-8")) if fixture_path else {}
    messages = fixture.get("chat_history") or []
    expected_count = len(messages) or 6
    message_selector = '.st-key-action_conversation [data-testid="stChatMessage"]'
    snapshot_expression = r"""(() => ({
      messages:[...document.querySelectorAll('.st-key-action_conversation [data-testid=stChatMessage]')].map(el=>{
        const answer=[...el.querySelectorAll('[class*="st-key-live_answer_text"] [data-testid=stMarkdownContainer]')].find(node=>node.querySelector('p,ul,ol'));
        return (answer || el.querySelector('[dir=auto]'))?.textContent.trim() || '';
      }),
      sources:[...document.querySelectorAll('.action-source-chip')].map(el=>el.textContent.trim()),
      trace:[...document.querySelectorAll('.trace-stage')].map(el=>el.innerText.trim()),
      metrics:[...document.querySelectorAll('.metric-card')].map(el=>el.innerText.trim()),
      feedback:[...document.querySelectorAll('.action-feedback')].map(el=>el.innerText.trim())
    }))()"""

    def require(condition, message, details=None):
        if not condition:
            extra = "; observed " + json.dumps(details, ensure_ascii=False) if details is not None else ""
            raise RuntimeError("Conversation check failed: " + message + extra)

    def wait_idle():
        browser.wait_for("!!document.querySelector('[data-test-script-state]') && !document.querySelector('[data-test-script-state=running]')")

    def wait_conversation():
        browser.wait_for("document.querySelectorAll(" + json.dumps(message_selector) + ").length === " + str(expected_count) +
                         " && document.querySelectorAll('.trace-stage').length === 7 && !!document.querySelector('.st-key-action_composer textarea') && !!document.querySelector('.st-key-action_validation') && !!document.querySelector('.page-footer')")
        browser.wait_for("document.fonts.status === 'loaded'")
        wait_idle()

    def snapshot():
        # Streamlit can mount the panel before delivering its metric cards.
        # Wait for script completion and a stable DOM snapshot before comparing.
        wait_idle()
        previous = browser.evaluate(snapshot_expression)
        for _ in range(20):
            time.sleep(.15)
            wait_idle()
            current = browser.evaluate(snapshot_expression)
            if current == previous:
                return current
            previous = current
        return previous

    def snapshot_difference(expected, actual):
        # Report only changed fields/counts, never entire generated answers.
        return {key:{"expected_count":len(expected[key]), "actual_count":len(actual.get(key, [])),
                     "different_positions":[index for index, (before, after) in enumerate(zip(expected[key], actual.get(key, []))) if before != after][:8]}
                for key in expected if expected[key] != actual.get(key)}

    def click_allowed(selector):
        # Selectors are fixed within this checker; there is deliberately no
        # helper that searches for arbitrary action labels or submit buttons.
        allow = ('.nav-links a[href="?page=dashboard"]', '.nav-links a[href="?page=action"]',
                 '.st-key-action_suggestions button[data-testid^="stBaseButton-"]', '.st-key-new_chat button')
        require(selector in allow, "unsafe control selector")
        clicked = browser.evaluate("((selector)=>{const el=[...document.querySelectorAll(selector)].find(el=>el.checkVisibility({checkVisibilityCSS:true,checkOpacity:true}));if(!el)return false;el.scrollIntoView({behavior:'instant',block:'center',inline:'nearest'});el.click();return true})(" + json.dumps(selector) + ")")
        require(clicked, "missing control " + selector)

    def screenshot_at(selector, filename):
        browser.evaluate("((selector)=>{const el=document.querySelector(selector);el?.scrollIntoView({behavior:'instant',block:'start'});const main=document.querySelector('[data-testid=stMain]');if(main)main.scrollTop=Math.max(0,main.scrollTop-(document.querySelector('.ragops-nav-shell')?.getBoundingClientRect().height||0)-12)})(" + json.dumps(selector) + ")")
        time.sleep(.25)
        browser.screenshot(output / filename)

    try:
        for viewport, viewport_height in ((width, height), (390, 844)):
            browser.command("Emulation.setDeviceMetricsOverride", {"width":viewport,"height":viewport_height,"deviceScaleFactor":1,"mobile":False})
            browser.navigate(f"http://127.0.0.1:{port}/?page=action")
            wait_conversation()
            time.sleep(.3)
            layout = browser.evaluate(r"""(() => {
              const bounds=el=>{const b=el.getBoundingClientRect();return {left:b.left,right:b.right,top:b.top,bottom:b.bottom,width:b.width,height:b.height}};
              const roots=[...document.querySelectorAll('.st-key-action_conversation [class*="st-key-action_chat_"]')];
              const userRoots=roots.filter(el=>el.className.includes('st-key-action_chat_user'));
              const assistantRoots=roots.filter(el=>el.className.includes('st-key-action_chat_assistant'));
              const query=document.querySelector('.st-key-action_query'),results=document.querySelector('.st-key-action_results');
              const conversation=document.querySelector('.st-key-action_conversation'),suggestions=document.querySelector('.st-key-action_suggestions'),composer=document.querySelector('.st-key-action_composer'),validation=document.querySelector('.st-key-action_validation');
              const suggestionRow=suggestions.querySelector('[data-testid=stHorizontalBlock]');
              const visible=el=>el.checkVisibility({checkVisibilityCSS:true,checkOpacity:true});
              return {
                exceptions:document.querySelectorAll('[data-testid=stException]').length,
                overflow:[document.documentElement,document.body,document.querySelector('[data-testid=stMain]')].filter(Boolean).some(el=>el.scrollWidth>el.clientWidth+2),
                roles:roots.map(el=>el.className.includes('st-key-action_chat_user')?'user':'assistant'),
                users:userRoots.map(root=>{const msg=root.querySelector('[data-testid=stChatMessage]'),content=root.querySelector('[dir=auto]'),rb=bounds(root),mb=bounds(msg);return {rightGap:rb.right-mb.right,ratio:mb.width/rb.width,direction:getComputedStyle(content).direction,text:content.textContent.trim()}}),
                assistants:assistantRoots.map(root=>{const msg=root.querySelector('[data-testid=stChatMessage]'),answer=[...root.querySelectorAll('[class*="st-key-live_answer_text"] [data-testid=stMarkdownContainer]')].find(el=>el.querySelector('p,ul,ol'));return {leftGap:bounds(msg).left-bounds(root).left,direction:answer?getComputedStyle(answer).direction:null,text:answer?.textContent.trim(),sources:[...root.querySelectorAll('.action-source-chip')].map(el=>el.textContent.trim()),excerpts:[...root.querySelectorAll('.action-source-excerpt')].map(el=>el.textContent.trim()),details:[...root.querySelectorAll('details')].map(el=>({open:el.open,label:el.querySelector(':scope > summary')?.textContent.trim()}))}}),
                panels:{query:bounds(query),results:bounds(results),conversation:bounds(conversation),suggestions:bounds(suggestions),composer:bounds(composer),validation:bounds(validation)},
                suggestionCount:[...suggestions.querySelectorAll('button[data-testid^="stBaseButton-"]')].filter(visible).length,
                suggestionControls:[...suggestions.querySelectorAll('button')].slice(0,12).map(el=>({label:el.innerText.trim().slice(0,100),testid:el.dataset.testid||'',kind:el.getAttribute('kind')||'',visible:visible(el),visibility:getComputedStyle(el).visibility,display:getComputedStyle(el).display})),
                suggestionScroll:{width:suggestionRow.clientWidth,scrollWidth:suggestionRow.scrollWidth,overflow:getComputedStyle(suggestionRow).overflowX},
                traceScroll:{width:results.querySelector('.trace-ribbon').clientWidth,scrollWidth:results.querySelector('.trace-ribbon').scrollWidth,overflow:getComputedStyle(results.querySelector('.trace-ribbon')).overflowX},
                traceNames:[...document.querySelectorAll('.trace-name')].map(el=>el.textContent.trim()),
                traceLabels:[...document.querySelectorAll('.trace-status')].map(el=>el.textContent.trim()),
                metrics:validation.querySelectorAll('.metric-card').length,
                metricColumns:validation.querySelector('.metric-grid')?getComputedStyle(validation.querySelector('.metric-grid')).gridTemplateColumns.split(' ').length:0,
                details:[...document.querySelectorAll('.st-key-action_query details,.st-key-action_results details')].map(el=>({open:el.open,label:el.querySelector(':scope > summary')?.textContent.trim()})),
                humanButtons:[...document.querySelectorAll('button')].filter(el=>/^(Approve Optimization|Reject \/ Keep Baseline)$/.test(el.innerText.trim())).length,
                modeLabels:[...document.querySelectorAll('.st-key-mode_choice [role=radiogroup] label')].map(el=>el.innerText.trim()),
                selectedMode:document.querySelector('.st-key-mode_choice input:checked')?.closest('label')?.innerText.trim()
              };
            })()""")
            label = f"{viewport}px"
            require(not layout["exceptions"] and not layout["overflow"], label + " has a render exception or page overflow", layout)
            require(layout["roles"] == ["user", "assistant"] * (expected_count // 2), label + " chronological conversation roles differ", layout["roles"])
            require(all(abs(row["rightGap"]) <= 3 and row["ratio"] <= .86 for row in layout["users"]), label + " user messages are not right-aligned", layout["users"])
            require(all(abs(row["leftGap"]) <= 3 and row["text"] for row in layout["assistants"]), label + " assistant messages are not left-aligned or are blank", layout["assistants"])
            import unicodedata
            for row in layout["users"] + layout["assistants"]:
                strong = next((unicodedata.bidirectional(char) for char in row["text"] if unicodedata.bidirectional(char) in {"L", "R", "AL"}), "L")
                require(row["direction"] == ("rtl" if strong in {"R", "AL"} else "ltr"), label + " message direction differs from its language")
            require(all(row["sources"] and row["excerpts"] and all(len(excerpt) <= 210 for excerpt in row["excerpts"]) for row in layout["assistants"]), label + " source chips or short excerpts missing")
            require(all(not item["open"] for item in layout["details"]), label + " evidence or technical disclosures expanded by default")
            require(all(any("View full evidence" in item["label"] for item in row["details"]) for row in layout["assistants"]), label + " answer lacks full-evidence disclosure")
            require(3 <= layout["suggestionCount"] <= 4, label + " suggestion count must be 3-4", {"count":layout["suggestionCount"],"controls":layout["suggestionControls"]})
            boxes = layout["panels"]
            require(boxes["conversation"]["bottom"] <= boxes["suggestions"]["top"] + 3 and boxes["suggestions"]["bottom"] <= boxes["composer"]["top"] + 3, label + " suggestions/composer do not follow the chat", boxes)
            require(boxes["validation"]["top"] >= max(boxes["query"]["bottom"], boxes["results"]["bottom"]) - 3, label + " validation is not below the main panels", boxes)
            if viewport > 1100:
                require(abs(boxes["validation"]["left"] - boxes["query"]["left"]) <= 3 and abs(boxes["validation"]["right"] - boxes["results"]["right"]) <= 3, label + " validation does not span both panels", boxes)
                require(not layout["metrics"] or layout["metricColumns"] == 5, label + " expected five desktop metric columns")
            else:
                require(layout["suggestionScroll"]["scrollWidth"] > layout["suggestionScroll"]["width"] and layout["suggestionScroll"]["overflow"] == "auto", label + " suggestion chips are not horizontally scrollable", layout["suggestionScroll"])
                require(layout["traceScroll"]["overflow"] == "auto", label + " compact trace cannot scroll")
                require(not layout["metrics"] or layout["metricColumns"] == 1, label + " expected one mobile metric column")
            require(layout["traceNames"] == ["Baseline RAG", "Monitoring", "Diagnosis", "Optimization", "Risk Gate", "Action Executor", "Validation"], label + " trace must contain seven latest-turn stages", layout["traceNames"])
            require(layout["selectedMode"] == "Live Run" and layout["modeLabels"] == ["Live Run", "View Saved Runs"], label + " runtime modes differ", layout["modeLabels"])
            require(layout["humanButtons"] == 0, label + " terminal captured run unexpectedly displays approval buttons")
            if messages:
                expected_users = [message for message in messages if message["role"] == "user"]
                expected_answers = [message for message in messages if message["role"] == "assistant"]
                require([row["text"] for row in layout["users"]] == [message["content"] for message in expected_users], label + " original user messages changed")
                for row, message in zip(layout["assistants"], expected_answers):
                    sources = message.get("sources") or []
                    require(len(row["sources"]) == len(sources), label + " per-answer source count differs from captured evidence")
                    for chip, source in zip(row["sources"], sources):
                        document = source["document"]
                        require(str(source["citation"]) in chip and all(str(value).casefold() in chip.casefold() for value in (document.get("platform"), document.get("service") or document.get("source")) if value), label + " source chip differs from captured metadata")
                latest = fixture.get("current_run") or {}
                action = (latest.get("optimization_proposal") or {}).get("action")
                action_label = {"rewrite_query":"Rewrite query", "change_top_k":"Change Top-K", "rechunk_and_reindex":"Re-chunk & re-index"}.get(action)
                if action_label:
                    require(layout["traceLabels"][3] == action_label, label + " trace shows an earlier turn's optimization", layout["traceLabels"])
            screenshot_at(".st-key-action_query", f"conversation-{viewport}.png")
            screenshot_at(".st-key-action_validation", f"conversation-validation-{viewport}.png")

            nonce = f"conversation-{viewport}-{time.monotonic_ns()}"
            browser.evaluate("window.__ragopsConversationNonce=" + json.dumps(nonce))
            expected = snapshot()
            browser.wait_for("typeof window.__ragopsSessionNavigation === 'function'")
            click_allowed('.nav-links a[href="?page=dashboard"]')
            browser.wait_for("new URLSearchParams(location.search).get('page')==='dashboard' && document.querySelector('h1')?.textContent.includes('Evaluation Evidence') && !!document.querySelector('.page-footer')")
            wait_idle()
            require(browser.evaluate("window.__ragopsConversationNonce === " + json.dumps(nonce)), label + " Dashboard navigation reloads the document")
            click_allowed('.nav-links a[href="?page=action"]')
            wait_conversation()
            require(browser.evaluate("window.__ragopsConversationNonce === " + json.dumps(nonce)), label + " returning to Action reloads the document")
            returned = snapshot()
            require(returned == expected, label + " Dashboard round trip changed conversation, trace, or metrics", snapshot_difference(expected, returned))

            suggestion = browser.evaluate("[...document.querySelectorAll('.st-key-action_suggestions button[data-testid^=stBaseButton-]')].find(el=>el.checkVisibility({checkVisibilityCSS:true,checkOpacity:true}))?.innerText.trim()")
            click_allowed('.st-key-action_suggestions button[data-testid^="stBaseButton-"]')
            browser.wait_for("document.querySelector('.st-key-action_composer textarea')?.value === " + json.dumps(suggestion))
            wait_conversation()
            suggested = snapshot()
            require(suggested == expected, label + " selecting a suggestion changed the conversation or current run", snapshot_difference(expected, suggested))
            screenshot_at(".st-key-action_suggestions", f"conversation-composer-{viewport}.png")
            click_allowed('.st-key-new_chat button')
            browser.wait_for("!document.querySelector('.st-key-action_conversation [data-testid=stChatMessage]') && !document.querySelector('.action-source-chip') && document.querySelector('.st-key-action_composer textarea')?.value === '' && document.querySelectorAll('.trace-stage').length === 7 && !document.querySelector('.st-key-action_validation')")
            wait_idle()
            require(browser.evaluate("[...document.querySelectorAll('.trace-status')].every(el=>el.innerText.trim()==='Waiting')"), label + " New Chat does not reset the trace")
            require(browser.evaluate("window.__ragopsConversationNonce === " + json.dumps(nonce)), label + " New Chat reloads the document")
            print(json.dumps({"conversation": "passed", "width":viewport, "messages":expected_count,
                              "rtl":True, "source_references":True, "latest_trace":True,
                              "dashboard_round_trip":True, "suggestion_preserves_history":True,
                              "new_chat_clears":True, "live_or_approval_buttons_clicked":False}), flush=True)
    finally:
        browser.command("Emulation.setDeviceMetricsOverride", {"width":width,"height":height,"deviceScaleFactor":1,"mobile":False})


def check_dashboard_interactions(browser, port, output, width, height):
    """Inspect only official stored Dashboard results at desktop/phone widths.

    The test reads Plotly's rendered traces and disclosure state. It never
    leaves Dashboard, submits a question, or invokes a backend operation.
    """
    evaluation = Path(__file__).resolve().parents[1] / "evaluation"
    retrieval = json.loads((evaluation / "retrieval_results_v2.json").read_text(encoding="utf-8"))
    workflow = json.loads((evaluation / "real_failure_workflow_results.json").read_text(encoding="utf-8"))
    stored_platforms = retrieval["summary"]["by_platform"]

    def require(condition, message, details=None):
        if not condition:
            raise RuntimeError("Dashboard check failed: " + message + (" " + json.dumps(details) if details is not None else ""))

    def screenshot_at(selector, name):
        browser.evaluate("""((selector) => {
          const target=document.querySelector(selector), main=document.querySelector('[data-testid=stMain]');
          target.scrollIntoView({behavior:'instant',block:'start'});
          const navBottom=document.querySelector('.ragops-nav-shell')?.getBoundingClientRect().bottom || 0;
          const adjustment=target.getBoundingClientRect().top - navBottom - 12;
          if(main) main.scrollBy({top:adjustment,behavior:'instant'});
          else window.scrollBy({top:adjustment,behavior:'instant'});
        })(""" + json.dumps(selector) + ")")
        time.sleep(.15)
        browser.screenshot(output / name)

    try:
        for viewport, viewport_height in ((width, height), (390, 844)):
            browser.command("Emulation.setDeviceMetricsOverride", {"width":viewport, "height":viewport_height, "deviceScaleFactor":1, "mobile":False})
            browser.navigate(f"http://127.0.0.1:{port}/?page=dashboard")
            browser.wait_for("document.querySelectorAll('.st-key-dashboard_official .js-plotly-plot .main-svg').length >= 6 && !!document.querySelector('.st-key-inspector')")
            time.sleep(.4)
            browser.screenshot(output / f"dashboard-initial-{viewport}.png")
            layout = browser.evaluate("""(() => {
              const box = el => el.getBoundingClientRect().toJSON();
              const keys = ['platform','failures','outcomes','compare','latency','chunking'];
              return {
                exceptions:[...document.querySelectorAll('[data-testid=stException]')].map(el=>el.innerText),
                overflow:[document.documentElement,document.body,document.querySelector('[data-testid=stMain]')].filter(Boolean).some(el=>el.scrollWidth>el.clientWidth+2),
                kpis:[...document.querySelectorAll('.st-key-dashboard_snapshot .kpi')].map(el=>({
                  label:el.querySelector('.label')?.textContent.trim(), value:el.querySelector('.value')?.textContent.trim(),
                  box:box(el), font:parseFloat(getComputedStyle(el.querySelector('.value')).fontSize),
                  clipped:el.scrollWidth>el.clientWidth+2
                })),
                charts:keys.map(key=>{
                  const panel=document.querySelector('.st-key-chart_'+key), plot=panel.querySelector('.js-plotly-plot');
                  const legends=[...plot.querySelectorAll('.legend .traces')].map(box);
                  const ticks=[...plot.querySelectorAll('.xtick text,.ytick text,.legendtext')].map(el=>({text:el.textContent,box:box(el)}));
                  return {key,panel:box(panel),plot:box(plot),legends,ticks,
                    htmlLegend:[...panel.querySelectorAll('.dashboard-chart-legend>span')].map(el=>({text:el.innerText.trim(),box:box(el)})),
                    traces:plot.data.map(trace=>({type:trace.type,name:trace.name,x:trace.x,y:trace.y,labels:trace.labels,values:trace.values,customdata:trace.customdata}))};
                }),
                history:box(document.querySelector('.st-key-history')),
                historyViews:{
                  desktop:document.querySelector('.st-key-dashboard_history_desktop')?.checkVisibility({checkVisibilityCSS:true,checkOpacity:true}) || false,
                  mobile:document.querySelector('.st-key-dashboard_history_mobile')?.checkVisibility({checkVisibilityCSS:true,checkOpacity:true}) || false,
                  mobileRows:document.querySelectorAll('.st-key-dashboard_history_mobile details').length
                },
                inspector:box(document.querySelector('.st-key-inspector')),
                details:[...document.querySelectorAll('.st-key-inspector details')].map(el=>({open:el.open,label:el.querySelector(':scope > summary')?.textContent.trim()})),
                hasLive:!!document.querySelector('.st-key-dashboard_live_run'),
                nav:[...document.querySelectorAll('.nav-links a')].map(el=>el.textContent.trim())
              };
            })()""")
            require(not layout["exceptions"] and not layout["overflow"], "render exception or page overflow", {"width":viewport,"exceptions":layout["exceptions"],"overflow":layout["overflow"]})
            require([(item["label"], item["value"]) for item in layout["kpis"]] == [
                ("Evaluation Queries", "48"), ("Platforms", "4"), ("Baseline Failures", "5"),
                ("Verified Labelled Failures Improved", "5/5"), ("Baseline Recall@4", "89.6%"),
            ], "official snapshot differs from stored totals", layout["kpis"])
            require(all(not item["clipped"] and item["font"] >= 20 for item in layout["kpis"]), "snapshot is clipped or too small", layout["kpis"])
            charts = {chart["key"]: chart for chart in layout["charts"]}
            require(len(charts) == 6, "expected six supported charts")
            for key, chart in charts.items():
                require(chart["plot"]["width"] >= 250 and chart["plot"]["height"] >= 200, "chart is too narrow or short", {"width":viewport,"chart":key,"box":chart["plot"]})
                for item in chart["htmlLegend"]:
                    require(item["box"]["left"] >= chart["panel"]["left"] and item["box"]["right"] <= chart["panel"]["right"],
                            "wrapping chart legend escapes its panel", {"width":viewport,"chart":key,"legend":item})
                for tick in chart["ticks"]:
                    require(tick["box"]["left"] >= chart["plot"]["left"] - 4 and tick["box"]["right"] <= chart["plot"]["right"] + 4,
                            "chart label escapes its plot", {"width":viewport,"chart":key,"tick":tick})
                for index, first in enumerate(chart["legends"]):
                    for second in chart["legends"][index + 1:]:
                        overlap_x = min(first["right"], second["right"]) - max(first["left"], second["left"])
                        overlap_y = min(first["bottom"], second["bottom"]) - max(first["top"], second["top"])
                        require(overlap_x <= 1 or overlap_y <= 1, "chart legends overlap", {"width":viewport,"chart":key})
            for trace in charts["platform"]["traces"]:
                metric = {"Recall@4":"recall_at_k", "Precision@4":"precision_at_k", "MRR":"mrr"}[trace["name"]]
                require(trace["x"] == ["Absher", "Balady", "Najiz", "Sakani"], "platform order differs")
                require(trace["y"] == [stored_platforms[platform.casefold()][metric] for platform in trace["x"]], "platform data differs from artifact")
            outcome = charts["outcomes"]["traces"][0]
            require(outcome["labels"] == ["Improved", "No Meaningful Change", "Worse"] and outcome["values"] == [5,0,0], "validation chart includes non-verdicts or unsupported counts")
            failures = charts["failures"]["traces"][0]
            require(dict(zip(failures["labels"], failures["values"])) == {"Query Mismatch":4,"Top-K Retrieval":1,"Chunking Quality":0}, "failure chart invents causes")
            for key in ("failures", "outcomes"):
                require(len(charts[key]["htmlLegend"]) == 3, "zero-count chart categories are hidden", {"chart":key})
            for trace in charts["latency"]["traces"]:
                require(trace["x"] == [f"Run {index}" for index in range(1,6)], "latency run labels are not compact")
                require(trace["customdata"] == [row["id"] for row in workflow["results"]], "latency hover omits actual case IDs")
            require(len(layout["details"]) >= 2 and all(not item["open"] for item in layout["details"]), "inspector raw evidence should be collapsed", layout["details"])
            require(any("Retrieved evidence" in item["label"] for item in layout["details"]) and any("Technical state" in item["label"] for item in layout["details"]), "inspector disclosures missing", layout["details"])
            require(layout["history"]["width"] >= viewport * .80 and layout["inspector"]["width"] >= viewport * .80, "history/inspector do not use the available width")
            require(layout["nav"] == ["Overview","RAGOps in Action","Dashboard","Architecture","Team"], "navigation changed")
            require(layout["historyViews"]["mobile"] == (viewport <= 800) and layout["historyViews"]["desktop"] == (viewport > 800),
                    "responsive history view does not match the viewport", layout["historyViews"])
            require(layout["historyViews"]["mobileRows"] == len(workflow["results"]), "mobile history does not contain every stored run")
            screenshot_at(".st-key-dashboard_snapshot", f"dashboard-snapshot-{viewport}.png")
            screenshot_at(".st-key-chart_platform", f"dashboard-platform-{viewport}.png")
            screenshot_at(".st-key-dashboard_compare_metrics", f"dashboard-comparison-{viewport}.png")
            screenshot_at(".st-key-history", f"dashboard-history-{viewport}.png")
            if viewport <= 800:
                case = workflow["results"][1]
                official_before = browser.evaluate("JSON.stringify({kpis:[...document.querySelectorAll('.st-key-dashboard_snapshot .kpi')].map(el=>el.innerText),plots:[...document.querySelectorAll('.st-key-dashboard_official .js-plotly-plot')].map(el=>el.data)})")
                browser.evaluate("document.querySelectorAll('.st-key-dashboard_history_mobile details')[1].querySelector('summary').click()")
                button = ".st-key-dashboard_inspect_" + case["id"] + " button"
                browser.wait_for("document.querySelector(" + json.dumps(button) + ")?.checkVisibility({checkVisibilityCSS:true,checkOpacity:true})")
                browser.evaluate("document.querySelector(" + json.dumps(button) + ").click()")
                browser.wait_for("document.querySelector('.dashboard-inspector-query p')?.textContent.trim() === " + json.dumps(case["original_query"]))
                browser.wait_for("!!document.querySelector('[data-test-script-state]') && !document.querySelector('[data-test-script-state=running]')")
                official_after = browser.evaluate("JSON.stringify({kpis:[...document.querySelectorAll('.st-key-dashboard_snapshot .kpi')].map(el=>el.innerText),plots:[...document.querySelectorAll('.st-key-dashboard_official .js-plotly-plot')].map(el=>el.data)})")
                require(official_after == official_before, "mobile case inspection changed official charts or KPIs")
                screenshot_at(".st-key-dashboard_history_mobile", f"dashboard-mobile-history-open-{viewport}.png")
            screenshot_at(".st-key-inspector", f"dashboard-inspector-{viewport}.png")
            print(json.dumps({"dashboard_interactions":"passed", "width":viewport, "official_kpis":True,
                              "stored_chart_values":True, "validation_decision_separation":True,
                              "charts":6, "disclosures_collapsed":True, "horizontal_page_overflow":False,
                              "latest_live_panel_present":layout["hasLive"], "backend_operations":False}), flush=True)
    finally:
        browser.command("Emulation.setDeviceMetricsOverride", {"width":width,"height":height,"deviceScaleFactor":1,"mobile":False})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8502)
    parser.add_argument("--width", type=int, default=1672)
    parser.add_argument("--height", type=int, default=1120)
    parser.add_argument("--page", choices=["overview","action","dashboard","architecture","team"])
    parser.add_argument("--diagnostics", action="store_true")
    parser.add_argument("--states", action="store_true", help="Alias for read-only Action / Dashboard saved-case checks")
    parser.add_argument("--action-dashboard-interactions", action="store_true", help="Check readiness modes and five real saved cases, plus Action / Dashboard at desktop and phone widths; never run live")
    parser.add_argument("--dashboard-interactions", action="store_true", help="Check only official Dashboard totals, chart evidence and desktop/phone readability; never execute the backend")
    parser.add_argument("--final-action-interactions", action="store_true", help="Inspect captured Action fixtures only, including chat, RTL, evidence disclosures, trace, feedback, and desktop/phone layouts; never run live or decide approval")
    parser.add_argument("--session-navigation", action="store_true", help="Check visible navbar and hero navigation preserves a preloaded answered Action run in the same document; never run live or decide approval")
    parser.add_argument("--session-clear", action="store_true", help="Also test explicit Clear after --session-navigation checks")
    parser.add_argument("--conversation", action="store_true", help="Check a preloaded three-turn Action conversation, latest trace/validation, mobile chips, navigation persistence, and New Chat; never send or approve")
    parser.add_argument("--conversation-fixture", help="Optional JSON with captured chat_history and current_run for exact conversation/source checks")
    parser.add_argument("--action-fixtures-dir", default=str(Path(tempfile.gettempdir()) / "ragops-action-final"), help="Directory containing captured terminal Action runs for --final-action-interactions")
    parser.add_argument("--overview-interactions", action="store_true", help="Check Overview motion, accessibility, and saved-case card navigation")
    parser.add_argument("--architecture-team-interactions", action="store_true", help="Check architecture route previews, team links and hover, phone layouts, and reduced motion")
    parser.add_argument("--architecture-interactions", action="store_true", help="Check only Architecture compactness, policy routes, Shared State expander, phone layout, and reduced motion")
    parser.add_argument("--responsive", action="store_true", help="Also capture all pages at phone width")
    parser.add_argument("--output", default=str(Path(tempfile.gettempdir()) / "ragops-ui-previews"))
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    chrome = Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Google/Chrome/Application/chrome.exe"
    profile = tempfile.mkdtemp(prefix="ragops-browser-")
    debug_port = 9231
    process = subprocess.Popen([
        str(chrome), "--headless=new", f"--remote-debugging-port={debug_port}", f"--user-data-dir={profile}",
        "--no-first-run", "--no-default-browser-check", "--disable-background-networking", "--disable-sync",
        "--disable-extensions", "--disable-component-update", "--disable-default-apps", "--metrics-recording-only",
        "--disable-features=MediaRouter,OptimizationHints", "about:blank",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
    browser = None
    try:
        tabs = None
        for _ in range(60):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{debug_port}/json", timeout=1) as response:
                    tabs = json.load(response)
                break
            except OSError:
                if process.poll() is not None:
                    raise RuntimeError("Headless Chrome could not start") from None
                time.sleep(.25)
        if not tabs:
            raise RuntimeError("Chrome debugging endpoint unavailable")
        page = next(tab for tab in tabs if tab["type"] == "page")
        browser = Browser(page["webSocketDebuggerUrl"])
        browser.command("Page.enable")
        browser.command("Network.enable")
        browser.command("Network.setBlockedURLs", {"urls":["https://*"]})
        browser.command("Emulation.setDeviceMetricsOverride", {"width":args.width,"height":args.height,"deviceScaleFactor":1,"mobile":False})
        pages = [] if args.final_action_interactions or args.session_navigation or args.conversation or args.dashboard_interactions else [args.page] if args.page else ["architecture"] if args.architecture_interactions else ["action","dashboard"] if args.action_dashboard_interactions or args.states else ["overview","action","dashboard","architecture","team"]
        for name in pages:
            browser.navigate(f"http://127.0.0.1:{args.port}/?page={name}")
            browser.wait_ready()
            if name == "dashboard":
                for _ in range(60):
                    if browser.evaluate("document.querySelectorAll('.js-plotly-plot .main-svg').length >= 6"):
                        break
                    time.sleep(.25)
            time.sleep(1)
            errors = browser.evaluate("document.querySelectorAll('[data-testid=stException]').length")
            overflow = browser.evaluate("[document.documentElement,document.body,document.querySelector('[data-testid=stMain]')].filter(Boolean).some(el=>el.scrollWidth>el.clientWidth+2)")
            if args.diagnostics:
                if name == "architecture":
                    print(json.dumps(browser.evaluate("""(() => {
                      const chain=[];
                      for(let element=document.querySelector('.ragops-nav-shell');element&&chain.length<8;element=element.parentElement){
                        const style=getComputedStyle(element),box=element.getBoundingClientRect();
                        chain.push({test:element.dataset.testid,tag:element.tagName,classes:element.className,
                          top:box.top,height:box.height,display:style.display,position:style.position,
                          css_height:style.height,min_height:style.minHeight,max_height:style.maxHeight,
                          flex:style.flex,margin:style.margin,padding:style.padding,gap:style.gap,overflow:style.overflow});
                      }
                      return {architecture_nav_ancestors:chain};
                    })()""")))
                layout = browser.evaluate("JSON.stringify({rootFont:getComputedStyle(document.documentElement).fontSize,headings:Array.from(document.querySelectorAll('h1')).map(el=>({font:getComputedStyle(el).fontSize,family:getComputedStyle(el).fontFamily,box:el.getBoundingClientRect().toJSON()})),panels:Array.from(document.querySelectorAll('.st-key-action_query,.st-key-action_results')).map(el=>({element:el.outerHTML.slice(0,450),parent:el.parentElement.outerHTML.slice(0,450)}))})")
                print(layout)
            preview = output / f"{name}-{args.width}.png"
            browser.screenshot(preview)
            print(json.dumps({"page":name,"exceptions":errors,"horizontal_overflow":overflow,"screenshot":str(preview)}))
            if errors or overflow:
                raise RuntimeError(f"Visible layout check failed on {name}")
        if args.overview_interactions:
            check_overview_interactions(browser, args.port, output)
        if args.architecture_team_interactions:
            check_architecture_team_interactions(browser, args.port, output, args.width, args.height)
        elif args.architecture_interactions:
            check_architecture_team_interactions(browser, args.port, output, args.width, args.height, architecture_only=True)
        if args.action_dashboard_interactions or args.states:
            check_action_dashboard_interactions(browser, args.port, output, args.width, args.height)
        if args.dashboard_interactions:
            check_dashboard_interactions(browser, args.port, output, args.width, args.height)
        if args.final_action_interactions:
            check_final_action_interactions(browser, args.port, output, args.width, args.height, args.action_fixtures_dir)
        if args.session_navigation:
            check_session_navigation(browser, args.port, output, args.width, clear=args.session_clear)
        if args.conversation:
            check_conversation(browser, args.port, output, args.width, args.height, args.conversation_fixture)
        if args.responsive:
            browser.command("Emulation.setDeviceMetricsOverride", {"width":390,"height":844,"deviceScaleFactor":1,"mobile":False})
            for name in pages:
                browser.navigate(f"http://127.0.0.1:{args.port}/?page={name}")
                browser.wait_ready()
                time.sleep(1)
                overflow = browser.evaluate("[document.documentElement,document.body,document.querySelector('[data-testid=stMain]')].filter(Boolean).some(el=>el.scrollWidth>el.clientWidth+2)")
                errors = browser.evaluate("document.querySelectorAll('[data-testid=stException]').length")
                browser.screenshot(output / f"{name}-390.png")
                print(json.dumps({"page":name,"width":390,"horizontal_overflow":overflow,"exception_count":errors}))
                if errors or overflow:
                    raise RuntimeError(f"Mobile layout check failed on {name}")
    finally:
        if browser:
            try:
                browser.command("Browser.close")
            except Exception:
                pass
            browser.ws.close()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.terminate()


if __name__ == "__main__":
    main()
