let currentPlayer = null;

const barcodeForm = document.querySelector("#barcodeForm");
const barcodeInput = document.querySelector("#barcodeInput");
const playerNameInput = document.querySelector("#playerNameInput");
const scanStatus = document.querySelector("#scanStatus");
const creditStatus = document.querySelector("#creditStatus");
const playerSummary = document.querySelector("#playerSummary");
const pairButton = document.querySelector("#pairButton");
const pairingCode = document.querySelector("#pairingCode");
const pairStatus = document.querySelector("#pairStatus");
const historyBody = document.querySelector("#historyBody");

barcodeForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const barcode = barcodeInput.value.trim();
  if (!barcode) return;

  try {
    setStatus(scanStatus, "Looking up barcode...");
    const response = await postJson("/api/barcode/lookup", {
      barcode_id: barcode,
      player_name: playerNameInput.value.trim(),
    });
    currentPlayer = response.player;
    setStatus(scanStatus, response.created ? "New account created." : "Account loaded.", "ok");
    pairingCode.hidden = true;
    pairStatus.textContent = "";
    renderPlayer();
    await loadHistory();
    barcodeInput.value = "";
    barcodeInput.focus();
  } catch (error) {
    setStatus(scanStatus, error.message, "error");
  }
});

document.querySelectorAll("[data-credit]").forEach((button) => {
  button.addEventListener("click", async () => {
    if (!currentPlayer) {
      setStatus(creditStatus, "Scan a barcode first.", "error");
      return;
    }
    try {
      const amount = Number(button.dataset.credit);
      const response = await postJson("/api/credits/add", {
        player_id: currentPlayer.id,
        amount,
        source: "kiosk",
        note: "Kiosk credit top-up",
      });
      currentPlayer = response.player;
      setStatus(creditStatus, `Added ${amount} credits.`, "ok");
      renderPlayer();
      await loadHistory();
    } catch (error) {
      setStatus(creditStatus, error.message, "error");
    }
  });
});

pairButton.addEventListener("click", async () => {
  if (!currentPlayer) {
    setStatus(pairStatus, "Scan a barcode first.", "error");
    return;
  }
  try {
    const response = await postJson(`/api/players/${currentPlayer.id}/pairing-code`, {});
    pairingCode.hidden = false;
    pairingCode.textContent = response.code;
    setStatus(pairStatus, `Code expires at ${new Date(response.expires_at).toLocaleTimeString()}.`, "ok");
  } catch (error) {
    setStatus(pairStatus, error.message, "error");
  }
});

function renderPlayer() {
  if (!currentPlayer) {
    playerSummary.textContent = "No player loaded.";
    return;
  }
  const name = currentPlayer.player_name || "Unnamed player";
  const rfid = currentPlayer.rfid_uid || "Not linked";
  playerSummary.innerHTML = `
    <div><strong>${escapeHtml(name)}</strong></div>
    <div>Barcode: ${escapeHtml(currentPlayer.barcode_id)}</div>
    <div>RFID: ${escapeHtml(rfid)}</div>
    <div>Credits</div>
    <div class="big-balance">${currentPlayer.credits}</div>
  `;
}

async function loadHistory() {
  if (!currentPlayer) return;
  const response = await fetch(`/api/history?player_id=${currentPlayer.id}&limit=10`);
  const data = await response.json();
  historyBody.innerHTML = data.history
    .map(
      (row) => `
      <tr>
        <td>${new Date(row.created_at).toLocaleString()}</td>
        <td>${escapeHtml(row.kind)}</td>
        <td>${row.amount}</td>
        <td>${row.old_credits} -> ${row.new_credits}</td>
      </tr>`
    )
    .join("");
}

async function postJson(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || "Request failed");
  }
  return data;
}

function setStatus(element, text, className = "") {
  element.className = `status ${className}`;
  element.textContent = text;
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[char];
  });
}
