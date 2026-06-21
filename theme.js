/**
 * Shared dark-mode controller for Actos Line Trans.
 *
 * - Reads/writes the user preference in localStorage('actos-theme').
 * - Applies the class 'dark' on <html> so Tailwind's class-based dark mode kicks in.
 * - Renders a fixed toggle button in the bottom-right corner of every page that loads it.
 * - Respects the system preference on first visit.
 */

(function () {
  const KEY = 'actos-theme';

  // Tell Tailwind to use the class strategy. This works because every page loads
  // tailwindcss via CDN BEFORE this script (so tailwind.config can still be patched).
  if (window.tailwind && tailwind.config) {
    tailwind.config.darkMode = 'class';
  }

  function getStored() {
    return localStorage.getItem(KEY); // 'dark' | 'light' | null
  }

  function systemPref() {
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }

  function apply(theme) {
    document.documentElement.classList.toggle('dark', theme === 'dark');
    document.documentElement.dataset.theme = theme;
    const btn = document.getElementById('actos-theme-toggle');
    if (btn) btn.textContent = theme === 'dark' ? '☀️' : '🌙';
  }

  function toggle() {
    const next = (document.documentElement.classList.contains('dark') ? 'light' : 'dark');
    localStorage.setItem(KEY, next);
    apply(next);
  }

  function injectButton() {
    if (document.getElementById('actos-theme-toggle')) return;
    const btn = document.createElement('button');
    btn.id = 'actos-theme-toggle';
    btn.title = 'Toggle dark mode';
    btn.style.cssText = [
      'position:fixed',
      'bottom:18px',
      'right:18px',
      'z-index:9999',
      'width:46px',
      'height:46px',
      'border-radius:9999px',
      'border:1px solid rgba(0,0,0,0.1)',
      'background:#fff',
      'color:#0f172a',
      'box-shadow:0 6px 20px rgba(0,0,0,0.15)',
      'font-size:20px',
      'cursor:pointer',
      'display:flex',
      'align-items:center',
      'justify-content:center',
      'transition:transform .15s, background .2s'
    ].join(';');
    btn.addEventListener('click', toggle);
    btn.addEventListener('mouseenter', () => btn.style.transform = 'scale(1.08)');
    btn.addEventListener('mouseleave', () => btn.style.transform = 'scale(1)');
    document.body.appendChild(btn);
  }

  // Apply ASAP to avoid flash
  const initial = getStored() || systemPref();
  apply(initial);

  // Inject styles to make body dark too — cheap, lets pages without explicit dark
  // classes still feel right.
  const style = document.createElement('style');
  style.textContent = `
    html.dark { color-scheme: dark; }
    html.dark body { background: #0b1220 !important; color: #e2e8f0 !important; }
    html.dark .bg-white { background: #111827 !important; color: #e2e8f0 !important; }
    html.dark .bg-slate-50, html.dark .bg-slate-100 { background: #0f172a !important; }
    html.dark .bg-blue-50, html.dark .bg-gradient-to-br { background: #0b1220 !important; }
    html.dark .text-slate-800, html.dark .text-slate-700 { color: #e2e8f0 !important; }
    html.dark .text-slate-600, html.dark .text-slate-500 { color: #94a3b8 !important; }
    html.dark .border-slate-200, html.dark .border-slate-100, html.dark .border-blue-100 { border-color: #1f2937 !important; }
    html.dark input, html.dark select, html.dark textarea {
      background: #0f172a !important; color: #e2e8f0 !important; border-color: #1f2937 !important;
    }
    html.dark .shadow-sm, html.dark .shadow-md, html.dark .shadow-xl { box-shadow: 0 6px 20px rgba(0,0,0,0.4) !important; }
    html.dark #actos-theme-toggle { background: #1e293b; color: #e2e8f0; border-color: #334155; }
    html.dark thead.bg-slate-100 { background: #0f172a !important; }
    html.dark .bg-slate-50\\/50 { background: #0b1220 !important; }
  `;
  document.head.appendChild(style);

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', injectButton);
  } else {
    injectButton();
  }

  window.actosTheme = { toggle, apply };
})();
