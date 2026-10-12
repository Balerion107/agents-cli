---
hide:
  - navigation
  - toc
---

<style>
  .md-typeset h1 { display: none; }
  .md-content__inner { padding-top: 0; padding-bottom: 0; margin-bottom: 0; }
  .md-content { padding-bottom: 0; }
</style>

# `agents-cli`

<div class="hero-grid">
  <div class="hero-content">
    <p class="headline"><strong><code>agents-cli</code></strong><br><span class="headline-sub">in Gemini platform</span></p>
    <p class="tagline">CLI and skills for building agents on Google Cloud.</p>
    <div class="home-cta">
      <a href="guide/getting-started/" class="cta-primary">Get Started &rarr;</a>
      <a href="https://github.com/google/agents-cli" class="cta-secondary" target="_blank" rel="noopener noreferrer">View on GitHub</a>
    </div>
    <div class="works-with">
      <p class="works-with-text">Works with your coding agent</p>
      <div class="works-with-logos">
        <a href="https://antigravity.google/" title="Antigravity CLI" target="_blank" rel="noopener noreferrer"><img src="assets/logos/antigravity.png" alt="Antigravity CLI"></a>
        <a href="https://docs.anthropic.com/en/docs/claude-code" title="Claude Code" target="_blank" rel="noopener noreferrer"><img src="assets/logos/claude.png" alt="Claude Code"></a>
        <a href="https://github.com/openai/codex" title="Codex" target="_blank" rel="noopener noreferrer"><img src="assets/logos/openai.svg" alt="Codex"></a>
        <span class="works-with-more">& more</span>
      </div>
    </div>
  </div>

  <div class="hero-side">
    <div class="raw-term install-card" data-copy="uvx google-agents-cli setup">
      <button class="copy-btn" type="button" aria-label="Copy install command">
        <svg class="icon-copy" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
        <svg class="icon-check" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>
      </button>
      <div class="raw-line"><span class="raw-comment"># install the cli + skills</span></div>
      <div class="raw-line"><span class="raw-prompt">$</span> <span class="raw-cmd">uvx google-agents-cli setup</span></div>
      <div class="raw-line raw-spacer"></div>
      <div class="raw-line"><span class="raw-comment"># now ask your coding agent to build</span></div>
      <div class="raw-line"><span class="raw-prompt raw-prompt-user">&gt;</span> <span class="rotator" data-words='["an agent that triages incidents","an agent that hunts down bugs","an agent that drafts your RFPs","an agent that audits your code","an agent that briefs you daily","an agent that watches the market"]'><span class="rotator-word">an agent that triages incidents</span></span><span class="raw-cursor"></span></div>
    </div>
  </div>
</div>

<script>
document.addEventListener("DOMContentLoaded", function() {
  document.querySelectorAll(".install-card .copy-btn").forEach(function(btn) {
    btn.addEventListener("click", function() {
      var card = btn.closest(".install-card");
      var text = card.getAttribute("data-copy") || card.querySelector("code").textContent;
      navigator.clipboard.writeText(text).then(function() {
        card.classList.add("copied");
        setTimeout(function() { card.classList.remove("copied"); }, 1500);
      });
    });
  });

  document.querySelectorAll(".rotator").forEach(function(el) {
    var words;
    try { words = JSON.parse(el.getAttribute("data-words") || "[]"); }
    catch (e) { return; }
    if (!words.length) return;

    var word = el.querySelector(".rotator-word");
    if (!word) return;
    var idx = 0;

    function rotate() {
      word.classList.add("slide-out");
      setTimeout(function() {
        idx = (idx + 1) % words.length;
        word.textContent = words[idx];
        word.classList.remove("slide-out");
        word.classList.add("slide-in-start");
        requestAnimationFrame(function() {
          requestAnimationFrame(function() {
            word.classList.remove("slide-in-start");
          });
        });
      }, 500);
    }
    setInterval(rotate, 4500);
  });
});
</script>
