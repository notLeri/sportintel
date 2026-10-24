/** «ge (Globo Esporte)» → GE, «CNN Brasil» → CNN, «Матч ТВ (Telegram)» → МТ, «Россия — праздники» → РП. */
export function sourceInitials(name: string): string {
  const words = name.replace(/\(.*?\)/g, " ").match(/\p{L}[\p{L}\p{N}]*/gu) ?? [];
  const [first = "", second] = words;
  if (/^\p{Lu}{2,4}$/u.test(first)) return first;
  return (second ? first.charAt(0) + second.charAt(0) : first.slice(0, 2)).toUpperCase() || "?";
}
