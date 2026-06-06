export function buildScenePrompt(params: {
  location?: any;
  entities?: any[];
}) {
  const locationName = params.location?.name ?? "unknown place";
  const description = params.location?.description ?? "";

  // Entities arrive as objects ({type,name,...}); pull names of creatures/NPCs
  // only (never other players) so the image matches what's actually present.
  const names = (params.entities ?? [])
    .filter((e: any) => e && (typeof e === "string" || e.type === "monster" || e.type === "npc"))
    .map((e: any) => (typeof e === "string" ? e : e.name));

  const creatures =
    names.length > 0
      ? `Depict exactly these living things and no others: ${names.join(", ")}.`
      : `No creatures or people are present; depict the empty location.`;

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
  ${creatures}
  Do not add extra characters, companions, adventurers, or a party.

  No text, no UI, no labels.
  `.trim();
}
