const SERVER =
  process.env.NEXT_PUBLIC_SERVER_URL ?? "http://localhost:8787";

export type CommandResponse = {
  ok: boolean;
  messages?: string[];
  state?: any;
  error?: string;
};

export async function sendCommand(
  text: string,
  playerId?: string | null
): Promise<CommandResponse> {
  const res = await fetch(`${SERVER}/command`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      ...(playerId ? { "x-player-id": playerId } : {}),
    },
    body: JSON.stringify({ text }),
  });

  return await res.json();
}

export type Intro = {
  paths: { id: string; name: string; description: string; passive: string }[];
  act: { index: number | null; total: number | null; name: string; blurb: string; climax: string | null } | null;
  heroes: string[];
  righted: number;
  total: number;
  art_prompt: string | null;
  images: boolean;
};

// The realm as it stands, for the welcome screen (see GET /intro).
export async function fetchIntro(): Promise<Intro> {
  const res = await fetch(`${SERVER}/intro`);
  if (!res.ok) throw new Error("intro unavailable");
  return await res.json();
}

// Background cache warming (Miriel location descriptions). Fire-and-forget.
export function prefetchCaches(playerId?: string | null): void {
  if (!playerId) return;
  fetch(`${SERVER}/prefetch`, {
    method: "POST",
    headers: { "content-type": "application/json", "x-player-id": playerId },
  }).catch(() => {});
}