"use client";

import { useEffect, useState } from "react";
import { fetchIntro, type Intro } from "./lib/api";
import { generateSceneImage } from "./lib/gemini";

// The title art is one image for the whole world (the server caches it by
// prompt), regenerated only when the realm's act changes.
let titleArtCache: { prompt: string; image: string } | null = null;

const ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"];

const DEFAULT_PATHS = [
  { id: "warden", name: "Warden", description: "Stands the line — soaks blows and grinds foes down.", passive: "" },
  { id: "trickster", name: "Trickster", description: "Quick and vicious — opens wounds and presses the advantage.", passive: "" },
  { id: "channeler", name: "Channeler", description: "Raw power — fire, force, and the breath to fight on.", passive: "" },
];

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
              // no art: the card stands on its own
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
  const chapterLabel = act && act.index != null
    ? `Act ${ROMAN[act.index] ?? act.index + 1}${act.total ? ` of ${act.total}` : ""}${act.name ? ` · ${act.name}` : ""}`
    : act?.name ?? "Chapter I";

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const n = name.trim().replace(/\s+/g, " ");
    if (!n || busy) return;
    onCreate(n, path);
  }

  return (
    <div className="flex-1 flex items-center justify-center px-7 py-10">
      <form onSubmit={submit}
        className="hb-card w-full max-w-[560px] shadow-welcome text-center flex flex-col overflow-hidden">
        {/* Title art, when the realm has painted one. */}
        {art && (
          <div className="relative aspect-[16/7] border-b border-rule">
            <div className="absolute inset-0 bg-center bg-cover" style={{ backgroundImage: `url(${art})` }} />
            <div className="absolute inset-0" style={{ background: "linear-gradient(to top, rgba(30,26,20,.6), rgba(30,26,20,0) 60%)" }} />
            <div className="absolute left-0 right-0 bottom-0 px-[18px] py-[14px] font-serif italic text-[15px] text-paper text-left">
              The realm lies fallen.
            </div>
          </div>
        )}

        <div className="px-12 py-11 flex flex-col gap-5">
          <div className="text-[11px] font-bold tracking-[.14em] uppercase text-ink-faint">{chapterLabel}</div>
          <h2 className="font-serif text-[36px] font-medium leading-[1.1] m-0">Every tale begins with a name.</h2>
          <p className="font-serif text-[16px] text-ink-muted m-0 leading-[1.5]">
            {act?.blurb
              ? act.blurb
              : intro && !act && !introFailed
              ? "The Chronicle is being written…"
              : "You arrive at the Town Square with ten hit points, empty pockets and a road heading north toward darker trees."}
            {act?.climax && <> Looming over it all: <span className="text-danger">{act.climax}</span>.</>}
          </p>

          {intro && act && (
            <div className="text-[12px] text-ink-faint">
              {intro.total > 0 && (
                <span>
                  <span className="font-semibold text-ink-muted">{intro.righted}</span> of{" "}
                  <span className="font-semibold text-ink-muted">{intro.total}</span> wrongs put right in this act
                </span>
              )}
              {intro.heroes.length > 0 ? (
                <span> — by {intro.heroes.join(", ")}. Their names are in the Chronicle; yours could be next.</span>
              ) : (
                <span>{intro.total > 0 ? ". " : ""}No hero has yet written their name in the Chronicle. Be the first.</span>
              )}
            </div>
          )}

          {introFailed && (
            <div className="text-[12px] text-danger">
              The realm is out of reach — is the game server running on port 8787?
            </div>
          )}

          <input
            autoFocus
            className="w-full box-border h-[52px] px-[18px] text-center border border-rule rounded-[4px] bg-white font-serif text-[20px] text-ink outline-none focus:border-accent placeholder:text-ink-faint/70"
            placeholder="Your name"
            value={name}
            maxLength={24}
            onChange={(e) => setName(e.target.value)}
          />

          <div className="text-left">
            <div className="hb-label mb-2">Choose your path</div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
              {(intro?.paths ?? DEFAULT_PATHS).map((p) => {
                const selected = path === p.id;
                return (
                  <button
                    type="button"
                    key={p.id}
                    onClick={() => setPath(p.id)}
                    className={`text-left rounded-[4px] px-3 py-[10px] border ${
                      selected ? "border-accent bg-paper-plate" : "border-rule bg-paper-inset hover:border-ink-faint"
                    }`}
                  >
                    <div className={`font-serif text-[16px] font-semibold ${selected ? "text-accent" : "text-ink"}`}>{p.name}</div>
                    <div className="text-[12px] text-ink-muted mt-[2px]">{p.description}</div>
                    {p.passive && <div className="text-[11px] text-ink-faint mt-1">{p.passive}</div>}
                  </button>
                );
              })}
            </div>
          </div>

          <button
            type="submit"
            disabled={!name.trim() || busy}
            className="h-12 rounded-[4px] bg-accent text-paper text-[14px] font-bold tracking-[.06em] uppercase hover:bg-accent-deep disabled:opacity-50 disabled:hover:bg-accent"
          >
            {busy ? "Forging…" : "Begin"}
          </button>

          <div className="text-[12px] text-ink-faint">
            Returning? Enter the same name to resume where you left off.
          </div>
        </div>
      </form>
    </div>
  );
}
