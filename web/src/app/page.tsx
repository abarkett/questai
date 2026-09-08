"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { sendCommand, prefetchCaches } from "./lib/api";
import { generateSceneImage } from "./lib/gemini";
import { buildScenePrompt } from "./lib/scene";
import { Welcome } from "./welcome";

type Line = {
  id: string;
  text: string;
};

// cache survives re-renders
const sceneImageCache = new Map<string, string>();
// in-flight renders, so foreground + prefetch never render the same scene twice
const sceneInFlight = new Map<string, Promise<string>>();

// Get a scene image for a key, reusing the cache or any in-flight render.
function renderSceneCached(key: string, prompt: string): Promise<string> {
  const cached = sceneImageCache.get(key);
  if (cached) return Promise.resolve(cached);
  const existing = sceneInFlight.get(key);
  if (existing) return existing;
  const p = generateSceneImage(prompt)
    .then((img) => {
      sceneImageCache.set(key, img);
      sceneInFlight.delete(key);
      return img;
    })
    .catch((e) => {
      sceneInFlight.delete(key);
      throw e;
    });
  sceneInFlight.set(key, p);
  return p;
}

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

  // NOTE: the key intentionally excludes hp — the scene art shouldn't change as
  // a monster takes damage, only when the *set* of creatures present changes
  // (a monster dies/spawns). This avoids regenerating on every hit.
  return JSON.stringify({
    locationId: state.location.id,
    locationDescription: state.location.description,
    entities: entities
      .map((e: any) => ({ type: e.type, name: e.name }))
      .sort((a: any, b: any) => a.name.localeCompare(b.name)),
  });
}

function computeMapLayout(mapData: any) {
  const byId: Record<string, any> = {};
  for (const n of mapData.locations) byId[n.id] = n;

  // Undirected adjacency among known nodes.
  const adj: Record<string, string[]> = {};
  const link = (a: string, b: string) => { (adj[a] ||= []).push(b); };
  for (const n of mapData.locations) {
    for (const ex of n.exits || []) {
      if (byId[ex.to]) { link(n.id, ex.to); link(ex.to, n.id); }
    }
  }
  for (const k in adj) adj[k] = Array.from(new Set(adj[k]));

  // Layered layout: BFS depth from the current location.
  const root = mapData.current && byId[mapData.current] ? mapData.current : mapData.locations[0]?.id;
  const depth: Record<string, number> = {};
  const layers: string[][] = [];
  if (root) {
    depth[root] = 0;
    layers[0] = [root];
    const queue = [root];
    while (queue.length) {
      const cur = queue.shift() as string;
      for (const nb of adj[cur] || []) {
        if (depth[nb] === undefined) {
          depth[nb] = depth[cur] + 1;
          (layers[depth[nb]] ||= []).push(nb);
          queue.push(nb);
        }
      }
    }
  }
  for (const n of mapData.locations) {
    if (depth[n.id] === undefined) {
      const d = layers.length;
      depth[n.id] = d;
      (layers[d] ||= []).push(n.id);
    }
  }

  // Barycenter ordering passes to reduce edge crossings.
  const idx: Record<string, number> = {};
  const reindex = () => { for (const L of layers) L.forEach((id, i) => (idx[id] = i)); };
  const bary = (id: string, layerIdx: number): number => {
    const neigh = (adj[id] || []).filter((nb) => depth[nb] === layerIdx);
    if (!neigh.length) return idx[id] ?? 0;
    return neigh.reduce((s, nb) => s + (idx[nb] ?? 0), 0) / neigh.length;
  };
  reindex();
  for (let pass = 0; pass < 4; pass++) {
    for (let d = 1; d < layers.length; d++) layers[d].sort((a, b) => bary(a, d - 1) - bary(b, d - 1));
    reindex();
    for (let d = layers.length - 2; d >= 0; d--) layers[d].sort((a, b) => bary(a, d + 1) - bary(b, d + 1));
    reindex();
  }

  // Coordinates: y = depth (row), x centered within each layer.
  const pos: Record<string, [number, number]> = {};
  const maxWidth = Math.max(1, ...layers.map((L) => L.length));
  layers.forEach((L, d) => {
    const offset = (maxWidth - L.length) / 2;
    L.forEach((id, i) => (pos[id] = [i + offset, d]));
  });

  const edges: { a: [number, number]; b: [number, number]; current: boolean }[] = [];
  const seen = new Set<string>();
  for (const n of mapData.locations) {
    for (const ex of n.exits || []) {
      if (!pos[n.id] || !pos[ex.to]) continue;
      const a = n.id < ex.to ? n.id : ex.to;
      const b = n.id < ex.to ? ex.to : n.id;
      const ek = `${a}|${b}`;
      if (seen.has(ek)) continue;
      seen.add(ek);
      edges.push({ a: pos[a], b: pos[b], current: n.id === mapData.current || ex.to === mapData.current });
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
      {/* Non-current edges first (dim), then current-location edges on top (bright). */}
      {L.edges.filter((e) => !e.current).map((e, i) => (
        <line key={`d${i}`} x1={cx(e.a[0])} y1={cy(e.a[1])} x2={cx(e.b[0])} y2={cy(e.b[1])}
          stroke="#14532d" strokeWidth={1.5} />
      ))}
      {L.edges.filter((e) => e.current).map((e, i) => (
        <line key={`c${i}`} x1={cx(e.a[0])} y1={cy(e.a[1])} x2={cx(e.b[0])} y2={cy(e.b[1])}
          stroke="#4ade80" strokeWidth={4} />
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
              fill={here ? "#bbf7d0" : n.visited ? "#86efac" : "#4b5563"}
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

// Mirrors app/companions.py: these NPCs anchor the world and can't be recruited.
const NON_RECRUITABLE_ROLES = ["shop", "quest_giver", "arc_giver"];
const COMPANION_TITLE: Record<string, string> = {
  vanguard: "Vanguard",
  mender: "Mender",
  outrider: "Outrider",
};

function StatusPane({ state, onCommand }: { state: any | null; onCommand: (cmd: string) => void; }) {
  const [tab, setTab] = useState<string>("summary");

  if (!state?.player || !state?.location) {
    return <div className="text-green-700">No character loaded</div>;
  }

  const { player, location } = state;
  const entities = state.entities ?? [];
  const monsters = entities.filter((e: any) => e.type === "monster");
  const people = entities.filter((e: any) => e.type === "npc" || e.type === "player");
  const abilities = state.abilities ?? [];
  const hpPct = Math.max(0, Math.min(100, (100 * player.hp) / player.max_hp));

  const Section = ({ title, children }: { title: string; children: ReactNode }) => (
    <div>
      <div className="text-green-400 font-bold">{title}</div>
      {children}
    </div>
  );

  const apMax = 30; // server cap (QUESTAI_AP_MAX); AP fields ship in player state
  const ap = typeof player.action_points === "number" ? player.action_points : null;
  const apPct = ap != null ? Math.max(0, Math.min(100, (100 * ap) / apMax)) : 0;

  const hpBar = (
    <div>
      <div className="flex items-center gap-2">
        <div className="flex-1 h-3 bg-green-950 border border-green-800">
          <div className="h-full bg-green-600" style={{ width: `${hpPct}%` }} />
        </div>
        <span className="text-xs whitespace-nowrap">{player.hp}/{player.max_hp}</span>
      </div>
      {ap != null && (
        <div className="flex items-center gap-2 mt-1" title="Action points — every world-changing action costs 1; they regenerate over time">
          <div className="flex-1 h-2 bg-green-950 border border-green-800">
            <div className="h-full bg-amber-500" style={{ width: `${apPct}%` }} />
          </div>
          <span className="text-xs whitespace-nowrap">AP {ap}/{apMax}</span>
        </div>
      )}
      <div className="text-xs mt-1">Level {player.level} · XP {player.xp}</div>
    </div>
  );

  const TABS: [string, string][] = [
    ["summary", "Summary"], ["gear", "Gear"], ["skills", "Skills"], ["party", "Party"],
  ];

  return (
    <div className="h-full flex flex-col text-sm">
      <div className="text-base font-bold text-green-300 mb-1 shrink-0">{player.name}</div>
      <div className="flex gap-1 mb-2 shrink-0">
        {TABS.map(([id, label]) => (
          <button key={id} onClick={() => setTab(id)}
            className={`px-2 py-0.5 text-xs border ${tab === id ? "border-green-400 text-green-200" : "border-green-800 text-green-600 hover:text-green-400"}`}>
            {label}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto pr-1 space-y-3">
        {tab === "summary" && (
          <>
            {Array.isArray(state.guidance) && state.guidance.length > 0 && (
              <Section title="What now?">
                <div className="space-y-1">
                  {state.guidance.map((g: any, i: number) => (
                    g.command ? (
                      <button key={i} className="block text-left text-xs text-green-300 hover:underline"
                        onClick={() => onCommand(g.command)}>• {g.text}</button>
                    ) : (
                      <div key={i} className="text-xs text-green-600">• {g.text}</div>
                    )
                  ))}
                </div>
              </Section>
            )}

            {state.campaign && (
              <Section title={state.campaign.complete ? "The Realm Restored" : `Act ${state.campaign.act_index + 1}${state.campaign.acts_total ? ` of ${state.campaign.acts_total}` : ""}: ${state.campaign.act_name}`}>
                <div className="text-xs text-green-600 mb-1">{state.campaign.act_blurb}</div>
                <div className="space-y-1">
                  {(state.campaign.wrongs || []).map((w: any) => (
                    <div key={w.id} className="text-xs flex items-start gap-2 flex-wrap" title={w.blurb ? `${w.blurb} ${w.deed}` : w.deed}>
                      <span className={
                        w.status === "righted" ? "text-green-800 line-through" :
                        w.status === "active" ? "text-yellow-300" : "text-green-300"
                      }>
                        {w.status === "righted" ? "✓" : w.status === "active" ? "…" : w.climax ? "!" : "•"} {w.title}
                      </span>
                      {w.status === "righted" && w.righted_by && (
                        <span className="text-green-800">— {w.righted_by}</span>
                      )}
                      {w.status === "righted" && w.entry && (
                        <span className="basis-full pl-4 italic text-green-900">“{w.entry}”</span>
                      )}
                      {w.status === "active" && w.progress && (
                        <span className="text-yellow-600">{w.progress}</span>
                      )}
                      {w.status === "open" && w.command && (
                        <button className="px-1 border border-green-800 hover:bg-green-900"
                          onClick={() => onCommand(w.command)}>undertake</button>
                      )}
                      {w.status === "open" && w.climax && (
                        <button className="px-1 border border-red-800 text-red-300 hover:bg-red-950"
                          onClick={() => onCommand("raid")}>the Warfront</button>
                      )}
                    </div>
                  ))}
                </div>
                {Array.isArray(state.campaign.titles) && state.campaign.titles.length > 0 && (
                  <div className="text-xs mt-1 text-yellow-300">Your Legend: {state.campaign.titles.join(", ")}</div>
                )}
              </Section>
            )}

            {hpBar}

            {state.identity && !state.identity.archetype && Array.isArray(state.identity.paths) && (
              <Section title="Choose your path">
                <div className="text-xs text-green-600 mb-1">The one choice that shapes how you fight.</div>
                <div className="space-y-1">
                  {state.identity.paths.map((p: any) => (
                    <button key={p.id} className="block text-left text-xs hover:underline"
                      title={`${p.description} — ${p.passive}`}
                      onClick={() => onCommand(`path ${p.id}`)}>
                      <span className="text-green-300">{p.name}</span> — {p.passive}
                    </button>
                  ))}
                </div>
              </Section>
            )}

            {state.identity && state.identity.archetype && (
              <Section title="Path">
                <div className="text-xs">
                  <span className="text-green-300">{state.identity.archetype_name}</span> · {state.identity.passive}
                </div>
                {state.identity.skill_points > 0 && (
                  <div className="mt-1">
                    <div className="text-xs text-yellow-300">{state.identity.skill_points} skill point(s) to spend:</div>
                    <div className="flex flex-wrap gap-1 mt-0.5">
                      {(state.identity.learnable || []).map((a: any) => (
                        <button key={a.id} className="px-1 border border-green-800 text-xs hover:bg-green-900"
                          onClick={() => onCommand(`learn ${a.id}`)}>learn {a.name}</button>
                      ))}
                    </div>
                  </div>
                )}
              </Section>
            )}

            {player.companion && (
              <Section title="Companion">
                <div className="text-xs">
                  <span className="text-green-300">{player.companion.name}</span>
                  {" — "}{COMPANION_TITLE[player.companion.archetype] ?? player.companion.archetype}
                  {" · Lv "}{1 + Math.floor(Math.min(player.companion.loyalty, 100) / 25)}
                  {" · loyalty "}{player.companion.loyalty}/100
                </div>
                <button className="text-green-700 hover:underline text-xs mt-0.5"
                  onClick={() => onCommand("dismiss")}>dismiss</button>
              </Section>
            )}

            {Array.isArray(state.incidents) && state.incidents.length > 0 && (
              <Section title="News of the Realm">
                <div className="space-y-1">
                  {state.incidents.map((inc: any) => (
                    <div key={inc.id} className="text-xs" title={inc.blurb}>
                      <span className={inc.kind === "incursion" ? "text-red-300" : "text-yellow-300"}>
                        {inc.kind === "incursion" ? "!" : "+"} {inc.title}
                      </span>
                      <span className="text-green-700"> — {inc.location_name}{inc.here ? " (here)" : ""}</span>
                      {inc.kind === "incursion" && inc.creatures_left != null && (
                        <span className="text-green-600"> · {inc.creatures_left} {inc.creature_name}{inc.creatures_left === 1 ? "" : "s"} left · {inc.turns_left} turns</span>
                      )}
                      {inc.kind === "boon" && inc.effect_words && (
                        <span className="text-green-600"> · {inc.effect_words} · {inc.turns_left} turns</span>
                      )}
                      {inc.kind === "incursion" && inc.here && inc.creatures_left > 0 && (
                        <button className="ml-2 px-1 border border-red-800 text-red-300 hover:bg-red-950"
                          onClick={() => onCommand(`fight ${inc.creature_name}`)}>fight</button>
                      )}
                    </div>
                  ))}
                </div>
              </Section>
            )}

            {state.raid && (
              <Section title="World Threat">
                <div className="text-xs">
                  <span className="text-red-300 font-bold">{state.raid.name}</span>
                  {state.raid.title ? ` — ${state.raid.title}` : ""}
                </div>
                <div className="mt-1 h-2 bg-red-950 border border-red-900">
                  <div className="h-full bg-red-600"
                    style={{ width: `${Math.max(0, Math.min(100, (100 * state.raid.hp) / state.raid.max_hp))}%` }} />
                </div>
                <div className="text-xs mt-0.5">
                  {state.raid.hp}/{state.raid.max_hp} HP · your blows: {state.raid.your_damage}
                </div>
                {Array.isArray(state.raid.top) && state.raid.top.length > 0 && (
                  <div className="text-xs text-green-700">
                    Top: {state.raid.top.map((t: any) => `${t.name} (${t.damage})`).join(", ")}
                  </div>
                )}
                {state.raid.at_lair ? (
                  <button className="px-1 mt-1 border border-red-800 text-red-300 text-xs hover:bg-red-950"
                    title={`Strike the boss — spoils pool ${state.raid.reward_pool} coins, split by damage done`}
                    onClick={() => onCommand("raid strike")}>strike</button>
                ) : (
                  <button className="px-1 mt-1 border border-red-800 text-red-300 text-xs hover:bg-red-950"
                    title="Travel to the Warfront to make your stand"
                    onClick={() => onCommand("go warfront")}>go to the Warfront</button>
                )}
              </Section>
            )}

            {state.stronghold && (
              <Section title="Stronghold">
                {state.stronghold.level === 0 ? (
                  <>
                    <div className="text-xs">You hold no ground of your own yet.</div>
                    <button className="px-1 mt-1 border border-green-800 text-xs hover:bg-green-900"
                      title="Found a Campsite — a stash, a tribute, and a place to grow"
                      onClick={() => onCommand("build")}>build a Campsite ({state.stronghold.next_cost})</button>
                  </>
                ) : (
                  <>
                    <div className="text-xs">
                      <span className="text-green-300">{state.stronghold.tier}</span> (tier {state.stronghold.level}/5)
                    </div>
                    <div className="flex flex-wrap gap-1 mt-1">
                      {state.stronghold.tribute > 0 && (
                        <button className="px-1 border border-yellow-800 text-yellow-300 text-xs hover:bg-yellow-950"
                          onClick={() => onCommand("collect")}>collect {state.stronghold.tribute} tribute</button>
                      )}
                      {state.stronghold.next_cost && (
                        <button className="px-1 border border-green-800 text-xs hover:bg-green-900"
                          onClick={() => onCommand("build")}>
                          upgrade to {state.stronghold.next_tier} ({state.stronghold.next_cost})
                        </button>
                      )}
                    </div>
                    {state.stronghold.stash && Object.keys(state.stronghold.stash).length > 0 && (
                      <div className="mt-1 text-xs">
                        <div className="text-green-700">
                          Stash ({Object.keys(state.stronghold.stash).length}/{state.stronghold.stash_cap}):
                        </div>
                        {Object.entries(state.stronghold.stash).map(([item, qty]: [string, any]) => (
                          <div key={item} className="flex items-center gap-2">
                            <span>{qty}x {item.replace(/_/g, " ")}</span>
                            <button className="text-green-700 hover:underline"
                              onClick={() => onCommand(`unstash ${item}`)}>withdraw</button>
                          </div>
                        ))}
                      </div>
                    )}
                  </>
                )}
              </Section>
            )}

            {player.status_effects && Object.keys(player.status_effects).length > 0 && (
              <Section title="Status">
                {Object.entries(player.status_effects).map(([eid, st]: [string, any]) => (
                  <div key={eid} className="text-xs">
                    {String(eid).replace(/_/g, " ")} ({st?.turns ?? 0} turns)
                  </div>
                ))}
              </Section>
            )}

            <Section title="Location"><div>{location.name}</div></Section>

            {monsters.length > 0 && (
              <Section title="Enemies Here">
                {monsters.map((m: any) => (
                  <div key={m.id} className="mb-1">
                    <div>{m.name}{m.hp != null ? ` (${m.hp} hp)` : ""}</div>
                    <div className="flex flex-wrap gap-1 mt-0.5">
                      <button className="px-1 border border-red-800 text-red-300 text-xs hover:bg-red-950"
                        onClick={() => onCommand(`attack ${m.id}`)}>attack</button>
                      <button className="px-1 border border-red-800 text-red-300 text-xs hover:bg-red-950"
                        title="Resolve the whole encounter in one action"
                        onClick={() => onCommand(`fight ${m.id}`)}>fight</button>
                      {abilities.filter((a: any) => a.ready && (a.kind === "attack" || a.kind === "dot")).map((a: any) => (
                        <button key={a.id} className="px-1 border border-green-800 text-xs hover:bg-green-900"
                          title={a.description} onClick={() => onCommand(`${a.id} ${m.id}`)}>{a.name}</button>
                      ))}
                    </div>
                  </div>
                ))}
              </Section>
            )}

            {abilities.some((a: any) => a.kind === "heal" || a.kind === "aoe") && (
              <Section title="Self / Area">
                <div className="flex flex-wrap gap-1">
                  {abilities.filter((a: any) => a.kind === "heal" || a.kind === "aoe").map((a: any) => (
                    <button key={a.id} disabled={!a.ready}
                      title={a.ready ? a.description : `On cooldown (${a.remaining}s)`}
                      className="px-1 border border-green-800 text-xs hover:bg-green-900 disabled:opacity-40"
                      onClick={() => onCommand(a.id)}>
                      {a.name}{a.ready ? "" : ` (${a.remaining}s)`}
                    </button>
                  ))}
                </div>
              </Section>
            )}

            {people.length > 0 && (
              <Section title="People Here">
                <div className="space-y-1">
                  {people.map((entity: any) => {
                    const isInParty = state.party?.members?.some((mm: any) => mm.player_id === entity.id);
                    const canRecruit = entity.type === "npc" && !player.companion
                      && !NON_RECRUITABLE_ROLES.includes(entity.role);
                    return (
                      <div key={entity.id} className="flex items-center gap-2">
                        <button className="text-left hover:underline"
                          onClick={() => onCommand(`talk ${entity.id}`)}>
                          {entity.name}{entity.type === "player" ? " (player)" : ""}{isInParty ? " ⚔️" : ""}
                        </button>
                        {canRecruit && (
                          <button className="px-1 border border-green-800 text-xs hover:bg-green-900"
                            title="Recruit as a companion (costs a coin signing bonus)"
                            onClick={() => onCommand(`recruit ${entity.id}`)}>recruit</button>
                        )}
                      </div>
                    );
                  })}
                </div>
              </Section>
            )}

            {((player.active_quests && Object.keys(player.active_quests).length > 0) ||
              (player.completed_quests && Object.keys(player.completed_quests).length > 0)) && (
              <Section title="Active Quests">
                {Object.values(player.active_quests ?? {}).map((q: any) => {
                  const staged = q.stages && q.stages.length > 0;
                  const objs = staged ? (q.stages[q.current_stage]?.objectives ?? []) : (q.objectives ?? []);
                  return (
                    <div key={q.quest_id} className="text-xs mb-1">
                      <div className="font-semibold">{q.name}</div>
                      {staged && (
                        <div className="text-green-600">
                          Stage {q.current_stage + 1}/{q.stages.length}: {q.stages[q.current_stage]?.description}
                        </div>
                      )}
                      {objs.map((obj: any, i: number) => (
                        <div key={i} className={obj.progress >= obj.required ? "text-green-400" : "text-green-700"}>
                          {obj.type} {String(obj.target).replace(/_/g, " ")}: {obj.progress}/{obj.required}
                        </div>
                      ))}
                    </div>
                  );
                })}
                {Object.values(player.completed_quests ?? {}).map((q: any) => {
                  const staged = q.stages && q.stages.length > 0;
                  const objs = staged ? (q.stages[q.current_stage]?.objectives ?? []) : (q.objectives ?? []);
                  return (
                    <div key={q.quest_id} className="text-xs mb-1">
                      <div className="font-semibold">{q.name}</div>
                      {objs.map((obj: any, i: number) => (
                        <div key={i} className="text-green-400">
                          {obj.type} {String(obj.target).replace(/_/g, " ")}: {obj.progress}/{obj.required}
                        </div>
                      ))}
                    </div>
                  );
                })}
              </Section>
            )}

            <Section title="Exits">
              <div className="flex flex-wrap gap-2 mt-1">
                {location.exits.map((e: any) => (
                  <button key={e.to} className="px-2 py-1 border border-green-700 hover:bg-green-900 text-green-300 text-xs"
                    onClick={() => onCommand(`go ${e.label}`)}>{e.name ?? e.label}</button>
                ))}
              </div>
            </Section>

            {state.rumors?.length > 0 && (
              <Section title="Word Going Around">
                {state.rumors.map((r: string, i: number) => (
                  <div key={`rumor-${i}`} className="text-xs text-amber-200/80 italic">{r}</div>
                ))}
              </Section>
            )}

            {(state.echoes?.length > 0 || state.notes?.length > 0) && (
              <Section title="Traces of Others">
                {(state.echoes ?? []).map((e: any, i: number) => (
                  <div key={`echo-${i}`} className="text-xs text-green-600 italic">
                    {e.description} ({e.ago})
                  </div>
                ))}
                {(state.notes ?? []).map((n: any, i: number) => (
                  <div key={`note-${i}`} className="text-xs text-green-500">
                    “{n.text}” — {n.player_name}
                  </div>
                ))}
              </Section>
            )}
          </>
        )}

        {tab === "gear" && (
          <>
            {hpBar}
            <Section title="Equipped">
              {player.equipment && Object.keys(player.equipment).length > 0 ? (
                Object.entries(player.equipment).map(([slot, itemId]) => (
                  <div key={slot} className="flex justify-between items-center text-xs">
                    <span>{slot}: {String(itemId).replace(/_/g, " ")}</span>
                    <button className="text-green-700 hover:underline" onClick={() => onCommand(`unequip ${slot}`)}>unequip</button>
                  </div>
                ))
              ) : (<div className="text-green-700 text-xs">Nothing equipped</div>)}
            </Section>
            <Section title="Inventory">
              {player.inventory && Object.keys(player.inventory).length > 0 ? (
                <ul className="space-y-0.5">
                  {Object.entries(player.inventory).map(([item, qty]) => {
                    const info = (state.item_info ?? {})[item] ?? {};
                    const isGear = info.type === "weapon" || info.type === "armor" || GEAR_RE.test(item);
                    const hasDelta = typeof info.delta === "number";
                    return (
                      <li key={item} className="flex justify-between items-center gap-2">
                        <span className="min-w-0">
                          {item.replace(/_/g, " ")} × {qty as number}
                          {info.stat && <span className="text-green-600"> ({info.stat}</span>}
                          {hasDelta && (
                            <span className={info.delta > 0 ? "text-green-400" : info.delta < 0 ? "text-red-400" : "text-green-700"}>
                              {info.delta > 0 ? `, ${info.delta} better` : info.delta < 0 ? `, ${-info.delta} worse` : ", same"}
                            </span>
                          )}
                          {info.stat && <span className="text-green-600">)</span>}
                        </span>
                        <span className="flex gap-2 shrink-0">
                          <button className="text-green-400 hover:underline text-xs" onClick={() => onCommand(`${isGear ? "equip" : "use"} ${item}`)}>{isGear ? "equip" : "use"}</button>
                          {state.stronghold?.level > 0 && item !== "coin" && (
                            <button className="text-green-700 hover:underline text-xs" onClick={() => onCommand(`stash ${item}`)}>stash</button>
                          )}
                          <button className="text-green-700 hover:underline text-xs" onClick={() => onCommand(`sell ${item}`)}>sell</button>
                        </span>
                      </li>
                    );
                  })}
                </ul>
              ) : (<div className="text-green-700">Empty</div>)}
            </Section>
          </>
        )}

        {tab === "skills" && (
          <Section title="Abilities">
            {abilities.length === 0 ? (
              <div className="text-green-700 text-xs">No abilities yet — level up to learn them.</div>
            ) : (
              <div className="space-y-2">
                {abilities.map((a: any) => {
                  const needsTarget = a.kind === "attack" || a.kind === "dot";
                  const needsEnemy = needsTarget || a.kind === "aoe";
                  const canUse = a.ready && (!needsEnemy || monsters.length > 0);
                  const icon = a.kind === "heal" ? " ✚" : a.kind === "aoe" ? " ✸" : a.kind === "dot" ? " ☠" : " ⚔";
                  const hint = !a.ready ? `On cooldown (${a.remaining}s)` : (needsEnemy && monsters.length === 0 ? "No enemy here" : "Use");
                  return (
                    <div key={a.id} className="border border-green-900 p-1">
                      <div className="flex justify-between items-center">
                        <span className="text-green-300">{a.name}{icon}</span>
                        <button disabled={!canUse} title={hint}
                          className="text-xs px-1 border border-green-700 hover:bg-green-900 disabled:opacity-40"
                          onClick={() => onCommand(needsTarget && monsters.length > 0 ? `${a.id} ${monsters[0].id}` : a.id)}>
                          {a.ready ? "use" : `${a.remaining}s`}
                        </button>
                      </div>
                      <div className="text-[11px] text-green-700">{a.description}</div>
                    </div>
                  );
                })}
              </div>
            )}
          </Section>
        )}

        {tab === "party" && (
          <>
            {state.party ? (
              <Section title={state.party.name || "Party"}>
                {state.party.members.map((member: any) => (
                  <div key={member.player_id} className={member.online ? "" : "text-green-800"}>
                    {member.online ? "● " : "○ "}{member.name}{member.is_leader ? " (Leader)" : ""}
                    {!member.online && member.last_seen_text ? ` — ${member.last_seen_text}` : ""}
                  </div>
                ))}
                <button className="text-red-400 hover:underline text-xs mt-1" onClick={() => onCommand("party leave")}>Leave Party</button>
              </Section>
            ) : (<div className="text-green-700 text-xs">Not in a party.</div>)}

            {state.party_invites?.length > 0 && (
              <Section title="Party Invites">
                {state.party_invites.map((invite: any) => (
                  <div key={invite.invite_id} className="text-xs mb-1 p-1 border border-green-600">
                    <div>From {invite.from_player_name}</div>
                    <button className="text-green-400 hover:underline text-xs mt-1" onClick={() => onCommand(`accept_party_invite ${invite.invite_id}`)}>Accept</button>
                  </div>
                ))}
              </Section>
            )}

            {(state.pending_trade_offers?.length > 0 || state.pending_trade_offers_sent?.length > 0) && (
              <Section title="Trades">
                {state.pending_trade_offers?.map((trade: any) => (
                  <div key={trade.trade_id} className={`text-xs mb-1 p-1 border ${trade.can_accept ? "border-green-600" : "border-green-900 opacity-50"}`}>
                    <div className="font-semibold">From {trade.from_player_name}:</div>
                    <div>Offers: {Object.entries(trade.offered_items).map(([it, q]) => `${it}:${q}`).join(", ")}</div>
                    <div>Wants: {Object.entries(trade.requested_items).map(([it, q]) => `${it}:${q}`).join(", ")}</div>
                    {trade.can_accept ? (
                      <button className="text-green-400 hover:underline text-xs mt-1" onClick={() => onCommand(`accept_trade ${trade.trade_id}`)}>Accept</button>
                    ) : (<div className="text-green-800 text-xs mt-1">Cannot accept</div>)}
                  </div>
                ))}
                {state.pending_trade_offers_sent?.map((trade: any) => (
                  <div key={trade.trade_id} className={`text-xs mb-1 p-1 border ${trade.can_be_accepted ? "border-green-600" : "border-green-900 opacity-50"}`}>
                    <div className="font-semibold">To {trade.to_player_name}:</div>
                    <div>You offer: {Object.entries(trade.offered_items).map(([it, q]) => `${it}:${q}`).join(", ")}</div>
                    <div>You want: {Object.entries(trade.requested_items).map(([it, q]) => `${it}:${q}`).join(", ")}</div>
                    <button className="text-red-400 hover:underline text-xs" onClick={() => onCommand(`cancel_trade ${trade.trade_id}`)}>Cancel</button>
                  </div>
                ))}
              </Section>
            )}
          </>
        )}
      </div>
    </div>
  );
}

export default function Page() {
  const [playerId, setPlayerId] = useState<string | null>(null);
  // A returning player's identity is restored from localStorage after mount;
  // until that check has run we must not flash the welcome screen at them.
  const [hasSavedPlayer, setHasSavedPlayer] = useState(true);
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
  const skipResumeLook = useRef(false);

  // Record a downscaled thumbnail for a location (first image we see wins).
  async function recordThumb(locId?: string, img?: string | null) {
    if (!locId || !img || thumbsRef.current[locId]) return;
    const small = await downscale(img);
    thumbsRef.current = { ...thumbsRef.current, [locId]: small };
    saveThumbs(thumbsRef.current);
  }

  const bottomRef = useRef<HTMLDivElement>(null);
  const lastPrefetchLoc = useRef<string | null>(null);

  // Warm Miriel description caches (this room + neighbors) once per room entry.
  function maybePrefetch(state: any, pid: string | null) {
    const loc = state?.location?.id;
    if (loc && loc !== lastPrefetchLoc.current) {
      lastPrefetchLoc.current = loc;
      prefetchCaches(pid);
    }
  }

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

      const img = await renderSceneCached(newKey, prompt); // reuses any prefetch
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
    else {
      setHasSavedPlayer(false);
      setLog([{
        id: crypto.randomUUID(),
        text: "Welcome to QuestAI.",
      }]);
    }
    thumbsRef.current = loadThumbs();
  }, []);

  useEffect(() => {
    if (!playerId) return;
    if (skipResumeLook.current) {
      skipResumeLook.current = false;
      return;
    }

    (async () => {
      try {
        const resp = await sendCommand("look", playerId);

        if (!resp.ok && !resp.state) {
          // Stale identity (e.g. the world was reset): drop it and start over.
          localStorage.removeItem("player_id");
          setPlayerId(null);
          setHasSavedPlayer(false);
          setLog([{
            id: crypto.randomUUID(),
            text: "Your hero is gone — the world has begun anew. Type: create <name> to forge a new one.",
          }]);
          return;
        }

        if (resp.state) {
          setLastState(resp.state);
          await handleSceneFromResponse(resp);
          prefetchAdjacentScenes(resp.state);
          prefetchCombatVariants(resp.state);
          maybePrefetch(resp.state, playerId);
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

  function prefetchAdjacentScenes(state: any) {
    for (const scene of state.adjacent_scenes ?? []) {
      const key = computeSceneKeyFromResponse({ state: scene });
      if (!key || sceneImageCache.has(key)) continue;
      const prompt = buildScenePrompt({ location: scene.location, entities: scene.entities });
      renderSceneCached(key, prompt)
        .then((img) => recordThumb(scene.location?.id, img))
        .catch(() => {});
    }
  }

  // Pre-generate the likely post-combat scenes for the current room (each single
  // enemy removed, and the fully-cleared room) so killing an enemy doesn't pause
  // to render. Fire-and-forget; failures are ignored. Costs a few extra renders.
  function prefetchCombatVariants(state: any) {
    const entities = state.entities ?? [];
    const monsters = entities.filter((e: any) => e.type === "monster");
    if (monsters.length === 0) return;

    const variants: any[][] = [entities.filter((e: any) => e.type !== "monster")]; // cleared
    if (monsters.length > 1) {
      for (const m of monsters) variants.push(entities.filter((e: any) => e.id !== m.id));
    }

    for (const ents of variants) {
      const key = computeSceneKeyFromResponse({ state: { ...state, entities: ents } });
      if (!key || sceneImageCache.has(key)) continue;
      const prompt = buildScenePrompt({ location: state.location, entities: ents });
      renderSceneCached(key, prompt).catch(() => {});
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
        if (pid !== playerId) {
          // A hero just forged: their welcome is in THIS response, so the
          // resume-look must not run and wipe it.
          skipResumeLook.current = true;
        }
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

      // Prefetch adjacent scenes + likely post-combat variants for this room,
      // and warm Miriel description caches when we enter a new room.
      if (resp.state?.location) {
        prefetchAdjacentScenes(resp.state);
        prefetchCombatVariants(resp.state);
        maybePrefetch(resp.state, playerId);
      }

      // Print messages
      const messages = resp.messages ?? [];
      if (messages.length > 0) {
        setLog((l) => [
          ...l,
          ...messages.map((m) => ({
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
            ["Gather", "gather"],
            ["Heal", "heal"],
            ["🗺 Map", "map"],
            ["Journal", "journal"],
            ["Bestiary", "bestiary"],
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
            <span className="text-green-400">Bright green lines</span> are the exits
            from where you are now; dim lines are paths elsewhere. Use the Exits
            buttons (side panel) or type a direction to travel.
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
                      {q.total_stages && (
                        <div className="text-[11px] text-green-500 mb-1">
                          Stage {q.stage}/{q.total_stages}: {q.stage_description}
                        </div>
                      )}
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

      {/* A newcomer sees the realm as it stands and forges a hero; the game
          proper waits until they have one. */}
      {!playerId && !hasSavedPlayer && (
        <Welcome
          busy={isWaitingForResponse}
          onCreate={(name, path) => runCommand(`create ${name} ${path}`)}
        />
      )}

      {/* Main area: left column (image over log) + full-height status pane */}
      <div className={`flex-1 min-h-0 mb-2 flex gap-2 ${!playerId && !hasSavedPlayer ? "hidden" : ""}`}>

        {/* Left column: scene image on top, log below */}
        <div className="flex-[3] flex flex-col min-h-0 gap-2">
          <div className="h-[420px] shrink-0 relative border border-green-700 overflow-hidden">
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
              // No art (image generation off, or a render failed): the place
              // still has a face — its name and its description.
              <div className="absolute inset-0 bg-gradient-to-b from-green-950 via-black to-black flex flex-col items-center justify-center p-6 text-center">
                <div className="text-2xl text-green-300">{lastState?.location?.name ?? "QuestAI"}</div>
                {lastState?.location?.description && (
                  <div className="text-xs text-green-600 mt-2 max-w-xl">{lastState.location.description}</div>
                )}
              </div>
            )}
          </div>

          {/* Log area – fills remaining height, scrolls */}
          <div className="flex-1 min-h-0 overflow-y-auto border border-green-700 p-2">
            {log.map((line) => (
              <div key={line.id}>{line.text}</div>
            ))}
            {isWaitingForResponse && (
              <div className="animate-pulse text-green-500">...</div>
            )}
            <div ref={bottomRef} />
          </div>
        </div>

        {/* Status pane – full height of the main area */}
        <div className="flex-[1] min-h-0 p-3 border border-green-700 overflow-hidden">
          <StatusPane state={lastState} onCommand={runCommand} />
        </div>
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} className={`flex gap-2 items-center border border-green-800 px-2 py-1 ${!playerId && !hasSavedPlayer ? "hidden" : ""}`}>
        <span className="text-green-500">&gt;</span>
        <input
          ref={inputRef}
          className="flex-1 bg-black text-green-300 outline-none disabled:text-green-700 placeholder:text-green-900"
          placeholder={isWaitingForResponse ? "the world turns…" : isLoadingScene ? "painting the scene…" : "type a command — look · go <exit> · fight <foe> · talk <npc> · next"}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={isLoadingScene || isWaitingForResponse}
        />
      </form>
    </div>
  );
}