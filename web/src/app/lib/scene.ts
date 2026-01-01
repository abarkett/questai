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
  Wide horizontal composition (16:9).
  Cinematic landscape framing.

  IMPORTANT:
  - The scene must fill the entire frame edge-to-edge.
  - No borders, no margins, no white space.
  - No blank background areas.
  - The image should extend fully to all edges.

  Style: detailed hand-painted fantasy art.
  Location: ${locationName}.
  Description: ${description}
  ${entities}

  No text, no UI, no labels.
  `.trim();
}