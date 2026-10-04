// Report pages: wire the print button (inline handlers are blocked by our CSP).
document.getElementById("print-btn")?.addEventListener("click", () => window.print());
