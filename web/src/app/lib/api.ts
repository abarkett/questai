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