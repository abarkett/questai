"use client";

import { useEffect, useState } from "react";
import { fetchIntro, type Intro } from "./lib/api";
import { generateSceneImage } from "./lib/gemini";

// The title art is one image for the whole world (the server caches it by
// prompt), regenerated only when the realm's act changes.
let titleArtCache: { prompt: string; image: string } | null = null;

const ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"];

export function Welcome({ onCreate, busy }: { onCreate: (name: string, path: string) => void; busy: boolean }) {
  const [intro, setIntro] = useState<Intro | null>(null);
  const [introFailed, setIntroFailed] = useState(false);
  const [art, setArt] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [path, setPath] = useState("warden");

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const i = await fetchIntro();
        if (!alive) return;
        setIntro(i);
        if (i.images && i.art_prompt) {
          if (titleArtCache && titleArtCache.prompt === i.art_prompt) {
            setArt(titleArtCache.image);
          } else {
            try {
              const img = await generateSceneImage(i.art_prompt);
              if (!alive) return;
              titleArtCache = { prompt: i.art_prompt, image: img };
              setArt(img);
            } catch {
              // no art: the styled panel stands in
            }
          }
        }
      } catch {
        if (alive) setIntroFailed(true);
      }
    })();
    return () => { alive = false; };
  }, []);

  const act = intro?.act;
  const actLabel = act && act.index != null
    ? `Act ${ROMAN[act.index] ?? act.index + 1}${act.total ? ` of ${act.total}` : ""}: ${act.name}`
    : act?.name ?? "";

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const n = name.trim().replace(/\s+/g, " ");
    if (!n || busy) return;
    onCreate(n, path);
  }

  return (
    <div className="flex-1 min-h-0 overflow-y-auto flex flex-col gap-3">
      {/* Title art */}
      <div className="relative h-[300px] shrink-0 border border-green-700 overflow-hidden">
        {art ? (
          <div className="absolute inset-0 bg-center bg-cover" style={{ backgroundImage: `url(${art})` }} />
        ) : (
          <div className="absolute inset-0 bg-gradient-to-b from-green-950 via-black to-black" />
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-black via-black/40 to-transparent" />
        <div className="absolute left-4 right-4 bottom-4">
          <div className="text-3xl text-green-200 drop-shadow">The realm lies fallen.</div>
          {act && (
            <div className="text-sm text-green-300 mt-1">
              <span className="text-green-400">{actLabel}.</span> {act.blurb}
            </div>
          )}
          {intro && !act && !introFailed && (
            <div className="text-sm text-green-300 mt-1">The Chronicle is being written…</div>
          )}
          {introFailed && (
            <div className="text-sm text-red-400 mt-1">
              The realm is out of reach — is the game server running on port 8787?
            </div>
          )}
        </div>
      </div>

      {/* The world so far */}
      {intro && act && (
        <div className="text-xs text-green-600 border border-green-900 p-2">
          {intro.total > 0 && (
            <span>
              <span className="text-green-300">{intro.righted}</span> of{" "}
              <span className="text-green-300">{intro.total}</span> wrongs put right in this act
            </span>
          )}
          {intro.heroes.length > 0 ? (
            <span> — by {intro.heroes.join(", ")}. Their names are in the Chronicle; yours could be next.</span>
          ) : (
            <span>{intro.total > 0 ? ". " : ""}No hero has yet written their name in the Chronicle. Be the first.</span>
          )}
          {act.climax && <span> Looming over it all: <span className="text-red-300">{act.climax}</span>.</span>}
        </div>
      )}

      {/* Forge a hero */}
      <form onSubmit={submit} className="border border-green-700 p-3 flex flex-col gap-3">
        <div className="text-green-400">Forge your hero</div>
        <label className="flex items-center gap-2 text-sm">
          <span className="text-green-600 w-16">Name</span>
          <input
            autoFocus
            className="flex-1 bg-black border border-green-800 px-2 py-1 text-green-200 outline-none focus:border-green-400"
            placeholder="What are you called?"
            value={name}
            maxLength={24}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
          {(intro?.paths ?? [
            { id: "warden", name: "Warden", description: "Stands the line — soaks blows and grinds foes down.", passive: "" },
            { id: "trickster", name: "Trickster", description: "Quick and vicious — opens wounds and presses the advantage.", passive: "" },
            { id: "channeler", name: "Channeler", description: "Raw power — fire, force, and the breath to fight on.", passive: "" },
          ]).map((p) => (
            <button
              type="button"
              key={p.id}
              onClick={() => setPath(p.id)}
              className={`text-left p-2 border ${path === p.id ? "border-green-300 bg-green-950" : "border-green-800 hover:border-green-600"}`}
            >
              <div className={path === p.id ? "text-green-200" : "text-green-400"}>{p.name}</div>
              <div className="text-xs text-green-600">{p.description}</div>
              {p.passive && <div className="text-[11px] text-green-800 mt-1">{p.passive}</div>}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-3">
          <button
            type="submit"
            disabled={!name.trim() || busy}
            className="px-3 py-1 border border-green-500 text-green-200 hover:bg-green-900 disabled:opacity-40"
          >
            {busy ? "Forging…" : "Begin"}
          </button>
          <span className="text-xs text-green-700">
            Then: <span className="text-green-500">look</span> around, <span className="text-green-500">talk</span> to
            the Warden, and type <span className="text-green-500">next</span> whenever you are unsure what to do.
          </span>
        </div>
      </form>
    </div>
  );
}
