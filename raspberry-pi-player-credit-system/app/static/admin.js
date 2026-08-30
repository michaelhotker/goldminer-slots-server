const playersBody = document.querySelector("#playersBody");
const historyBody = document.querySelector("#historyBody");
const playerCount = document.querySelector("#playerCount");
const creditTotal = document.querySelector("#creditTotal");
const rfidCount = document.querySelector("#rfidCount");

loadAdmin();
setInterval(loadAdmin, 10000);

async function loadAdmin() {
  const [playersResponse, historyResponse] = await Promise.all([
    fetch("/api/players"),
    fetch("/api/history?limit=100"),
  ]);
  const playersData = await playersResponse.json();
  const historyData = await historyResponse.json();
  renderPlayers(playersData.players);
  renderHistory(historyData.history);
}

function renderPlayers(players) {
  playerCount.textContent = players.length;
  creditTotal.textContent = players.reduce((sum, player) => sum + player.credits, 0);
  rfidCount.textContent = players.filter((player) => player.rfid_uid).length;
  playersBody.innerHTML = players
    .map(
      (player) => `
      <tr>
        <td>${player.id}</td>
        <td>${escapeHtml(player.player_name || "Unnamed")}</td>
        <td>${escapeHtml(player.barcode_id)}</td>
        <td>${escapeHtml(player.rfid_uid || "Not linked")}</td>
        <td>${player.credits}</td>
        <td>${new Date(player.updated_at).toLocaleString()}</td>
      </tr>`
    )
    .join("");
}

function renderHistory(rows) {
  historyBody.innerHTML = rows
    .map(
      (row) => `
      <tr>
        <td>${new Date(row.created_at).toLocaleString()}</td>
        <td>${escapeHtml(row.player_name || row.barcode_id)}</td>
        <td>${escapeHtml(row.kind)}</td>
        <td>${row.amount}</td>
        <td>${row.old_credits} -> ${row.new_credits}</td>
        <td>${escapeHtml(row.source)}</td>
        <td>${escapeHtml(row.note)}</td>
      </tr>`
    )
    .join("");
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[char];
  });
}
