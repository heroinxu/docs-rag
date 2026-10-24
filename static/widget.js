/*
 * docs-rag website widget.
 *
 * <script src="https://YOUR-HOST/widget.js" async
 *   data-title="Ask the docs"          (panel header)
 *   data-greeting="Hi! Ask me anything about our docs."
 *   data-color="#2563eb"               (brand color)
 *   data-position="right"              (right | left)
 * ></script>
 *
 * Renders inside a Shadow DOM so the host site's CSS can't break it (and it can't break the site).
 */
(function () {
  const script = document.currentScript;
  if (!script || window.__docsRagWidget) return;
  window.__docsRagWidget = true;

  const api = new URL(script.src).origin + "/ask";
  const cfg = {
    title: script.dataset.title || "Ask the docs",
    greeting: script.dataset.greeting || "Hi! Ask me anything about the docs. Every answer links to its source.",
    color: script.dataset.color || "#2563eb",
    side: script.dataset.position === "left" ? "left" : "right",
  };

  const host = document.createElement("div");
  host.style.cssText = "position:fixed;z-index:2147483000;bottom:0;" + cfg.side + ":0;";
  document.body.appendChild(host);
  const root = host.attachShadow({ mode: "open" });

  root.innerHTML = `
<style>
  :host { all: initial; }
  * { box-sizing: border-box; font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }
  .bubble { position: fixed; bottom: 20px; ${cfg.side}: 20px; width: 56px; height: 56px; border-radius: 50%;
    border: 0; background: ${cfg.color}; color: #fff; cursor: pointer; box-shadow: 0 6px 20px rgba(0,0,0,.25);
    display: flex; align-items: center; justify-content: center; }
  .bubble svg { width: 26px; height: 26px; }
  .panel { position: fixed; bottom: 88px; ${cfg.side}: 20px; width: 380px; height: min(560px, calc(100vh - 110px));
    background: #fff; color: #1a1a1a; border-radius: 14px; box-shadow: 0 12px 40px rgba(0,0,0,.25);
    display: none; flex-direction: column; overflow: hidden; font-size: 14px; line-height: 1.5; }
  .panel.open { display: flex; }
  header { background: ${cfg.color}; color: #fff; padding: 14px 16px; font-weight: 600; display: flex; justify-content: space-between; align-items: center; }
  header button { background: none; border: 0; color: #fff; font-size: 20px; cursor: pointer; line-height: 1; }
  .log { flex: 1; overflow-y: auto; padding: 14px; background: #f7f7f8; }
  .msg { padding: 10px 12px; border-radius: 10px; margin: 0 0 10px; white-space: pre-wrap; word-wrap: break-word; max-width: 92%; }
  .bot { background: #fff; border: 1px solid #e5e5e5; }
  .user { background: ${cfg.color}; color: #fff; margin-left: auto; }
  .cites { margin-top: 8px; font-size: 12px; }
  .cites a { display: block; color: ${cfg.color}; text-decoration: none; margin: 3px 0; overflow-wrap: anywhere; }
  .cites a:hover { text-decoration: underline; }
  form { display: flex; gap: 8px; padding: 10px; border-top: 1px solid #e5e5e5; background: #fff; }
  input { flex: 1; padding: 10px 12px; border: 1px solid #d4d4d4; border-radius: 8px; font-size: 14px; outline: none; color: #1a1a1a; background: #fff; }
  input:focus { border-color: ${cfg.color}; }
  form button { padding: 0 14px; border: 0; border-radius: 8px; background: ${cfg.color}; color: #fff; cursor: pointer; font-size: 14px; }
  form button:disabled { opacity: .5; cursor: default; }
  .foot { font-size: 11px; color: #888; text-align: center; padding: 0 0 8px; background: #fff; }
  @media (max-width: 480px) {
    .panel { width: 100vw; height: auto; top: 0; bottom: 0; ${cfg.side}: 0; border-radius: 0; }
  }
</style>
<button class="bubble" aria-label="Open docs assistant">
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
</button>
<div class="panel" role="dialog">
  <header><span class="title"></span><button class="close" aria-label="Close">&times;</button></header>
  <div class="log" aria-live="polite"></div>
  <form><input placeholder="Ask a question..." maxlength="2000" autocomplete="off"><button>Ask</button></form>
  <div class="foot">Answers come only from the docs, with sources.</div>
</div>`;

  const $ = (s) => root.querySelector(s);
  const panel = $(".panel"), log = $(".log"), input = $("input"), send = $("form button");
  $(".title").textContent = cfg.title;
  panel.setAttribute("aria-label", cfg.title);

  function add(text, cls) {
    const d = document.createElement("div");
    d.className = "msg " + cls;
    d.textContent = text;
    log.appendChild(d);
    log.scrollTop = log.scrollHeight;
    return d;
  }

  function toggle(open) {
    panel.classList.toggle("open", open);
    if (open) {
      if (!log.childElementCount) add(cfg.greeting, "bot");
      input.focus();
    }
  }

  $(".bubble").onclick = () => toggle(!panel.classList.contains("open"));
  $(".close").onclick = () => toggle(false);
  root.addEventListener("keydown", (e) => { if (e.key === "Escape") toggle(false); });

  $("form").onsubmit = async (e) => {
    e.preventDefault();
    const question = input.value.trim();
    if (!question) return;
    input.value = "";
    send.disabled = true;
    add(question, "user");
    const box = add("Searching the docs...", "bot");
    try {
      const r = await fetch(api, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question }) });
      if (r.status === 429) throw new Error("Too many questions. Please wait a minute and try again.");
      if (!r.ok) throw new Error("Sorry, something went wrong. Please try again.");
      const data = await r.json();
      box.textContent = data.answer;
      if (data.citations && data.citations.length) {
        const c = document.createElement("div");
        c.className = "cites";
        data.citations.forEach((x, i) => {
          const a = document.createElement("a");
          a.href = x.url;
          a.target = "_blank";
          a.rel = "noopener";
          a.textContent = `[${i + 1}] ${x.heading}`;
          a.title = x.quote;
          c.appendChild(a);
        });
        box.appendChild(c);
      }
    } catch (err) {
      box.textContent = err.message || "Error contacting the docs assistant.";
    } finally {
      send.disabled = false;
      log.scrollTop = log.scrollHeight;
    }
  };
})();
