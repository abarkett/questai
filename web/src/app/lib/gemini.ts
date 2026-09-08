const API_BASE = "http://127.0.0.1:8787";

export type SceneRequestOptions = {
  // Foreground (default): the server renders on a miss and answers with the
  // image. Prefetch (wait=false): a miss is queued on the server's background
  // warmer and answered 202 at once, so warming never ties up a connection.
  wait?: boolean;
};

// Fetch a scene image for a prompt. Resolves to the data URI, or to null when
// `wait` is false and the server is still rendering it (poll again later).
export async function requestSceneImage(
  prompt: string,
  opts: SceneRequestOptions = {}
): Promise<string | null> {
  const wait = opts.wait ?? true;
  const res = await fetch(`${API_BASE}/api/ai/image`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ prompt, wait }),
  });

  if (res.status === 202) return null;
  if (!res.ok) {
    throw new Error("Scene generation failed");
  }

  const data = await res.json();
  return data.image;
}

export async function generateSceneImage(prompt: string): Promise<string> {
  const img = await requestSceneImage(prompt, { wait: true });
  if (!img) throw new Error("Scene generation failed");
  return img;
}
