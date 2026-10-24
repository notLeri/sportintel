export const ROW_HEIGHT = 64;
/** На телефоне заголовок — в две строки, иначе его не прочитать. */
export const ROW_HEIGHT_NARROW = 84;
export const NARROW_QUERY = "(max-width: 767px)";

export function rowId(id: string) {
  return `event-row-${id}`;
}
