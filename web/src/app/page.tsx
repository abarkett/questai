"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { sendCommand } from "./lib/api";
import { generateSceneImage } from "./lib/gemini";
import { buildScenePrompt } from "./lib/scene";

type Line = {
  id: string;
  text: string;
};

// cache survives re-renders
const sceneImageCache = new Map<string, string>();

// ---- Map thumbnails (downscaled scene art, persisted in localStorage) ----
const THUMBS_KEY = "location_thumbs";

function loadThumbs(): Record<string, string> {
  try {
    return JSON.parse(localStorage.getItem(THUMBS_KEY) || "{}");
  } catch {
    return {};
  }
}

function saveThumbs(thumbs: Record<string, string>) {
  try {
    localStorage.setItem(THUMBS_KEY, JSON.stringify(thumbs));
  } catch {
    // localStorage full / unavailable — thumbnails are best-effort.
  }
}

// Shrink a full scene image to a tiny JPEG so the whole map fits in localStorage.
function downscale(dataUri: string, w = 160, h = 90): Promise<string> {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => {
      try {
        const c = document.createElement("canvas");
        c.width = w;
        c.height = h;
        const ctx = c.getContext("2d");
        if (!ctx) return resolve(dataUri);
        ctx.drawImage(img, 0, 0, w, h);
        resolve(c.toDataURL("image/jpeg", 0.6));
      } catch {
        resolve(dataUri);
      }
    };
    img.onerror = () => resolve(dataUri);
    img.src = dataUri;
  });
}


function computeSceneKeyFromResponse(resp: any) {
  const state = resp?.state;
  if (!state?.location) return null;

  const entities = state.entities ?? [];

  return JSON.stringify({
    locationId: state.location.id,
    locationDescription: state.location.description,
    entities: entities
      .map((e: any) => ({
        type: e.type,
        name: e.name,
        hp: e.hp ?? null,
      }))
      .sort((a: any, b: any) => a.name.localeCompare(b.name)),
  });
}

// Direction labels -> grid deltas, used to lay the map out roughly spatially.
const DIR: Record<string, [number, number]> = {
  north: [0, -1], up: [0, -1], ascend: [0, -1], out: [0, -1], back: [0, -1], square: [0, -1],
  south: [0, 1], down: [0, 1], descend: [0, 1], deeper: [0, 1], in: [0, 1],
  cave: [0, 1], tunnel: [0, 1], hollow: [0, 1], mill: [0, 1],
  east: [1, 0], west: [-1, 0],
};

function computeMapLayout(mapData: any) {
  const byId: Record<string, any> = {};
  for (const n of mapData.locations) byId[n.id] = n;

  const pos: Record<string, [number, number]> = {};
  const occupied = new Set<string>();
  const key = (x: number, y: number) => `${x},${y}`;

  function place(id: string, x: number, y: number) {
    let cx = x, cy = y, r = 1;
    while (occupied.has(key(cx, cy))) {
      let found = false;
      for (let dy = -r; dy <= r && !found; dy++) {
        for (let dx = -r; dx <= r && !found; dx++) {
          if (Math.abs(dx) !== r && Math.abs(dy) !== r) continue;
          if (!occupied.has(key(x + dx, y + dy))) { cx = x + dx; cy = y + dy; found = true; }
        }
      }
      if (!found) r++;
      if (r > 60) break;
    }
    occupied.add(key(cx, cy));
    pos[id] = [cx, cy];
  }

  const start =
    mapData.current && byId[mapData.current] ? mapData.current : mapData.locations[0]?.id;
  const queue: string[] = [];
  if (start) { place(start, 0, 0); queue.push(start); }

  while (queue.length) {
    const cur = queue.shift() as string;
    const node = byId[cur];
    if (!node || !pos[cur]) continue;
    const [px, py] = pos[cur];
    for (const ex of node.exits || []) {
      if (!byId[ex.to] || pos[ex.to]) continue;
      const d = DIR[ex.label] || [1, 0];
      place(ex.to, px + d[0], py + d[1]);
      queue.push(ex.to);
    }
  }
  // Any nodes not reached via forward edges: drop them in a spare row.
  let spare = 0;
  for (const n of mapData.locations) if (!pos[n.id]) place(n.id, spare++, 99);

  const edges: [number, number][][] = [];
  const seen = new Set<string>();
  for (const n of mapData.locations) {
    for (const ex of n.exits || []) {
      if (!pos[n.id] || !pos[ex.to]) continue;
      const a = n.id < ex.to ? n.id : ex.to;
      const b = n.id < ex.to ? ex.to : n.id;
      const ek = `${a}|${b}`;
      if (seen.has(ek)) continue;
      seen.add(ek);
      edges.push([pos[a], pos[b]]);
    }
  }

  const xs = Object.values(pos).map((p) => p[0]);
  const ys = Object.values(pos).map((p) => p[1]);
  return {
    pos,
    edges,
    minX: Math.min(...xs), maxX: Math.max(...xs),
    minY: Math.min(...ys), maxY: Math.max(...ys),
  };
}

function MapGraph({ mapData, thumbs }: { mapData: any; thumbs: Record<string, string> }) {
  const L = computeMapLayout(mapData);
  const cell = 130, pad = 24, nodeW = 100, nodeH = 64;
  const cols = L.maxX - L.minX + 1, rows = L.maxY - L.minY + 1;
  const W = cols * cell + pad * 2, H = rows * cell + pad * 2;
  const cx = (gx: number) => pad + (gx - L.minX) * cell + cell / 2;
  const cy = (gy: number) => pad + (gy - L.minY) * cell + cell / 2;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ maxHeight: "72vh" }}>
      {L.edges.map(([a, b], i) => (
        <line
          key={i}
          x1={cx(a[0])} y1={cy(a[1])} x2={cx(b[0])} y2={cy(b[1])}
          stroke="#15803d" strokeWidth={2}
        />
      ))}
      {mapData.locations.map((n: any) => {
        const p = L.pos[n.id];
        if (!p) return null;
        const X = cx(p[0]) - nodeW / 2;
        const Y = cy(p[1]) - nodeH / 2;
        const thumb = n.visited ? thumbs[n.id] : undefined;
        const here = n.id === mapData.current;
        return (
          <g key={n.id}>
            {thumb && (
              <image
                href={thumb} x={X} y={Y} width={nodeW} height={nodeH}
                preserveAspectRatio="xMidYMid slice"
              />
            )}
            <rect
              x={X} y={Y} width={nodeW} height={nodeH}
              fill={thumb ? "transparent" : n.visited ? "#052e16" : "#0a0a0a"}
              stroke={here ? "#86efac" : n.visited ? "#15803d" : "#14532d"}
              strokeWidth={here ? 3 : 1.5}
            />
            {!thumb && !n.visited && (
              <text x={cx(p[0])} y={cy(p[1]) + 5} fill="#3f6212" fontSize="22" textAnchor="middle">?</text>
            )}
            <text
              x={cx(p[0])} y={Y + nodeH + 14}
              fill={here ? "#bbf7d0" : n.visited ? "#86efac" : "#3f6212"}
              fontSize="12" textAnchor="middle"
            >
              {n.visited ? n.name : "Unexplored"}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

function Modal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  return (
    <div
      className="fixed inset-0 z-50 bg-black/90 p-6 overflow-auto"
      onClick={onClose}
    >
      <div className="max-w-5xl mx-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg text-green-300">{title}</h2>
          <button
            className="border border-green-700 px-3 py-1 text-sm hover:bg-green-900"
            onClick={onClose}
          >
            Close
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

// Heuristic: which inventory items are equippable gear vs. consumed/used.
const GEAR_RE = /(sword|blade|dagger|armor|mail|scale|axe|shield|bow|staff)/i;

function StatusPane({ state, onCommand }: { state: any | null; onCommand: (cmd: string) => void; }) {
  if (!state?.player || !state?.location) {
    return (
      <div className="text-green-700">
        No character loaded
      </div>
    );
  }

  const { player, location } = state;

  return (
    <div className="space-y-3 text-sm">
      <div className="text-lg font-bold text-green-300">
        {state.player.name}
      </div>
      {/* Location */}
      <div>
        <div className="text-green-400 font-bold">Location</div>
        <div>{location.name}</div>
      </div>
      <div>
        <div className="text-green-400 font-bold">People Here</div>
        <div className="space-y-1">
          {state.entities
            .filter((e: any) => e.type === "npc" || e.type === "player")
            .map((entity: any) => {
              const isInParty = state.party?.members?.some((m: any) => m.player_id === entity.id);
              return (
                <button
                  key={entity.id}
                  className="block text-left hover:underline"
                  onClick={() => onCommand(`talk ${entity.id}`)}
                >
                  {entity.name} {entity.type === "player" ? "(player)" : ""}
                  {isInParty && " ⚔️"}
                </button>
              );
            })}
        </div>
      </div>
      {/* Active Quests */}
      {state.player.active_quests && Object.keys(state.player.active_quests).length > 0 && (
        <div>
          <div className="text-green-400 font-bold">Active Quests</div>
          {Object.values(state.player.active_quests).map((q: any) => (
            <div key={q.quest_id} className="text-xs mb-1">
              <div className="font-semibold">{q.name}</div>
              {q.objectives.map((obj: any, i: number) => (
                <div key={i} className="text-green-700">
                  {obj.target}: {obj.progress}/{obj.required}
                </div>
              ))}
            </div>
          ))}
        </div>
      )}

      {/* Completed Quests */}
      {state.player.completed_quests && Object.keys(state.player.completed_quests).length > 0 && (
        <div>
          <div className="text-green-400 font-bold">Completed Quests</div>
          {Object.values(state.player.completed_quests).map((q: any) => (
            <div key={q.quest_id} className="text-xs mb-1 text-yellow-400">
              {q.name} (Ready to turn in)
            </div>
          ))}
        </div>
      )}

      {/* Party Invites */}
      {state.party_invites?.length > 0 && (
        <div>
          <div className="text-green-400 font-bold">Party Invites</div>
          {state.party_invites.map((invite: any) => (
            <div key={invite.invite_id} className="text-xs mb-1 p-1 border border-green-600">
              <div>From {invite.from_player_name}</div>
              <button
                className="text-green-400 hover:underline text-xs mt-1"
                onClick={() => onCommand(`accept_party_invite ${invite.invite_id}`)}
              >
                Accept
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Current Party */}
      {state.party && (
        <div>
          <div className="text-green-400 font-bold">Party</div>
          <div className="text-xs mb-1">
            <div className="font-semibold">{state.party.name}</div>
            {state.party.members.map((member: any) => (
              <div key={member.player_id}>
                {member.name} {member.is_leader && '(Leader)'}
              </div>
            ))}
            <button
              className="text-red-400 hover:underline text-xs mt-1"
              onClick={() => onCommand('party leave')}
            >
              Leave Party
            </button>
          </div>
        </div>
      )}

      {/* Pending Trade Offers */}
      {(state.pending_trade_offers?.length > 0 || state.pending_trade_offers_sent?.length > 0) && (
        <div>
          <div className="text-green-400 font-bold">Trades</div>

          {/* Incoming offers */}
          {state.pending_trade_offers?.map((trade: any) => (
            <div
              key={trade.trade_id}
              className={`text-xs mb-1 p-1 border ${trade.can_accept ? 'border-green-600' : 'border-green-900 opacity-50'}`}
            >
              <div className="font-semibold">From {trade.from_player_name}:</div>
              <div>Offers: {Object.entries(trade.offered_items).map(([item, qty]) => `${item}:${qty}`).join(', ')}</div>
              <div>Wants: {Object.entries(trade.requested_items).map(([item, qty]) => `${item}:${qty}`).join(', ')}</div>
              {trade.can_accept ? (
                <button
                  className="text-green-400 hover:underline text-xs mt-1"
                  onClick={() => onCommand(`accept_trade ${trade.trade_id}`)}
                >
                  Accept
                </button>
              ) : (
                <div className="text-green-800 text-xs mt-1">Cannot accept</div>
              )}
            </div>
          ))}

          {/* Outgoing offers */}
          {state.pending_trade_offers_sent?.map((trade: any) => (
            <div
              key={trade.trade_id}
              className={`text-xs mb-1 p-1 border ${trade.can_be_accepted ? 'border-green-600' : 'border-green-900 opacity-50'}`}
            >
              <div className="font-semibold">To {trade.to_player_name}:</div>
              <div>You offer: {Object.entries(trade.offered_items).map(([item, qty]) => `${item}:${qty}`).join(', ')}</div>
              <div>You want: {Object.entries(trade.requested_items).map(([item, qty]) => `${item}:${qty}`).join(', ')}</div>
              <button
                className="text-red-400 hover:underline text-xs mt-1"
                onClick={() => onCommand(`cancel_trade ${trade.trade_id}`)}
              >
                Cancel
              </button>
              {!trade.can_be_accepted && (
                <div className="text-green-800 text-xs">They cannot accept</div>
              )}
            </div>
          ))}
        </div>
      )}

      <div>
        <div className="text-green-400 font-bold">Exits</div>
        <div className="flex flex-wrap gap-2 mt-1">
          {location.exits.map((e: any) => (
            <button
              key={e.to}
              className="px-2 py-1 border border-green-700 hover:bg-green-900 text-green-300 text-xs"
              onClick={() => onCommand(`go ${e.label}`)}
            >
              {e.label}
            </button>
          ))}
        </div>
      </div>

      {/* Stats */}
      <div>
        <div className="text-green-400 font-bold">Stats</div>
        <div className="flex items-center gap-2">
          <div className="flex-1 h-3 bg-green-950 border border-green-800">
            <div
              className="h-full bg-green-600"
              style={{
                width: `${Math.max(0, Math.min(100, (100 * player.hp) / player.max_hp))}%`,
              }}
            />
          </div>
          <span className="text-xs whitespace-nowrap">
            {player.hp}/{player.max_hp}
          </span>
        </div>
        <div className="text-xs mt-1">
          Level {player.level} · XP {player.xp}
        </div>
      </div>

      {/* Equipped */}
      {player.equipment && Object.keys(player.equipment).length > 0 && (
        <div>
          <div className="text-green-400 font-bold">Equipped</div>
          {Object.entries(player.equipment).map(([slot, itemId]) => (
            <div key={slot} className="text-xs">
              {slot}: {String(itemId).replace(/_/g, " ")}
            </div>
          ))}
        </div>
      )}

      {/* Status effects */}
      {player.status_effects && Object.keys(player.status_effects).length > 0 && (
        <div>
          <div className="text-green-400 font-bold">Status</div>
          {Object.entries(player.status_effects).map(([eid, st]: [string, any]) => (
            <div key={eid} className="text-xs">
              {String(eid).replace(/_/g, " ")} ({st?.turns ?? 0} turns)
            </div>
          ))}
        </div>
      )}

      {/* Abilities */}
      {Array.isArray(player.abilities) && player.abilities.length > 0 && (
        <div>
          <div className="text-green-400 font-bold">Abilities</div>
          {player.abilities.map(( a: string) => (
            <div key={a} className="text-xs">
              {String(a).replace(/_/g, " ")}
            </div>
          ))}
        </div>
      )}

      {/* Inventory */}
      <div>
        <div className="text-green-400 font-bold">Inventory</div>
        {player.inventory && Object.keys(player.inventory).length > 0 ? (
          <ul className="space-y-0.5">
            {Object.entries(player.inventory).map(([item, qty]) => {
              const gear = GEAR_RE.test(item);
              return (
                <li key={item} className="flex justify-between items-center gap-2">
                  <span>
                    {item.replace(/_/g, " ")} × {qty as number}
                  </span>
                  <span className="flex gap-2 shrink-0">
                    <button
                      className="text-green-400 hover:underline text-xs"
                      onClick={() => onCommand(`${gear ? "equip" : "use"} ${item}`)}
                    >
                      {gear ? "equip" : "use"}
                    </button>
                    <button
                      className="text-green-700 hover:underline text-xs"
                      onClick={() => onCommand(`sell ${item}`)}
                    >
                      sell
                    </button>
                  </span>
                </li>
              );
            })}
          </ul>
        ) : (
          <div className="text-green-700">Empty</div>
        )}
      </div>
    </div>
  );
}

export default function Page() {
  const [playerId, setPlayerId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [log, setLog] = useState<Line[]>([]);
  const [sceneImage, setSceneImage] = useState<string | null>(null);
  const [isLoadingScene, setIsLoadingScene] = useState(false);
  const [isWaitingForResponse, setIsWaitingForResponse] = useState(false);
  const [lastState, setLastState] = useState<any | null>(null);
  const [currentSceneKey, setCurrentSceneKey] = useState<string | null>(null);
  const [mapData, setMapData] = useState<any | null>(null);
  const [showMap, setShowMap] = useState(false);
  const [journalData, setJournalData] = useState<any | null>(null);
  const [showJournal, setShowJournal] = useState(false);
  const [bestiaryData, setBestiaryData] = useState<any | null>(null);
  const [showBestiary, setShowBestiary] = useState(false);
  const thumbsRef = useRef<Record<string, string>>({});
  const inputRef = useRef<HTMLInputElement>(null);

  // Record a downscaled thumbnail for a location (first image we see wins).
  async function recordThumb(locId?: string, img?: string | null) {
    if (!locId || !img || thumbsRef.current[locId]) return;
    const small = await downscale(img);
    thumbsRef.current = { ...thumbsRef.current, [locId]: small };
    saveThumbs(thumbsRef.current);
  }

  const bottomRef = useRef<HTMLDivElement>(null);

  async function handleSceneFromResponse(resp: any) {
    const newKey = computeSceneKeyFromResponse(resp);
    if (!newKey || newKey === currentSceneKey) return;

    setCurrentSceneKey(newKey);

    if (sceneImageCache.has(newKey)) {
      const cached = sceneImageCache.get(newKey)!;
      setSceneImage(cached);
      recordThumb(resp.state?.location?.id, cached);
      return;
    }

    setIsLoadingScene(true);
    try {
      const prompt = buildScenePrompt({
        location: resp.state?.location,
        entities: resp.state?.entities ?? [],
      });

      const img = await generateSceneImage(prompt);
      sceneImageCache.set(newKey, img);
      setSceneImage(img);
      recordThumb(resp.state?.location?.id, img);
    } catch {
      // non-fatal
    } finally {
      setIsLoadingScene(false);
    }
  }

  useEffect(() => {
    if (!isLoadingScene) {
      inputRef.current?.focus();
    }
  }, [isLoadingScene, log]);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // Restore player_id + saved map thumbnails from localStorage
  useEffect(() => {
    const saved = localStorage.getItem("player_id");
    if (saved) setPlayerId(saved);
    thumbsRef.current = loadThumbs();
  }, []);

  useEffect(() => {
    if (!playerId) return;

    (async () => {
      try {
        const resp = await sendCommand("look", playerId);

        if (resp.state) {
          setLastState(resp.state);
          await handleSceneFromResponse(resp);
          prefetchAdjacentScenes(resp.state); // 👈 THIS WAS MISSING
        }

        if (resp.messages) {
          setLog(
            resp.messages.map((m) => ({
              id: crypto.randomUUID(),
              text: m,
            }))
          );
        }
      } catch {
        // If resume fails, user can recreate character
      }
    })();
  }, [playerId]);

  // Auto-scroll log
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [log, isWaitingForResponse]);

  async function prefetchAdjacentScenes(state: any) {
    for (const scene of state.adjacent_scenes ?? []) {
      const fakeResp = { state: scene };

      const key = computeSceneKeyFromResponse(fakeResp);
      if (!key || sceneImageCache.has(key)) continue;

      try {
        const prompt = buildScenePrompt({
          location: scene.location,
          entities: scene.entities,
        });

        const img = await generateSceneImage(prompt);
        sceneImageCache.set(key, img);
        recordThumb(scene.location?.id, img);
      } catch {
        // prefetch failure is fine
      }
    }
  }

  async function runCommand(command: string) {
    if (isLoadingScene || isWaitingForResponse || !command.trim()) return;

    setInput("");
    setIsWaitingForResponse(true);

    // Echo command
    setLog((l) => [
      ...l,
      { id: crypto.randomUUID(), text: `> ${command}` },
    ]);

    try {
      const resp = await sendCommand(command, playerId);

      if (resp.state) {
        setLastState(resp.state);
      }

      // Panel commands open their overlays with the returned structured data.
      if (resp.state?.map) {
        setMapData(resp.state.map);
        setShowMap(true);
      }
      if (resp.state?.journal) {
        setJournalData(resp.state.journal);
        setShowJournal(true);
      }
      if (resp.state?.bestiary) {
        setBestiaryData(resp.state.bestiary);
        setShowBestiary(true);
      }

      // Capture player_id if returned
      if (resp.state?.player?.player_id) {
        const pid = resp.state.player.player_id;
        setPlayerId(pid);
        localStorage.setItem("player_id", pid);
      }

      // Handle errors
      if (!resp.ok && resp.error) {
        setLog((l) => [
          ...l,
          { id: crypto.randomUUID(), text: `[error] ${resp.error}` },
        ]);
      }

      // Scene handling
      if (resp.state?.scene_dirty) {
        await handleSceneFromResponse(resp);
      }

      // Prefetch adjacent scenes
      if (resp.state?.location) {
        prefetchAdjacentScenes(resp.state);
      }

      // Print messages
      if (resp.messages) {
        setLog((l) => [
          ...l,
          ...resp.messages.map((m) => ({
            id: crypto.randomUUID(),
            text: m,
          })),
        ]);
      }
    } catch {
      setLog((l) => [
        ...l,
        { id: crypto.randomUUID(), text: "[error] network error" },
      ]);
    } finally {
      setIsWaitingForResponse(false);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    await runCommand(input);
  }

  return (
    <div className="h-screen bg-black text-green-300 font-mono p-4 flex flex-col">
      <div className="flex items-center justify-between mb-2 gap-2 flex-wrap">
        <h1 className="text-xl">QuestAI</h1>
        <div className="flex flex-wrap gap-1">
          {[
            ["Look", "look"],
            ["🗺 Map", "map"],
            ["Journal", "journal"],
            ["Bestiary", "bestiary"],
            ["Stats", "stats"],
            ["Inventory", "inventory"],
            ["Gather", "gather"],
            ["Heal", "heal"],
          ].map(([label, cmd]) => (
            <button
              key={cmd}
              className="border border-green-700 px-2 py-1 text-xs hover:bg-green-900 disabled:opacity-40"
              onClick={() => runCommand(cmd)}
              disabled={!playerId || isWaitingForResponse}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {showMap && mapData && (
        <Modal title="World Map" onClose={() => setShowMap(false)}>
          <MapGraph mapData={mapData} thumbs={thumbsRef.current} />
          <div className="text-[11px] text-green-700 mt-3">
            Lines are paths between areas; the bright node is where you are.
            Click an exit (in the side panel) or type a direction to travel.
          </div>
        </Modal>
      )}

      {showJournal && journalData && (
        <Modal title="Quest Journal" onClose={() => setShowJournal(false)}>
          {["active", "completed", "archived"].map((bucket) => {
            const items = journalData[bucket] ?? [];
            if (items.length === 0) return null;
            const heading =
              bucket === "active"
                ? "Active"
                : bucket === "completed"
                ? "Ready to turn in"
                : "Finished";
            return (
              <div key={bucket} className="mb-4">
                <div className="text-green-400 font-bold mb-1">{heading}</div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                  {items.map((q: any) => (
                    <div key={q.quest_id} className="border border-green-800 p-2">
                      <div className="text-green-300">{q.name}</div>
                      <div className="text-[11px] text-green-700 mb-1">
                        {q.description}
                      </div>
                      {q.objectives?.map((o: any, i: number) => {
                        const done = o.progress >= o.required;
                        return (
                          <div
                            key={i}
                            className={`text-xs ${done ? "text-green-400" : "text-green-600"}`}
                          >
                            {done ? "✓" : "•"} {o.type} {o.target.replace(/_/g, " ")}:{" "}
                            {o.progress}/{o.required}
                          </div>
                        );
                      })}
                      <div className="text-[10px] text-green-700 mt-1">
                        reward:{" "}
                        {Object.entries(q.rewards || {})
                          .map(([it, n]) => `${n} ${it.replace(/_/g, " ")}`)
                          .join(", ")}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
          {(journalData.active?.length ?? 0) === 0 &&
            (journalData.completed?.length ?? 0) === 0 &&
            (journalData.archived?.length ?? 0) === 0 && (
              <div className="text-green-700">
                No quests yet — talk to a quest giver (Warden, Huntmaster, Scholar).
              </div>
            )}
        </Modal>
      )}

      {showBestiary && bestiaryData && (
        <Modal
          title={`Bestiary — ${bestiaryData.discovered.length}/${bestiaryData.total} discovered`}
          onClose={() => setShowBestiary(false)}
        >
          {bestiaryData.discovered.length === 0 ? (
            <div className="text-green-700">
              Nothing discovered yet — explore and fight to fill these pages.
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2">
              {bestiaryData.discovered.map((e: any) => (
                <div key={e.name} className="border border-green-800 p-2">
                  <div className="text-green-300">{e.name}</div>
                  <div className="text-xs text-green-600">
                    HP {e.max_hp} · ATK {e.attack} · {e.xp_reward} XP
                  </div>
                  {e.inflicts && (
                    <div className="text-[11px] text-red-400">
                      inflicts {e.inflicts}
                    </div>
                  )}
                  <div className="text-[10px] text-green-700 mt-1">
                    found in: {e.locations.join(", ")}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Modal>
      )}

      {/* Top area: image + status pane */}
      <div className="h-[420px] mb-2 flex border border-green-700">

        {/* Image side */}
        <div className="flex-[3] relative border-r border-green-700 overflow-hidden">
          {isLoadingScene && (
            <div className="absolute inset-0 z-10 flex items-center justify-center bg-black/80">
              <div className="animate-pulse text-green-400">
                Generating scene…
              </div>
            </div>
          )}

          {sceneImage ? (
            <div
              className="absolute inset-0 bg-center bg-cover"
              style={{ backgroundImage: `url(${sceneImage})` }}
            />
          ) : (
            <div className="flex items-center justify-center h-full text-green-700">
              No scene
            </div>
          )}
        </div>

        {/* Status pane */}
        <div className="flex-[1] p-3 overflow-y-auto">
          <StatusPane state={lastState} onCommand={runCommand} />
        </div>
      </div>

      {/* Log area – fixed height, scrolls */}
      <div className="flex-1 overflow-y-auto border border-green-700 p-2 mb-2">
        {log.map((line) => (
          <div key={line.id}>{line.text}</div>
        ))}
        {isWaitingForResponse && (
          <div className="animate-pulse text-green-500">...</div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} className="flex gap-2">
        <span>&gt;</span>
        <input
          ref={inputRef}
          className="flex-1 bg-black text-green-300 outline-none disabled:text-green-700"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={isLoadingScene || isWaitingForResponse}
        />
      </form>
    </div>
  );
}