export async function generateSceneImage(prompt: string): Promise<string> {
  // We now call the Python backend which runs on port 8787 (proxied or direct)
  // Assuming Next.js rewrites or direct URL. Use full URL for now to be safe if no proxy.
  // Or relative if Next.js rewrites /api/py -> localhost:8787
  // Let's assume we need to hit the backend directly or via extraction.
  // The user's setup seems to run on different ports.
  // Let's try direct fetch to backend URL.
  const API_BASE = "http://127.0.0.1:8787";

  const res = await fetch(`${API_BASE}/api/ai/image`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ prompt }),
  });

  if (!res.ok) {
    throw new Error("Scene generation failed");
  }

  const data = await res.json();
  return data.image;
}