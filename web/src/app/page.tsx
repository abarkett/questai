"use client";

import { useEffect, useRef, useState } from "react";
import { sendCommand } from "./lib/api";
import { generateSceneImage } from "./lib/gemini";
import { buildScenePrompt } from "./lib/scene";

type Line = {
  id: string;
  text: string;
};

// cache survives re-renders
const sceneImageCache = new Map<string, string>();


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

function StatusPane({state, onCommand}: {state: any | null; onCommand: (cmd: string) => void;}) {
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
        <div>HP: {player.hp}/{player.max_hp}</div>
        <div>XP: {player.xp}</div>
        <div>Level: {player.level}</div>
      </div>

      {/* Inventory */}
      <div>
        <div className="text-green-400 font-bold">Inventory</div>
        {player.inventory && Object.keys(player.inventory).length > 0 ? (
          <ul className="list-disc list-inside">
            {Object.entries(player.inventory).map(([item, qty]) => (
              <li
                key={item}
                className="cursor-pointer hover:underline"
                onClick={() => onCommand(`use ${item}`)}
              >
                {item} × {qty as number}
              </li>
            ))}
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
  const [lastState, setLastState] = useState<any | null>(null);
  const [currentSceneKey, setCurrentSceneKey] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const bottomRef = useRef<HTMLDivElement>(null);

  async function handleSceneFromResponse(resp: any) {
    const newKey = computeSceneKeyFromResponse(resp);
    if (!newKey || newKey === currentSceneKey) return;

    setCurrentSceneKey(newKey);

    if (sceneImageCache.has(newKey)) {
      setSceneImage(sceneImageCache.get(newKey)!);
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

  // Restore player_id from localStorage
  useEffect(() => {
    const saved = localStorage.getItem("player_id");
    if (saved) setPlayerId(saved);
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
  }, [log]);

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
      } catch {
        // prefetch failure is fine
      }
    }
  }

  async function runCommand(command: string) {
    if (isLoadingScene || !command.trim()) return;

    setInput("");

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
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    await runCommand(input);
  }

  return (
    <div className="h-screen bg-black text-green-300 font-mono p-4 flex flex-col">
      <h1 className="text-xl mb-2">QuestAI</h1>

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
          disabled={isLoadingScene}
        />
      </form>
    </div>
  );
}