const tilesContainer = document.getElementById("tiles");

function parseTileSize(sizeText) {
  if (typeof sizeText !== "string") {
    return [1, 1];
  }
  const match = sizeText.trim().match(/^(\d+)x(\d+)$/i);
  if (!match) {
    return [1, 1];
  }
  const cols = Math.max(1, Number.parseInt(match[1], 10));
  const rows = Math.max(1, Number.parseInt(match[2], 10));
  return [cols, rows];
}

function createTile(titleText, sizeText = "1x1") {
  const tile = document.createElement("article");
  tile.className = "tile";
  const [cols, rows] = parseTileSize(sizeText);
  tile.style.gridColumn = `span ${cols}`;
  tile.style.gridRow = `span ${rows}`;

  const title = document.createElement("h2");
  title.className = "tile-title";
  title.textContent = titleText;
  tile.appendChild(title);

  return tile;
}

function createInfoMessage(text, tone = "neutral") {
  const message = document.createElement("p");
  message.className = `tile-message ${tone}`;
  message.textContent = text;
  return message;
}

function appTitle(source) {
  if (typeof source?.app_id === "string" && source.app_id.length > 0) {
    return source.app_id;
  }
  if (typeof source?.display_name === "string" && source.display_name.length > 0) {
    return source.display_name.toLowerCase();
  }
  return "app";
}

function toCommands(appStatus) {
  const commands = appStatus?.event?.payload?.commands;
  return Array.isArray(commands) ? commands.slice(0, 3) : [];
}

function shortenCommandId(commandId) {
  if (typeof commandId !== "string" || commandId.length <= 7) {
    return commandId ?? "-";
  }
  return `${commandId.slice(0, -7)}…`;
}

function createAwakerStatusIcon(command) {
  const acknowledged = Boolean(command?.ack_timestamp);
  const icon = document.createElement("span");
  icon.className = acknowledged ? "status-icon acknowledged" : "status-icon waiting";
  icon.textContent = acknowledged ? "✓" : "⏳";
  icon.title = acknowledged
    ? `Acknowledged at ${command.ack_timestamp}`
    : "Waiting for acknowledgment";
  return icon;
}

function renderAwakerTile(appStatus, uiTile = {}) {
  const tile = createTile(appTitle(appStatus), uiTile.size || "1x1");
  const table = document.createElement("table");
  table.className = "commands-table";
  table.innerHTML = `
    <thead>
      <tr>
        <th>Command ID</th>
        <th>Status</th>
      </tr>
    </thead>
    <tbody></tbody>
  `;

  const tbody = table.querySelector("tbody");
  const commands = toCommands(appStatus);
  if (commands.length === 0) {
    const row = document.createElement("tr");
    row.innerHTML = `<td colspan="2">No commands found</td>`;
    tbody.appendChild(row);
  } else {
    commands.forEach((command) => {
      const row = document.createElement("tr");

      const idCell = document.createElement("td");
      idCell.textContent = shortenCommandId(command?.id);
      if (command?.id) {
        idCell.title = command.id;
      }

      const statusCell = document.createElement("td");
      statusCell.className = "status-cell";
      statusCell.appendChild(createAwakerStatusIcon(command));

      row.appendChild(idCell);
      row.appendChild(statusCell);
      tbody.appendChild(row);
    });
  }

  tile.appendChild(table);
  return tile;
}

function renderS1ProTile(appStatus, uiTile = {}) {
  const tile = createTile(appTitle(appStatus), uiTile.size || "1x1");
  const event = appStatus?.event;

  if (!event) {
    tile.appendChild(
      createInfoMessage("Waiting for first status update from S1 Pro.", "warning"),
    );
    return tile;
  }

  if (event.status !== "ok") {
    const detail = event.message || "The printer endpoint is not reachable right now.";
    tile.appendChild(
      createInfoMessage(
        `S1 Pro unavailable: ${detail}`,
        "warning",
      ),
    );
    return tile;
  }

  const payload = event.payload || {};
  const rows = [
    ["State", payload.state ?? "-"],
    ["File", payload.filename ?? "-"],
    ["Progress", payload.progress ?? "-"],
    ["Layers", payload.layers ?? "- / -"],
  ];

  const table = document.createElement("table");
  table.className = "details-table";
  table.innerHTML = `<tbody></tbody>`;
  const tbody = table.querySelector("tbody");

  rows.forEach(([label, value]) => {
    const row = document.createElement("tr");
    const keyCell = document.createElement("th");
    keyCell.textContent = label;
    const valueCell = document.createElement("td");
    valueCell.textContent = value;
    row.appendChild(keyCell);
    row.appendChild(valueCell);
    tbody.appendChild(row);
  });

  tile.appendChild(table);
  return tile;
}

function renderGenericTile(appStatus, uiTile = {}) {
  const title = appTitle(appStatus);
  const tile = createTile(title, uiTile.size || "1x1");
  const event = appStatus?.event;

  if (!event) {
    tile.appendChild(createInfoMessage("Waiting for first status update.", "warning"));
    return tile;
  }

  if (event.message) {
    tile.appendChild(createInfoMessage(event.message, event.status === "ok" ? "neutral" : "warning"));
  } else {
    tile.appendChild(createInfoMessage(`Latest status: ${event.status ?? "unknown"}`));
  }

  return tile;
}

function renderJellyfinTile(appStatus, uiTile = {}) {
  const tile = createTile(appTitle(appStatus), uiTile.size || "2x1");
  const event = appStatus?.event;
  const activities = Array.isArray(event?.payload?.activities) ? event.payload.activities : [];

  if (!event || event.status !== "ok") {
    const detail = event?.message || "Jellyfin activity is unavailable.";
    tile.appendChild(createInfoMessage(`Jellyfin unavailable: ${detail}`, "warning"));
    return tile;
  }

  if (activities.length === 0) {
    tile.appendChild(createInfoMessage("No recent activity.", "neutral"));
    return tile;
  }

  const list = document.createElement("ul");
  list.className = "activity-list";
  activities.forEach((activity) => {
    const item = document.createElement("li");
    item.className = "activity-item";
    const title = activity?.title || activity?.type || "Activity";
    const timestamp = activity?.created_at || "";
    item.innerHTML = `${title}${timestamp ? `<small>${timestamp}</small>` : ""}`;
    list.appendChild(item);
  });
  tile.appendChild(list);
  return tile;
}

function renderPiHoleTile(appStatus, uiTile = {}) {
  const tile = createTile(appTitle(appStatus), uiTile.size || "1x1");
  const event = appStatus?.event;

  if (!event) {
    tile.appendChild(createInfoMessage("Waiting for first status update from Pi-hole.", "warning"));
    return tile;
  }

  if (event.status !== "ok") {
    const detail = event.message || "Pi-hole is unavailable.";
    tile.appendChild(createInfoMessage(`Pi-hole unavailable: ${detail}`, "warning"));
    return tile;
  }

  const payload = event.payload || {};
  const rows = [
    ["Total", payload.total ?? "-"],
    ["Blocked", payload.blocked ?? "-"],
    ["Blocked %", payload.percent_blocked ?? "-"],
  ];

  const table = document.createElement("table");
  table.className = "details-table";
  table.innerHTML = `<tbody></tbody>`;
  const tbody = table.querySelector("tbody");

  rows.forEach(([label, value]) => {
    const row = document.createElement("tr");
    const keyCell = document.createElement("th");
    keyCell.textContent = label;
    const valueCell = document.createElement("td");
    valueCell.textContent = value;
    row.appendChild(keyCell);
    row.appendChild(valueCell);
    tbody.appendChild(row);
  });

  tile.appendChild(table);
  return tile;
}

function renderPageErrorTile(message) {
  const tile = createTile("Flight Board", "1x1");
  tile.appendChild(createInfoMessage(message, "error"));
  return tile;
}

function renderOneTile(appStatus, uiTile) {
  if (appStatus?.app_id === "awaker" && uiTile?.type === "status") {
    return renderAwakerTile(appStatus, uiTile);
  }
  if (appStatus?.app_id === "s1_pro" && uiTile?.type === "status") {
    return renderS1ProTile(appStatus, uiTile);
  }
  if (appStatus?.app_id === "jellyfin" && uiTile?.type === "activity") {
    return renderJellyfinTile(appStatus, uiTile);
  }
  if (appStatus?.app_id === "pihole" && uiTile?.type === "status") {
    return renderPiHoleTile(appStatus, uiTile);
  }
  return renderGenericTile(appStatus, uiTile);
}

function createLoadingTile(appMeta, uiTile) {
  const title = appTitle(appMeta);
  const tile = createTile(title, uiTile?.size || "1x1");
  tile.appendChild(createInfoMessage("Loading status...", "loading"));
  return tile;
}

function tilesForApp(appMeta) {
  if (Array.isArray(appMeta?.ui?.tiles)) {
    return appMeta.ui.tiles;
  }
  return [{ id: `${appMeta?.app_id || "app"}-default`, type: "status", size: "1x1" }];
}

async function loadTileStatus(tileDescriptor) {
  const { appId, uiTile, placeholder } = tileDescriptor;
  try {
    const response = await fetch(`/apps/${encodeURIComponent(appId)}/status/latest`);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const data = await response.json();
    const appStatus = data?.app;
    const rendered = renderOneTile(appStatus, uiTile);
    placeholder.replaceWith(rendered);
  } catch (error) {
    const fallbackStatus = {
      app_id: appId,
      display_name: tileDescriptor.displayName,
      event: {
        status: "error",
        message: `Failed to load status: ${error.message}`,
      },
    };
    const rendered = renderGenericTile(fallbackStatus, uiTile);
    placeholder.replaceWith(rendered);
  }
}

async function renderTiles() {
  try {
    const catalogResponse = await fetch("/apps/catalog");
    if (!catalogResponse.ok) {
      throw new Error(`HTTP ${catalogResponse.status}`);
    }

    const catalogData = await catalogResponse.json();
    const apps = Array.isArray(catalogData.apps) ? catalogData.apps : [];
    const descriptors = [];

    apps.forEach((appMeta) => {
      const appTiles = tilesForApp(appMeta);
      appTiles.forEach((uiTile, index) => {
        const placeholder = createLoadingTile(appMeta, uiTile);
        descriptors.push({
          appId: appMeta.app_id,
          displayName: appMeta.display_name,
          uiTile: {
            id: uiTile?.id || `${appMeta.app_id}-tile-${index + 1}`,
            type: uiTile?.type || "status",
            title: uiTile?.title || appMeta.display_name,
            size: uiTile?.size || "1x1",
          },
          placeholder,
        });
      });
    });

    tilesContainer.replaceChildren(...descriptors.map((item) => item.placeholder));
    descriptors.forEach((item) => {
      loadTileStatus(item);
    });
  } catch (error) {
    const message = `Failed to load app tiles: ${error.message}`;
    tilesContainer.replaceChildren(renderPageErrorTile(message));
  }
}

renderTiles();
