export async function generateSceneImage(prompt: string): Promise<string> {
  const res = await fetch("/api/scene", {
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