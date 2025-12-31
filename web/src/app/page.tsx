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

function sceneKey(location: any, entities: string[]) {
  return JSON.stringify({
    loc: location?.id,
    entities: [...entities].sort(),
  });
}

export default function Page() {
  const [playerId, setPlayerId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [log, setLog] = useState<Line[]>([]);
  const [sceneImage, setSceneImage] = useState<string | null>(null);
  const [isLoadingScene, setIsLoadingScene] = useState(false);

  const bottomRef = useRef<HTMLDivElement>(null);

  // Restore player_id from localStorage
  useEffect(() => {
    const saved = localStorage.getItem("player_id");
    if (saved) setPlayerId(saved);
  }, []);

  // Auto-scroll log
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [log]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (isLoadingScene) return;
    if (!input.trim()) return;

    const command = input;
    setInput("");

    // Echo command
    setLog((l) => [
      ...l,
      { id: crypto.randomUUID(), text: `> ${command}` },
    ]);

    try {
      const resp = await sendCommand(command, playerId);

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

      // ---- Scene image generation (blocking UX) ----
      const location = resp.state?.location;
      if (location) {
        setIsLoadingScene(true);

        const entities =
          resp.messages
            ?.find((m) => m.startsWith("You see:"))
            ?.replace("You see:", "")
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean) ?? [];

        const key = sceneKey(location, entities);

        try {
          if (sceneImageCache.has(key)) {
            setSceneImage(sceneImageCache.get(key)!);
          } else {
            const prompt = buildScenePrompt({ location, entities });
            const img = await generateSceneImage(prompt);
            sceneImageCache.set(key, img);
            setSceneImage(img);
          }
        } catch {
          // image failure is non-fatal
        } finally {
          setIsLoadingScene(false);
        }
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

  return (
    <div className="h-screen bg-black text-green-300 font-mono p-4 flex flex-col">
      <h1 className="text-xl mb-2">QuestAI</h1>

      {/* Image area – fixed height */}
      <div className="h-[420px] mb-2 flex items-center justify-center border border-green-700 relative">
        {isLoadingScene && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/80">
            <div className="animate-pulse text-green-400">
              Generating scene…
            </div>
          </div>
        )}

        {sceneImage ? (
          <img
            src={sceneImage}
            className="max-h-full max-w-full object-contain"
            alt="Scene"
          />
        ) : (
          <div className="text-green-700">No scene</div>
        )}
      </div>`

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
          className="flex-1 bg-black text-green-300 outline-none disabled:text-green-700"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          autoFocus
          disabled={isLoadingScene}
        />
      </form>
    </div>
  );
}