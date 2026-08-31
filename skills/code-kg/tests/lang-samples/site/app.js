const consoleEl = document.getElementById("console");

function appendLine(text) {
  const div = document.createElement("div");
  div.textContent = text;
  consoleEl.appendChild(div);
}

appendLine("agent console ready");
