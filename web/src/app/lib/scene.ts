export function buildScenePrompt(params: {
  location?: any;
  entities?: string[];
}) {
  const locationName = params.location?.name ?? "unknown place";
  const description = params.location?.description ?? "";

  const entities =
    params.entities && params.entities.length > 0
      ? `Visible creatures or objects: ${params.entities.join(", ")}.`
      : "No visible creatures.";

  return `
Fantasy RPG scene illustration.
Style: detailed hand-painted fantasy art.
Perspective: isometric or eye-level.
Location: ${locationName}.
Description: ${description}
${entities}
Mood: atmospheric, immersive.
No text, no UI, no labels.
`.trim();
}