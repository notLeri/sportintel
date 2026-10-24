import type { components } from "@/shared/api";

export type SportItem = components["schemas"]["SportItem"];
export type EntityItem = components["schemas"]["EntityItem"];
export type EntityKind = "competition" | "team" | "player" | "coach" | "person" | "venue";
