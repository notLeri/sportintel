/** Один ключ на одну попытку пользователя: повтор после сбоя сети не создаёт дубль. */
export function newIdempotencyKey(): string {
  return crypto.randomUUID();
}
