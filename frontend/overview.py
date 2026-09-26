"""Local Overview enhancements. No backend access or external JavaScript."""

OVERVIEW_INTERACTIONS = r"""
<script>
(() => {
  if (window.__ragopsOverviewCleanup) window.__ragopsOverviewCleanup();
  const media = window.matchMedia('(prefers-reduced-motion: reduce)');
  let frame = 0;
  let attempts = 0;
  let teardown = () => {};
  const init = () => {
    const snapshot = document.getElementById('evaluation-snapshot');
    const cue = document.querySelector('.overview-scroll-cue');
    if (!snapshot || !cue) {
      if (++attempts < 120) frame = requestAnimationFrame(init);
      return;
    }
    const counters = [...snapshot.querySelectorAll('.kpi-count')];
    const main = document.querySelector('[data-testid="stMain"]') || window;
    const gate = document.querySelector('.orbit-gate');
    const structural = document.querySelector('a.failure-card[data-failure-kind="structural"]');
    let countFrame = 0;
    const paint = (progress) => counters.forEach(el => {
      const target = Number(el.dataset.countTo);
      const digits = Number(el.dataset.countDecimals);
      el.textContent = (target * progress).toFixed(digits) + el.dataset.countSuffix;
    });
    const finishCount = () => { cancelAnimationFrame(countFrame); paint(1); };
    if (!window.__ragopsOverviewCounted && !media.matches) {
      window.__ragopsOverviewCounted = true;
      const started = performance.now();
      paint(0);
      const tick = now => {
        if (!snapshot.isConnected || media.matches) { finishCount(); return; }
        const t = Math.min(1, (now - started) / 950);
        paint(1 - Math.pow(1 - t, 3));
        if (t < 1) countFrame = requestAnimationFrame(tick);
      };
      countFrame = requestAnimationFrame(tick);
    } else {
      window.__ragopsOverviewCounted = true;
      paint(1);
    }
    const updateCue = () => {
      const offset = main === window ? window.scrollY : main.scrollTop;
      cue.hidden = offset > 60;
    };
    const explore = event => {
      event.preventDefault();
      snapshot.scrollIntoView({behavior: media.matches ? 'instant' : 'smooth', block: 'start'});
      snapshot.focus({preventScroll: true});
    };
    const previewRisk = () => gate?.classList.add('is-preview-relevant');
    const clearRisk = () => gate?.classList.remove('is-preview-relevant');
    const motionChanged = () => { if (media.matches) finishCount(); };
    cue.addEventListener('click', explore);
    main.addEventListener('scroll', updateCue, {passive:true});
    media.addEventListener('change', motionChanged);
    structural?.addEventListener('mouseenter', previewRisk);
    structural?.addEventListener('mouseleave', clearRisk);
    structural?.addEventListener('focus', previewRisk);
    structural?.addEventListener('blur', clearRisk);
    updateCue();
    teardown = () => {
      cancelAnimationFrame(countFrame);
      cue.removeEventListener('click', explore);
      main.removeEventListener('scroll', updateCue);
      media.removeEventListener('change', motionChanged);
      structural?.removeEventListener('mouseenter', previewRisk);
      structural?.removeEventListener('mouseleave', clearRisk);
      structural?.removeEventListener('focus', previewRisk);
      structural?.removeEventListener('blur', clearRisk);
      clearRisk();
    };
  };
  window.__ragopsOverviewCleanup = () => { cancelAnimationFrame(frame); teardown(); };
  frame = requestAnimationFrame(init);
})();
</script>
"""
