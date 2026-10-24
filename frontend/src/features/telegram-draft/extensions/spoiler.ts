import { Mark } from "@tiptap/react";

declare module "@tiptap/react" {
  interface Commands<ReturnType> {
    spoiler: { toggleSpoiler: () => ReturnType };
  }
}

/** <tg-spoiler> как mark (в редакторе — span.tg-spoiler). */
export const Spoiler = Mark.create({
  name: "spoiler",
  parseHTML: () => [{ tag: "tg-spoiler" }, { tag: "span.tg-spoiler" }],
  renderHTML: () => ["span", { class: "tg-spoiler-edit" }, 0],
  addCommands() {
    return {
      toggleSpoiler:
        () =>
        ({ commands }) =>
          commands.toggleMark(this.name),
    };
  },
});
