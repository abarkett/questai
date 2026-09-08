"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { sendCommand, prefetchCaches } from "./lib/api";
import { generateSceneImage, requestSceneImage } from "./lib/gemini";
import { buildScenePrompt } from "./lib/scene";
import { Welcome } from "./welcome";

type Line = {
  id: string;
  text: string;
};

type View = "play" | "map" | "journal" | "bestiary";
type Tab = "here" | "gear" | "skills" | "party";

const ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"];

// cache survives re-renders
const sceneImageCache = new Map<string, string>();
// in-flight foreground renders, so two views never render the same scene twice
const sceneInFlight = new Map<string, Promise<string>>();
// scenes being warmed in the background (polled, never awaited by the foreground)
const scenePrefetching = new Set<string>();

// Get a scene image for a key, reusing the cache or any in-flight render.
// The server single-flights renders too, so a foreground request for a scene
// the warmer is already painting waits for that one instead of a second.
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

// Poll intervals for a scene the server is still rendering (ms). Short
// requests only: the browser's per-origin connection budget stays free for
// the player's next command and for the foreground scene.
const PREFETCH_POLL_MS = [2500, 4000, 6000, 8000, 10000, 12000, 15000, 15000, 15000, 20000, 20000, 20000];

// Warm a scene into the local cache without ever blocking: ask the server
// (which renders in the background), then poll until it's there. Resolves to
// the image, or null if it never arrived. Never rejects.
async function prefetchScene(key: string, prompt: string): Promise<string | null> {
  if (sceneImageCache.has(key) || scenePrefetching.has(key)) return sceneImageCache.get(key) ?? null;
  scenePrefetching.add(key);
  try {
    for (let i = 0; i <= PREFETCH_POLL_MS.length; i++) {
      const img = await requestSceneImage(prompt, { wait: false });
      if (img) {
        sceneImageCache.set(key, img);
        return img;
      }
      if (i === PREFETCH_POLL_MS.length) break;
      await new Promise((r) => setTimeout(r, PREFETCH_POLL_MS[i]));
      const arrived = sceneImageCache.get(key); // a foreground render may have landed it
      if (arrived) return arrived;
    }
  } catch {
    // best-effort: no image this time
  } finally {
    scenePrefetching.delete(key);
  }
  return null;
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


// The scene key IS the image prompt: two states that would paint the same
// picture share one cache entry, so returning to an unchanged place (or one
// where only other players moved) is instant. The prompt already ignores hp
// (art shouldn't change as a monster takes damage) and other players.
function computeSceneKeyFromResponse(resp: any) {
  const state = resp?.state;
  if (!state?.location) return null;
  return buildScenePrompt({ location: state.location, entities: state.entities ?? [] });
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

  const edges: { a: [number, number]; b: [number, number]; current: boolean; unexplored: boolean }[] = [];
  const seen = new Set<string>();
  for (const n of mapData.locations) {
    for (const ex of n.exits || []) {
      if (!pos[n.id] || !pos[ex.to]) continue;
      const a = n.id < ex.to ? n.id : ex.to;
      const b = n.id < ex.to ? ex.to : n.id;
      const ek = `${a}|${b}`;
      if (seen.has(ek)) continue;
      seen.add(ek);
      edges.push({
        a: pos[a], b: pos[b],
        current: n.id === mapData.current || ex.to === mapData.current,
        unexplored: !byId[a]?.visited || !byId[b]?.visited,
      });
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

const MAP_COLORS = {
  accent: "#2f3a5c",
  accentTint: "#d6dceb",
  paper: "#f6f1e7",
  plate: "#fbf8f0",
  ink: "#2a2620",
  inkFaint: "#8a7f66",
  ruleFaint: "#b9ab8a",
};

function MapGraph({ mapData, thumbs }: { mapData: any; thumbs: Record<string, string> }) {
  const L = computeMapLayout(mapData);
  const cell = 150, pad = 24, nodeW = 112, nodeH = 60;
  const cols = L.maxX - L.minX + 1, rows = L.maxY - L.minY + 1;
  const W = cols * cell + pad * 2, H = rows * cell + pad * 2;
  const cx = (gx: number) => pad + (gx - L.minX) * cell + cell / 2;
  const cy = (gy: number) => pad + (gy - L.minY) * cell + cell / 2;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full block font-sans" style={{ maxHeight: "70vh" }}>
      {/* Faint roads elsewhere first, then the roads out of here on top. */}
      {L.edges.filter((e) => !e.current).map((e, i) => (
        <line key={`d${i}`} x1={cx(e.a[0])} y1={cy(e.a[1])} x2={cx(e.b[0])} y2={cy(e.b[1])}
          stroke={MAP_COLORS.ruleFaint} strokeWidth={1.5} strokeDasharray={e.unexplored ? "4 4" : undefined} />
      ))}
      {L.edges.filter((e) => e.current).map((e, i) => (
        <line key={`c${i}`} x1={cx(e.a[0])} y1={cy(e.a[1])} x2={cx(e.b[0])} y2={cy(e.b[1])}
          stroke={MAP_COLORS.accent} strokeWidth={3} />
      ))}
      {mapData.locations.map((n: any) => {
        const p = L.pos[n.id];
        if (!p) return null;
        const X = cx(p[0]) - nodeW / 2;
        const Y = cy(p[1]) - nodeH / 2;
        const here = n.id === mapData.current;
        const thumb = n.visited && !here ? thumbs[n.id] : undefined;
        const clipId = `clip-${n.id.replace(/[^a-zA-Z0-9_-]/g, "_")}`;
        const roads = (n.exits || []).length;
        const sub = here
          ? "you are here"
          : n.visited
          ? roads === 1 ? "1 road" : `${roads} roads`
          : "unexplored";
        const fill = here ? MAP_COLORS.accent : n.visited ? MAP_COLORS.plate : "transparent";
        const stroke = here ? MAP_COLORS.accent : n.visited ? MAP_COLORS.inkFaint : MAP_COLORS.ruleFaint;
        const textFill = here ? MAP_COLORS.paper : n.visited ? MAP_COLORS.ink : MAP_COLORS.inkFaint;
        const subFill = here ? MAP_COLORS.accentTint : MAP_COLORS.inkFaint;
        return (
          <g key={n.id}>
            {thumb && (
              <clipPath id={clipId}>
                <rect x={X} y={Y} width={nodeW} height={nodeH} rx={5} />
              </clipPath>
            )}
            <rect
              x={X} y={Y} width={nodeW} height={nodeH} rx={5}
              fill={fill}
              stroke={stroke}
              strokeWidth={here ? 2 : 1.25}
              strokeDasharray={n.visited ? undefined : "4 3"}
            />
            {thumb && (
              <g clipPath={`url(#${clipId})`}>
                <image href={thumb} x={X} y={Y} width={nodeW} height={nodeH} preserveAspectRatio="xMidYMid slice" />
                {/* Label plate over the lower part of the thumbnail. */}
                <rect x={X} y={Y + 16} width={nodeW} height={nodeH - 16} fill={MAP_COLORS.plate} fillOpacity={0.92} />
              </g>
            )}
            <text x={cx(p[0])} y={Y + 27} fill={textFill} fontSize={12} fontWeight={600} textAnchor="middle">
              {n.visited ? n.name : "?"}
            </text>
            <text x={cx(p[0])} y={Y + 44} fill={subFill} fontSize={10} fontStyle="italic"
              fontFamily="var(--font-spectral), Georgia, serif" textAnchor="middle">
              {sub}
            </text>
          </g>
        );
      })}
    </svg>
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

const ABILITY_KIND_LABEL: Record<string, string> = {
  attack: "attack", dot: "bleed", heal: "heal", aoe: "area",
};
const ABILITY_KIND_CLASS: Record<string, string> = {
  attack: "text-danger", dot: "text-danger", heal: "text-good", aoe: "text-accent",
};

const DIRECTION_ARROW: Record<string, string> = {
  north: "↑", south: "↓", east: "→", west: "←",
};

function humanize(s: string) {
  return String(s).replace(/_/g, " ");
}

function titleCase(s: string) {
  return humanize(s).replace(/\b\w/g, (c) => c.toUpperCase());
}

function totalXpForLevel(level: number) {
  return level <= 1 ? 0 : 10 * (level - 1) * level;
}

function pct(n: number, max: number) {
  if (!max) return 0;
  return Math.max(0, Math.min(100, (100 * n) / max));
}

// ---- Story log line kinds ----
type LineKind = "cmd" | "narr" | "sys" | "error";

const SYSTEM_LINE_RE = /^(Welcome|Quest updated|Quest Journal|Map opened|Bestiary|Your hero is gone|You have discovered|You gained|You learned|Level up)/i;

function classifyLine(text: string): { kind: LineKind; text: string } {
  if (text.startsWith("> ")) return { kind: "cmd", text: text.slice(2) };
  if (text.startsWith("[error]")) return { kind: "error", text: text.replace(/^\[error\]\s*/, "") };
  if (SYSTEM_LINE_RE.test(text)) return { kind: "sys", text };
  return { kind: "narr", text };
}

// ---- Autocomplete candidates, built from the live state ----
type Suggestion = { cmd: string; hint: string };

const STATIC_COMMANDS: Suggestion[] = [
  { cmd: "look", hint: "describe the scene" },
  { cmd: "gather", hint: "search for herbs" },
  { cmd: "heal", hint: "use a healing item" },
  { cmd: "rest", hint: "recover between fights" },
  { cmd: "next", hint: "what to do now" },
  { cmd: "map", hint: "open the known world" },
  { cmd: "journal", hint: "open your quests" },
  { cmd: "bestiary", hint: "open the bestiary" },
  { cmd: "party status", hint: "who travels with you" },
  { cmd: "reputation", hint: "how the factions see you" },
];

function buildCandidates(state: any | null): Suggestion[] {
  if (!state?.player) return STATIC_COMMANDS;
  const out: Suggestion[] = [];
  const entities = state.entities ?? [];
  const monsters = entities.filter((e: any) => e.type === "monster");
  const people = entities.filter((e: any) => e.type === "npc" || e.type === "player");
  const abilities = state.abilities ?? [];
  const player = state.player;

  for (const m of monsters) {
    out.push({ cmd: `attack ${m.id}`, hint: `strike the ${m.name}` });
    out.push({ cmd: `fight ${m.id}`, hint: `fight the ${m.name} to the end` });
    for (const a of abilities) {
      if (a.ready && (a.kind === "attack" || a.kind === "dot")) {
        out.push({ cmd: `${a.id} ${m.id}`, hint: `${a.name} · ready` });
      }
    }
  }
  for (const a of abilities) {
    if (a.kind === "heal" || a.kind === "aoe") {
      out.push({ cmd: a.id, hint: a.ready ? `${a.name} · ready` : `${a.name} · ${a.remaining}s` });
    }
  }
  for (const e of people) {
    out.push({ cmd: `talk ${e.id}`, hint: `speak with ${e.name}` });
    if (e.type === "npc" && !player.companion && !NON_RECRUITABLE_ROLES.includes(e.role)) {
      out.push({ cmd: `recruit ${e.id}`, hint: `hire ${e.name} as a companion` });
    }
  }
  for (const ex of state.location?.exits ?? []) {
    out.push({ cmd: `go ${ex.label}`, hint: ex.name ?? ex.label });
  }
  for (const [item] of Object.entries(player.inventory ?? {})) {
    const info = (state.item_info ?? {})[item] ?? {};
    const isGear = info.type === "weapon" || info.type === "armor" || GEAR_RE.test(item);
    const verb = isGear ? "equip" : "use";
    const hint = info.stat
      ? `${info.stat}${typeof info.delta === "number" ? (info.delta > 0 ? ` +${info.delta}` : info.delta < 0 ? ` ${info.delta}` : "") : ""}`
      : isGear ? "wield it" : "consume it";
    out.push({ cmd: `${verb} ${item}`, hint });
    if (item !== "coin") out.push({ cmd: `sell ${item}`, hint: "sell to a merchant" });
  }
  return out.concat(STATIC_COMMANDS);
}

function matchSuggestions(input: string, candidates: Suggestion[]): Suggestion[] {
  const q = input.trim().toLowerCase();
  if (!q) return [];
  const seen = new Set<string>();
  const hits: Suggestion[] = [];
  for (const c of candidates) {
    const cmd = c.cmd.toLowerCase();
    if (seen.has(cmd)) continue;
    if (cmd.startsWith(q) || cmd.split(" ").some((w) => w.startsWith(q))) {
      seen.add(cmd);
      hits.push(c);
    }
  }
  // Typing the full command exactly needs no hint.
  if (hits.length === 1 && hits[0].cmd.toLowerCase() === q) return [];
  return hits.slice(0, 6);
}

// ---- Small handbook pieces ----

function Section({ title, children, className = "" }: { title: ReactNode; children: ReactNode; className?: string }) {
  return (
    <div className={className}>
      <div className="hb-label mb-2">{title}</div>
      {children}
    </div>
  );
}

function Track({ value, max, height, colorClass }: { value: number; max: number; height: number; colorClass: string }) {
  return (
    <div className="flex-1 bg-paper-track overflow-hidden" style={{ height, borderRadius: height / 2 }}>
      <div className={`h-full ${colorClass}`} style={{ width: `${pct(value, max)}%`, borderRadius: height / 2 }} />
    </div>
  );
}

function CharacterCard({ state, onTab }: { state: any; onTab: (t: Tab) => void }) {
  const { player, identity } = state;
  const apMax = 30; // server cap (QUESTAI_AP_MAX); AP fields ship in player state
  const ap = typeof player.action_points === "number" ? player.action_points : null;
  const effects = Object.entries(player.status_effects ?? {}) as [string, any][];
  const skillPoints = identity?.skill_points ?? 0;
  // Mirrors app/progression.py: total XP to reach level L is 10 * (L-1) * L.
  const xpFloor = totalXpForLevel(player.level);
  const xpCeil = totalXpForLevel(player.level + 1);

  return (
    <div className="hb-card px-5 py-[18px]">
      <div className="flex justify-between items-baseline gap-3">
        <div className="font-serif text-[22px] font-semibold leading-tight truncate">{player.name}</div>
        <div className="text-[12px] font-semibold tracking-[.06em] uppercase text-ink-muted whitespace-nowrap">
          Level {player.level}
        </div>
      </div>

      <div className="mt-3 flex items-center gap-[10px]">
        <Track value={player.hp} max={player.max_hp} height={8} colorClass="bg-danger" />
        <span className="text-[12px] font-semibold tabular-nums text-danger whitespace-nowrap">
          {player.hp} / {player.max_hp}
        </span>
      </div>

      <div className="mt-[6px] flex items-center gap-[10px]">
        <Track value={player.xp - xpFloor} max={xpCeil - xpFloor} height={4} colorClass="bg-accent" />
        <span className="text-[12px] tabular-nums text-ink-muted whitespace-nowrap" title={`${Math.max(0, xpCeil - player.xp)} xp to level ${player.level + 1}`}>
          {player.xp} xp
        </span>
      </div>

      {ap != null && (
        <div className="mt-[6px] flex items-center gap-[10px]"
          title="Action points — every world-changing action costs 1; they regenerate over time">
          <Track value={ap} max={apMax} height={4} colorClass="bg-good" />
          <span className="text-[12px] tabular-nums text-ink-muted whitespace-nowrap">{ap} / {apMax} ap</span>
        </div>
      )}

      {identity?.archetype && (
        <div className="mt-3 text-[12px] text-ink-muted">
          <span className="font-semibold text-ink">{identity.archetype_name}</span>
          {identity.passive ? <> · {identity.passive}</> : null}
        </div>
      )}

      {(effects.length > 0 || skillPoints > 0) && (
        <div className="mt-3 flex gap-[6px] flex-wrap">
          {effects.map(([eid, st]) => (
            <span key={eid} className="hb-tag">
              {titleCase(eid)} · {st?.turns ?? 0} {st?.turns === 1 ? "turn" : "turns"}
            </span>
          ))}
          {skillPoints > 0 && (
            <button className="hb-tag hb-tag-accent hover:underline" onClick={() => onTab("skills")}
              title="Spend them in Skills">
              {skillPoints} skill {skillPoints === 1 ? "point" : "points"} to spend
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function ItemsList(items: Record<string, number> | undefined) {
  return Object.entries(items ?? {}).map(([it, q]) => `${q} ${humanize(it)}`).join(", ");
}

function quickObjective(q: any): { done: boolean; text: string | null } {
  const staged = q.stages && q.stages.length > 0;
  const objs: any[] = staged ? (q.stages[q.current_stage]?.objectives ?? []) : (q.objectives ?? []);
  if (objs.length === 0) return { done: false, text: null };
  const pending = objs.find((o) => o.progress < o.required);
  if (!pending) return { done: true, text: null };
  return { done: false, text: `${pending.progress} / ${pending.required} ${humanize(pending.target)}` };
}

function StatusPane({
  state, tab, onTab, onCommand, bestiaryByName,
}: {
  state: any;
  tab: Tab;
  onTab: (t: Tab) => void;
  onCommand: (cmd: string) => void;
  bestiaryByName: Record<string, any>;
}) {
  const { player, location } = state;
  const entities = state.entities ?? [];
  const monsters = entities.filter((e: any) => e.type === "monster");
  const people = entities.filter((e: any) => e.type === "npc" || e.type === "player");
  const abilities = state.abilities ?? [];
  const selfAbilities = abilities.filter((a: any) => a.kind === "heal" || a.kind === "aoe");
  const activeQuests = Object.values(player.active_quests ?? {}) as any[];
  const completedQuests = Object.values(player.completed_quests ?? {}) as any[];
  const hasStronghold = (state.stronghold?.level ?? 0) > 0;

  const TABS: [Tab, string][] = [
    ["here", "Here"], ["gear", "Gear"], ["skills", "Skills"], ["party", "Party"],
  ];

  return (
    <div className="hb-card overflow-hidden">
      <div className="flex border-b border-paper-track">
        {TABS.map(([id, label]) => (
          <button key={id} onClick={() => onTab(id)}
            className={`flex-1 py-[10px] text-[12px] font-bold tracking-[.06em] uppercase border-b-2 ${
              tab === id ? "text-accent border-accent" : "text-ink-faint border-transparent hover:text-accent"
            }`}>
            {label}
          </button>
        ))}
      </div>

      <div className="px-5 py-4 flex flex-col gap-[18px]">
        {tab === "here" && (
          <>
            {Array.isArray(state.guidance) && state.guidance.length > 0 && (
              <Section title="What now?">
                <div className="flex flex-col gap-1">
                  {state.guidance.map((g: any, i: number) =>
                    g.command ? (
                      <button key={i} className="text-left text-[13px] text-accent hover:underline"
                        onClick={() => onCommand(g.command)}>· {g.text}</button>
                    ) : (
                      <div key={i} className="text-[13px] text-ink-muted">· {g.text}</div>
                    )
                  )}
                </div>
              </Section>
            )}

            {state.campaign && (
              <Section title={state.campaign.complete
                ? "The Realm Restored"
                : `Act ${ROMAN[state.campaign.act_index] ?? state.campaign.act_index + 1}${state.campaign.acts_total ? ` of ${state.campaign.acts_total}` : ""} · ${state.campaign.act_name}`}>
                {state.campaign.act_blurb && (
                  <div className="font-serif italic text-[13px] text-ink-muted mb-2">{state.campaign.act_blurb}</div>
                )}
                <div className="flex flex-col gap-[6px]">
                  {(state.campaign.wrongs || []).map((w: any) => (
                    <div key={w.id} className="text-[13px] flex items-start gap-2 flex-wrap"
                      title={w.blurb ? `${w.blurb} ${w.deed}` : w.deed}>
                      <span className={
                        w.status === "righted" ? "text-ink-faint line-through" :
                        w.status === "active" ? "text-accent font-semibold" : "text-ink"
                      }>
                        {w.status === "righted" ? "✓" : w.status === "active" ? "…" : w.climax ? "!" : "•"} {w.title}
                      </span>
                      {w.status === "righted" && w.righted_by && (
                        <span className="text-ink-faint text-[12px]">— {w.righted_by}</span>
                      )}
                      {w.status === "righted" && w.entry && (
                        <span className="basis-full pl-4 font-serif italic text-[13px] text-ink-faint">“{w.entry}”</span>
                      )}
                      {w.status === "active" && w.progress && (
                        <span className="text-ink-muted text-[12px]">{w.progress}</span>
                      )}
                      {w.status === "open" && w.command && (
                        <button className="hb-btn hb-btn-outline py-[2px] px-2" onClick={() => onCommand(w.command)}>Undertake</button>
                      )}
                      {w.status === "open" && w.climax && (
                        <button className="hb-btn hb-btn-danger py-[2px] px-2" onClick={() => onCommand("raid")}>The Warfront</button>
                      )}
                    </div>
                  ))}
                </div>
                {Array.isArray(state.campaign.titles) && state.campaign.titles.length > 0 && (
                  <div className="text-[12px] mt-2 text-ink-muted">
                    <span className="font-semibold text-ink">Your legend</span> · {state.campaign.titles.join(", ")}
                  </div>
                )}
              </Section>
            )}

            {monsters.length > 0 && (
              <Section title="Enemies">
                <div className="flex flex-col gap-[10px]">
                  {monsters.map((m: any) => {
                    const maxHp = bestiaryByName[m.name]?.max_hp;
                    return (
                      <div key={m.id} className="hb-inset flex flex-col gap-[6px]">
                        <div className="flex justify-between items-baseline gap-3">
                          <span className="font-serif text-[16px] font-semibold">{m.name}</span>
                          {m.hp != null && (
                            <span className="text-[12px] text-danger font-semibold tabular-nums whitespace-nowrap">{m.hp} hp</span>
                          )}
                        </div>
                        {m.hp != null && maxHp > 0 && (
                          <div className="h-[3px] rounded-[2px] bg-paper-track overflow-hidden">
                            <div className="h-full bg-danger" style={{ width: `${pct(m.hp, maxHp)}%` }} />
                          </div>
                        )}
                        <div className="flex gap-[6px] flex-wrap mt-[2px]">
                          <button className="hb-btn hb-btn-danger" onClick={() => onCommand(`attack ${m.id}`)}>Attack</button>
                          <button className="hb-btn hb-btn-outline" title="Resolve the whole encounter in one action"
                            onClick={() => onCommand(`fight ${m.id}`)}>Fight</button>
                          {abilities.filter((a: any) => a.ready && (a.kind === "attack" || a.kind === "dot")).map((a: any) => (
                            <button key={a.id} className="hb-btn hb-btn-outline" title={a.description}
                              onClick={() => onCommand(`${a.id} ${m.id}`)}>{a.name}</button>
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </Section>
            )}

            {selfAbilities.length > 0 && (
              <Section title="Self / Area">
                <div className="flex gap-[6px] flex-wrap">
                  {selfAbilities.map((a: any) => (
                    <button key={a.id} disabled={!a.ready} className="hb-btn hb-btn-outline"
                      title={a.ready ? a.description : `On cooldown (${a.remaining}s)`}
                      onClick={() => onCommand(a.id)}>
                      {a.name}{a.ready ? "" : ` · ${a.remaining}s`}
                    </button>
                  ))}
                </div>
              </Section>
            )}

            {people.length > 0 && (
              <Section title="People">
                <div className="flex flex-col gap-[6px]">
                  {people.map((entity: any) => {
                    const isInParty = state.party?.members?.some((mm: any) => mm.player_id === entity.id);
                    const canRecruit = entity.type === "npc" && !player.companion
                      && !NON_RECRUITABLE_ROLES.includes(entity.role);
                    return (
                      <div key={entity.id} className="hb-row">
                        <button className="flex-1 flex justify-between items-center text-left gap-3 hover:text-accent min-w-0"
                          onClick={() => onCommand(`talk ${entity.id}`)}>
                          <span className="font-serif text-[16px] truncate">
                            {entity.name}
                            {entity.type === "player" && <span className="font-sans text-[11px] text-ink-faint"> player</span>}
                            {isInParty && <span className="font-sans text-[11px] text-ink-faint"> · party</span>}
                          </span>
                          <span className="text-[12px] text-ink-faint whitespace-nowrap">Talk →</span>
                        </button>
                        {canRecruit && (
                          <button className="hb-link" title="Recruit as a companion (costs a coin signing bonus)"
                            onClick={() => onCommand(`recruit ${entity.id}`)}>Recruit</button>
                        )}
                      </div>
                    );
                  })}
                </div>
              </Section>
            )}

            {(activeQuests.length > 0 || completedQuests.length > 0) && (
              <Section title="Quests">
                <div className="flex flex-col gap-2">
                  {activeQuests.map((q: any) => {
                    const staged = q.stages && q.stages.length > 0;
                    const prog = quickObjective(q);
                    return (
                      <div key={q.quest_id}>
                        <div className="flex justify-between gap-3">
                          <span className="font-semibold">{q.name}</span>
                          {prog.done ? (
                            <span className="text-[12px] text-good font-semibold whitespace-nowrap">Ready to turn in</span>
                          ) : prog.text ? (
                            <span className="text-[12px] text-ink-muted tabular-nums whitespace-nowrap">{prog.text}</span>
                          ) : null}
                        </div>
                        {staged && (
                          <div className="text-[12px] text-ink-muted">
                            Stage {q.current_stage + 1} of {q.stages.length} · {q.stages[q.current_stage]?.description}
                          </div>
                        )}
                      </div>
                    );
                  })}
                  {completedQuests.map((q: any) => (
                    <div key={q.quest_id} className="flex justify-between gap-3">
                      <span className="font-semibold">{q.name}</span>
                      <span className="text-[12px] text-good font-semibold whitespace-nowrap">Ready to turn in</span>
                    </div>
                  ))}
                </div>
              </Section>
            )}

            <Section title="Paths">
              {location.exits.length === 0 ? (
                <div className="font-serif italic text-[14px] text-ink-faint">No road leads out of here.</div>
              ) : (
                <div className="flex gap-[6px] flex-wrap">
                  {location.exits.map((e: any) => {
                    const arrow = DIRECTION_ARROW[String(e.label).toLowerCase()];
                    return (
                      <button key={e.to} className="hb-chip" onClick={() => onCommand(`go ${e.label}`)}>
                        {arrow ? `${arrow} ` : ""}{e.name ?? e.label}
                      </button>
                    );
                  })}
                </div>
              )}
            </Section>

            {Array.isArray(state.incidents) && state.incidents.length > 0 && (
              <Section title="News of the Realm">
                <div className="flex flex-col gap-[6px]">
                  {state.incidents.map((inc: any) => (
                    <div key={inc.id} className="text-[13px]" title={inc.blurb}>
                      <span className={inc.kind === "incursion" ? "text-danger font-semibold" : "text-good font-semibold"}>
                        {inc.kind === "incursion" ? "!" : "+"} {inc.title}
                      </span>
                      <span className="text-ink-muted text-[12px]"> — {inc.location_name}{inc.here ? " (here)" : ""}</span>
                      {inc.kind === "incursion" && inc.creatures_left != null && (
                        <span className="text-ink-faint text-[12px]"> · {inc.creatures_left} {inc.creature_name}{inc.creatures_left === 1 ? "" : "s"} left · {inc.turns_left} turns</span>
                      )}
                      {inc.kind === "boon" && inc.effect_words && (
                        <span className="text-ink-faint text-[12px]"> · {inc.effect_words} · {inc.turns_left} turns</span>
                      )}
                      {inc.kind === "incursion" && inc.here && inc.creatures_left > 0 && (
                        <button className="hb-btn hb-btn-danger py-[2px] px-2 ml-2"
                          onClick={() => onCommand(`fight ${inc.creature_name}`)}>Fight</button>
                      )}
                    </div>
                  ))}
                </div>
              </Section>
            )}

            {state.raid && (
              <Section title="World Threat">
                <div className="hb-inset flex flex-col gap-[6px]">
                  <div className="flex justify-between items-baseline gap-3">
                    <span className="font-serif text-[16px] font-semibold text-danger">{state.raid.name}</span>
                    <span className="text-[12px] text-danger font-semibold tabular-nums whitespace-nowrap">
                      {state.raid.hp} / {state.raid.max_hp}
                    </span>
                  </div>
                  {state.raid.title && <div className="text-[12px] text-ink-muted">{state.raid.title}</div>}
                  <div className="h-[3px] rounded-[2px] bg-paper-track overflow-hidden">
                    <div className="h-full bg-danger" style={{ width: `${pct(state.raid.hp, state.raid.max_hp)}%` }} />
                  </div>
                  <div className="text-[12px] text-ink-muted">Your blows: {state.raid.your_damage}</div>
                  {Array.isArray(state.raid.top) && state.raid.top.length > 0 && (
                    <div className="text-[12px] text-ink-faint">
                      Top: {state.raid.top.map((t: any) => `${t.name} (${t.damage})`).join(", ")}
                    </div>
                  )}
                  <div className="flex gap-[6px] flex-wrap mt-[2px]">
                    {state.raid.at_lair ? (
                      <button className="hb-btn hb-btn-danger"
                        title={`Strike the boss — spoils pool ${state.raid.reward_pool} coins, split by damage done`}
                        onClick={() => onCommand("raid strike")}>Strike</button>
                    ) : (
                      <button className="hb-btn hb-btn-outline" title="Travel to the Warfront to make your stand"
                        onClick={() => onCommand("go warfront")}>Go to the Warfront</button>
                    )}
                  </div>
                </div>
              </Section>
            )}

            {state.stronghold && (
              <Section title="Stronghold">
                {state.stronghold.level === 0 ? (
                  <div className="flex flex-col gap-2">
                    <div className="text-[13px] text-ink-muted">You hold no ground of your own yet.</div>
                    <div>
                      <button className="hb-btn hb-btn-outline"
                        title="Found a Campsite — a stash, a tribute, and a place to grow"
                        onClick={() => onCommand("build")}>Build a Campsite · {state.stronghold.next_cost}</button>
                    </div>
                  </div>
                ) : (
                  <div className="flex flex-col gap-2">
                    <div className="text-[13px]">
                      <span className="font-serif text-[16px] font-semibold">{state.stronghold.tier}</span>
                      <span className="text-ink-muted text-[12px]"> · tier {state.stronghold.level} of 5</span>
                    </div>
                    <div className="flex flex-wrap gap-[6px]">
                      {state.stronghold.tribute > 0 && (
                        <button className="hb-btn hb-btn-accent" onClick={() => onCommand("collect")}>
                          Collect {state.stronghold.tribute} tribute
                        </button>
                      )}
                      {state.stronghold.next_cost && (
                        <button className="hb-btn hb-btn-outline" onClick={() => onCommand("build")}>
                          Upgrade to {state.stronghold.next_tier} · {state.stronghold.next_cost}
                        </button>
                      )}
                    </div>
                    {state.stronghold.stash && Object.keys(state.stronghold.stash).length > 0 && (
                      <div>
                        <div className="text-[12px] text-ink-faint mb-1">
                          Stash · {Object.keys(state.stronghold.stash).length} of {state.stronghold.stash_cap}
                        </div>
                        {Object.entries(state.stronghold.stash).map(([item, qty]: [string, any]) => (
                          <div key={item} className="hb-row">
                            <span>
                              <span className="font-serif text-[16px]">{titleCase(item)}</span>
                              <span className="text-ink-faint text-[12px]"> ×{qty}</span>
                            </span>
                            <button className="hb-link" onClick={() => onCommand(`unstash ${item}`)}>Withdraw</button>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </Section>
            )}

            {state.rumors?.length > 0 && (
              <Section title="Word Going Around">
                <div className="flex flex-col gap-1">
                  {state.rumors.map((r: string, i: number) => (
                    <div key={`rumor-${i}`} className="font-serif italic text-[14px] text-ink-muted">{r}</div>
                  ))}
                </div>
              </Section>
            )}

            {(state.echoes?.length > 0 || state.notes?.length > 0) && (
              <Section title="Traces of Others">
                <div className="flex flex-col gap-1">
                  {(state.echoes ?? []).map((e: any, i: number) => (
                    <div key={`echo-${i}`} className="font-serif italic text-[14px] text-ink-muted">
                      {e.description} <span className="font-sans not-italic text-[12px] text-ink-faint">({e.ago})</span>
                    </div>
                  ))}
                  {(state.notes ?? []).map((n: any, i: number) => (
                    <div key={`note-${i}`} className="font-serif text-[14px] text-ink">
                      “{n.text}” <span className="font-sans text-[12px] text-ink-faint">— {n.player_name}</span>
                    </div>
                  ))}
                </div>
              </Section>
            )}
          </>
        )}

        {tab === "gear" && (
          <>
            <Section title="Equipped">
              {player.equipment && Object.keys(player.equipment).length > 0 ? (
                Object.entries(player.equipment).map(([slot, itemId]) => (
                  <div key={slot} className="hb-row">
                    <span className="min-w-0 truncate">
                      <span className="text-ink-faint text-[12px]">{titleCase(slot)} · </span>
                      <span className="font-serif text-[16px]">{titleCase(String(itemId))}</span>
                    </span>
                    <button className="text-[12px] text-ink-faint hover:text-danger whitespace-nowrap"
                      onClick={() => onCommand(`unequip ${slot}`)}>Unequip</button>
                  </div>
                ))
              ) : (
                <div className="font-serif italic text-[14px] text-ink-faint">Nothing equipped.</div>
              )}
            </Section>

            <Section title="Pack">
              {player.inventory && Object.keys(player.inventory).length > 0 ? (
                <div className="flex flex-col">
                  {Object.entries(player.inventory).map(([item, qty]) => {
                    const info = (state.item_info ?? {})[item] ?? {};
                    const isGear = info.type === "weapon" || info.type === "armor" || GEAR_RE.test(item);
                    const hasDelta = typeof info.delta === "number";
                    const noteClass = hasDelta
                      ? info.delta > 0 ? "text-good" : info.delta < 0 ? "text-danger" : "text-ink-muted"
                      : "text-ink-muted";
                    const note = info.stat
                      ? `${info.stat}${hasDelta ? (info.delta > 0 ? ` · ${info.delta} better than equipped` : info.delta < 0 ? ` · ${-info.delta} worse than equipped` : " · same as equipped") : ""}`
                      : null;
                    return (
                      <div key={item} className="hb-row py-[7px]">
                        <div className="min-w-0">
                          <span className="font-serif text-[16px]">{titleCase(item)}</span>
                          <span className="text-ink-faint text-[12px]"> ×{qty as number}</span>
                          {note && <div className={`text-[12px] ${noteClass}`}>{note}</div>}
                        </div>
                        <div className="flex gap-2 shrink-0">
                          <button className="hb-link" onClick={() => onCommand(`${isGear ? "equip" : "use"} ${item}`)}>
                            {isGear ? "Equip" : "Use"}
                          </button>
                          {hasStronghold && item !== "coin" && (
                            <button className="hb-link-faint" onClick={() => onCommand(`stash ${item}`)}>Stash</button>
                          )}
                          <button className="hb-link-faint" onClick={() => onCommand(`sell ${item}`)}>Sell</button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="font-serif italic text-[14px] text-ink-faint">Your pack is empty.</div>
              )}
            </Section>
          </>
        )}

        {tab === "skills" && (
          <>
            {state.identity && !state.identity.archetype && Array.isArray(state.identity.paths) && (
              <Section title="Choose your path">
                <div className="text-[12.5px] text-ink-muted mb-2">The one choice that shapes how you fight.</div>
                <div className="flex flex-col gap-2">
                  {state.identity.paths.map((p: any) => (
                    <div key={p.id} className="hb-inset">
                      <div className="flex justify-between items-baseline gap-3">
                        <span className="font-serif text-[16px] font-semibold">{p.name}</span>
                        <button className="hb-btn hb-btn-outline py-1" onClick={() => onCommand(`path ${p.id}`)}>Choose</button>
                      </div>
                      <div className="text-[12.5px] text-ink-muted mt-[2px]">{p.description}</div>
                      {p.passive && <div className="text-[12px] text-ink-faint mt-1">{p.passive}</div>}
                    </div>
                  ))}
                </div>
              </Section>
            )}

            {state.identity?.skill_points > 0 && (
              <Section title={`${state.identity.skill_points} skill ${state.identity.skill_points === 1 ? "point" : "points"} to spend`}>
                {(state.identity.learnable || []).length > 0 ? (
                  <div className="flex flex-wrap gap-[6px]">
                    {(state.identity.learnable || []).map((a: any) => (
                      <button key={a.id} className="hb-btn hb-btn-accent" onClick={() => onCommand(`learn ${a.id}`)}>
                        Learn {a.name}
                      </button>
                    ))}
                  </div>
                ) : (
                  <div className="font-serif italic text-[14px] text-ink-faint">Nothing new to learn yet.</div>
                )}
              </Section>
            )}

            {abilities.length === 0 ? (
              <div className="font-serif italic text-[14px] text-ink-faint">No abilities yet — level up to learn them.</div>
            ) : (
              <div className="flex flex-col gap-[10px]">
                {abilities.map((a: any) => {
                  const needsTarget = a.kind === "attack" || a.kind === "dot";
                  const needsEnemy = needsTarget || a.kind === "aoe";
                  const canUse = a.ready && (!needsEnemy || monsters.length > 0);
                  const status = !a.ready
                    ? `Cooldown · ${a.remaining}s`
                    : needsEnemy && monsters.length === 0 ? "Ready · no enemy here" : "Ready";
                  return (
                    <div key={a.id} className="hb-inset" style={{ opacity: a.ready ? 1 : 0.55 }}>
                      <div className="flex justify-between items-baseline gap-3">
                        <span className="font-serif text-[16px] font-semibold">{a.name}</span>
                        <span className={`text-[11px] font-bold tracking-[.06em] uppercase ${ABILITY_KIND_CLASS[a.kind] ?? "text-accent"}`}>
                          {ABILITY_KIND_LABEL[a.kind] ?? a.kind}
                        </span>
                      </div>
                      <div className="text-[12.5px] text-ink-muted mt-[2px]">{a.description}</div>
                      <div className="flex justify-between items-center mt-2 gap-3">
                        <span className="text-[12px] text-ink-faint">{status}</span>
                        <button disabled={!canUse} className="hb-btn hb-btn-outline py-1"
                          onClick={() => onCommand(needsTarget && monsters.length > 0 ? `${a.id} ${monsters[0].id}` : a.id)}>
                          Use
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </>
        )}

        {tab === "party" && (
          <>
            {player.companion && (
              <Section title="Companion">
                <div className="hb-inset">
                  <div className="flex justify-between items-baseline gap-3">
                    <span className="font-serif text-[16px] font-semibold">{player.companion.name}</span>
                    <span className="text-[11px] font-bold tracking-[.06em] uppercase text-accent">
                      {COMPANION_TITLE[player.companion.archetype] ?? player.companion.archetype}
                    </span>
                  </div>
                  <div className="text-[12.5px] text-ink-muted mt-[2px]">
                    Level {1 + Math.floor(Math.min(player.companion.loyalty, 100) / 25)} · loyalty {player.companion.loyalty} / 100
                  </div>
                  <div className="mt-2">
                    <button className="hb-link-danger" onClick={() => onCommand("dismiss")}>Dismiss</button>
                  </div>
                </div>
              </Section>
            )}

            {state.party ? (
              <Section title={state.party.name || "Party"}>
                {state.party.members.map((member: any) => (
                  <div key={member.player_id}
                    className={`flex items-center gap-[10px] py-[6px] border-b border-dotted border-rule ${member.online ? "" : "text-ink-faint"}`}>
                    <span className={`w-2 h-2 rounded-full shrink-0 ${member.online ? "bg-good" : "border border-ink-faint"}`} />
                    <span className="font-serif text-[16px]">{member.name}</span>
                    {member.is_leader && <span className="text-[11px] text-ink-faint">Leader</span>}
                    {!member.online && member.last_seen_text && (
                      <span className="text-[11px] text-ink-faint">{member.last_seen_text}</span>
                    )}
                  </div>
                ))}
                <button className="hb-link-danger mt-[10px]" onClick={() => onCommand("party leave")}>Leave party</button>
              </Section>
            ) : (
              <div className="font-serif italic text-[14px] text-ink-faint">You travel alone.</div>
            )}

            {state.party_invites?.length > 0 && (
              <Section title="Invitations">
                <div className="flex flex-col gap-2">
                  {state.party_invites.map((invite: any) => (
                    <div key={invite.invite_id} className="hb-inset">
                      <div className="font-semibold">From {invite.from_player_name}</div>
                      <div className="text-[12.5px] text-ink-muted">Asks you to join their party.</div>
                      <div className="flex gap-2 mt-2">
                        <button className="hb-btn hb-btn-accent"
                          onClick={() => onCommand(`accept_party_invite ${invite.invite_id}`)}>Accept</button>
                      </div>
                    </div>
                  ))}
                </div>
              </Section>
            )}

            {(state.pending_trade_offers?.length > 0 || state.pending_trade_offers_sent?.length > 0) && (
              <Section title="Trade offers">
                <div className="flex flex-col gap-2">
                  {state.pending_trade_offers?.map((trade: any) => (
                    <div key={trade.trade_id} className="hb-inset" style={{ opacity: trade.can_accept ? 1 : 0.55 }}>
                      <div className="font-semibold">From {trade.from_player_name}</div>
                      <div className="text-[12.5px] text-ink-muted">
                        Offers {ItemsList(trade.offered_items) || "nothing"} · Wants {ItemsList(trade.requested_items) || "nothing"}
                      </div>
                      <div className="flex gap-2 mt-2">
                        {trade.can_accept ? (
                          <button className="hb-btn hb-btn-accent" onClick={() => onCommand(`accept_trade ${trade.trade_id}`)}>Accept</button>
                        ) : (
                          <span className="text-[12px] text-ink-faint">You lack what they ask for.</span>
                        )}
                      </div>
                    </div>
                  ))}
                  {state.pending_trade_offers_sent?.map((trade: any) => (
                    <div key={trade.trade_id} className="hb-inset" style={{ opacity: trade.can_be_accepted ? 1 : 0.55 }}>
                      <div className="font-semibold">To {trade.to_player_name}</div>
                      <div className="text-[12.5px] text-ink-muted">
                        You offer {ItemsList(trade.offered_items) || "nothing"} · You want {ItemsList(trade.requested_items) || "nothing"}
                      </div>
                      <div className="flex gap-2 mt-2">
                        <button className="hb-btn hb-btn-quiet" onClick={() => onCommand(`cancel_trade ${trade.trade_id}`)}>Cancel</button>
                      </div>
                    </div>
                  ))}
                </div>
              </Section>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function StoryLog({ log, waiting, logRef }: { log: Line[]; waiting: boolean; logRef: React.RefObject<HTMLDivElement | null> }) {
  return (
    <div ref={logRef}
      className="hb-card pt-[22px] px-[26px] pb-[18px] flex flex-col gap-3 font-serif text-[16.5px] leading-[1.55] max-h-[420px] overflow-y-auto">
      {log.length === 0 && !waiting && (
        <div className="italic text-ink-faint text-[15px]">The page is blank. Type a command, or look around.</div>
      )}
      {log.map((line) => {
        const c = classifyLine(line.text);
        if (c.kind === "cmd") {
          return (
            <div key={line.id} className="flex gap-3 items-baseline">
              <span className="font-sans text-[11px] font-bold tracking-[.08em] uppercase text-ink-faint shrink-0">you</span>
              <span className="italic text-[15px] text-ink-muted">{c.text}</span>
            </div>
          );
        }
        if (c.kind === "sys" || c.kind === "error") {
          return (
            <div key={line.id} className={`text-[13px] whitespace-pre-wrap ${c.kind === "error" ? "text-danger" : "text-ink-faint"}`}>
              {c.text}
            </div>
          );
        }
        return <div key={line.id} className="text-ink whitespace-pre-wrap">{c.text}</div>;
      })}
      {waiting && (
        <div className="flex gap-[6px] items-center text-ink-faint font-sans text-[12px]">
          <span className="w-[6px] h-[6px] rounded-full bg-accent inline-block animate-blink" />
          The world turns…
        </div>
      )}
    </div>
  );
}

function SceneFrame({ image, loading, location }: { image: string | null; loading: boolean; location: any | null }) {
  return (
    <div className="relative w-full aspect-[16/7] rounded-[6px] overflow-hidden border border-rule shadow-frame bg-paper-inset">
      {image ? (
        <div className="absolute inset-0 bg-center bg-cover" style={{ backgroundImage: `url(${image})` }} />
      ) : (
        <div className="absolute inset-0 flex items-center justify-center font-serif italic text-ink-faint">
          {loading ? "" : location ? "" : "No scene"}
        </div>
      )}
      {loading && (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-paper-inset/85">
          <div className="animate-pulse font-serif italic text-ink-faint">Generating scene…</div>
        </div>
      )}
      {location && (
        <div className={`absolute left-0 right-0 bottom-0 px-[18px] py-[14px] pointer-events-none ${
          image ? "text-paper" : "text-ink"
        }`}
          style={{ background: image ? "linear-gradient(to top, rgba(30,26,20,.72), rgba(30,26,20,0))" : undefined }}>
          <div className="font-serif text-[24px] font-medium leading-[1.1]">{location.name}</div>
          {location.description && (
            <div className="font-serif italic text-[14px] opacity-85 line-clamp-2">{location.description}</div>
          )}
        </div>
      )}
    </div>
  );
}

function SubPage({ children }: { children: ReactNode }) {
  return (
    <div className="flex-1 w-full max-w-[1100px] mx-auto p-7 flex flex-col gap-4 box-border">
      {children}
    </div>
  );
}

function PageTitle({ title, meta }: { title: string; meta?: ReactNode }) {
  return (
    <div className="flex justify-between items-baseline flex-wrap gap-2">
      <h2 className="font-serif text-[32px] font-medium m-0 leading-tight">{title}</h2>
      {meta && <div className="text-[13px] text-ink-muted">{meta}</div>}
    </div>
  );
}

function Pending({ text }: { text: string }) {
  return <div className="font-serif italic text-ink-faint">{text}</div>;
}

function MapView({ mapData, thumbs }: { mapData: any | null; thumbs: Record<string, string> }) {
  const visited = mapData ? mapData.locations.filter((n: any) => n.visited).length : 0;
  const unexplored = mapData ? mapData.locations.length - visited : 0;
  return (
    <SubPage>
      <PageTitle title="Known World"
        meta={mapData ? `${visited} ${visited === 1 ? "place" : "places"} visited · ${unexplored} ${unexplored === 1 ? "path" : "paths"} unexplored` : null} />
      <div className="hb-card p-4">
        {mapData ? <MapGraph mapData={mapData} thumbs={thumbs} /> : <Pending text="Unrolling the map…" />}
      </div>
      <div className="font-serif italic text-[13px] text-ink-muted">
        Solid ink marks the roads out of where you stand; faint lines are roads you know of elsewhere. Dashed places are yet unexplored.
      </div>
    </SubPage>
  );
}

function JournalView({ journalData }: { journalData: any | null }) {
  const buckets: [string, string, string, number][] = [
    ["active", "Active", "text-accent", 1],
    ["completed", "Ready to turn in", "text-good", 1],
    ["archived", "Finished", "text-ink-faint", 0.7],
  ];
  const empty = journalData && buckets.every(([b]) => (journalData[b]?.length ?? 0) === 0);
  return (
    <SubPage>
      <div className="flex flex-col gap-7">
        <PageTitle title="Journal" />
        {!journalData && <Pending text="Turning the pages…" />}
        {empty && (
          <div className="font-serif italic text-ink-faint">
            No quests yet — talk to a quest giver (Warden, Huntmaster, Scholar).
          </div>
        )}
        {journalData && buckets.map(([bucket, heading, colorClass, opacity]) => {
          const items = journalData[bucket] ?? [];
          if (items.length === 0) return null;
          return (
            <div key={bucket}>
              <div className="flex items-center gap-3 mb-3">
                <span className={`text-[11px] font-bold tracking-[.1em] uppercase ${colorClass}`}>{heading}</span>
                <span className="flex-1 h-px bg-rule" />
              </div>
              <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))" }}>
                {items.map((q: any) => {
                  const reward = Object.entries(q.rewards || {})
                    .map(([it, n]) => `${n} ${humanize(it)}`).join(", ");
                  return (
                    <div key={q.quest_id} className="hb-card px-5 py-[18px] flex flex-col gap-2" style={{ opacity }}>
                      <div className="font-serif text-[20px] font-semibold leading-[1.2]">{q.name}</div>
                      {q.description && (
                        <div className="font-serif text-[15px] text-ink-muted leading-[1.45]">{q.description}</div>
                      )}
                      {q.total_stages && (
                        <div className="text-[12px] font-semibold text-accent">
                          Stage {q.stage} of {q.total_stages}{q.stage_description ? ` · ${q.stage_description}` : ""}
                        </div>
                      )}
                      {q.objectives?.length > 0 && (
                        <div className="flex flex-col gap-1">
                          {q.objectives.map((o: any, i: number) => {
                            const done = o.progress >= o.required;
                            return (
                              <div key={i} className="flex items-center gap-2 text-[13px]">
                                <span className={`w-[14px] h-[14px] rounded-full shrink-0 box-border ${
                                  done ? "bg-good border-[1.5px] border-good" : "border-[1.5px] border-rule-faint"
                                }`} />
                                <span className={`flex-1 ${done ? "text-ink-muted" : "text-ink"}`}>
                                  {titleCase(o.type)} {humanize(o.target)}
                                </span>
                                <span className="tabular-nums text-ink-muted">{o.progress} / {o.required}</span>
                              </div>
                            );
                          })}
                        </div>
                      )}
                      {reward && (
                        <div className="mt-1 pt-2 border-t border-dotted border-rule text-[12px] text-ink-faint">
                          <span className="font-bold tracking-[.06em] uppercase">Reward</span> · {reward}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </SubPage>
  );
}

function BestiaryView({ bestiaryData }: { bestiaryData: any | null }) {
  const discovered: any[] = bestiaryData?.discovered ?? [];
  const total: number = bestiaryData?.total ?? 0;
  const blank = Math.max(0, total - discovered.length);
  return (
    <SubPage>
      <div className="flex flex-col gap-5">
        <PageTitle title="Bestiary"
          meta={bestiaryData ? `${discovered.length} of ${total} creatures recorded` : null} />
        {!bestiaryData && <Pending text="Opening the codex…" />}
        {bestiaryData && discovered.length === 0 && (
          <div className="font-serif italic text-ink-faint">
            Nothing discovered yet — explore and fight to fill these pages.
          </div>
        )}
        {bestiaryData && (
          <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))" }}>
            {discovered.map((e: any) => (
              <div key={e.name} className="hb-card overflow-hidden flex flex-col">
                <div className="h-[120px] bg-paper-inset-deep" />
                <div className="px-4 pt-[14px] pb-4 flex flex-col gap-[6px]">
                  <div className="font-serif text-[20px] font-semibold">{e.name}</div>
                  <div className="flex gap-[14px] text-[12px] tabular-nums">
                    <span className="whitespace-nowrap"><span className="text-ink-faint">HP</span> <b>{e.max_hp}</b></span>
                    <span className="whitespace-nowrap"><span className="text-ink-faint">ATK</span> <b>{e.attack}</b></span>
                    <span className="whitespace-nowrap"><span className="text-ink-faint">XP</span> <b>{e.xp_reward}</b></span>
                  </div>
                  {e.inflicts && (
                    <span className="hb-tag self-start py-[2px]">Inflicts {humanize(e.inflicts)}</span>
                  )}
                  {e.locations?.length > 0 && (
                    <div className="font-serif italic text-[13px] text-ink-muted">{e.locations.join(", ")}</div>
                  )}
                </div>
              </div>
            ))}
            {blank > 0 && (
              <div className="border-[1.5px] border-dashed border-rule rounded-[6px] min-h-[200px] flex items-center justify-center text-center p-5 font-serif italic text-ink-faint">
                {blank} {blank === 1 ? "page remains" : "pages remain"} blank.<br />Explore and fight to fill {blank === 1 ? "it" : "them"}.
              </div>
            )}
          </div>
        )}
      </div>
    </SubPage>
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
  const [view, setView] = useState<View>("play");
  const [tab, setTab] = useState<Tab>("here");
  const [mapData, setMapData] = useState<any | null>(null);
  const [journalData, setJournalData] = useState<any | null>(null);
  const [bestiaryData, setBestiaryData] = useState<any | null>(null);
  const thumbsRef = useRef<Record<string, string>>({});
  const inputRef = useRef<HTMLInputElement>(null);
  const logRef = useRef<HTMLDivElement>(null);
  const skipResumeLook = useRef(false);

  // Record a downscaled thumbnail for a location (first image we see wins).
  async function recordThumb(locId?: string, img?: string | null) {
    if (!locId || !img || thumbsRef.current[locId]) return;
    const small = await downscale(img);
    thumbsRef.current = { ...thumbsRef.current, [locId]: small };
    saveThumbs(thumbsRef.current);
  }

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
      // The key is the prompt; the server joins any render already underway.
      const img = await renderSceneCached(newKey, newKey);
      setSceneImage(img);
      recordThumb(resp.state?.location?.id, img);
    } catch {
      // non-fatal
    } finally {
      setIsLoadingScene(false);
    }
  }

  useEffect(() => {
    if (!isLoadingScene && !isWaitingForResponse && view === "play") {
      inputRef.current?.focus();
    }
  }, [isLoadingScene, isWaitingForResponse, log, view]);

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
            text: "Your hero is gone — the world has begun anew. Forge a new one to continue.",
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

  // Auto-scroll the story log (the log scrolls inside its own card, so the
  // page itself stays put).
  useEffect(() => {
    const el = logRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [log, isWaitingForResponse, view]);

  // The server already warms these the moment we arrive (see
  // app/engine/prefetch.py); this pulls the finished images into the browser
  // so the next move shows its scene with no round-trip at all.
  function prefetchAdjacentScenes(state: any) {
    for (const scene of state.adjacent_scenes ?? []) {
      const key = computeSceneKeyFromResponse({ state: scene });
      if (!key || sceneImageCache.has(key)) continue;
      prefetchScene(key, key).then((img) => {
        if (img) recordThumb(scene.location?.id, img);
      });
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
      prefetchScene(key, key);
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

      // Panel commands open their views with the returned structured data.
      if (resp.state?.map) {
        setMapData(resp.state.map);
        setView("map");
      }
      if (resp.state?.journal) {
        setJournalData(resp.state.journal);
        setView("journal");
      }
      if (resp.state?.bestiary) {
        setBestiaryData(resp.state.bestiary);
        setView("bestiary");
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

  // Play-view actions (chips, panel buttons) always return to the tale.
  function runFromPanel(command: string) {
    setView("play");
    runCommand(command);
  }

  // Map / Journal / Bestiary are full views: show what we have at once and
  // refresh it through the ordinary command.
  function openView(v: View) {
    setView(v);
    if (v !== "play") runCommand(v);
  }

  // Forget this hero on this device and start over at the first-run screen.
  // The hero still exists on the server: typing the same name resumes them.
  function newTale() {
    if (playerId && !window.confirm("Close this tale and begin another? Your hero is kept — enter the same name later to resume.")) return;
    localStorage.removeItem("player_id");
    setPlayerId(null);
    setHasSavedPlayer(false);
    setLastState(null);
    setLog([]);
    setSceneImage(null);
    setCurrentSceneKey(null);
    setMapData(null);
    setJournalData(null);
    setBestiaryData(null);
    setInput("");
    setTab("here");
    setView("play");
    lastPrefetchLoc.current = null;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    await runCommand(input);
  }

  const firstRun = !playerId && !hasSavedPlayer;
  const busy = isWaitingForResponse || isLoadingScene;
  const suggestions = matchSuggestions(input, buildCandidates(lastState));

  function onInputKey(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Tab" && suggestions[0]) {
      e.preventDefault();
      setInput(suggestions[0].cmd);
    } else if (e.key === "Escape") {
      setInput("");
    }
  }

  const location = lastState?.location ?? null;
  const campaign = lastState?.campaign;
  const contextLine = location
    ? campaign
      ? `${campaign.complete ? "The Realm Restored" : `Act ${ROMAN[campaign.act_index] ?? campaign.act_index + 1}`} · ${location.name}`
      : location.name
    : "";

  const bestiaryByName: Record<string, any> = {};
  for (const e of bestiaryData?.discovered ?? []) bestiaryByName[e.name] = e;

  const monsters = (lastState?.entities ?? []).filter((e: any) => e.type === "monster");
  const npcs = (lastState?.entities ?? []).filter((e: any) => e.type === "npc" || e.type === "player");
  const quickActions: [string, string][] = [
    ["Look", "look"], ["Gather", "gather"], ["Heal", "heal"],
  ];
  if (monsters[0]) quickActions.push([`Attack ${monsters[0].name}`, `attack ${monsters[0].id}`]);
  if (npcs[0]) quickActions.push([`Talk ${npcs[0].name}`, `talk ${npcs[0].id}`]);

  const NAV: [View, string][] = [
    ["play", "Tale"], ["map", "Map"], ["journal", "Journal"], ["bestiary", "Bestiary"],
  ];

  return (
    <div className="min-h-screen flex flex-col bg-paper-deep text-ink">
      {/* Top bar */}
      <div className="flex items-center justify-between gap-4 px-7 py-[14px] border-b border-rule bg-paper flex-wrap">
        <div className="flex items-baseline gap-[14px] min-w-0">
          <button className="font-serif text-[22px] font-semibold tracking-[-.01em] text-accent" onClick={() => setView("play")}>
            QuestAI
          </button>
          {contextLine && (
            <span className="font-serif italic text-[15px] text-ink-muted truncate">{contextLine}</span>
          )}
        </div>
        {!firstRun && (
          <div className="flex gap-1 flex-wrap">
            {NAV.map(([v, label]) => (
              <button key={v} onClick={() => openView(v)}
                className={`px-3 py-[6px] font-semibold text-[13px] tracking-[.02em] uppercase border-b-2 ${
                  view === v ? "text-accent border-accent" : "text-ink-faint border-transparent hover:text-accent"
                }`}>
                {label}
              </button>
            ))}
            <button onClick={newTale}
              className="px-3 py-[6px] font-semibold text-[13px] tracking-[.02em] uppercase text-ink-faint hover:text-accent border-b-2 border-transparent">
              New tale
            </button>
          </div>
        )}
      </div>

      {/* A newcomer sees the realm as it stands and forges a hero; the game
          proper waits until they have one. */}
      {firstRun && (
        <Welcome
          busy={isWaitingForResponse}
          onCreate={(name, path) => runCommand(`create ${name} ${path}`)}
        />
      )}

      {!firstRun && view === "map" && <MapView mapData={mapData} thumbs={thumbsRef.current} />}
      {!firstRun && view === "journal" && <JournalView journalData={journalData} />}
      {!firstRun && view === "bestiary" && <BestiaryView bestiaryData={bestiaryData} />}

      {!firstRun && view === "play" && (
        <>
          <div className="flex-1 flex flex-wrap gap-5 px-7 pt-5 items-start">
            {/* Left column: scene over the story log */}
            <div className="flex flex-col gap-4 min-w-0" style={{ flex: "3 1 460px" }}>
              <SceneFrame image={sceneImage} loading={isLoadingScene} location={location} />
              <StoryLog log={log} waiting={isWaitingForResponse} logRef={logRef} />
            </div>

            {/* Right column: character card + tabbed panel */}
            <div className="flex flex-col gap-[14px] min-w-0" style={{ flex: "1 1 280px" }}>
              {lastState?.player && lastState?.location ? (
                <>
                  <CharacterCard state={lastState} onTab={setTab} />
                  <StatusPane state={lastState} tab={tab} onTab={setTab} onCommand={runFromPanel} bestiaryByName={bestiaryByName} />
                </>
              ) : (
                <div className="hb-card px-5 py-[18px] font-serif italic text-ink-faint">
                  {playerId ? "Finding your place in the tale…" : "No character loaded."}
                </div>
              )}
            </div>
          </div>

          {/* Command bar */}
          <div className="sticky bottom-0 mt-5 px-7 pt-[14px] pb-[18px]"
            style={{ background: "linear-gradient(to bottom, rgba(233,225,207,0), #e9e1cf 30%)" }}>
            <div className="max-w-[1400px] flex flex-col gap-[10px] relative">
              <div className="flex gap-[6px] flex-wrap">
                {quickActions.map(([label, cmd]) => (
                  <button key={cmd} className="hb-pill" disabled={!playerId || busy} onClick={() => runCommand(cmd)}>
                    {label}
                  </button>
                ))}
              </div>

              {suggestions.length > 0 && (
                <div className="absolute bottom-full left-0 mb-[6px] min-w-[280px] max-w-full bg-paper border border-rule rounded-[6px] shadow-dropdown overflow-hidden">
                  {suggestions.map((s) => (
                    <button key={s.cmd} type="button"
                      className="flex justify-between gap-4 w-full text-left px-[14px] py-[9px] border-b border-rule-soft last:border-b-0 hover:bg-paper-inset"
                      onMouseDown={(e) => e.preventDefault()}
                      onClick={() => { setInput(s.cmd); inputRef.current?.focus(); }}>
                      <span className="font-semibold text-accent">{s.cmd}</span>
                      <span className="text-[12px] text-ink-faint truncate">{s.hint}</span>
                    </button>
                  ))}
                </div>
              )}

              <form onSubmit={handleSubmit}
                className="flex items-center gap-3 px-4 h-12 bg-paper border border-rule rounded-[6px]"
                style={{ boxShadow: "0 1px 0 #fff inset" }}>
                <span className="font-serif italic text-ink-faint shrink-0 hidden sm:inline">What do you do?</span>
                <input
                  ref={inputRef}
                  className="flex-1 min-w-0 border-0 outline-none bg-transparent font-serif text-[17px] text-ink disabled:text-ink-faint placeholder:text-ink-faint/70"
                  placeholder={isWaitingForResponse ? "the world turns…" : isLoadingScene ? "painting the scene…" : "attack wolf, go north, talk huntmaster…"}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={onInputKey}
                  disabled={busy}
                  autoComplete="off"
                  spellCheck={false}
                />
                <span className="text-[11px] font-semibold tracking-[.06em] text-ink-faint shrink-0">↵ ENTER</span>
              </form>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
